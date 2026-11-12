-- ============================================================================
-- 0027: retenção por coorte de ingresso
--
-- gold.retencao_cursos_unb junta só as coortes com 8 anos de acompanhamento. Esta tabela abre o
-- mesmo cálculo por ano de ingresso, com todas as coortes da Silver, para o painel mostrar uma
-- turma de cada vez. coorte_madura marca as que entram na tabela agregada; as outras ainda não
-- tiveram tempo de se formar (ou de ter a evasão registrada), e o painel avisa.
-- ============================================================================

CREATE TABLE IF NOT EXISTS gold.retencao_cursos_coorte (
  curso                     TEXT NOT NULL,
  ano_ingresso              INTEGER NOT NULL,
  coorte_madura             BOOLEAN NOT NULL,
  semestre_ideal_previsto   NUMERIC(4,1) NOT NULL,
  total_discentes_registrados INTEGER NOT NULL CHECK (total_discentes_registrados >= 5),
  total_formados            INTEGER NOT NULL CHECK (total_formados >= 0),
  total_evadidos_desligados INTEGER NOT NULL CHECK (total_evadidos_desligados >= 0),
  total_ainda_ativos        INTEGER NOT NULL CHECK (total_ainda_ativos >= 0),
  taxa_formatura_pct        NUMERIC(5,2) NOT NULL CHECK (taxa_formatura_pct BETWEEN 0 AND 100),
  taxa_evasao_pct           NUMERIC(5,2) NOT NULL CHECK (taxa_evasao_pct BETWEEN 0 AND 100),
  formados_tempo_minimo_pct NUMERIC(5,2) NOT NULL,
  formados_tempo_ideal_pct  NUMERIC(5,2) NOT NULL,
  formados_acima_ideal_pct  NUMERIC(5,2) NOT NULL,
  formados_limite_maximo_pct NUMERIC(5,2) NOT NULL,
  tempo_medio_real_semestres NUMERIC(5,2),
  PRIMARY KEY (curso, ano_ingresso)
);
COMMENT ON TABLE gold.retencao_cursos_coorte IS
  'Retenção, formatura e evasão por curso canônico e ano de ingresso, todas as coortes. Mesmas definições de gold.retencao_cursos_unb. Só entram coortes com 5 ou mais discentes (k-anonimato).';
COMMENT ON COLUMN gold.retencao_cursos_coorte.coorte_madura IS 'Verdadeiro se a coorte tem o acompanhamento mínimo (anos de maturação) e portanto entra em gold.retencao_cursos_unb.';
COMMENT ON COLUMN gold.retencao_cursos_coorte.formados_tempo_minimo_pct IS 'Percentual dos formados com prazo calculável que concluíram no tempo mínimo da matriz.';

CREATE OR REPLACE PROCEDURE gold.atualizar_retencao_coorte(p_anos_maturacao integer)
LANGUAGE plpgsql
AS $$
BEGIN
    TRUNCATE gold.retencao_cursos_coorte;
    INSERT INTO gold.retencao_cursos_coorte
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
               min(semestre_conclusao_ideal) AS sem_ideal
        FROM silver.v_vinculo_estrutura
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
           gold.arredondar(a.media, 2)
    FROM agrupado a;
END
$$;
COMMENT ON PROCEDURE gold.atualizar_retencao_coorte(integer) IS
  'Refaz gold.retencao_cursos_coorte: a retenção por curso e ano de ingresso, com todas as coortes.';
REVOKE EXECUTE ON PROCEDURE gold.atualizar_retencao_coorte(integer) FROM PUBLIC;

CREATE OR REPLACE PROCEDURE gold.atualizar_gold(
    p_anos_maturacao integer,
    p_cursos_tronco text[],
    p_min_matriculas_inep integer,  -- só o corte de matrículas entra no cálculo; o mínimo de 10 federais é de apresentação (painel)
    p_valor_bolsa_ic numeric)
LANGUAGE plpgsql
AS $$
DECLARE
    v_ha_discentes boolean := EXISTS (SELECT 1 FROM silver.discentes_graduacao);
BEGIN
    IF v_ha_discentes THEN
        CALL gold.atualizar_regras();
        CALL gold.atualizar_ativos_hoje(p_cursos_tronco);
        CALL gold.atualizar_retencao(p_anos_maturacao);
        CALL gold.atualizar_retencao_coorte(p_anos_maturacao);
        CALL gold.atualizar_inep_benchmark(p_min_matriculas_inep);
    ELSE
        RAISE WARNING 'silver.discentes_graduacao está vazia. Pulando a Gold de retenção.';
    END IF;

    CALL gold.atualizar_pibic_social();

    IF v_ha_discentes THEN
        CALL gold.atualizar_relatorios_retencao(p_anos_maturacao, p_cursos_tronco);
    END IF;
    CALL gold.atualizar_relatorio_pibic(p_valor_bolsa_ic);
END
$$;
COMMENT ON PROCEDURE gold.atualizar_gold(integer, text[], integer, numeric) IS
  'ELT da Gold: refaz retenção (agregada e por coorte), ativos, benchmark INEP, PIBIC e relatórios a partir da Silver, na transação de quem chama. Pré-requisito: gold.regras_harmonizacao_canonicas semeada.';
