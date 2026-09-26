# ADR 0012: SIGAA como fonte principal, unido ao SIGRA

- **Status:** Aceita
- **Data:** 2026-09-26

## Contexto

O projeto usava só o SIGRA (Matrícula Web), o sistema legado. Ao comparar as bases, viu-se que elas são uma partição: o SIGRA tem apenas vínculos encerrados até 2020/1; o SIGAA tem os ativos na migração e os posteriores (extrato de 07/2024). Os pseudônimos das duas não se ligam.

## Decisão

Unir as duas em `silver.discentes_graduacao`, com a coluna `fonte` (SIGRA/SIGAA). Não há deduplicação porque não há sobreposição. Migração `0007_sigaa.sql`.

## Consequências

152.680 vínculos, todos casados com a estrutura curricular. Os dois sistemas diferem em granularidade (ver [ADR 0013](0013-evasao-saida-sem-diploma.md) e [ADR 0015](0015-semestre-de-saida-estimado.md)).
