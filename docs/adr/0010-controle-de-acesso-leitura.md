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

## Atualização (24/11/2026): recorte de linha e de coluna para quem precisa do vínculo

O gatilho desta revisão foi a consequência acima: "quem precisa da Silver usa o usuário dono do banco". Para quem precisa do vínculo individual, como a secretaria acadêmica de um campus, isso dava acesso a todos os campi e ao `id_discente`. Era o contrário de privilégio mínimo.

A migração 0028 cria o papel `secretaria_campus` com dois recortes em `silver.movimentacoes_vinculos`:

- **linha (RLS):** só os vínculos dos campi em que o usuário está lotado (`acesso.lotacao_campus`);
- **coluna:** todas as colunas menos `id_discente`.

O papel não lê `silver.discentes`, as partições nem a bronze. O dono do banco continua sem RLS, então pipeline, dbt e CDC não mudam. A política usa `= ANY(ARRAY(...))` para virar condição de índice: com `IN (subconsulta)`, custava 10 vezes o filtro escrito à mão. Demonstração, medições e testes em [docs/controle_de_acesso.md](../controle_de_acesso.md).

**Gatilho de revisão:** se uma secretaria precisar identificar o aluno (contato, por exemplo), o `id_discente` não deve ser liberado no papel. O caminho é uma view própria com base legal registrada no registro de privacidade.
