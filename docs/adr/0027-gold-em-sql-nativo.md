# ADR 0027: Agregações da gold em SQL nativo, sem Pandas nem Spark

- **Status:** Aceita
- **Data:** 2026-10-19

## Contexto

As agregações de retenção, evasão e fluxo discente eram calculadas em memória com Pandas em `src/pipeline/build_gold.py`, e a gold era gravada com `TRUNCATE` + `COPY`. As mesmas regras já existiam em SQL (`src/db/povoar_dimensional.py` recalculava retenção e IRC para o Star Schema), então qualquer mudança de regra pedia duas edições que podiam divergir.

Migrar para PySpark foi considerado e descartado: a silver tem 57 MB, o pipeline roda em um runner de CI e no Docker Compose, e o Spark traria JVM, tempo de inicialização e uma dependência a mais para um volume que o PostgreSQL agrega em menos de dois segundos. O `percentile_approx` do Spark também não reproduz o `quantile` do Pandas, e a paridade numérica era requisito.

## Decisão

Todo o cálculo da gold fica no banco (migração `0022_gold_sql_nativo.sql`):

- funções `gold.calcular_retencao`, `calcular_ativos_hoje`, `calcular_inep_benchmark` e `calcular_pibic_social`, que devolvem as linhas de cada tabela gold (`RETURNS SETOF` o tipo da tabela);
- funções `gold.relatorio_*`, que montam em `jsonb` os relatórios de `gold.relatorios`;
- views de apoio (`vw_vinculos_canonicos`, `vw_catalogo_por_nome`, `vw_area_por_curso`, `vw_oferta_por_curso`, `vw_pibic_planos`); as que têm registro individual são `security_invoker` e sem acesso para `observatorio_leitura`;
- procedure `gold.materializar_gold`, que trunca e recarrega as tabelas gold na transação de quem chama.

As tabelas gold continuam tabelas, porque o painel, a view materializada, o CDC e a sincronização com o Supabase dependem delas e dos seus CHECKs. O `build_gold.py` só carrega as regras de harmonização (`CANONICAL_RULES_METADATA` continua sendo a fonte), lê o valor da bolsa de IC do JSON do CNPq e chama a procedure, tudo numa transação. Os parâmetros (`ANOS_MATURACAO_COORTE`, cursos-tronco, corte do benchmark) seguem no Python e entram como argumentos.

Para manter a paridade, o SQL reproduz as três formas de arredondar do código antigo: `gold.arredondar_py` (`round` do Python sobre `int/int`), `gold.arredondar_np` (`Series.round` e `round` de `np.float64`) e `gold.quantil_linear` (interpolação do numpy). O `round` do `numeric` do PostgreSQL arredondaria 0,125 para 0,13 e 12,475 para 12,48 onde o Python dá 0,12 e 12,47.

## Consequências

- Uma regra da gold se muda em um lugar. O `fato_retencao_curso` do Star Schema ainda tem a própria versão do cálculo, sobre a Silver 3NF, e é o próximo candidato a reaproveitar `gold.calcular_retencao`.
- Alterar o esquema de uma tabela gold (nova coluna) exige reescrever a função `calcular_*` correspondente na mesma migração, porque ela devolve o tipo da tabela.
- Na reconciliação da migração, as cinco tabelas gold (retencao, ativos, benchmark INEP, PIBIC e regras) e os quatro relatórios JSON saíram idênticos aos do Pandas, célula a célula, com 152.680 vínculos. Os testes de `tests/test_gold_sql.py` cobrem as funções puras e as views de catálogo.
