# ADR 0003: Harmonização canônica dos nomes de curso

- **Status:** Aceita
- **Data:** 2026-09-09

## Contexto

O nome do curso na base de discentes não bate com o da estrutura curricular (ex.: `CONTROLE E AUTOMACAO` × `ENGENHARIA MECATRONICA - CONTROLE E AUTOMACAO`). Sem tratamento, parte dos alunos ficava sem prazo ideal e saía da análise.

## Decisão

Uma lista explícita de regras origem → destino (`CANONICAL_RULES_METADATA` em `src/pipeline/build_gold.py`), cada uma com categoria e justificativa, publicada em `data/gold/regras_harmonizacao_canonicas.json` com o número de vínculos afetados.

## Consequências

Casamento de 100% dos vínculos, sem descarte, e cada reclassificação é auditável no painel. Curso novo com grafia diferente exige regra nova; o relatório `relatorio_casamento_joins.json` lista os que não casaram.
