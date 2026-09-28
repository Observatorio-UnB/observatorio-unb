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
