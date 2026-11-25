# 0024 — Camada analítica em Delta Lake, Parquet com ZSTD e partição por quinquênio

- **Status:** aceito
- **Data:** 2026-10-10
- **Decisores:** Squad Observatório UnB (redação: Leandro de Almeida Oliveira; gatilhos de revisão: murilopbs)

## Contexto

Silver e gold só existiam no PostgreSQL (ADR 0009): para ler o dado, era preciso o banco no ar e o motor que o escreveu. A E2 pede uma camada analítica em formato aberto, Parquet com uma tabela Iceberg ou Delta por cima.

O padrão de acesso é o de análise: varreduras de colunas inteiras agregadas por curso e coorte (taxa de evasão por curso e quinquênio de ingresso, por exemplo), com escrita uma vez por mês (`atualiza-dados.yml`). A maior tabela é `silver.movimentacoes_vinculos`, com 152.680 vínculos em três quinquênios de ingresso (2010, 2015 e 2020). As demais têm de 4 a 286 linhas.

## Alternativas consideradas

### A. Opção nula — continuar como está

Sem camada aberta: o dado fica só no PostgreSQL. Não atende à E2, porque para ler é preciso o banco no ar e o motor que o escreveu. A mesma tabela de vínculos ocupa 15 MB no PostgreSQL.

### B. Delta Lake sobre Parquet

- **Escrita sem JVM nem catálogo.** O `deltalake` (delta-rs) grava de Python puro, com o log de transações na própria pasta.
- **Overwrite com predicado.** `write_deltalake(mode="overwrite", predicate=...)` troca só as partições de uma janela numa transação. É o que o reprocessamento de janela precisa.
- **Leitura.** DuckDB (`delta_scan`), Spark, Polars e pandas leem Delta. Os arquivos de dados são Parquet comum, que qualquer leitor de Parquet abre mesmo sem entender o log.

### C. Apache Iceberg sobre Parquet

O Iceberg em Python (`pyiceberg`) exige um catálogo (REST, SQL ou Glue), que seria mais um serviço no `docker-compose.yml`. A evolução de esquema dele é mais rica (renomear e reordenar coluna por id de campo).

Dentro da alternativa escolhida, mais duas escolhas foram medidas: o **codec** (a opção nula é o Snappy, padrão do pyarrow) e o **particionamento** (por ano, por quinquênio ou sem partição).

## Medição

Os 152.680 vínculos num arquivo Parquet. A leitura é a mediana de 15 execuções de uma agregação de evasão por curso e quinquênio no DuckDB.

Como reproduzir:

```bash
python3 src/db/exportar_lago.py          # grava o lago em data/lake/lote/
python3 -m unittest tests/test_unit_lago.py
```

| Compressão | Tamanho | Escrita | Leitura |
|---|---|---|---|
| Nenhuma | 3.319 KB | 62 ms | 17 ms |
| Snappy (padrão do pyarrow, opção nula do codec) | 2.222 KB | 66 ms | 22 ms |
| GZIP | 1.462 KB | 3.527 ms | 19 ms |
| ZSTD 1 | 1.439 KB | 60 ms | 22 ms |
| **ZSTD 3** | **1.434 KB** | **173 ms** | **25 ms** |
| ZSTD 9 | 1.364 KB | 192 ms | 18 ms |

O ZSTD ocupa 35% menos que o Snappy, e a diferença de leitura entre os codecs (17 a 25 ms) fica dentro do ruído da medição. Os níveis 1 e 3 empatam no tamanho. O GZIP comprime parecido, mas escreve 20 vezes mais devagar.

Particionamento:

| Partição | Linhas por arquivo | Tamanho por arquivo |
|---|---|---|
| Por ano de ingresso | cerca de 10 mil | uns 100 KB (muitos arquivos pequenos, cada um com seu rodapé e sua abertura na leitura) |
| **Por quinquênio** | — | **370 a 560 KB** |

## Decisão

Escolhemos **Delta Lake (B), com Parquet ZSTD nível 3 e partição dos vínculos por quinquênio de ingresso**:

