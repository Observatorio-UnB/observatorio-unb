# ADR 0022: Cursos-tronco (ABI) fora das visões por curso

- **Status:** Aceita
- **Data:** 2026-09-26

## Contexto

Engenharia e Educação Física – Ciclo Básico são Áreas Básicas de Ingresso: o aluno cursa os semestres comuns e depois escolhe uma habilitação (bacharelado ou licenciatura, no caso de Educação Física). Ninguém se forma no tronco, então taxas de formatura e prazos dele não têm sentido.

## Decisão

Os troncos ficam em `EXCLUDED_GENERIC_COURSES` (`src/pipeline/build_gold.py`) e são excluídos das tabelas por curso. A lista é publicada em `metricas_gerais_unb.json` (`cursos_tronco`), e o painel e a auditoria a leem de lá.

## Consequências

Um novo tronco exige uma linha no código. O painel publicado não depende de importar `src.*`.
