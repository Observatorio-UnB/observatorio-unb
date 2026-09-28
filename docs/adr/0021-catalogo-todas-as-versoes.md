# ADR 0021: Catálogo de cursos com todas as versões, a mais recente valendo

- **Status:** Aceita (substitui a ADR 0016)
- **Data:** 2026-09-26

## Contexto

O catálogo fixo em 2022 (ADR 0016) não traz cursos novos, como Educação Física – Ciclo Básico (2024), e precisaria de troca manual a cada versão publicada. As versões novas, por outro lado, deixam de listar alguns códigos (ex.: 414162, um dos dois cadastros de Comunicação Social – Jornalismo em 2022; o curso segue com os códigos 414164 e 414165) e não trazem `unidade_responsavel`. Além disso, o turno e o campus de um nome com várias ofertas dependiam da ordem das linhas.

## Decisão

- A ingestão baixa e empilha todas as versões do pacote `cursos-de-graduacao` (padrão `^cursos?[-_](de-)?gradua\w*(-\d{2}-\d{4})?\.csv$`), com `arquivo_origem` e `publicado_em`.
- A Silver consolida um registro por `id_curso`: em cada campo vale a versão mais recente que o preenche. Curso ausente da última versão fica com `no_catalogo_vigente = false`.
- Nome de curso com oferta diurna e noturna recebe turno "DIURNO E NOTURNO"; com mais de um campus, "MULTICAMPUS" (mesma lógica do grau MISTO, ADR 0004).

## Consequências

Nova versão publicada entra sem mudança de código. Os 19 cursos DIURNO E NOTURNO saem da comparação noturno vs. diurno (GQ4), que antes usava um turno arbitrário para eles. Migração `0009_catalogo_todas_as_versoes.sql`.

## Adendo: prefixos de curso guarda-chuva

Comunicação Social e Ciências Sociais eram cursos guarda-chuva cujas habilitações viraram cursos próprios. As fontes usam os dois nomes para o mesmo curso (o catálogo tem 414164 "COMUNICAÇÃO SOCIAL - JORNALISMO" e 414165 "JORNALISMO"). `normalize_curso` (`src/pipeline/transform_silver.py`) remove os prefixos "COMUNICACAO SOCIAL - " e "CIENCIAS SOCIAIS - " em todas as fontes, e a Gold usa o nome atual: JORNALISMO, AUDIOVISUAL, PUBLICIDADE E PROPAGANDA, COMUNICACAO ORGANIZACIONAL, ANTROPOLOGIA e SOCIOLOGIA. Prefixos de habilitação que ainda definem o curso (Letras, Música, Design, Educação do Campo) ficam.
