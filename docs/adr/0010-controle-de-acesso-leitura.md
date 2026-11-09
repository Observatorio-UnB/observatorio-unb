# ADR 0010: Papel de leitura que só enxerga gold e busca (e os marts do dbt, desde a E3)

- **Status:** Aceita
- **Data:** 2026-09-24

## Contexto

Bronze e Silver no banco têm registro individual de discente.

## Decisão

Papel `observatorio_leitura` com `SELECT` apenas nos esquemas `gold` e `busca` (e privilégio padrão para tabelas futuras). Usuários de consulta herdam esse papel.

## Consequências

Consultas analíticas não têm como ler dado pessoal por engano. Quem precisa da Silver usa o usuário dono do banco.

## Atualização (09/11/2026)

Desde a E3, o papel `observatorio_leitura` também lê o esquema `dbt_marts`, a camada de consumo do dbt. O grant vem do próprio projeto dbt (`+grants` e `on-run-end` em `transform/dbt_project.yml`). Os marts são agregados com k ≥ 5, como a gold. Os esquemas `dbt_staging`, `dbt_intermediate` e `dbt_snapshots` ficam fora do papel: os dois primeiros carregam vínculos individuais, como a silver ([ADR 0029](0029-transformacoes-em-dbt.md)).
