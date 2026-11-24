-- ============================================================================
-- 0028: faixas de tempo de formatura que não se sobrepõem
--
-- As colunas formados_*_pct (migração 0004) são cumulativas: "tempo ideal" (<= ideal) inclui quem
-- fechou no mínimo, e "limite" (>= máximo) inclui parte de "acima do ideal". Somadas passam de 100%,
-- o que engana em gráfico de distribuição. As colunas faixa_*_pct abaixo dividem os formados com
-- permanência calculável em quatro faixas exclusivas, pela matriz curricular do curso:
--
--   MINIMO  permanência <= semestre mínimo
--   IDEAL   mínimo < permanência <= semestre ideal
--   ACIMA   ideal < permanência < semestre máximo
--   LIMITE  permanência >= semestre máximo (prazo de jubilamento)
--
-- Quando o máximo coincide com o ideal (ex.: Arquivologia), quem fechou nesse semestre é LIMITE: o
-- limite prevalece. As colunas cumulativas continuam como estavam (IRC e mart dbt dependem delas).
-- ============================================================================

CREATE OR REPLACE FUNCTION gold.faixa_tempo(permanencia numeric, minimo numeric, ideal numeric, maximo numeric)
RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    SELECT CASE
        WHEN permanencia IS NULL THEN NULL
        WHEN permanencia >= maximo THEN 'LIMITE'
        WHEN permanencia <= minimo THEN 'MINIMO'
        WHEN permanencia <= ideal THEN 'IDEAL'
        ELSE 'ACIMA'
    END
$$;
COMMENT ON FUNCTION gold.faixa_tempo(numeric, numeric, numeric, numeric) IS
  'Faixa de tempo de formatura (MINIMO, IDEAL, ACIMA ou LIMITE) de uma permanência em semestres, pelos prazos da matriz. As faixas não se sobrepõem; o limite prevalece sobre as demais.';

ALTER TABLE gold.retencao_cursos_unb
  ADD COLUMN IF NOT EXISTS faixa_minimo_pct NUMERIC(5,2),
  ADD COLUMN IF NOT EXISTS faixa_ideal_pct  NUMERIC(5,2),
  ADD COLUMN IF NOT EXISTS faixa_acima_pct  NUMERIC(5,2),
  ADD COLUMN IF NOT EXISTS faixa_limite_pct NUMERIC(5,2);
ALTER TABLE gold.retencao_cursos_coorte
  ADD COLUMN IF NOT EXISTS faixa_minimo_pct NUMERIC(5,2),
  ADD COLUMN IF NOT EXISTS faixa_ideal_pct  NUMERIC(5,2),
  ADD COLUMN IF NOT EXISTS faixa_acima_pct  NUMERIC(5,2),
  ADD COLUMN IF NOT EXISTS faixa_limite_pct NUMERIC(5,2);

COMMENT ON COLUMN gold.retencao_cursos_unb.faixa_minimo_pct IS '% dos formados com permanência calculável que concluíram em até o semestre mínimo da matriz. Faixas exclusivas: as quatro faixa_*_pct somam 100.';
COMMENT ON COLUMN gold.retencao_cursos_unb.faixa_ideal_pct  IS '% dos formados entre o semestre mínimo (exclusive) e o ideal (inclusive).';
COMMENT ON COLUMN gold.retencao_cursos_unb.faixa_acima_pct  IS '% dos formados acima do ideal e abaixo do semestre máximo.';
COMMENT ON COLUMN gold.retencao_cursos_unb.faixa_limite_pct IS '% dos formados no semestre máximo da matriz (limite de jubilamento) ou depois.';
COMMENT ON COLUMN gold.retencao_cursos_coorte.faixa_minimo_pct IS 'Como em gold.retencao_cursos_unb.faixa_minimo_pct, só para a coorte.';
COMMENT ON COLUMN gold.retencao_cursos_coorte.faixa_ideal_pct  IS 'Como em gold.retencao_cursos_unb.faixa_ideal_pct, só para a coorte.';
COMMENT ON COLUMN gold.retencao_cursos_coorte.faixa_acima_pct  IS 'Como em gold.retencao_cursos_unb.faixa_acima_pct, só para a coorte.';
COMMENT ON COLUMN gold.retencao_cursos_coorte.faixa_limite_pct IS 'Como em gold.retencao_cursos_unb.faixa_limite_pct, só para a coorte.';

