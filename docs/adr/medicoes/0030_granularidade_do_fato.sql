-- Medição dos níveis de grão do fato de retenção (ADR 0030, Decisão 2).
-- Coortes maduras (ingresso até o último ano da base menos 8), k-anonimato com k = 5 (ADR 0005).
--   docker compose exec -T db psql -U observatorio -d observatorio < docs/adr/medicoes/0030_granularidade_do_fato.sql
CREATE TEMP TABLE base AS
SELECT e.nome_curso_canonico AS curso, m.ano_ingresso, m.semestre_ingresso, m.tipo_saida_grupo, m.ano_saida, m.semestre_saida
FROM silver.movimentacoes_vinculos m
JOIN silver.estruturas_curriculares e USING (id_estrutura)
WHERE m.ano_ingresso <= (SELECT max(ano_ingresso) - 8 FROM silver.movimentacoes_vinculos);

CREATE TEMP TABLE g_vinculo AS SELECT * FROM base;
CREATE TEMP TABLE g_curso AS SELECT curso, count(*) AS n FROM base GROUP BY 1;
CREATE TEMP TABLE g_coorte AS SELECT curso, ano_ingresso, count(*) AS n FROM base GROUP BY 1, 2;
CREATE TEMP TABLE g_saida AS
SELECT curso, ano_ingresso, semestre_ingresso, tipo_saida_grupo, ano_saida, semestre_saida, count(*) AS n
FROM base GROUP BY 1, 2, 3, 4, 5, 6;

SELECT grao, linhas, abaixo_de_k,
       round(100.0 * abaixo_de_k / linhas, 1) AS pct_grupos_suprimidos,
       vinculos_perdidos,
       round(100.0 * vinculos_perdidos / total, 1) AS pct_vinculos_perdidos,
       pg_size_pretty(tamanho) AS tamanho
FROM (
    SELECT 'vínculo' AS grao, count(*) AS linhas, count(*) AS abaixo_de_k, count(*) AS vinculos_perdidos,
           count(*) AS total, pg_total_relation_size('g_vinculo') AS tamanho
    FROM g_vinculo
    UNION ALL
    SELECT 'curso', count(*), count(*) FILTER (WHERE n < 5), coalesce(sum(n) FILTER (WHERE n < 5), 0), sum(n),
           pg_total_relation_size('g_curso')
    FROM g_curso
    UNION ALL
    SELECT 'curso x coorte', count(*), count(*) FILTER (WHERE n < 5), coalesce(sum(n) FILTER (WHERE n < 5), 0), sum(n),
           pg_total_relation_size('g_coorte')
    FROM g_coorte
    UNION ALL
    SELECT 'curso x coorte x desfecho x semestre de saída', count(*), count(*) FILTER (WHERE n < 5),
           coalesce(sum(n) FILTER (WHERE n < 5), 0), sum(n), pg_total_relation_size('g_saida')
    FROM g_saida
) t;
