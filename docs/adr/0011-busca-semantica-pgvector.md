# ADR 0011: Busca semântica com pgvector e embedding multilíngue local

- **Status:** Aceita
- **Data:** 2026-09-24

## Contexto

Planos de iniciação científica e a documentação são texto livre, e a busca por palavra-chave não achava temas próximos.

## Decisão

Embeddings com `paraphrase-multilingual-MiniLM-L12-v2` (384 dimensões) via fastembed, rodando local em CPU, guardados em pgvector com índice HNSW e comparados por cosseno. Os documentos são cursos da Gold, planos de IC (sem nome nem matrícula) e seções de `docs/`.

## Consequências

Nenhum dado vai para API externa. A busca acerta tema, mas não filtra por número ("evasão alta" mistura faixas); para atributo, o caminho é SQL ou o painel. No CI só cursos e documentação são vetorizados, por tempo.
