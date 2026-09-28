-- ============================================================================
-- Migração 0013: Views Materializadas para o Dashboard Gerencial (DEG/DAA)
--
-- Consolida joins dimensionais da Gold em uma View Materializada indexada com
-- suporte formal ao comando REFRESH MATERIALIZED VIEW CONCURRENTLY.
-- ============================================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS gold.mv_dashboard_executivo AS
SELECT 
    c.sk_curso,
    c.id_curso_origem,
    c.nome_curso,
    c.area_conhecimento,
    c.categoria_grau,
    camp.campus,
    f.total_ingressantes,
    f.total_formados,
    f.total_evadidos,
    f.total_ainda_ativos,
    f.taxa_formatura_pct,
    f.taxa_evasao_pct,
    f.formados_tempo_ideal_pct,
    f.atraso_medio_semestres,
    f.indice_retencao_critica,
    f.classificacao_retencao,
    COALESCE(fa.total_ativos, 0) AS ativos_hoje_total,
    COALESCE(fa.ativos_acima_prazo_ideal, 0) AS ativos_hoje_atrasados,
    COALESCE(fa.pct_acima_prazo_ideal, 0.0) AS pct_ativos_hoje_atrasados,
    now() AS gerado_em
FROM gold.fato_retencao_curso f
JOIN gold.dim_curso c ON f.sk_curso = c.sk_curso
JOIN gold.dim_campus camp ON f.sk_campus = camp.sk_campus
LEFT JOIN gold.fato_alunos_ativos fa ON c.sk_curso = fa.sk_curso
WHERE c.is_tronco_abi = false;

-- O índice exclusivo é requisito obrigatório do PostgreSQL para REFRESH CONCURRENTLY
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_executivo_sk ON gold.mv_dashboard_executivo (sk_curso, campus);

COMMENT ON MATERIALIZED VIEW gold.mv_dashboard_executivo IS
  'Visão Executiva do DEG pré-computada para renderização sub-milissegundo no Streamlit.';

-- Permissão para o papel de leitura
GRANT SELECT ON gold.mv_dashboard_executivo TO observatorio_leitura;
