# ADR 0011: Busca semântica com pgvector e embedding multilíngue local

- **Status:** Aceita
- **Data:** 2026-09-24

## Contexto

Planos de iniciação científica e a documentação são texto livre, e a busca por palavra-chave não achava temas próximos.

## Decisão

Embeddings com `paraphrase-multilingual-MiniLM-L12-v2` (384 dimensões) via fastembed, rodando local em CPU, guardados em pgvector com índice HNSW e comparados por cosseno. Os documentos são cursos da Gold, planos de IC (sem nome nem matrícula) e seções de `docs/`.

## Consequências

Nenhum dado vai para API externa. A busca acerta tema, mas não filtra por número ("evasão alta" mistura faixas); para atributo, o caminho é SQL ou o painel. No CI só cursos e documentação são vetorizados, por tempo.

## Revisão de 2026-11-03: busca híbrida, limiar de evidência e documentação inteira

Um conjunto de 20 consultas com o documento esperado (`tests/test_banco_busca.py`) mostrou três falhas da busca só vetorial:

- **A documentação indexada era só a raiz de `docs/`:** 14 dos 54 `.md`, sem os ADRs nem `arquitetura/`. A documentação acertava 5 de 10 consultas no top 5.
- **Sigla, número e termo técnico se perdem no embedding:** "ADR 0028" não trazia o ADR 0028, e "SLA de frescor" não trazia `frescor_sla.md`.
- **A similaridade de cosseno não separa acerto de ruído:** os documentos esperados ficaram entre 0,29 e 0,81, e consultas sem sentido ("lorem ipsum dolor", "o rato roeu a roupa do rei de roma") chegaram a 0,53. Como a busca sempre devolvia os k mais próximos, a consulta sem sentido recebia 5 resultados.

**Decisão:**

- **Documentação inteira:** `docs/` com as subpastas e o `README.md`. Trechos de desenho em ASCII (menos de 40% de letras) ficam de fora. Os trechos são cortados em espaço, com 80 caracteres de sobreposição.
- **Busca híbrida** (migração 0026), com três listas combinadas por Reciprocal Rank Fusion:
  - a vetorial;
  - o texto completo em português (`tsvector` gerado), que exige ao menos metade dos termos da consulta;
  - o trigrama no título, em que o título que contém a consulta inteira vale como primeiro de mais uma lista.
- **Limiar por evidência:** o vetor sozinho só basta a partir de 0,55. Abaixo disso, o documento entra se a consulta tiver evidência de texto em algum documento; aí os vizinhos vetoriais a partir de 0,45 também entram.

**Medido nas 20 consultas:**
- recall@5 subiu de 14 para 18;
- o MRR, a média de 1/posição do documento esperado, subiu de 0,55 para 0,75;
- as 8 consultas sem sentido do teste voltam vazias;
- a busca leva de 10 a 80 ms depois do modelo carregado.

**Alternativas descartadas:**
- **Trigrama no conteúdo:** Seq Scan de 860 ms numa consulta comum.
- **Texto completo calculado na hora:** 280 ms.
- **Texto completo com qualquer termo:** "dolor" trazia "dolorosos" para "lorem ipsum dolor".

**O que se perde:**
- Uma consulta cujas palavras estão espalhadas por trechos diferentes e que fica abaixo de 0,55 no vetor volta vazia. Exemplo: "pergunta de gestão do decanato no challenge canvas", em que cada trecho do canvas tem um só dos termos.
- O teste acompanha esse caso como um dos 2 de 20 que faltam.

