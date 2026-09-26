# ADR 0020: Lista de ativos do SIGAA com minimização de colunas

- **Status:** Aceita
- **Data:** 2026-09-26

## Contexto

A tabela de ativos ([ADR 0019](0019-ativos-hoje.md)) usava o extrato `sigaa.csv` de 07/2024. O portal publica, no pacote *lista-de-discentes-de-graduacao-pos-graduacao-latu-sensu-mestrado-e-doutorado*, a lista `sigaa_ativos_2025_1.csv`: mais recente e com o **semestre** de ingresso, mas com nome, CPF parcial e nacionalidade, e por isso fora da ingestão ([ADR 0017](0017-arquivos-nominais-fora.md)).

A comparação das duas fontes mostrou que o status do extrato é defasado: a coorte de 2022 tinha 8.530 vínculos ATIVO em 07/2024 e 5.698 na lista de 2025/1; a de 2023, 8.935 contra 7.011, com só 525 cancelados no extrato. O SIGAA registra o cancelamento com atraso (ACHADO-11 do relatório de qualidade).

## Decisão

A ingestão baixa a lista de ativos mais recente (`^sigaa_ativos_\d{4}_\d\.csv$`) para a memória e grava só `grau`, `curso`, `ano_ingresso` e `periodo_ingresso` (`download_minimizado` em `src/ingestion/ckan_client.py`). Nome, CPF e nacionalidade nunca chegam ao disco, ao banco nem ao CI. Um teste confere que a Bronze tem exatamente essas colunas.

A Silver (`silver.sigaa_ativos`) fica com a graduação (grau preenchido e diferente de Mestrado/Doutorado; o lato sensu vem sem grau) e calcula os semestres cursados até o semestre de referência, tirado do nome do arquivo. A Gold `ativos_hoje_cursos_unb` passa a vir dessa lista. Migração `0008_ativos_hoje.sql`.

Os arquivos `SIGAA_Concluintes_*` continuam fora: as listas de 2024/1 (1.508 formados na graduação) e 2024/2 (1.009) são parciais perto dos 3 a 4 mil formados por semestre no SIGAA, e não acrescentam nada que o `sigaa.csv` não tenha.

## Consequências

- Referência 2025/1 em vez de 2024/1, e contagem exata de semestres cursados, sem o limite inferior da ADR 0019.
- A lista não separa formandos nem trancados; essas colunas saíram da Gold.
- 38 registros de graduação sem grau (Filosofia e Música) ficam de fora, por não se distinguirem do lato sensu.
- Quando a UnB publicar `sigaa_ativos_2025_2.csv`, a ingestão semanal pega sozinha ([ADR 0018](0018-atualizacao-semanal-commit-na-main.md)).

## Adendo: bolsistas de IC

A mesma minimização vale para `bolsistas-de-iniciacao-cientifica.csv`, que traz nome e matrícula do discente e nome do orientador. A ingestão grava só as colunas usadas pela análise (`DATASETS_CONFIG["pibic"]["colunas"]`); `download_minimizado` aceita o separador e o encoding de cada fonte. A silver deixou de ter a matrícula mascarada e o orientador, que nenhuma análise usava. Migração `0010_pibic.sql`.
