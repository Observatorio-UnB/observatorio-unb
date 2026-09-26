# ADR 0005: Privacidade: k-anonimato ≥ 5 na Gold e dado pessoal fora do que é publicado

- **Status:** Aceita
- **Data:** 2026-08-31 (revista em 2026-09-26)

## Contexto

As bases de discentes trazem nascimento, sexo, raça/cor e cota. A análise de `src/privacy/lgpd_check.py` mostrou que 89% dos registros do SIGRA e 66% do SIGAA são únicos nessa combinação (k = 1).

## Decisão

Só a Gold agregada é publicada, e só com grupos de 5 ou mais vínculos (`CHECK (total >= 5)` no banco). Bronze e Silver nunca saem da máquina que roda o pipeline nem do runner do CI. Os arquivos `SIGAA_Concluintes_*` e "SIGAA Ativos", que têm nome e CPF parcial, nem são baixados.

## Consequências

O painel público não permite reidentificação. Cursos pequenos somem da Gold. Um banco hospedado por terceiros deve receber só a Gold (`carregar.py --camadas gold`).
