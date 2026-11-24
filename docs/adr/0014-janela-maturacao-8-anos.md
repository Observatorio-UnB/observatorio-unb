# ADR 0014: Só entram na análise coortes com 8 anos de acompanhamento

- **Status:** Aceita
- **Data:** 2026-09-26

## Contexto

Com a união ao SIGAA, coortes recentes ainda têm muitos alunos cursando. Com janela de 6 anos, a coorte de 2018 tinha 34% de ativos, o que inflava a pontualidade (quem se forma no prazo aparece antes de quem atrasa).

## Decisão

`ANOS_MATURACAO_COORTE = 8`: a última coorte é o último ano de ingresso menos 8 (hoje, coortes 2010–2016). A Gold publica `total_ainda_ativos` para mostrar o que resta em aberto.

## Consequências

Ativos nas coortes analisadas caem para ~3%. O preço é olhar turmas de 8 a 14 anos atrás; o retrato do presente fica na tabela de ativos ([ADR 0019](0019-ativos-hoje.md)).

## Atualização (24/11/2026) — Exploração interativa de coortes no painel

O painel passou a oferecer um seletor global de intervalo de `ano_ingresso` (a partir de `gold.retencao_cursos_coorte`) e um heatmap longitudinal para exploração pelo DEG. Para preservar integralmente esta decisão:

- O padrão oficial do painel e o ranking da E1 (`dbt_marts.painel_cursos_criticos`) permanecem ancorados exclusivamente nas coortes maduras (`2010–2016`), sem alteração de fórmula nem de recorte.
- O Simulador What-If e os cruzamentos de PIBIC/INEP permanecem travados nas coortes maduras oficiais.
- Sempre que o usuário amplia o seletor para anos posteriores ao corte de maturação (`> 2016`), o painel exibe aviso persistente de censura à direita, destaca a fronteira visual entre coortes maduras e imaturas no heatmap e calibra a escala de cor exclusivamente sobre as coortes maduras.
