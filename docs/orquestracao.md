# Orquestração em Dagster

O pipeline roda como um grafo de assets do Dagster (`orquestracao/definicoes.py`), conforme o ADR 0030. Cada etapa chama o mesmo script de `src/` que o `scripts/rodar_pipeline.sh` chama: a lógica não mudou de lugar. O Dagster acrescenta três coisas que a sequência em shell não tinha: as dependências explícitas, o retry de cada etapa e o backfill por partição.

## O grafo

**O grafo do Dagster é a fonte da verdade da ordem das etapas**: é ele que roda no agendamento mensal e no CI. O `scripts/rodar_pipeline.sh` continua existindo para o Docker e para quem roda sem o Dagster. Como os dois listam as etapas, `tests/test_unit_orquestracao.py` exige que chamem exatamente os mesmos scripts. Etapa nova entra nos dois, ou o teste falha.

```text
migracoes ─┬─ bronze_ckan ─┐
           ├─ bronze_inep ─┼─ silver ─┬─ gold_tabular ─┬─ star_schema ─┬─ view_painel ─────────┐
           └─ bronze_cnpq ─┘          │                 │  (10 tabelas: │                       │
                                      ├─ auditoria ─────┤   silver 3NF  ├─ camadas_dbt ─ dicionario ─┤
                                      └─ privacidade ───┘   e gold)     │  (12 modelos e         │
                                                                        │   1 snapshot)          │
                                                                        ├─ lago ─────────────────┼─ supabase
                                                                        └─ lago_vinculos_por_quinquenio
                                                                           (partições; backfill)  │
                                         gold_tabular ── vetorizacao ───────────────────────────┘
```

- **`star_schema`** é um asset múltiplo: declara as 10 tabelas que `povoar_dimensional.py` grava numa transação (Silver 3NF e o star schema da gold).
- **Os 12 modelos e o snapshot do dbt** entram um a um, pelo `dagster-dbt`. As fontes do dbt têm as mesmas chaves das tabelas do `star_schema` (`silver/movimentacoes_vinculos`, `gold/dim_curso`, ...), e é isso que faz o dbt rodar só depois dele. Os testes do dbt aparecem como checagens dos assets.
- **Uma etapa por vez** (`in_process_executor`): o pipeline usa um banco só, e as etapas pesadas disputariam memória no runner.
- **Etapa que falha de vez** impede as que dependem dela. As que não dependem dela seguem.

| Job | O que roda |
|---|---|
| `pipeline_mensal` | Todas as etapas, do portal ao Supabase |
| `backfill_lago` | `lago_vinculos_por_quinquenio`, por partição |

## Retry

| Política | Onde | Novas tentativas e espera |
|---|---|---|
| `RETRY_BANCO` | Etapas que só dependem do banco | 3, esperando 10, 30 e 70 s entre uma tentativa e a seguinte |
| `RETRY_PORTAL` | Ingestão (CKAN, INEP, CNPq) e Supabase | 3, esperando 30, 90 e 210 s entre uma tentativa e a seguinte |

As esperas não são acumuladas: a 4ª tentativa começa 110 s (10 + 30 + 70) depois da 1ª falha. Uma etapa que passa de 1 h rodando é interrompida e conta como falha, e o retry assume.

O INEP e o CNPq continuam tolerados como no `rodar_pipeline.sh`: se falharem nas 4 tentativas, a etapa registra um aviso e o pipeline segue com o que já está versionado.

## Agenda

- **No GitHub Actions:** o `atualiza-dados.yml` dispara `dagster job execute -m orquestracao -j pipeline_mensal` no dia 1 de cada mês, às 06:00 UTC. O projeto não tem servidor; o Dagster roda dentro do job.
- **Com o Dagster no ar** (`dagster dev`): a agenda `agenda_mensal` tem o mesmo horário e já vem ligada.
- **No CI** (`medalhao.yml`, a cada push): o grafo é validado e o backfill das janelas do lago roda sobre o lago recém-gravado.

## Backfill

`lago_vinculos_por_quinquenio` tem uma partição por quinquênio de ingresso, de 2000 até o atual. É a partição do lago Delta (ADR 0024). Materializar uma partição regrava aquela janela inteira, com o overwrite com predicado do ADR 0026. Um intervalo de partições vira uma execução só (`BackfillPolicy.single_run`).

```bash
dagster asset materialize -m orquestracao --select lago_vinculos_por_quinquenio --partition-range 2000...2025   # hoje; INTERVALO_BACKFILL dá o atual
```

## Demonstrações

Todas rodaram no PostgreSQL local, com o pipeline carregado. Os logs, filtrados aos eventos de etapa, estão em [`evidencias/`](orquestracao/evidencias/).

| # | O que foi feito | O que aconteceu | Evidência |
|---|---|---|---|
| 1 | **Dependência derrubada de propósito:** `docker compose stop db`, o `star_schema` disparado, e o banco religado 25 s depois | O `star_schema` falhou com `Connection refused`, foi repetido depois de 10 s e de 30 s, e passou na 3ª tentativa, com o banco de volta. A `view_painel` só rodou depois dele | [01_retry_banco_fora.txt](orquestracao/evidencias/01_retry_banco_fora.txt) |
| 2 | **Falha definitiva:** o banco apontado para uma porta sem servidor | As 4 tentativas falharam (esperas de 10, 30 e 70 s), o run terminou com código 1, e a `view_painel` não rodou ("Dependencies for step view_painel failed… Not executing"). A view do painel ficou com a última versão boa | [02_falha_definitiva.txt](orquestracao/evidencias/02_falha_definitiva.txt) |
| 3 | **Backfill de verdade:** numa cópia do lago, a janela de 2015 foi apagada (56.600 vínculos), e o backfill de 2000 a 2025 rodou duas vezes | A 1ª execução restaurou a janela: o lago voltou a 152.680 vínculos e 3 arquivos. A 2ª deu o mesmo resultado, sem duplicar nada. As 6 partições ficaram registradas como materializadas | [03_backfill_lago.txt](orquestracao/evidencias/03_backfill_lago.txt) |
| 4 | **Job completo:** `dagster job execute -m orquestracao -j pipeline_mensal` | 15 etapas, todas com sucesso, em 1 min 3 s, cada uma depois das que ela depende | [04_pipeline_mensal.txt](orquestracao/evidencias/04_pipeline_mensal.txt) |

## Como rodar

```bash
pip install -r requirements-orquestracao.txt     # dagster, dagster-dbt e o dbt
docker compose up -d db
dagster dev -m orquestracao                       # UI em http://localhost:3000: grafo, runs, backfills
dagster job execute -m orquestracao -j pipeline_mensal
```

Para reproduzir a demonstração 1: rode `docker compose stop db`; em outro terminal, rode `dagster asset materialize -m orquestracao --select '(group:gold and not key:gold_tabular) or key:view_painel'`; depois de uns 20 s, rode `docker compose start db`.

Para o backfill não tocar o lago de verdade, aponte `LAGO_DIR` para uma cópia.
