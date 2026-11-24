# ADR 0001: Arquitetura medalhão (Bronze, Silver, Gold)

- **Status:** Aceita
- **Data:** 2026-08-31

## Contexto

Os CSVs do portal têm encoding, delimitador e grafia de cursos inconsistentes, e parte deles traz dado pessoal. Era preciso separar o dado bruto do dado limpo e do dado publicável.

## Decisão

Três camadas em `data/`: **Bronze** guarda o arquivo como veio do portal; **Silver** limpa, tipa e normaliza (um registro por vínculo); **Gold** agrega por curso e é a única camada publicada. Cada camada é regenerada do zero a cada execução (`scripts/rodar_pipeline.sh`).

## Consequências

Reprocessar é sempre seguro e o CI prova que o pipeline roda numa máquina limpa. Bronze e Silver ficam fora do git (`.gitignore`) por conterem dado pessoal. O custo é baixar e recalcular tudo a cada execução, o que hoje leva poucos minutos.

## Atualização (09/11/2026)

As três camadas continuam, mas saíram de `data/`: desde a migração 0016 cada uma é um esquema do PostgreSQL (`bronze`, `silver`, `gold`), gravado direto no banco e sem arquivo intermediário ([ADR 0009](0009-postgres-migracoes-contrato.md)). A Silver ganhou o modelo em 3NF, e a Gold, o Star Schema. A ordem das etapas agora é o grafo do Dagster ([ADR 0030](0030-modelagem-analitica-e-ferramentas.md)); o `scripts/rodar_pipeline.sh` ficou para o Docker e para quem roda sem o Dagster.

## Gatilhos de revisão

- **CSVs intermediários em `data/` causarem quebra de contrato, crescimento do repositório (> 30 MB versionados) ou exigirem integridade relacional (`PK`/`FK`/`CHECK`) na Silver.**
  - *Estado no semestre (até 24/11/2026):* **Disparou — decisão revista** (Semanas 06–07, migrações `0011` e `0016`, atualização de 09/11/2026). Os CSVs intermediários foram removidos (-30 MB no git) e as três camadas passaram a esquemas do PostgreSQL (`bronze`, `silver` em 3NF e `gold` em Star Schema), preservando o princípio medalhão.
- **Execução linear em shell (`scripts/rodar_pipeline.sh`) deixar de atender a retry por etapa, linhagem ou backfill por partição.**
  - *Estado no semestre (até 24/11/2026):* **Disparou — decisão revista** (Semana 13, PR #55, [ADR 0030](0030-modelagem-analitica-e-ferramentas.md)). A orquestração passou para o grafo de assets do Dagster (`orquestracao/definicoes.py`), mantendo `rodar_pipeline.sh` como fallback para Docker e execução sem Dagster.
- **Regeneração completa do zero ultrapassar 10 minutos no runner ou o volume crescer acima de 10× (hoje 152.680 vínculos), tornando o reprocessamento integral custoso.**
  - *Estado no semestre (até 24/11/2026):* **Não disparou — decisão mantida.** A carga SQL completa da fonte até a Silver 3NF e Star Schema leva ~46 s (Semana 07).
- **Exposição de dado pessoal ou célula com $k < 5$ na Gold ou em artefato publicado.**
  - *Estado no semestre (até 24/11/2026):* **Não disparou — decisão mantida.** Bronze e Silver permanecem fora do git e fora do Supabase; a fronteira de $k \ge 5$ passou a ser conferida por `src/db/reconciliar_supabase.py` ([ADR 0031](0031-escopo-disponibilizacao-online-supabase-lgpd.md)) e pelos testes do dbt ([ADR 0029](0029-transformacoes-em-dbt.md)).
