# ADR 0006: Índice de Retenção Crítica (IRC) com peso maior para evasão

- **Status:** Aceita
- **Data:** 2026-08-31

## Contexto

O DEG precisava de uma ordenação única de cursos que combinasse atraso e evasão.

## Decisão

IRC = (0,3 × atraso normalizado + 0,7 × evasão normalizada) × 100. A normalização min-max satura nos percentis 5 e 95, para que um curso extremo não comprima a escala. A classificação é por quartis.

## Consequências

Evasão pesa mais porque perder o aluno é pior que ele se formar devagar. Os pesos são uma escolha de valor, não estatística, e estão documentados no painel.
