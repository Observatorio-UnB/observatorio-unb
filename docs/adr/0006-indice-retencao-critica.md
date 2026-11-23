# ADR 0006: Índice de Retenção Crítica (IRC) com peso maior para evasão

- **Status:** Aceita
- **Data:** 2026-08-31

## Contexto

O DEG precisava de uma ordenação única de cursos que combinasse atraso e evasão.

## Decisão

IRC = (0,3 × atraso normalizado + 0,7 × evasão normalizada) × 100. A normalização min-max satura nos percentis 5 e 95, para que um curso extremo não comprima a escala. A classificação é por quartis.

## Consequências

Evasão pesa mais porque perder o aluno é pior que ele se formar devagar. Os pesos são uma escolha de valor, não estatística, e estão documentados no painel.

## Corte de amostra na fila de intervenção

A resposta da E1 considera só cursos com 30 ou mais ingressantes: com menos que isso o IRC oscila muito e um curso pequeno lideraria a fila por acaso. A tabela completa continua mostrando todos os cursos. A regra vive no mart `painel_cursos_criticos` (coluna `na_fila_de_intervencao`); o painel usa a mesma constante (`N_MIN_RANKING` em `src/dashboard/app.py`).
