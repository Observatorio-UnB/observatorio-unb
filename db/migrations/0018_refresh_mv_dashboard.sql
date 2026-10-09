-- ============================================================================
-- Migração 0018: Procedure de atualização da gold.mv_dashboard_executivo
--
-- Centraliza o REFRESH MATERIALIZED VIEW CONCURRENTLY, chamado ao fim da carga do Star Schema
-- (src/db/povoar_dimensional.py) e da sincronização com o Supabase (src/db/sincronizar_supabase.py).
--
-- Com gold.fato_retencao_curso vazia, a procedure recusa o refresh: a view esvaziaria e o painel
-- passaria a servir uma tela em branco. Mantém a última versão boa até a carga ser refeita.
-- ============================================================================

CREATE OR REPLACE PROCEDURE gold.atualizar_mv_dashboard_executivo()
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM gold.fato_retencao_curso) THEN
        RAISE EXCEPTION 'gold.fato_retencao_curso vazia: refresh da gold.mv_dashboard_executivo cancelado'
            USING HINT = 'Refaça a carga da Silver 3NF e do Star Schema (src/db/povoar_dimensional.py).';
    END IF;

    -- CONCURRENTLY exige o índice único idx_mv_executivo_sk (0013) e não bloqueia leituras.
    REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_dashboard_executivo;
END
$$;

COMMENT ON PROCEDURE gold.atualizar_mv_dashboard_executivo() IS
  'REFRESH CONCURRENTLY da gold.mv_dashboard_executivo; recusa se gold.fato_retencao_curso estiver vazia.';
