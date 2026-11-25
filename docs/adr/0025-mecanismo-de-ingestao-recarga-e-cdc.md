# 0025 — Recarga periódica como mecanismo principal de ingestão, CDC como caminho opcional

- **Status:** aceito
- **Data:** 2026-10-10
- **Decisores:** Squad Observatório UnB: Felipe de Sousa Coelho, Joao Victor Marques Reis de Miranda, Leandro de Almeida Oliveira, Murilo Perazzo Barbosa Souto, Thales Germano Vargas Lima e Vitor Carvalho Pereira (redação: Leandro de Almeida Oliveira; gatilhos de revisão: Murilo Perazzo Barbosa Souto)

## Contexto

O dado chega ao lago analítico (`data/lake/`, Delta Lake sobre Parquet, ADR 0024) por dois caminhos:

- **Lote (recarga periódica):** fonte pública (API CKAN da UnB, Censo do INEP) → bronze → silver → Silver 3NF e Star Schema no PostgreSQL → `src/db/exportar_lago.py` → `data/lake/lote/`. Hoje roda uma vez por mês (`atualiza-dados.yml`, dia 1, 06:00 UTC).
- **CDC (captura de mudanças):** WAL do PostgreSQL (decodificação lógica, `pgoutput`, publicação `observatorio_cdc`) → Debezium → Kafka → `src/cdc/consumidor.py` → `data/lake/cdc/`.

**O OLTP é a Silver 3NF** (`silver.cursos`, `silver.estruturas_curriculares` e `silver.movimentacoes_vinculos`; migração 0011). É o modelo transacional normalizado da E1 ([prova da 3NF](../arquitetura/01_PROVA_MATEMATICA_NORMALIZACAO_3NF.md)), com chaves primárias, chaves estrangeiras e partições. O CDC captura essas três tabelas. `silver.discentes` fica de fora dos dois caminhos, porque guarda nascimento, sexo e raça/cor por pessoa.

A pergunta é qual dos dois é o mecanismo de ingestão do projeto, e o que se paga por cada um. A opção nula é não ter CDC: uma recarga agendada (`INSERT ... SELECT`, ou o export do lote) depois de cada carga.

## Alternativas consideradas

### A. Opção nula — continuar como está

Recarga periódica: o pipeline mensal recarrega a Silver 3NF inteira (`TRUNCATE` + `INSERT ... SELECT`) e regrava o lago em lote (`exportar_lago.py`) depois de cada carga. Nenhum serviço novo.

### B. CDC por decodificação lógica do WAL

Debezium lê o WAL (`pgoutput`, publicação `observatorio_cdc`), publica no Kafka, e `src/cdc/consumidor.py` aplica as mudanças no lago por `MERGE`. Leva cada INSERT, UPDATE e DELETE ao lago em menos de 1 s.

### C. Recarga periódica mais frequente (cron de hora em hora)

O mesmo caminho da A, com agendamento de hora em hora. Baixaria a latência para até 1 hora, ainda sem Kafka nem slot de replicação.

## Medição

Como reproduzir:

```bash
docker compose --profile cdc up -d db kafka connect
bash scripts/cdc.sh registrar
python3 src/cdc/demonstrar.py                 # INSERT, UPDATE e DELETE atravessando o fluxo
python3 src/cdc/demonstrar_reprocessamento.py # reprocessamento forçado: o lago não muda
bash scripts/cdc.sh remover
```

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

### Como cada caminho falhou


Os dois caminhos falham de jeitos diferentes. Estas são as falhas vistas durante a construção e na revisão do CDC, e o que foi feito com cada uma.

