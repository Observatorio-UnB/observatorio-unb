# Camada semântica de métricas e ETL reverso (E4)

O dado sai do painel e volta a um processo onde alguém age. Esta página descreve os dois lados: onde
cada métrica é definida, e como a métrica tratada chega à coordenação de curso.

## Camada semântica: cada métrica definida num lugar só

| Peça | Onde | Papel |
|---|---|---|
| Fórmula executável | [`transform/macros/metricas.sql`](../transform/macros/metricas.sql) | Uma macro por métrica derivada (taxas, médias). É o **único** lugar onde a conta é escrita. |
| Bases aditivas | [`int_bases_curso`](../transform/models/intermediate/int_bases_curso.sql) | Contagens e somas por curso, que se podem somar entre cursos. |
| Grão do curso | `int_metricas_curso` → `fct_retencao_curso` → `painel_cursos_criticos` | Aplica as macros às bases de cada curso. |
| Recortes acima do curso | [`dbt_marts.metricas_por_recorte`](../transform/models/marts/metricas_por_recorte.sql) | UnB, campus, grau, área e turno: soma as bases e aplica **as mesmas macros**. |
| Definição versionada | [`transform/seeds/metricas_definicoes.csv`](../transform/seeds/metricas_definicoes.csv) → `dbt_marts.metricas_definicoes` | Rótulo, definição de negócio, fórmula, unidade, recortes válidos, se é aditiva, **versão**, data e ADR. |

Os dois consumidores leem dessas tabelas, e nenhum deles refaz a conta:

- **Painel** (Streamlit e GitHub Pages): o ranking vem de `painel_cursos_criticos`. As comparações por turno, grau e campus vêm de `metricas_por_recorte` ([`src/dashboard/metricas.py`](../src/dashboard/metricas.py)). Cada comparação mostra a fonte e a definição versionada de cada métrica.
- **ETL reverso**: lê `painel_cursos_criticos` e grava, ao lado de cada número, a versão da definição (`indice_retencao_critica@1.0.0;taxa_evasao_pct@1.0.0;...`).

### O que os testes garantem

| Teste | Garante |
|---|---|
| `metricas_registro_completo` (dbt) | Toda métrica publicada tem definição no registro, e toda definição é publicada. |
| `metricas_recortes_fecham_com_o_painel` (dbt) | O recorte UnB tem os mesmos cursos e contagens do ranking do painel. Cada recorte particiona esse universo. As taxas do painel são as que as macros dão. |
| `reconcilia_fato_retencao_com_a_gold` (dbt, já existia) | A refatoração para macros não mudou nenhum número: o fato continua igual ao da gold, curso a curso. |
| `tests/test_banco_etl_reverso.py::TestMesmoNumero` | A fila de intervenção e o painel têm o mesmo IRC, evasão, atraso, % no prazo, ingressantes e posição, curso a curso. A evasão da UnB da camada semântica é a razão das somas do ranking do painel. |
| `tests/test_unit_metricas_painel.py` | Sem o mart, o painel usa a mesma regra (razão das somas) e o mesmo universo, e deixa vazio o que não consegue calcular pela definição. |

### A divergência que a camada semântica corrigiu

Antes, a aba "Noturno vs. Diurno & Turnos" do painel tirava a **média simples das taxas** dos cursos por turno e por grau. Assim, um curso de 20 ingressantes pesava o mesmo que um de 2.000. Já a comparação por campus, na mesma aba, usava a **razão das somas**. Eram duas definições de "taxa de evasão" na mesma tela. Medido na carga de 24/11/2026 (cursos terminais):

| Recorte | Definição (razão das somas) | Painel antes (média das taxas) | Diferença |
|---|---|---|---|
| Turno DIURNO E NOTURNO | 44,68% | 47,56% | +2,88 p.p. |
| Grau MISTO | 52,84% | 54,23% | +1,39 p.p. |
| Turno NOTURNO | 49,99% | 50,90% | +0,91 p.p. |
| Grau BACHARELADO | 37,71% | 38,38% | +0,67 p.p. |

Agora as três comparações vêm de `metricas_por_recorte`.

### Como mudar uma métrica

1. Altere a macro em `transform/macros/metricas.sql`.
2. Suba a `versao` e a `vigente_desde` da métrica em `metricas_definicoes.csv`, e registre a decisão em ADR (o número do ADR vai na coluna `adr`).
3. `bash scripts/dbt.sh build`. Na sincronização seguinte, o ETL reverso grava a versão nova na fila. Assim a coordenação vê que o número mudou de definição, e não só de valor.

Uma métrica nova sem linha no registro, ou uma linha sem métrica publicada, faz o `dbt build` falhar.

