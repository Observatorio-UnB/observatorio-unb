# ADR 0016: Catálogo de cursos fixo na versão de 2022

- **Status:** Substituída pela ADR 0021
- **Data:** 2026-09-26

## Contexto

As versões de 03/2023 e 08/2024 de `curso_graduacao` removem cursos extintos (ex.: Comunicação Social – Jornalismo), o que quebrava a chave estrangeira da estrutura curricular, e reordenam ofertas, trocando turno e campus de cursos na Gold.

## Decisão

O padrão de ingestão fica fixo em `^curso_graduacao\.csv$`, a versão de 2022, que cobre os cursos das coortes analisadas.

## Consequências

Metadados estáveis. Cursos criados depois de 2022 não têm turno e campus do catálogo; revisar quando a análise passar a incluir coortes que entraram neles.
