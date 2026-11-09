# ADR 0002: Ingestão pela API CKAN, escolhendo o recurso pelo nome do arquivo

- **Status:** Aceita
- **Data:** 2026-08-31 (revista em 2026-09-26)

## Contexto

O dados.unb.br roda CKAN 2.11. Um mesmo pacote tem vários arquivos (por exemplo `sigra.csv`, `sigaa.csv` e `SIGAA_Concluintes_*`), e a UnB publica versões novas com outro nome. A primeira versão pegava o primeiro CSV do pacote.

## Decisão

`src/ingestion/ckan_client.py` consulta `package_show` e escolhe o recurso por uma regex sobre o nome do arquivo na URL (`resource_pattern`); entre os que casam, fica o de `last_modified` mais recente. Não há fallback para "primeiro CSV": sem casamento, a fonte falha. Os metadados de cada pacote vão para `data/bronze/metadata_*.json`, versionados no git.

## Consequências

Uma versão nova com o mesmo padrão de nome (ex.: `sigaa_2025_2.csv`) entra sozinha; um arquivo de outra natureza no pacote não é pego por engano. Os `metadata_*.json` servem de detector de mudança no portal (ver [ADR 0018](0018-atualizacao-mensal-commit-na-main.md)).

## Atualização (09/11/2026)

Os metadados de cada pacote não vão mais para `data/bronze/metadata_*.json`. Desde a migração 0016, a resposta do `package_show` fica em `bronze.ingestoes.metadados`, junto com o hash, o tamanho e o encoding de cada download (`src/ingestion/procedencia.py`). A data de publicação de cada arquivo processado sai desse registro: é ela que define a marca d'água do dado atrasado (`src/db/dado_atrasado.py`) e a carga que a verificação de frescor compara com o portal. A consulta ao portal em tempo real, para saber se saiu arquivo novo, é do `src/db/frescor.py --fonte` ([`docs/frescor_sla.md`](../frescor_sla.md)).
