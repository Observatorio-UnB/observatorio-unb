# ADR 0023: Valor da bolsa IC por uma tabela de vigências lida do CNPq

- **Status:** Aceita
- **Data:** 2026-09-26

## Contexto

O investimento em PIBIC era estimado com R$ 400 × 12 até o ciclo 2022 e R$ 700 × 12 a partir de 2023, valores escritos no código. O reajuste vale desde fev/2023 (paga em março), no meio do ciclo 2022 (jul/2022 a jun/2023). O CNPq só publica a tabela de valores vigente. Os microdados de pagamentos (Base dos Dados, BigQuery) param em 2022 e trazem o nome do bolsista.

## Decisão

- `data/bronze/cnpq_valor_bolsa_ic.json` guarda as vigências (`vigente_desde` AAAA-MM, `valor_mensal`, `fonte`) e é versionado, como os `metadata_*.json`. O histórico (R$ 400 desde jul/2012, R$ 700 desde fev/2023) foi conferido nas cópias da página oficial no Internet Archive, citadas no campo `fonte`.
- `src/ingestion/cnpq_valor_bolsa.py` faz uma requisição à tabela oficial de valores de bolsas no país, lê o valor da Iniciação Científica e, se mudou, acrescenta uma linha valendo desde o mês da leitura.
- A Silver soma, mês a mês da vigência de cada bolsa remunerada (`inicio` a `fim`), o valor em vigor.

## Consequências

Um reajuste futuro entra sozinho, com atraso de até um mês (a frequência do `atualiza-dados.yml`); se a portaria fixar outra data de início, basta corrigir `vigente_desde` no JSON. O investimento considera só o valor da cota CNPq: bolsas pagas pela UnB ou pela FAP-DF com outro valor não são distinguidas no arquivo de bolsistas.