## ETL reverso: a fila de intervenção

**Quem consome:** a coordenação de cada curso, acompanhada pelo Decanato de Ensino de Graduação (DEG).

**O que faz com o dado:** a pergunta da E1 é "em quais cursos intervir primeiro?". O painel responde com um ranking. A fila transforma essa resposta em trabalho. Cada curso em RETENÇÃO CRÍTICA vira uma linha em `operacional.fila_intervencao`, e nela a coordenação:

- registra o responsável e o plano de ação;
- avança o status: `NOVO` → `EM_ANALISE` → `PLANO_EM_EXECUCAO` → `CONCLUIDO` (ou `DESCARTADO`).

O DEG consulta quais cursos críticos ainda estão em `NOVO`, ou seja, sem ninguém responsável. Também acompanha, nos ciclos seguintes, se os cursos com plano saíram da fila (`na_fila = false`, `saiu_da_fila_em`).

```sql
-- O que o DEG olha: cursos críticos sem plano, do mais crítico ao menos.
SELECT posicao, nome_curso, campus, indice_retencao_critica, taxa_evasao_pct, entrou_na_fila_em
FROM operacional.fila_intervencao
WHERE na_fila AND status = 'NOVO'
ORDER BY posicao;
```

| Decisão | Escolha | Por quê |
|---|---|---|
| Origem | `dbt_marts.painel_cursos_criticos` | É a mesma tabela do painel, então o número da fila é o número do painel. |
| Push ou pull | **Push**, depois de cada carga (`rodar_pipeline.sh`, asset `etl_reverso` no Dagster, CI) | A origem muda uma vez por mês. Quem sabe que há dado novo é o pipeline. |
| Por estado ou por evento | **Por estado** | Cada execução leva o destino ao estado da origem. Uma execução perdida é coberta pela seguinte, sem fila de eventos pendentes. |
| Idempotência | Só grava linha cujo valor mudou | A segunda execução do mesmo ciclo dá `0 novos, 0 atualizados, 0 saíram`. |
| O que é da coordenação | `status`, `responsavel`, `plano_de_acao` nunca são sobrescritos | O papel `coordenacao_academica` só tem `UPDATE` nessas colunas (privilégio por coluna) e não pode apagar linhas. |
| Curso que melhora | Não é apagado: `na_fila = false` e data de saída | O histórico da intervenção fica. Se o curso voltar à fila, mantém o andamento e ganha nova data de entrada. |
| Proteções | Recusa origem vazia (o dbt não rodou) e ciclo mais antigo que o da última execução | Um banco desatualizado não esvazia nem regride a fila. |
| Destino fora do ar | 4 tentativas (espera de 2, 4 e 8 s), depois sai com código 2 | O Dagster aplica o retry do asset. Como a sincronização é por estado, nada fica pendente. |
| Destino | `ETL_REVERSO_DATABASE_URL`, que por padrão é o próprio banco (esquema `operacional`) | Num destino novo, como o Supabase (onde a coordenação editaria pela interface de tabelas), basta rodar uma vez com `--preparar-destino`. A fila é agregada por curso (k ≥ 5). |

**A opção nula:** `--csv` grava o mesmo conteúdo num CSV agendado. Para comparação:

| | CSV agendado (opção nula) | Fila no banco |
|---|---|---|
| Tempo por ciclo (23 cursos) | < 1 s | 3 a 4 ms de sincronização |
| Andamento da coordenação | Fica fora do arquivo (planilha à parte, que o próximo CSV não conhece) | Na mesma linha, preservado entre ciclos |
| Curso que sai da fila | Some do arquivo | Fica, com a data de saída |
| Quem pode alterar o quê | Quem tem o arquivo altera tudo | Privilégio por coluna |

O CSV basta para **avisar**. Não basta para **acompanhar**, que é o que o DEG precisa para saber se a intervenção funcionou. A decisão completa, com medições, vai no ADR da E4.

### Rodar e demonstrar

```bash
python3 src/etl_reverso/fila_intervencao.py          # sincroniza: "23 novos, 0 atualizados, 0 saíram da fila"
python3 src/etl_reverso/fila_intervencao.py          # de novo: "0 novos, 0 atualizados, 0 saíram da fila"
python3 src/etl_reverso/fila_intervencao.py --csv export/fila_intervencao.csv   # opção nula
ETL_REVERSO_DATABASE_URL=postgresql://x:y@127.0.0.1:5999/z \
  python3 src/etl_reverso/fila_intervencao.py        # destino fora: 4 tentativas, código 2
python3 -m unittest tests/test_banco_etl_reverso.py tests/test_unit_metricas_painel.py
```
