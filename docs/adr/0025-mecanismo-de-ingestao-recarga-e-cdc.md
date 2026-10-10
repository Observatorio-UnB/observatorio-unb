# ADR 0025: Recarga periódica como mecanismo principal de ingestão, CDC como caminho opcional

- **Status:** Aceita
- **Data:** 2026-10-10

## Contexto

O dado chega ao lago analítico (`data/lake/`, Delta Lake sobre Parquet, ADR 0024) por dois caminhos:

- **Lote (recarga periódica):** fonte pública (API CKAN da UnB, Censo do INEP) → bronze → silver → Silver 3NF e Star Schema no PostgreSQL → `src/db/exportar_lago.py` → `data/lake/lote/`. Hoje roda uma vez por mês (`atualiza-dados.yml`, dia 1, 06:00 UTC).
- **CDC (captura de mudanças):** WAL do PostgreSQL (decodificação lógica, `pgoutput`, publicação `observatorio_cdc`) → Debezium → Kafka → `src/cdc/consumidor.py` → `data/lake/cdc/`.

**O OLTP é a Silver 3NF** (`silver.cursos`, `silver.estruturas_curriculares` e `silver.movimentacoes_vinculos`; migração 0011). É o modelo transacional normalizado da E1 ([prova da 3NF](../arquitetura/01_PROVA_MATEMATICA_NORMALIZACAO_3NF.md)), com chaves primárias, chaves estrangeiras e partições. O CDC captura essas três tabelas. `silver.discentes` fica de fora dos dois caminhos, porque guarda nascimento, sexo e raça/cor por pessoa.

A pergunta é qual dos dois é o mecanismo de ingestão do projeto, e o que se paga por cada um. A opção nula é não ter CDC: uma recarga agendada (`INSERT ... SELECT`, ou o export do lote) depois de cada carga.

## Medições

Ambiente local: PostgreSQL 16, Kafka 3.7 (KRaft) e Debezium 2.7 no `docker-compose.yml`, com 152.680 vínculos, 158 cursos e 112 matrizes.

| | Recarga periódica (opção nula) | CDC |
|---|---|---|
| Latência de uma mudança no OLTP até o lago | até 1 mês (intervalo do agendamento) + 0,9 s de export | 0,25 a 0,87 s (`src/cdc/demonstrar.py`, INSERT, UPDATE e DELETE) |
| Recarga inteira da Silver 3NF (152.953 linhas) | export completo em 0,9 s | 152.953 eventos; lago em dia 6,6 s depois do commit |
| Pipeline da fonte até a Silver 3NF | 46 s (sem a vetorização) | o mesmo; o CDC não substitui essa parte |
| Serviços a mais | nenhum | Kafka e Kafka Connect: 0,9 GB + 1,0 GB de RAM |
| Disco a mais | lago em lote: 5 MB | tópicos: 378 MB depois de 3 cargas (JSON, com before/after); lago CDC: 66 MB com 7 dias de versões |
| Risco no banco | nenhum | slot de replicação segura WAL. Chegou a 239 MB e depois a 86 MB logo após uma recarga, e volta a KB quando o Debezium confirma. Com o conector parado, cresce até `max_slot_wal_keep_size` (2 GB). |
| Operação | um cron que já existe | registrar e remover o conector (`scripts/cdc.sh`), acompanhar o slot, compactar os arquivos pequenos |

O dado de origem muda uma vez por mês. O único processo que escreve no OLTP é o próprio pipeline, que recarrega a Silver 3NF inteira (`TRUNCATE` + `INSERT ... SELECT`). Para o CDC, cada recarga mensal vira 152.953 eventos e 1,9 GB de RAM em serviços. O export do lote entrega o mesmo resultado em menos de 1 segundo.

## Decisão

