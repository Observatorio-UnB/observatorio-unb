# ADR 0004: Cursos com bacharelado e licenciatura sob o mesmo nome ficam como MISTO

- **Status:** Aceita
- **Data:** 2026-09-09

## Contexto

Química, Física, Letras e outros têm as duas ofertas no catálogo, mas nenhuma fonte pública liga o aluno ao grau. Separar pelo código de opção isolou, em Física, um subgrupo sem nenhum formado, sinal de atribuição errada.

## Decisão

Esses cursos ficam numa linha só na Gold, com `categoria_grau = MISTO`, em vez de assumir um grau.

## Consequências

Nenhum aluno é atribuído ao grau errado. Em troca, as comparações bacharelado × licenciatura deixam esses cursos de fora.
