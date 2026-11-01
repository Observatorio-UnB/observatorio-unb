# Testes de dados da camada transformada

Os testes ficam no projeto dbt (`transform/`) e rodam a cada `dbt build`: no CI (`medalhao.yml`), no `rodar_pipeline.sh` e no Docker. Teste que falha interrompe o build, e o dbt pula os modelos que dependem do dado reprovado. São 61 testes. Um deles (`dominio_saida_estimada_antes_do_ingresso`) avisa sem falhar, porque cobre uma anomalia conhecida da fonte.

## Por tipo

| Tipo | Testes | O que pega |
|---|---|---|
| **Esquema** | Contrato de nomes e tipos (`contract: enforced`) em `stg_vinculos`, `fct_retencao_curso` e `painel_cursos_criticos`; `accepted_values` em categoria, desfecho, fonte e classificação | Coluna renomeada ou com outro tipo na silver; categoria nova que ninguém mapeou |
| **Volume** | `volume_entre` em `stg_cursos` (100 a 300), `stg_estruturas_curriculares` (80 a 200), `stg_vinculos` (100 mil a 300 mil), `dim_curso` (80 a 200), `fct_retencao_curso` e `painel_cursos_criticos` (60 a 150) | Carga parcial, arquivo truncado, duplicação em massa |
| **Unicidade** | `unique` nas chaves de todos os modelos e no nome canônico | Vínculo ou curso duplicado, que conta duas vezes no fato |
| **Integridade referencial** | `relationships` do vínculo para a matriz, da matriz para o curso, e do fato para as duas dimensões | Vínculo sem matriz, fato apontando para curso que não está na dimensão |
| **Distribuição** | `distribuicao_salto_de_serie_entre_coortes`, `distribuicao_desfechos_por_coorte`, `distribuicao_curso_que_some`, `distribuicao_mediana_evasao_por_curso` | O erro silencioso: todos os valores válidos, e o resultado errado |
| **Domínio (o que o dado tem de sujo)** | Permanência entre 1 e 35 semestres; prazo ideal entre 4 e 16; ano de ingresso plausível; saída antes do ingresso; desfechos que somam mais que os ingressantes; taxas e IRC entre 0 e 100; k ≥ 5 no fato | Valor negativo onde não cabe, saída antes de entrar, contagem dupla na junção |
| **Reconciliação** | `reconcilia_fato_retencao_com_a_gold` | O fato do dbt diverge, em qualquer curso ou medida, do fato do pipeline Python |

## Distribuição: os limites e de onde vêm

Os limites foram medidos na base de 10/2026 (152.680 vínculos; coortes maduras de 2010 a 2016) e têm folga para a variação normal entre cargas:

| Teste | Regra | Na base atual |
|---|---|---|
| Salto de série | O volume de uma coorte madura não varia mais de 30% em relação à anterior | Maior variação: 15% (2013 para 2014) |
| Desfechos por coorte | Evasão entre 30% e 60%, formatura entre 35% e 70%, em cada coorte madura | Evasão de 40% a 47%; formatura de 47% a 57% |
| Curso que some | Curso com 80 ou mais ingressantes na coorte anterior e na seguinte não pode ter zero na do meio | Os buracos reais são de cursos com entrada alternada, com no máximo 66 ingressantes ao lado (Educação do Campo) |
| Mediana da evasão por curso | Entre 30% e 60% | 44,2% |

**A anomalia conhecida.** Há 9 vínculos do SIGAA com a saída antes do ingresso. Todos têm o período de saída estimado pela data do diploma (ADR 0015), e todos ingressaram em 2023 ou 2024. Esses casos geram aviso, e viram erro se passarem de 50. Saída antes do ingresso com o período publicado pela fonte é sempre erro.

## A prova: cada teste falha com o dado ruim

`tests/test_dbt_dado_ruim.py` copia as tabelas da silver para o esquema `silver_injetado`, estraga a cópia e roda o `dbt build` sobre ela, com as camadas em esquemas próprios (`inj_dbt_*`). Nada toca a silver nem as camadas de verdade, e tudo é apagado no fim. A base sem injeção passa inteira, e cada injeção derruba o teste esperado:

| Dado ruim injetado | Teste que falha |
|---|---|
| `semestres_permanencia_valida` vira `numeric` na fonte | Contrato de `stg_vinculos` (o build do modelo para) |
| Metade dos vínculos não veio | `volume_entre` de `stg_vinculos` |
| Um vínculo duplicado | `unique` de `stg_vinculos.id_vinculo` |
| Três vínculos apontando para matriz inexistente | `relationships` do vínculo para a matriz |
| Coorte de 2013 pela metade | `distribuicao_salto_de_serie_entre_coortes` |
| Evasão de 2012 classificada como OUTROS | `distribuicao_desfechos_por_coorte` |
| MEDICINA some da coorte de 2014 | `distribuicao_curso_que_some` |
| Formados contados como evadidos | `distribuicao_mediana_evasao_por_curso` (com o staging pulado: no `build`, o teste por coorte pega antes) |
| Permanência de −3 semestres | `entre` de `semestres_permanencia_valida` |
| Saída dois anos antes do ingresso, com período publicado | `dominio_saida_antes_do_ingresso` |
| Prazo ideal zerado numa matriz | `entre` de `semestre_ideal` |

Ficam de fora da injeção dois testes que o dado da silver não consegue violar: o k-anonimato e a soma dos desfechos. O primeiro é garantido pelo `HAVING` do modelo, e o segundo pela contagem sobre os mesmos vínculos. Os dois existem para pegar uma regressão no modelo, não um dado sujo.

```bash
pip install -r requirements-dbt.txt
bash scripts/dbt.sh build --full-refresh               # os 61 testes sobre o dado real
python3 -m unittest tests/test_dbt_dado_ruim.py         # a prova com dado estragado (~50 s)
```
