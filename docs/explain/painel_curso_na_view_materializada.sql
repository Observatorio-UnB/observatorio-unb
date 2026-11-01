-- Linha de um curso na view do painel (gold.mv_dashboard_executivo, migração 0013), pela chave
-- do índice único idx_mov_executivo_sk. É a leitura da Visão Executiva, já agregada na carga.
--
-- Reproduzir: docker compose exec -T db psql -U observatorio -d observatorio -f - < docs/explain/painel_curso_na_view_materializada.sql
-- A consulta roda duas vezes; o plano versionado é o da segunda, com o cache quente.
EXPLAIN (ANALYZE, BUFFERS)
SELECT nome_curso, campus, total_ingressantes, taxa_formatura_pct, taxa_evasao_pct
FROM gold.mv_dashboard_executivo
WHERE sk_curso = (SELECT sk_curso FROM gold.dim_curso WHERE nome_curso = 'CIENCIA DA COMPUTACAO')
  AND campus = 'DARCY RIBEIRO';
