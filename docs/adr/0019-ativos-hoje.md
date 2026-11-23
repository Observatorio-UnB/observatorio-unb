# ADR 0019: Tabela de alunos ativos hoje com contagem conservadora de atraso

- **Status:** Substituída em parte pela [ADR 0020](0020-lista-de-ativos-com-minimizacao.md) (a fonte passou a ser a lista de ativos de 2025/1)
- **Data:** 2026-09-26

## Contexto

A análise por coorte ([ADR 0014](0014-janela-maturacao-8-anos.md)) não mostra onde a retenção está se acumulando agora.

## Decisão

`gold.ativos_hoje_cursos_unb`: por curso, os vínculos ativos, formandos e trancados no extrato do SIGAA, e quantos já passaram do prazo ideal e do máximo. Semestres cursados = (ano do extrato − ano de ingresso) × 2, limite inferior, porque o SIGAA só publica o ano de ingresso. Cursos-tronco ficam de fora (o tronco de Engenharia tem prazo máximo menor que o ideal). k ≥ 5.

## Consequências

"Acima do prazo" nunca inclui quem ainda está dentro dele, mas pode deixar de fora quem estourou há 1 semestre. A referência é a data do extrato do portal (hoje 2024/1), não a data da execução.
