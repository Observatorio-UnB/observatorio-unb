-- ============================================================================
-- Migração 0019: Provisionamento automático de partições de silver.movimentacoes_vinculos
--
-- As partições de 0011 cobrem 2000 a 2034. A função abaixo cria partições por quinquênio
-- (2035-2039, 2040-2044, ...) até ano_referencia + anos_a_frente, antes que os ingressos desses
-- anos caiam na partição default. É chamada por src/db/povoar_silver_3nf.py a cada carga.
--
-- Idempotente: parte do maior limite superior entre as partições existentes, então rodar de novo
-- não cria nada. Linhas que já estejam na default dentro de um quinquênio novo são movidas para a
-- partição criada (sem isso o PostgreSQL recusa o CREATE TABLE ... PARTITION OF).
-- ============================================================================

CREATE OR REPLACE FUNCTION silver.provisionar_particoes_movimentacoes(
    ano_referencia INTEGER DEFAULT extract(year FROM current_date)::int,
    anos_a_frente  INTEGER DEFAULT 5
) RETURNS SETOF TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    limite INTEGER;
    alvo   INTEGER;
    nome   TEXT;
BEGIN
    -- Maior "TO (...)" entre as partições por intervalo; a default não tem limite.
    SELECT max(substring(pg_get_expr(c.relpartbound, c.oid) FROM 'TO \(''?(\d+)''?\)')::int)
      INTO limite
      FROM pg_inherits i
      JOIN pg_class c ON c.oid = i.inhrelid
     WHERE i.inhparent = 'silver.movimentacoes_vinculos'::regclass
       AND pg_get_expr(c.relpartbound, c.oid) <> 'DEFAULT';

    -- Cobre também anos que já tenham caído na default.
    SELECT greatest(ano_referencia + anos_a_frente, max(ano_ingresso))
      INTO alvo
      FROM silver.movimentacoes_p_default
     WHERE ano_ingresso >= limite;

    WHILE limite <= alvo LOOP
        nome := format('movimentacoes_p%s_%s', limite, limite + 4);

        CREATE TEMP TABLE _movidas ON COMMIT DROP AS
            SELECT * FROM silver.movimentacoes_p_default
             WHERE ano_ingresso >= limite AND ano_ingresso < limite + 5;
        DELETE FROM silver.movimentacoes_p_default
         WHERE ano_ingresso >= limite AND ano_ingresso < limite + 5;

        EXECUTE format('CREATE TABLE silver.%I PARTITION OF silver.movimentacoes_vinculos '
                       'FOR VALUES FROM (%s) TO (%s)', nome, limite, limite + 5);

        INSERT INTO silver.movimentacoes_vinculos OVERRIDING SYSTEM VALUE SELECT * FROM _movidas;
        DROP TABLE _movidas;

        RETURN NEXT 'silver.' || nome;
        limite := limite + 5;
    END LOOP;
END
$$;

COMMENT ON FUNCTION silver.provisionar_particoes_movimentacoes(INTEGER, INTEGER) IS
  'Cria partições por quinquênio de silver.movimentacoes_vinculos até ano_referencia + anos_a_frente; '
  'devolve as partições criadas.';