| Caminho | Falha | Tratamento |
|---|---|---|
| Lote | Servidor do INEP fora do ar, ou com a cadeia TLS incompleta | Retentativas e a CA intermediária anexada (`inep_censo_superior.py`); sem o arquivo, o pipeline segue sem o benchmark |
| Lote | Reexecução duplicando linhas | `TRUNCATE` + `COPY` numa transação (`tabelas.gravar_varias`); `overwrite` no lago |
| Lote | Coluna toda nula mudando de tipo entre execuções e quebrando o `overwrite` do Delta | Tipos tirados do catálogo do PostgreSQL, e não inferidos do dado (`exportar_lago.montar_tabela_arrow`) |
| CDC | O Debezium ignora `TRUNCATE` por padrão: depois de uma recarga, as linhas apagadas ficariam vivas no lago | `skipped.operations=none` e marca de exclusão das linhas anteriores ao `TRUNCATE` (`lago._truncar`) |
| CDC | O `sequence` do Debezium vem sem LSN de commit no snapshot e na primeira transação: com tópicos recriados, as mudanças novas seriam ignoradas | Sem o commit, vale o LSN do próprio evento (`lago.decodificar`), com teste |
| CDC | DELETE seguido de um INSERT antigo reprocessado ressuscitaria a linha | A exclusão vira marca (`_deletado`) com a posição no WAL, e não DELETE (demonstrado acima) |
| CDC | O consumidor cai entre gravar e confirmar | O lote volta e o `MERGE` o absorve (demonstrado acima) |
| CDC | Slot de replicação segurando WAL (até 239 MB depois de uma recarga) | `max_slot_wal_keep_size=2GB` no banco e `scripts/cdc.sh remover`, que apaga conector, offsets e slot |
| CDC | Fluxo interrompido (slot invalidado pelo limite de WAL, Kafka recriado sem volume, consumidor parado além da retenção): o snapshot refeito só traz as linhas que ainda existem, e um DELETE perdido deixaria a linha viva no lago | O fim do snapshot de cada tabela marca as linhas do lago anteriores a ele (`lago.aplicar`); tópicos sem retenção por tempo (`retention.ms=-1`); `remover` apaga os offsets do conector, sem os quais o `registrar` seguinte não refaz o snapshot |
| CDC | Banco recriado ou restaurado: o WAL recomeça numa posição menor que a do lago, e os eventos novos perderiam o `MERGE` sem aviso | O consumidor compara o lago com `pg_current_wal_lsn()` quando chega um lote mais antigo que o lago, e aborta se o lago estiver à frente (`Consumidor.conferir_wal`) |
| CDC | Kafka e Kafka Connect publicados em todas as interfaces, sem autenticação; a configuração do conector devolve a senha do banco | Portas só em `127.0.0.1` no `docker-compose.yml` |
| CDC | Cada `MERGE` grava arquivos novos (arquivos pequenos) | Compactação a cada 50 lotes e ao esvaziar os tópicos |
| CDC | Um processo que lê o lago e sai logo em seguida abortava (`terminate called without an active exception`): o pyarrow desmontava a leitura numa thread própria, que precisa do Python já finalizado | Leitura do lago sem as threads do pyarrow (`lago._ler_delta`) |

## Decisão

Escolhemos **a recarga periódica (A) como mecanismo principal e o CDC (B) como caminho opcional**:


- **A recarga periódica é o mecanismo principal.** O lago em lote é regravado depois de cada carga (`rodar_pipeline.sh` e `medalhao.yml`). A latência de até um mês é a da própria fonte: chegar ao lago em 0,5 s não adianta quando a UnB publica uma vez por mês. Esse mês vem do agendamento, e não do mecanismo: o export leva 0,9 s, e com `--janelas-alteradas` uma execução sem mudança não grava versão nova no lago. Um cron de hora em hora custaria praticamente o mesmo e baixaria a latência para até 1 hora, ainda sem Kafka nem slot de replicação.
- **O CDC fica como caminho opcional**, fora do pipeline e do CI, no profile `cdc` do compose. Ele se justifica quando alguém escreve no OLTP fora do pipeline, como numa correção manual de um curso ou de uma matriz. Nesse caso, a recarga só levaria a correção ao lago no mês seguinte, e o CDC a leva em menos de 1 s, sem reprocessar nada.
- **A semântica de entrega do CDC é "no mínimo uma vez" no transporte e "exatamente uma vez" no efeito.** O offset só é confirmado no Kafka depois da gravação no lago, e o `MERGE` só aplica um evento mais novo, pela posição no WAL, que a linha do lago. `src/cdc/demonstrar_reprocessamento.py` comprova isso com três reprocessamentos:
  - o consumidor cai depois de gravar e antes de confirmar, e o Kafka entrega de novo o lote de 100 mensagens;
  - o grupo relê os tópicos inteiros desde o primeiro offset (766 mil eventos na última execução);
  - os sentinelas são excluídos, e o grupo relê tudo outra vez, com os INSERTs antigos, sem ressuscitar nenhum.

  Nos três casos o sha256 do lago não muda, nem com a hora de gravação de cada linha (`_gravado_em`): a entrega repetida não regrava nada. A demonstração também confere o conteúdo. O lote muda o lago e chega com o valor do UPDATE, que é gravado num `MERGE` separado do INSERT e vence pelo commit da transação. "No máximo uma vez", confirmando antes de gravar, perderia o lote em silêncio numa queda. Só um reprocessamento manual do tópico o recuperaria, e só enquanto o tópico tiver o histórico. Não há transação entre o Kafka e o Delta, então o "exatamente uma vez" de ponta a ponta vem da idempotência do `MERGE`.
