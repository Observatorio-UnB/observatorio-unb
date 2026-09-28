# ADR 0015: Semestre de conclusão do SIGAA estimado pela data do diploma

- **Status:** Aceita
- **Data:** 2026-09-26

## Contexto

O SIGAA não publica o período de saída, só `data_registro_diploma`. Sem o semestre de saída não há tempo de formatura.

## Decisão

Regra calibrada no SIGRA, onde as duas informações existem: registro em jan–abr → (ano−1)/2; mai–out → ano/1; nov–dez → ano/2. A coluna `periodo_saida_estimado` marca as linhas estimadas.

## Consequências

Acerta 94,6% no SIGRA; no calendário deslocado da pandemia pode errar 1 semestre. Melhoria possível: tabela com as datas oficiais de fim de semestre da SAA.
