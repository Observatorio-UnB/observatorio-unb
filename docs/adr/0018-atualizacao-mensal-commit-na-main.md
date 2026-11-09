# ADR 0018: Atualização automática com commit direto na main

- **Status:** Aceita
- **Data:** 2026-09-26

## Contexto

Os dados publicados dependiam de alguém rodar o pipeline à mão.

## Decisão

O workflow `atualiza-dados.yml` roda no dia 1 de cada mês às 06:00 UTC (e sob demanda), separado do `medalhao.yml`, que fica como CI de push/PR e deploy do Pages. Ele roda `scripts/rodar_pipeline.sh` e os testes; se a Gold, os `metadata_*.json`, a série do valor da bolsa ou os relatórios gerados mudaram, o `github-actions[bot]` commita direto na `main` e dispara o `medalhao.yml` para republicar o painel. Execuções sem mudança não commitam.

A frequência começou semanal e passou a mensal: as fontes (listas do SIGAA, catálogo, tabela do CNPq) mudam no máximo a cada semestre.

## Consequências

Decisão provisória, para o momento do projeto: sem revisão humana antes de publicar, e falha se a `main` tiver proteção de branch. Caminhos futuros: abrir PR em vez de commit, ou carregar a Gold num banco hospedado (ex.: Supabase).

## Atualização (09/11/2026)

O fluxo mudou em três pontos:

- O workflow roda o job `pipeline_mensal` do Dagster (`dagster job execute -m orquestracao -j pipeline_mensal`), e não mais o `scripts/rodar_pipeline.sh` ([ADR 0030](0030-modelagem-analitica-e-ferramentas.md)).
- A gold vive só no banco (local e Supabase) e não é versionada. Os `metadata_*.json` deixaram de existir ([ADR 0002](0002-ingestao-api-ckan.md)). O bot versiona apenas `data/bronze/cnpq_valor_bolsa_ic.json`, `docs/relatorio_qualidade.md`, `docs/registro_privacidade_lgpd.md` e `docs/dicionario_dados_banco.md`.
- Quando algo muda, o `medalhao.yml` disparado em seguida refaz o export da gold a partir do banco e republica o painel.
