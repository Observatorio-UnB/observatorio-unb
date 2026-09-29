# ADR 0007: Painel em Streamlit publicado no GitHub Pages via stlite

- **Status:** Aceita
- **Data:** 2026-09-07

## Contexto

O projeto não tem servidor, e o painel precisava de um endereço público.

## Decisão

O `app.py` roda no navegador do visitante com stlite (Pyodide), servido pelo GitHub Pages. O job `deploy` do `medalhao.yml` monta `_site/` com o app, a Gold e os docs. A página de busca semântica, que exige o banco, só existe na execução local.

## Consequências

Custo zero de hospedagem e nenhum dado além da Gold sai do CI. A primeira carga no navegador é lenta, e só dependências puras em Python (ou empacotadas no Pyodide) funcionam no site.
