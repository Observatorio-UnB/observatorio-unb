# ADR 0024: Camada analítica em Delta Lake, Parquet com ZSTD e partição por quinquênio

- **Status:** Aceita
- **Data:** 2026-10-10

## Contexto

Silver e gold só existiam no PostgreSQL (ADR 0009): para ler o dado, era preciso o banco no ar e o motor que o escreveu. A E2 pede uma camada analítica em formato aberto, Parquet com uma tabela Iceberg ou Delta por cima.

O padrão de acesso é o de análise: varreduras de colunas inteiras agregadas por curso e coorte (taxa de evasão por curso e quinquênio de ingresso, por exemplo), com escrita uma vez por mês (`atualiza-dados.yml`). A maior tabela é `silver.movimentacoes_vinculos`, com 152.680 vínculos em três quinquênios de ingresso (2010, 2015 e 2020). As demais têm de 4 a 286 linhas.

## Decisão

- **Delta Lake, e não Iceberg.** Os critérios foram estes:
  - **Escrita sem JVM nem catálogo.** O `deltalake` (delta-rs) grava de Python puro, com o log de transações na própria pasta. O Iceberg em Python (`pyiceberg`) exige um catálogo (REST, SQL ou Glue), que seria mais um serviço no `docker-compose.yml`.
  - **Overwrite com predicado.** `write_deltalake(mode="overwrite", predicate=...)` troca só as partições de uma janela numa transação. É o que o reprocessamento de janela precisa.
  - **Leitura.** DuckDB (`delta_scan`), Spark, Polars e pandas leem Delta. Os arquivos de dados são Parquet comum, que qualquer leitor de Parquet abre mesmo sem entender o log.
  - **O que se perde.** A evolução de esquema do Iceberg é mais rica (renomear e reordenar coluna por id de campo). Aqui o esquema vem das migrações do PostgreSQL (ADR 0009), e a mudança de esquema é rara e deliberada.
- **Exportação por `src/db/exportar_lago.py`.** O script exporta `silver.cursos`, `silver.estruturas_curriculares`, `silver.movimentacoes_vinculos` e o Star Schema da gold para `data/lake/lote/<esquema>/<tabela>`. Os tipos de cada coluna saem do catálogo do PostgreSQL, e não do dado: uma coluna toda nula numa execução não muda o esquema do Delta. `silver.discentes` fica fora, porque guarda nascimento, sexo e raça/cor por pessoa.
- **Idempotência.** Cada execução é um `overwrite` numa versão nova do log. Regravar dá as mesmas linhas e o mesmo número de arquivos ativos (`tests/test_unit_lago.py`).
- **Reprocessamento de janela.** `--quinquenio 2020` regrava só aquela partição dos vínculos. As outras não são tocadas, e seus arquivos continuam os mesmos. Se a janela vier vazia do banco, a partição fica vazia.
- **Particionamento só dos vínculos, por quinquênio de ingresso.** É o mesmo corte das partições do PostgreSQL (migração 0019), e o filtro por coorte é o mais comum nas consultas.
  - Partição por ano daria cerca de 10 mil linhas, uns 100 KB por arquivo: muitos arquivos pequenos, cada um com seu rodapé e sua abertura de arquivo na leitura.
  - Por quinquênio, cada partição tem um arquivo de 370 a 560 KB.
  - As tabelas pequenas não são particionadas e ficam com um arquivo só.
- **ZSTD nível 3.** Medido com os 152.680 vínculos num arquivo Parquet. A leitura é a mediana de 15 execuções de uma agregação de evasão por curso e quinquênio no DuckDB:

  | Compressão | Tamanho | Escrita | Leitura |
  |---|---|---|---|
  | Nenhuma | 3.319 KB | 62 ms | 17 ms |
  | Snappy (padrão do pyarrow) | 2.222 KB | 66 ms | 22 ms |
  | GZIP | 1.462 KB | 3.527 ms | 19 ms |
  | ZSTD 1 | 1.439 KB | 60 ms | 22 ms |
  | **ZSTD 3** | **1.434 KB** | **173 ms** | **25 ms** |
  | ZSTD 9 | 1.364 KB | 192 ms | 18 ms |

  O ZSTD ocupa 35% menos que o Snappy, e a diferença de leitura entre os codecs (17 a 25 ms) fica dentro do ruído da medição. A escrita é mensal, então o custo dela não pesa. Os níveis 1 e 3 empatam no tamanho. O 3 é o nível padrão do ZSTD e deixa margem caso as tabelas cresçam. O GZIP comprime parecido, mas escreve 20 vezes mais devagar. Para comparação, a mesma tabela ocupa 15 MB no PostgreSQL.
- **VACUUM com retenção de 7 dias.** Os arquivos das versões substituídas ficam 7 dias no disco. Nesse prazo, a viagem no tempo do Delta (`DeltaTable(..., version=n)`) compara uma reexecução com a anterior. Depois disso, o VACUUM apaga esses arquivos.

## Consequências

O lago é derivado do banco e regravável a qualquer momento, então não precisa de backup. `data/` não é versionado, e o lago com vínculos individuais (id sintético) fica só na máquina ou no runner que rodou o pipeline, como a silver no banco. A nova etapa entra em `scripts/rodar_pipeline.sh` depois do povoamento dimensional.

O lago é carga em lote a partir do banco. A captura de mudanças (CDC) é outro caminho e tem decisão própria.