- **Exportação por `src/db/exportar_lago.py`.** O script exporta `silver.cursos`, `silver.estruturas_curriculares`, `silver.movimentacoes_vinculos` e o Star Schema da gold para `data/lake/lote/<esquema>/<tabela>`. Os tipos de cada coluna saem do catálogo do PostgreSQL, e não do dado: uma coluna toda nula numa execução não muda o esquema do Delta. `silver.discentes` fica fora, porque guarda nascimento, sexo e raça/cor por pessoa.
- **Idempotência.** Cada execução é um `overwrite` numa versão nova do log. Regravar dá as mesmas linhas e o mesmo número de arquivos ativos (`tests/test_unit_lago.py`).
- **Reprocessamento de janela.** `--quinquenio 2020` regrava só aquela partição dos vínculos. As outras não são tocadas, e seus arquivos continuam os mesmos. Se a janela vier vazia do banco, a partição fica vazia.
- **Particionamento só dos vínculos, por quinquênio de ingresso.** É o mesmo corte das partições do PostgreSQL (migração 0019), e o filtro por coorte é o mais comum nas consultas. As tabelas pequenas não são particionadas e ficam com um arquivo só.
- **ZSTD nível 3.** A escrita é mensal, então o custo dela não pesa. O 3 é o nível padrão do ZSTD e deixa margem caso as tabelas cresçam.
- **VACUUM com retenção de 7 dias.** Os arquivos das versões substituídas ficam 7 dias no disco. Nesse prazo, a viagem no tempo do Delta (`DeltaTable(..., version=n)`) compara uma reexecução com a anterior. Depois disso, o VACUUM apaga esses arquivos.

## Consequências

**O que ganhamos:**

- O dado fica legível sem o banco, por DuckDB, Spark, Polars ou pandas, e em 1.434 KB contra 15 MB no PostgreSQL.
- O reprocessamento de uma janela regrava só aquela partição.
- O lago é derivado do banco e regravável a qualquer momento, então não precisa de backup.
- Nenhum serviço novo no `docker-compose.yml`. A nova etapa entra em `scripts/rodar_pipeline.sh` depois do povoamento dimensional.

**O que perdemos:**

- A evolução de esquema do Iceberg (renomear e reordenar coluna por id de campo). Aqui o esquema vem das migrações do PostgreSQL (ADR 0009), e a mudança de esquema é rara e deliberada.
- Versões anteriores do lago só por 7 dias; depois o VACUUM as apaga.
- `data/` não é versionado, e o lago com vínculos individuais (id sintético) fica só na máquina ou no runner que rodou o pipeline, como a silver no banco.

**O que se torna irreversível:**

Pouco, porque o lago é sempre regerado do banco. O que fica preso ao Delta é o código: o export (`exportar_lago.py`) e o consumidor do CDC, que aplica as mudanças por `MERGE` do Delta (`src/cdc/lago.py`, ADR 0025). Trocar para Iceberg exigiria reescrever os dois, mas não o dado.

O lago é carga em lote a partir do banco. A captura de mudanças (CDC) é outro caminho e tem decisão própria (ADR 0025).

## Gatilho de revisão

- **Partição por quinquênio sair da faixa saudável** (crescer acima de 128 MB por arquivo Parquet, pedindo partição por `ano_ingresso`, ou acumular > 50 arquivos pequenos por partição sem compactação).
  - *Estado no semestre (até 24/11/2026):* **Não disparou — decisão mantida.** Os arquivos por quinquênio ficam entre 370 KB e 560 KB (152.680 vínculos em 6 quinquênios, 2000–2025), com reprocessamento seletivo (`--janelas-alteradas`) em ~1,8 s (Semana 10) e backfill validado na Semana 13.
- **Evolução de esquema frequente por ID de campo (renomear/reordenar colunas) ou entrada de múltiplos escritores concorrentes no lago**, cenário em que Apache Iceberg com catálogo gerenciado passaria a se pagar.
  - *Estado no semestre (até 24/11/2026):* **Não disparou — decisão mantida.** `src/db/exportar_lago.py` segue como único escritor do lago em lote, lendo os tipos do catálogo do PostgreSQL.
- **Tempo de escrita em ZSTD nível 3 ultrapassar 5 s ou leitura analítica de agregação no DuckDB passar de 500 ms**, justificando migrar para ZSTD nível 1 ou Snappy.
  - *Estado no semestre (até 24/11/2026):* **Não disparou — decisão mantida.** A escrita dos vínculos segue em ~173 ms (export completo em ~0,9 s) e a leitura analítica em ~25 ms.
- **Não-determinismo entre recargas fazendo o Delta regravar todas as partições mesmo sem mudança na fonte.**
  - *Estado no semestre (até 24/11/2026):* **Disparou — decisão mantida com correção na carga** (Semana 10). Sem ordenação explícita na carga da Silver 3NF, os `id_vinculo` (`IDENTITY`) flutuavam entre execuções e invalidavam todas as partições do lago. A adição de `ORDER BY dg.id` eliminou a variação sem alterar o formato Delta nem o particionamento por quinquênio.