- **A recarga periódica é o mecanismo principal.** O lago em lote é regravado depois de cada carga (`rodar_pipeline.sh` e `medalhao.yml`). A latência de até um mês é a da própria fonte: chegar ao lago em 0,5 s não adianta quando a UnB publica uma vez por mês.
- **O CDC fica como caminho opcional**, fora do pipeline e do CI, no profile `cdc` do compose. Ele se justifica quando alguém escreve no OLTP fora do pipeline, como numa correção manual de um curso ou de uma matriz. Nesse caso, a recarga só levaria a correção ao lago no mês seguinte, e o CDC a leva em menos de 1 s, sem reprocessar nada.
- **A semântica de entrega do CDC é "no mínimo uma vez" no transporte e "exatamente uma vez" no efeito.** O offset só é confirmado no Kafka depois da gravação no lago, e o `MERGE` só aplica um evento mais novo, pela posição no WAL, que a linha do lago. `src/cdc/demonstrar_reprocessamento.py` comprova isso com dois reprocessamentos:
  - o consumidor cai depois de gravar e antes de confirmar, e o Kafka entrega de novo o lote de 100 mensagens;
  - o grupo relê os 306.009 eventos dos tópicos desde o primeiro offset.

  Nos dois casos o sha256 do lago não muda. "No máximo uma vez", confirmando antes de gravar, perderia o lote numa queda. Não há transação entre o Kafka e o Delta, então o "exatamente uma vez" de ponta a ponta vem da idempotência do `MERGE`.
- **O lote é idempotente por substituição.** O banco faz `TRUNCATE` + `COPY` numa transação, e o lago faz `overwrite` numa versão nova. Rodar duas vezes dá as mesmas linhas.
- **O formato é Delta Lake, e não Iceberg.** Os critérios de evolução de esquema e de ecossistema de leitura estão no ADR 0024.

## Como cada caminho falhou

Os dois caminhos falham de jeitos diferentes. Estas são as falhas vistas durante a construção e o que foi feito com cada uma.

| Caminho | Falha | Tratamento |
|---|---|---|
| Lote | Servidor do INEP fora do ar, ou com a cadeia TLS incompleta | Retentativas e a CA intermediária anexada (`inep_censo_superior.py`); sem o arquivo, o pipeline segue sem o benchmark |
| Lote | Reexecução duplicando linhas | `TRUNCATE` + `COPY` numa transação (`tabelas.gravar_varias`); `overwrite` no lago |
| Lote | Coluna toda nula mudando de tipo entre execuções e quebrando o `overwrite` do Delta | Tipos tirados do catálogo do PostgreSQL, e não inferidos do dado (`exportar_lago.montar_tabela_arrow`) |
| CDC | O Debezium ignora `TRUNCATE` por padrão: depois de uma recarga, as linhas apagadas ficariam vivas no lago | `skipped.operations=none` e marca de exclusão das linhas anteriores ao `TRUNCATE` (`lago._truncar`) |
| CDC | O `sequence` do Debezium vem sem LSN de commit no snapshot e na primeira transação: com tópicos recriados, as mudanças novas seriam ignoradas | Sem o commit, vale o LSN do próprio evento (`lago.decodificar`), com teste |
| CDC | DELETE seguido de um INSERT antigo reprocessado ressuscitaria a linha | A exclusão vira marca (`_deletado`) com a posição no WAL, e não DELETE |
| CDC | O consumidor cai entre gravar e confirmar | O lote volta e o `MERGE` o absorve (demonstrado acima) |
| CDC | Slot de replicação segurando WAL (até 239 MB depois de uma recarga) | `max_slot_wal_keep_size=2GB` no banco e `scripts/cdc.sh remover`, que apaga conector e slot |
| CDC | Cada `MERGE` grava arquivos novos (arquivos pequenos) | Compactação a cada 50 lotes e ao esvaziar os tópicos |

## Consequências

O projeto fica com um caminho barato e sempre ligado (lote) e um caro e opcional (CDC). Desligar o CDC exige `scripts/cdc.sh remover`. Parar só os containers deixa o slot segurando WAL até o limite de 2 GB.

Se o OLTP passar a receber escrita contínua fora do pipeline, por exemplo de uma aplicação de secretaria, a conta da latência muda e o CDC passa a ser o caminho principal. Os números acima precisam ser medidos de novo nesse cenário.
