# ADR 0014: Só entram na análise coortes com 8 anos de acompanhamento

- **Status:** Aceita
- **Data:** 2026-09-26

## Contexto

Com a união ao SIGAA, coortes recentes ainda têm muitos alunos cursando. Com janela de 6 anos, a coorte de 2018 tinha 34% de ativos, o que inflava a pontualidade (quem se forma no prazo aparece antes de quem atrasa).

## Decisão

`ANOS_MATURACAO_COORTE = 8`: a última coorte é o último ano de ingresso menos 8 (hoje, coortes 2010–2016). A Gold publica `total_ainda_ativos` para mostrar o que resta em aberto.

## Consequências

Ativos nas coortes analisadas caem para ~3%. O preço é olhar turmas de 8 a 14 anos atrás; o retrato do presente fica na tabela de ativos ([ADR 0019](0019-ativos-hoje.md)).