- **O lote é idempotente por substituição.** O banco faz `TRUNCATE` + `COPY` numa transação, e o lago faz `overwrite` numa versão nova. Rodar duas vezes dá as mesmas linhas.
- **O formato é Delta Lake, e não Iceberg.** Os critérios de evolução de esquema e de ecossistema de leitura estão no ADR 0024.

## Consequências

**O que ganhamos:**

- Um caminho barato e sempre ligado: um cron que já existe, export em 0,9 s, idempotente por substituição.
- O CDC pronto e demonstrado para o dia em que alguém escrever no OLTP fora do pipeline, com a semântica de entrega comprovada.

**O que perdemos:**

- Latência de até um mês entre uma mudança no OLTP e o lago, pelo agendamento (o CDC levaria 0,25 a 0,87 s).
- O CDC custa 1,9 GB de RAM em serviços (Kafka e Kafka Connect) quando está ligado.
- Parar só os containers do CDC deixa o slot segurando WAL até o limite de 2 GB; desligar exige `scripts/cdc.sh remover`. Religar com `scripts/cdc.sh registrar` refaz o snapshot inicial.
- Os tópicos não têm retenção por tempo, então crescem a cada recarga (378 MB depois de 3 cargas) até alguém os apagar.

**O que se torna irreversível:**

Nada no dado: o lago é regerado do banco a qualquer momento. O que fica fixado é o contrato de idempotência do lago em lote (substituição inteira a cada carga). Uma carga incremental no futuro precisaria de chave estável entre publicações da fonte, o que a recarga inteira dispensa.

Se o OLTP passar a receber escrita contínua fora do pipeline, por exemplo de uma aplicação de secretaria, a conta da latência muda e o CDC passa a ser o caminho principal. Os números acima precisam ser medidos de novo nesse cenário.

## Gatilho de revisão

- **O OLTP (`silver` 3NF) passar a receber escrita contínua fora do pipeline mensal** (ex.: secretaria ou sistema transacional gravando correções linha a linha, exigindo latência < 1 hora até o lago).
  - *Estado no semestre (até 24/11/2026):* **Não disparou — decisão mantida.** O pipeline mensal continua sendo o único escritor da Silver 3NF; o papel `secretaria_campus` (E4, PR #84) é somente leitura.
- **A fonte pública (API CKAN da UnB) passar a publicar com frequência diária/contínua ou o SLA de frescor do painel cair abaixo de 24 horas** (hoje 35 dias, `docs/frescor_sla.md`).
  - *Estado no semestre (até 24/11/2026):* **Não disparou — decisão mantida.** A publicação da fonte segue mensal/semestral e o SLA formalizado na E3 (Semana 13) é de 35 dias (0,0/35 dias na carga de 11/2026).
- **Retenção de WAL no slot de replicação ultrapassar 50% de `max_slot_wal_keep_size` (> 1 GB) em operação recorrente, ou o crescimento dos tópicos Kafka exigir retenção finita/compactação ativa.**
  - *Estado no semestre (até 24/11/2026):* **Não disparou em produção — decisão mantida.** O CDC permanece opcional no profile `cdc` do `docker-compose.yml` (fora do CI e do cron mensal); nos ensaios da Semana 09 o pico de WAL foi de 239 MB e o slot é removido com `scripts/cdc.sh remover`.
- **Recarga completa da Silver 3NF + export do lago ultrapassar 10 minutos**, tornando a substituição integral (`TRUNCATE` + `COPY` + `overwrite`) inviável na janela do job.
  - *Estado no semestre (até 24/11/2026):* **Não disparou — decisão mantida.** A carga completa até a Silver 3NF leva ~46 s e o export do lago leva ~0,9 s.
