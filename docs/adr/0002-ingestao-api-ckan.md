# ADR 0002: Ingestão pela API CKAN, escolhendo o recurso pelo nome do arquivo

- **Status:** Aceita
- **Data:** 2026-08-31 (revista em 2026-09-26)

## Contexto

O dados.unb.br roda CKAN 2.11. Um mesmo pacote tem vários arquivos (por exemplo `sigra.csv`, `sigaa.csv` e `SIGAA_Concluintes_*`), e a UnB publica versões novas com outro nome. A primeira versão pegava o primeiro CSV do pacote.

## Decisão

`src/ingestion/ckan_client.py` consulta `package_show` e escolhe o recurso por uma regex sobre o nome do arquivo na URL (`resource_pattern`); entre os que casam, fica o de `last_modified` mais recente. Não há fallback para "primeiro CSV": sem casamento, a fonte falha. Os metadados de cada pacote vão para `data/bronze/metadata_*.json`, versionados no git.

## Consequências

Uma versão nova com o mesmo padrão de nome (ex.: `sigaa_2025_2.csv`) entra sozinha; um arquivo de outra natureza no pacote não é pego por engano. Os `metadata_*.json` servem de detector de mudança no portal (ver [ADR 0018](0018-atualizacao-semanal-commit-na-main.md)).