CREATE OR REPLACE PROCEDURE gold.atualizar_retencao_coorte(p_anos_maturacao integer)
LANGUAGE plpgsql
AS $$
BEGIN
    TRUNCATE gold.retencao_cursos_coorte;
    INSERT INTO gold.retencao_cursos_coorte (
        curso, ano_ingresso, coorte_madura, semestre_ideal_previsto, total_discentes_registrados, total_formados,
        total_evadidos_desligados, total_ainda_ativos, taxa_formatura_pct, taxa_evasao_pct,
        formados_tempo_minimo_pct, formados_tempo_ideal_pct, formados_acima_ideal_pct, formados_limite_maximo_pct,
        tempo_medio_real_semestres, faixa_minimo_pct, faixa_ideal_pct, faixa_acima_pct, faixa_limite_pct)
    WITH corte AS (
        SELECT max(ano_ingresso) - p_anos_maturacao AS ano FROM silver.v_vinculo_estrutura
    ), agrupado AS (
        SELECT curso, ano_ingresso,
               count(*) AS total,
               count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA') AS formados,
               count(*) FILTER (WHERE tipo_saida_grupo = 'EVASAO') AS evadidos,
               count(*) FILTER (WHERE tipo_saida_grupo = 'ATIVO') AS ativos,
               count(permanencia) FILTER (WHERE tipo_saida_grupo = 'FORMATURA') AS com_prazo,
               count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA' AND permanencia <= semestre_conclusao_minimo) AS no_minimo,
               count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA' AND permanencia <= semestre_conclusao_ideal) AS no_ideal,
               count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA' AND permanencia > semestre_conclusao_ideal) AS acima_ideal,
               count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA' AND permanencia >= semestre_conclusao_maximo) AS no_maximo,
               (avg(permanencia::numeric) FILTER (WHERE tipo_saida_grupo = 'FORMATURA'))::double precision AS media,
               count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA' AND f = 'MINIMO') AS f_minimo,
               count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA' AND f = 'IDEAL') AS f_ideal,
               count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA' AND f = 'ACIMA') AS f_acima,
               count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA' AND f = 'LIMITE') AS f_limite,
               min(semestre_conclusao_ideal) AS sem_ideal
        FROM (SELECT *, gold.faixa_tempo(permanencia, semestre_conclusao_minimo, semestre_conclusao_ideal,
                                         semestre_conclusao_maximo) AS f
              FROM silver.v_vinculo_estrutura) v
        WHERE semestre_conclusao_ideal IS NOT NULL
        GROUP BY curso, ano_ingresso
        HAVING count(*) >= 5
    )
    SELECT a.curso, a.ano_ingresso, a.ano_ingresso <= (SELECT ano FROM corte), a.sem_ideal,
           a.total, a.formados, a.evadidos, a.ativos,
           gold.arredondar(a.formados::double precision / a.total * 100, 2),
           gold.arredondar(a.evadidos::double precision / a.total * 100, 2),
           CASE WHEN a.com_prazo > 0 THEN gold.arredondar(a.no_minimo::double precision / a.com_prazo * 100, 2) ELSE 0 END,
           CASE WHEN a.com_prazo > 0 THEN gold.arredondar(a.no_ideal::double precision / a.com_prazo * 100, 2) ELSE 0 END,
           CASE WHEN a.com_prazo > 0 THEN gold.arredondar(a.acima_ideal::double precision / a.com_prazo * 100, 2) ELSE 0 END,
           CASE WHEN a.com_prazo > 0 THEN gold.arredondar(a.no_maximo::double precision / a.com_prazo * 100, 2) ELSE 0 END,
           gold.arredondar(a.media, 2),
           CASE WHEN a.com_prazo > 0 THEN gold.arredondar(a.f_minimo::double precision / a.com_prazo * 100, 2) ELSE 0 END,
           CASE WHEN a.com_prazo > 0 THEN gold.arredondar(a.f_ideal::double precision / a.com_prazo * 100, 2) ELSE 0 END,
           CASE WHEN a.com_prazo > 0 THEN gold.arredondar(a.f_acima::double precision / a.com_prazo * 100, 2) ELSE 0 END,
           CASE WHEN a.com_prazo > 0 THEN gold.arredondar(a.f_limite::double precision / a.com_prazo * 100, 2) ELSE 0 END
    FROM agrupado a;

    -- Faixas por curso (coortes maduras, mesma população de gold.retencao_cursos_unb).
    UPDATE gold.retencao_cursos_unb r
    SET faixa_minimo_pct = x.minimo, faixa_ideal_pct = x.ideal, faixa_acima_pct = x.acima, faixa_limite_pct = x.limite
    FROM (
        SELECT curso,
               CASE WHEN count(permanencia) FILTER (WHERE tipo_saida_grupo = 'FORMATURA') = 0 THEN 0 ELSE
                 gold.arredondar(count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA' AND f = 'MINIMO')::double precision
                   / count(permanencia) FILTER (WHERE tipo_saida_grupo = 'FORMATURA') * 100, 2) END AS minimo,
               CASE WHEN count(permanencia) FILTER (WHERE tipo_saida_grupo = 'FORMATURA') = 0 THEN 0 ELSE
                 gold.arredondar(count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA' AND f = 'IDEAL')::double precision
                   / count(permanencia) FILTER (WHERE tipo_saida_grupo = 'FORMATURA') * 100, 2) END AS ideal,
               CASE WHEN count(permanencia) FILTER (WHERE tipo_saida_grupo = 'FORMATURA') = 0 THEN 0 ELSE
                 gold.arredondar(count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA' AND f = 'ACIMA')::double precision
                   / count(permanencia) FILTER (WHERE tipo_saida_grupo = 'FORMATURA') * 100, 2) END AS acima,
               CASE WHEN count(permanencia) FILTER (WHERE tipo_saida_grupo = 'FORMATURA') = 0 THEN 0 ELSE
                 gold.arredondar(count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA' AND f = 'LIMITE')::double precision
                   / count(permanencia) FILTER (WHERE tipo_saida_grupo = 'FORMATURA') * 100, 2) END AS limite
        FROM (SELECT *, gold.faixa_tempo(permanencia, semestre_conclusao_minimo, semestre_conclusao_ideal,
                                         semestre_conclusao_maximo) AS f
              FROM silver.v_vinculo_estrutura) v
        WHERE semestre_conclusao_ideal IS NOT NULL
          AND ano_ingresso <= (SELECT max(ano_ingresso) - p_anos_maturacao FROM silver.v_vinculo_estrutura)
        GROUP BY curso
    ) x
    WHERE r.curso = x.curso;
END
$$;
COMMENT ON PROCEDURE gold.atualizar_retencao_coorte(integer) IS
  'Refaz gold.retencao_cursos_coorte (retenção por curso e ano de ingresso, todas as coortes) e preenche as faixas exclusivas de tempo de gold.retencao_cursos_unb. Roda depois de gold.atualizar_retencao.';
