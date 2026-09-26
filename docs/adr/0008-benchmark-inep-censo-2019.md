# ADR 0008: Benchmark nacional pelo Censo da Educação Superior 2019

- **Status:** Aceita
- **Data:** 2026-09-24

## Contexto

Nenhuma base da UnB responde se a UnB perde mais alunos que as outras federais no mesmo curso.

## Decisão

Usar os microdados do Censo (INEP), recortados para cursos presenciais de universidades federais, com ano-base **2019**. Só entram cursos com pelo menos 50 matrículas e 10 federais comparáveis. O Censo 2023 foi descartado porque o trancamento declarado pela UnB cai de 8,4% para 1,0% enquanto o nacional sobe, sinal de mudança de critério de preenchimento. Detalhes em [fonte_inep_censo_superior.md](../fonte_inep_censo_superior.md).

## Consequências

Comparação pelo nome do curso, numa fotografia de um ano, e com taxas que medem outra coisa que a evasão por coorte. O servidor do INEP cai com frequência; o CI segue com o CSV já versionado.
