# ADR 0029: Transformações da gold em dbt, em três camadas

- **Status:** Aceita
- **Data:** 2026-11-01

## Contexto

Na E2, as transformações da gold ficaram em dois lugares. A gold tabular é feita em pandas (`src/pipeline/build_gold.py`). O star schema é feito por SQL guardado em strings Python (`src/db/povoar_dimensional.py`), executado em sequência numa transação. Funciona, mas tem três problemas:

- **Dependências implícitas.** A ordem das etapas está escrita à mão. Nada mostra que o IRC depende das métricas, que dependem das coortes maduras.
- **Testes de dados longe dos modelos.** Os testes estão em `tests/test_banco*.py`, ligados ao pipeline, e não a cada tabela que o modelo produz.
- **Sem documentação nem linhagem geradas.** O dicionário vem do catálogo, mas não diz de onde cada tabela vem.

A E3 pede transformações declarativas e versionadas, em camadas.

## Alternativas

| | dbt | SQLMesh | Opção nula: SQL em scripts Python (como está) |
|---|---|---|---|
| Grafo de dependência | Inferido dos `ref()` | Inferido do SQL (parser próprio) | Escrito à mão, na ordem dos `execute` |
| Testes de dados | Genéricos (`unique`, `not_null`, `relationships`, `accepted_values`) e singulares em SQL | Auditorias e testes unitários | `unittest` separado dos modelos |
| Documentação e linhagem | `dbt docs`, com página estática | UI própria (servidor) | Nenhuma |
| Ambientes e backfill | Por alvo e `--full-refresh`; incremental exige configuração | Planos com ambientes virtuais e backfill por intervalo embutidos | Nenhum |
| Adoção e material | Ferramenta padrão de mercado, muito material | Menor comunidade, API ainda mudando | Nenhuma dependência nova |
| Custo de entrada aqui | Um `pip install`, um projeto | Um `pip install` e o estado do SQLMesh no banco | Zero |

**A opção nula foi levada a sério.** O volume é pequeno: 152 mil vínculos, e os marts levam menos de 5 s. O SQL já existe e é testado. Um cron com esses scripts atenderia o agendamento. O que ela não dá é o que a E3 cobra: o grafo é implícito, não há testes por modelo nem documentação, e cada tabela nova exige mexer na ordem dos `execute`.

**SQLMesh** tem vantagens reais: ambientes virtuais e backfill por intervalo sem configuração extra. Elas pesam mais em modelos incrementais grandes, que não é o caso. Todos os modelos daqui são reconstruídos inteiros em segundos, e a equipe tem mais material de referência para o dbt.

## Decisão

- **dbt** (`dbt-core` e `dbt-postgres`, em `requirements-dbt.txt`), projeto em `transform/`, rodado por `scripts/dbt.sh`. O script lê o `DATABASE_URL` do projeto.
- **Três camadas, cada uma no seu esquema:**
  - `staging` (`dbt_staging`, views): uma view por tabela da Silver 3NF. Só renomeia e tipa, e o `id_discente` fica de fora.
  - `intermediate` (`dbt_intermediate`, views): as regras de negócio. Atributos do curso (oferta principal, MISTO), campus (MULTICAMPUS), coortes maduras (8 anos), métricas com k ≥ 5 e IRC com a classificação por quartis.
  - `marts` (`dbt_marts`, tabelas): `dim_curso`, `dim_campus`, `fct_retencao_curso` (grão: um curso canônico) e `painel_cursos_criticos`, a tabela que responde à pergunta da E1.
- **Acesso.** Só os marts, agregados com k ≥ 5, recebem `GRANT SELECT` para `observatorio_leitura`. `staging` e `intermediate` carregam vínculos individuais e ficam inacessíveis a esse papel, como a silver.
- **Mesmo arredondamento da gold.** Desde a migração 0022, a gold arredonda em ponto flutuante, com empate para o par (`gold.arredondar`, como o `numpy.round`). Os modelos do dbt usam a macro `arredondar`, idêntica a ela, e as mesmas fórmulas: a razão em ponto flutuante vezes 100, e o IRC na mesma ordem de operações. Com o `round(numeric)` do PostgreSQL, que arredonda o empate para cima, 102/320 = 31,875% dava 31,88 no dbt e 31,87 na gold, e a reconciliação acusava.
- **Chave substituta por hash** (`md5(nome_curso)` nas dimensões sem histórico; na `dim_curso`, o nome com o início da vigência). É estável entre reconstruções e entre bancos, o que um `IDENTITY` não é.
- **`dim_curso` com histórico (SCD tipo 2, ADR 0028).** O snapshot `snap_atributos_curso` (`transform/snapshots/`, esquema `dbt_snapshots`) guarda as versões dos atributos rastreados, com a estratégia `check`. A `dim_curso` tem uma linha por versão (`vigente_de`, `vigente_ate`, `is_atual`), e o fato aponta para a versão atual. O `--full-refresh` reconstrói os marts, mas não apaga o snapshot.
- **Reconciliação com a gold atual.** O teste `reconcilia_fato_retencao_com_a_gold` exige que `fct_retencao_curso` seja igual, curso a curso e em todas as medidas, ao `gold.fato_retencao_curso` do pipeline Python. Com o corte de maturação trocado para 7 anos, o teste acusa 188 diferenças, então ele não passa por acaso.
- **No CI** (`medalhao.yml`), depois do refresh da view do painel: `dbt build --full-refresh` reconstrói tudo do zero e roda os testes de dados (`docs/testes_de_dados.md`). Em seguida, `dbt docs generate --static` gera a documentação e a linhagem, publicadas no GitHub Pages em `/dbt/`. No `rodar_pipeline.sh` e na imagem Docker a etapa também roda; fora deles, sem o dbt instalado, ela só avisa.

## Consequências

- Durante a migração, o star schema existe em dois lugares: o da gold, feito pelo pipeline Python e lido pelo painel e pelo Supabase, e o dos marts do dbt. A reconciliação garante que os dois são iguais. Ligar o painel à camada transformada é o passo seguinte (issue #44). Depois disso, `povoar_dimensional.py` sai.
- A gold tabular em pandas (`build_gold.py`) não foi portada. Ela tem regras que não estão no star schema, como os joins com o INEP e o PIBIC.
- O agendamento e o retry continuam no GitHub Actions. A escolha do orquestrador é tema de outro ADR (issue #40).
- Nova dependência de CI e da imagem Docker: o dbt e o adaptador do Postgres. O painel não depende dele: o `requirements.txt` do Streamlit não muda.
