-- ============================================================================
-- Migração 0022: agregações da Gold em SQL nativo (ELT dentro do PostgreSQL)
--
-- Até aqui src/pipeline/build_gold.py lia a Silver para o Pandas, agregava em memória e gravava a
-- Gold de volta. A regra de retenção existia duas vezes (Pandas e SQL_FATO_RETENCAO). Agora a
-- regra mora só no banco; o Python semeia gold.regras_harmonizacao_canonicas e chama
--
--     CALL gold.atualizar_gold(anos_maturacao, cursos_tronco, min_matriculas_inep, valor_bolsa_ic);
--
-- Tudo roda na transação de quem chama: a Gold é trocada inteira ou não é trocada.
--
-- As views auxiliares ficam em silver porque expõem vínculo individual (v_vinculo_estrutura) e o
-- papel observatorio_leitura não lê silver. As procedures ficam em gold.
--
-- Paridade com o Pandas: os arredondamentos usam gold.arredondar (double precision, empate para
-- o par, como o numpy.round), e não o round(numeric) do PostgreSQL, que arredonda o empate para cima.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Funções puras (as helpers normalize_* de build_gold.py)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION gold.arredondar(valor double precision, casas integer)
RETURNS double precision
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    SELECT round(valor * power(10::double precision, casas)) / power(10::double precision, casas)
$$;

COMMENT ON FUNCTION gold.arredondar(double precision, integer) IS
  'Arredonda em ponto flutuante com empate para o par (numpy.round). Mantém a paridade numérica com o Pandas.';

CREATE OR REPLACE FUNCTION gold.turno_grupo(turno_norm text)
RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    SELECT CASE WHEN turno_norm LIKE '%NOTURNO%' THEN 'NOTURNO'
                WHEN turno_norm LIKE '%INTEGRAL%' THEN 'INTEGRAL'
                ELSE 'DIURNO' END
$$;

COMMENT ON FUNCTION gold.turno_grupo(text) IS
  'Unifica matutino e vespertino em DIURNO; preserva NOTURNO e INTEGRAL.';

CREATE OR REPLACE FUNCTION gold.categoria_grau(grau_norm text)
RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    SELECT CASE WHEN coalesce(grau_norm, '') LIKE '%LICENCI%' THEN 'LICENCIATURA' ELSE 'BACHARELADO' END
$$;

COMMENT ON FUNCTION gold.categoria_grau(text) IS
  'Agrupa a titulação em BACHARELADO ou LICENCIATURA ("LICENCIADO" no catálogo de 2022, "LICENCIATURA" depois).';

CREATE OR REPLACE FUNCTION gold.campus_nome(campus_raw text)
RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    SELECT CASE WHEN campus_raw LIKE '%GAMA%' THEN 'FACULDADE DE CIENCIAS E TECNOLOGIAS EM ENGENHARIA (FCTE)'
                WHEN campus_raw LIKE '%CEILANDIA%' THEN 'FACULDADE DE CIENCIAS E TECNOLOGIAS EM SAUDE (FCTS)'
                WHEN campus_raw LIKE '%PLANALTINA%' THEN 'FACULDADE DE PLANALTINA (FUP)'
                ELSE 'DARCY RIBEIRO' END
$$;

COMMENT ON FUNCTION gold.campus_nome(text) IS
  'Unifica as grafias de campus entre SIGRA, SIGAA e PIBIC (FGA vira FCTE, FCE vira FCTS).';

-- ---------------------------------------------------------------------------
-- Views auxiliares (em silver: não são lidas pelo papel observatorio_leitura)
-- ---------------------------------------------------------------------------

-- Cada discente com o curso canônico (gold.regras_harmonizacao_canonicas) e os prazos da estrutura.
-- semestre_conclusao_ideal nulo = discente sem estrutura casada.
CREATE OR REPLACE VIEW silver.v_vinculo_estrutura AS
SELECT d._ordem,
       coalesce(r.destino_estrutura, d.curso_norm) AS curso,
       d.curso_norm,
       d.ano_ingresso,
       d.tipo_saida_grupo,
       d.semestres_permanencia_valida AS permanencia,
       d.departamento_norm,
       e.semestre_conclusao_minimo,
       e.semestre_conclusao_ideal,
       e.semestre_conclusao_maximo,
       e.ch_total_minima
FROM silver.discentes_graduacao d
LEFT JOIN gold.regras_harmonizacao_canonicas r ON r.origem_sigra = d.curso_norm
LEFT JOIN silver.estrutura_curricular e ON e.nome_curso_norm = coalesce(r.destino_estrutura, d.curso_norm);

COMMENT ON VIEW silver.v_vinculo_estrutura IS
  'Discente com curso canônico e prazos da estrutura curricular. Base das agregações de retenção da Gold.';

-- Um nome de curso pode ter várias ofertas no catálogo. Cada atributo vem da oferta de menor id_curso
-- entre as do catálogo vigente, ignorando nulos (first() do Pandas).
CREATE OR REPLACE VIEW silver.v_catalogo_curso AS
SELECT nome_curso_norm,
       (array_agg(turno_norm ORDER BY no_catalogo_vigente DESC, id_curso)
            FILTER (WHERE turno_norm IS NOT NULL))[1] AS turno_norm,
       (array_agg(campus_norm ORDER BY no_catalogo_vigente DESC, id_curso)
            FILTER (WHERE campus_norm IS NOT NULL))[1] AS campus_norm,
       (array_agg(grau_academico_norm ORDER BY no_catalogo_vigente DESC, id_curso)
            FILTER (WHERE grau_academico_norm IS NOT NULL))[1] AS grau_academico_norm,
       (array_agg(area_conhecimento_norm ORDER BY no_catalogo_vigente DESC, id_curso)
            FILTER (WHERE area_conhecimento_norm IS NOT NULL))[1] AS area_conhecimento_norm
FROM silver.cursos_graduacao
GROUP BY nome_curso_norm;

COMMENT ON VIEW silver.v_catalogo_curso IS
  'Uma linha por nome de curso, com a oferta principal do catálogo vigente (menor id_curso).';

-- Nomes com oferta de Bacharelado e de Licenciatura: nenhuma fonte liga o discente ao grau
-- conferido, então a Gold marca o curso como MISTO em vez de escolher um grau.
CREATE OR REPLACE VIEW silver.v_curso_misto AS
SELECT nome_curso_norm AS nome
FROM silver.cursos_graduacao
GROUP BY nome_curso_norm
HAVING count(DISTINCT gold.categoria_grau(grau_academico_norm)) > 1;

COMMENT ON VIEW silver.v_curso_misto IS
  'Nomes de curso com oferta de Bacharelado e de Licenciatura sob o mesmo nome.';

-- Turno e campus considerando todas as ofertas do nome. Mais de um turno vira "DIURNO E NOTURNO";
-- mais de um campus, MULTICAMPUS.
CREATE OR REPLACE VIEW silver.v_oferta_curso AS
WITH turnos AS (
    SELECT DISTINCT nome_curso_norm AS nome, gold.turno_grupo(turno_norm) AS valor
    FROM silver.cursos_graduacao WHERE turno_norm IS NOT NULL
), campi AS (
    SELECT DISTINCT nome_curso_norm AS nome, gold.campus_nome(campus_norm) AS valor
    FROM silver.cursos_graduacao WHERE campus_norm IS NOT NULL
), turno_do_nome AS (
    SELECT nome, string_agg(valor, ' E ' ORDER BY valor COLLATE "C") AS turno FROM turnos GROUP BY nome
), campus_do_nome AS (
    SELECT nome, CASE WHEN count(*) > 1 THEN 'MULTICAMPUS' ELSE min(valor) END AS campus FROM campi GROUP BY nome
)
SELECT n.nome,
       coalesce(t.turno, 'DIURNO') AS turno,
       coalesce(c.campus, 'DARCY RIBEIRO') AS campus
FROM (SELECT DISTINCT nome_curso_norm AS nome FROM silver.cursos_graduacao) n
LEFT JOIN turno_do_nome t USING (nome)
LEFT JOIN campus_do_nome c USING (nome);

COMMENT ON VIEW silver.v_oferta_curso IS
  'Turno (DIURNO, NOTURNO, "DIURNO E NOTURNO") e campus (ou MULTICAMPUS) de cada nome de curso.';

-- Grande Área por nome de curso: a moda do catálogo (empate pelo menor texto). Curso-tronco sem
-- entrada própria (ex.: COMUNICACAO SOCIAL) herda a área das habilitações "NOME - ...", quando todas
-- concordam.
CREATE OR REPLACE VIEW silver.v_area_curso AS
WITH moda AS (
    SELECT DISTINCT ON (nome) nome, area
    FROM (SELECT nome_curso_norm AS nome, area_conhecimento_norm AS area, count(*) AS n
          FROM silver.cursos_graduacao
          WHERE area_conhecimento_norm IS NOT NULL
          GROUP BY nome_curso_norm, area_conhecimento_norm) t
    ORDER BY nome, n DESC, area COLLATE "C"
), bases AS (
    SELECT curso AS nome FROM silver.v_vinculo_estrutura
    UNION
    SELECT coalesce(r.destino_estrutura, p.curso_pibic_norm)
    FROM silver.pibic_bolsistas p
    LEFT JOIN gold.regras_harmonizacao_canonicas r ON r.origem_sigra = p.curso_pibic_norm
), herdada AS (
    SELECT b.nome, min(m.area) AS area
    FROM bases b
    JOIN moda m ON starts_with(m.nome, b.nome || ' - ')
    WHERE b.nome <> '' AND NOT EXISTS (SELECT 1 FROM moda WHERE moda.nome = b.nome)
    GROUP BY b.nome
    HAVING count(DISTINCT m.area) = 1
)
SELECT nome, area FROM moda
UNION ALL
SELECT nome, area FROM herdada;

COMMENT ON VIEW silver.v_area_curso IS
  'Grande Área (CNPq/MEC) por nome de curso canônico, com herança para cursos-tronco.';

-- ---------------------------------------------------------------------------
-- Procedures: uma por tabela da Gold, mais a orquestradora
-- ---------------------------------------------------------------------------

-- Conta os discentes de cada regra e põe as mais usadas primeiro (empate: ordem original).
CREATE OR REPLACE PROCEDURE gold.atualizar_regras()
LANGUAGE plpgsql
AS $$
BEGIN
    WITH contagem AS (
        SELECT curso_norm, count(*) AS n FROM silver.discentes_graduacao GROUP BY curso_norm
    )
    UPDATE gold.regras_harmonizacao_canonicas r
    SET discentes_impactados = coalesce((SELECT c.n FROM contagem c WHERE c.curso_norm = r.origem_sigra), 0);

    UPDATE gold.regras_harmonizacao_canonicas r
    SET _ordem = x.rn
    FROM (SELECT origem_sigra,
                 row_number() OVER (ORDER BY discentes_impactados DESC, _ordem) AS rn
          FROM gold.regras_harmonizacao_canonicas) x
    WHERE x.origem_sigra = r.origem_sigra;
END
$$;

COMMENT ON PROCEDURE gold.atualizar_regras() IS
  'Preenche discentes_impactados de cada regra de harmonização e ordena da mais usada para a menos usada.';

CREATE OR REPLACE PROCEDURE gold.atualizar_ativos_hoje(p_cursos_tronco text[])
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM silver.sigaa_ativos) THEN
        RAISE WARNING 'silver.sigaa_ativos está vazia. Pulando Ativos Hoje.';
        RETURN;
    END IF;

    TRUNCATE gold.ativos_hoje_cursos_unb;
    INSERT INTO gold.ativos_hoje_cursos_unb (
        curso, periodo_referencia, semestre_ideal_previsto, semestre_maximo_previsto, total_ativos_hoje,
        ativos_acima_prazo_ideal, ativos_acima_prazo_maximo, pct_acima_prazo_ideal, _ordem)
    WITH referencia AS (
        SELECT periodo_referencia FROM silver.sigaa_ativos ORDER BY _ordem LIMIT 1
    ), ativos AS (
        -- Troncos ficam de fora: o aluno escolhe a habilitação no meio do curso e o prazo máximo do
        -- tronco de Engenharia (3) é menor que o ideal (5), o que não mede atraso.
        SELECT coalesce(r.destino_estrutura, s.curso_norm) AS curso,
               s.semestres_cursados,
               e.semestre_conclusao_ideal AS ideal,
               e.semestre_conclusao_maximo AS maximo
        FROM silver.sigaa_ativos s
        LEFT JOIN gold.regras_harmonizacao_canonicas r ON r.origem_sigra = s.curso_norm
        JOIN silver.estrutura_curricular e ON e.nome_curso_norm = coalesce(r.destino_estrutura, s.curso_norm)
        WHERE coalesce(r.destino_estrutura, s.curso_norm) <> ALL (coalesce(p_cursos_tronco, '{}'))
    ), por_curso AS (
        SELECT curso,
               min(ideal) AS ideal,
               min(maximo) AS maximo,
               count(*) AS total,
               count(*) FILTER (WHERE semestres_cursados > ideal) AS acima_ideal,
               count(*) FILTER (WHERE semestres_cursados > maximo) AS acima_maximo
        FROM ativos
        GROUP BY curso
        HAVING count(*) >= 5   -- k-anonimato, como na tabela de retenção
    )
    SELECT p.curso, (SELECT periodo_referencia FROM referencia), p.ideal, p.maximo, p.total,
           p.acima_ideal, p.acima_maximo,
           gold.arredondar(p.acima_ideal::double precision / p.total * 100, 2),
           row_number() OVER (ORDER BY gold.arredondar(p.acima_ideal::double precision / p.total * 100, 2) DESC,
                                       p.curso COLLATE "C")
    FROM por_curso p;
END
$$;

COMMENT ON PROCEDURE gold.atualizar_ativos_hoje(text[]) IS
  'Refaz gold.ativos_hoje_cursos_unb: ativos do semestre mais recente por curso e quem já passou do prazo.';

CREATE OR REPLACE PROCEDURE gold.atualizar_retencao(p_anos_maturacao integer)
LANGUAGE plpgsql
AS $$
BEGIN
    TRUNCATE gold.retencao_cursos_unb;
    INSERT INTO gold.retencao_cursos_unb (
        curso, departamento, campus, turno, area_conhecimento, grau_academico, categoria_grau,
        semestre_minimo_previsto, semestre_ideal_previsto, semestre_maximo_previsto, carga_horaria_minima,
        total_discentes_registrados, total_formados, total_evadidos_desligados, total_ainda_ativos,
        taxa_formatura_pct, taxa_evasao_pct, formados_tempo_minimo_pct, formados_tempo_ideal_pct,
        formados_acima_ideal_pct, formados_limite_maximo_pct, tempo_medio_real_semestres,
        tempo_mediano_real_semestres, desvio_medio_semestres, indice_retencao_critica,
        classificacao_retencao, pibic_total_projetos, pibic_bolsas_remuneradas, pibic_bolsas_voluntarias,
        pibic_cotistas, pibic_investimento_total, pibic_projetos_por_100_alunos, _ordem)
    WITH corte AS (
        -- Só coortes que já tiveram tempo de concluir: ingresso até (último ano - anos de maturação).
        SELECT max(ano_ingresso) - p_anos_maturacao AS ano FROM silver.v_vinculo_estrutura
    ), agrupado AS (
        SELECT curso,
               count(*) AS total,
               count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA') AS formados,
               count(*) FILTER (WHERE tipo_saida_grupo = 'EVASAO') AS evadidos,
               count(*) FILTER (WHERE tipo_saida_grupo = 'ATIVO') AS ativos,
               -- Percentuais de prazo só sobre formados com permanência calculável.
               count(permanencia) FILTER (WHERE tipo_saida_grupo = 'FORMATURA') AS com_prazo,
               count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA' AND permanencia <= semestre_conclusao_minimo) AS no_minimo,
               count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA' AND permanencia <= semestre_conclusao_ideal) AS no_ideal,
               count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA' AND permanencia > semestre_conclusao_ideal) AS acima_ideal,
               count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA' AND permanencia >= semestre_conclusao_maximo) AS no_maximo,
               (avg(permanencia::numeric) FILTER (WHERE tipo_saida_grupo = 'FORMATURA'))::double precision AS media,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY permanencia::double precision)
                   FILTER (WHERE tipo_saida_grupo = 'FORMATURA') AS mediana,
               (avg(permanencia::numeric - semestre_conclusao_ideal)
                   FILTER (WHERE tipo_saida_grupo = 'FORMATURA'))::double precision AS desvio,
               min(semestre_conclusao_minimo) AS sem_minimo,
               min(semestre_conclusao_ideal) AS sem_ideal,
               min(semestre_conclusao_maximo) AS sem_maximo,
               min(ch_total_minima) AS ch_total,
               (array_agg(departamento_norm ORDER BY _ordem) FILTER (WHERE departamento_norm IS NOT NULL))[1] AS depto
        FROM silver.v_vinculo_estrutura
        WHERE semestre_conclusao_ideal IS NOT NULL
          AND ano_ingresso <= (SELECT ano FROM corte)
        GROUP BY curso
        HAVING count(*) >= 5   -- supressão ética de grupos pequenos
    ), metricas AS (
        SELECT a.*,
               gold.arredondar(a.formados::double precision / a.total * 100, 2) AS taxa_formatura,
               gold.arredondar(a.evadidos::double precision / a.total * 100, 2) AS taxa_evasao,
               CASE WHEN a.com_prazo > 0 THEN gold.arredondar(a.no_minimo::double precision / a.com_prazo * 100, 2) ELSE 0 END AS pct_minimo,
               CASE WHEN a.com_prazo > 0 THEN gold.arredondar(a.no_ideal::double precision / a.com_prazo * 100, 2) ELSE 0 END AS pct_ideal,
               CASE WHEN a.com_prazo > 0 THEN gold.arredondar(a.acima_ideal::double precision / a.com_prazo * 100, 2) ELSE 0 END AS pct_acima,
               CASE WHEN a.com_prazo > 0 THEN gold.arredondar(a.no_maximo::double precision / a.com_prazo * 100, 2) ELSE 0 END AS pct_maximo,
               gold.arredondar(a.media, 2) AS tempo_medio,
               gold.arredondar(a.mediana, 2) AS tempo_mediano,
               gold.arredondar(a.desvio, 2) AS desvio_medio
        FROM agrupado a
    ), entradas AS (
        SELECT curso,
               greatest(coalesce(desvio_medio, 0), 0) AS x_desvio,
               coalesce(taxa_evasao, 0) AS x_evasao
        FROM metricas
    ), limites AS (
        -- Satura nos percentis 5 e 95 antes do min-max: um curso outlier não comprime a escala dos demais.
        SELECT percentile_cont(0.05) WITHIN GROUP (ORDER BY x_desvio) AS d05,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY x_desvio) AS d95,
               percentile_cont(0.05) WITHIN GROUP (ORDER BY x_evasao) AS e05,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY x_evasao) AS e95
        FROM entradas
    ), saturados AS (
        SELECT e.curso,
               least(greatest(e.x_desvio, l.d05), l.d95) AS s_desvio,
               least(greatest(e.x_evasao, l.e05), l.e95) AS s_evasao
        FROM entradas e CROSS JOIN limites l
    ), irc AS (
        -- Evasão pesa mais que atraso: perder o aluno é mais grave que formá-lo mais devagar.
        SELECT curso,
               gold.arredondar(
                   (0.3 * ((s_desvio - min(s_desvio) OVER ()) / (max(s_desvio) OVER () - min(s_desvio) OVER () + 1e-6))
                  + 0.7 * ((s_evasao - min(s_evasao) OVER ()) / (max(s_evasao) OVER () - min(s_evasao) OVER () + 1e-6))
                   ) * 100, 1) AS indice
        FROM saturados
    ), quartis AS (
        SELECT percentile_cont(0.25) WITHIN GROUP (ORDER BY indice) AS q25,
               percentile_cont(0.50) WITHIN GROUP (ORDER BY indice) AS q50,
               percentile_cont(0.75) WITHIN GROUP (ORDER BY indice) AS q75
        FROM irc
    ), pibic AS (
        SELECT coalesce(r.destino_estrutura, p.curso_pibic_norm) AS curso,
               count(*) AS total,
               count(*) FILTER (WHERE p.tipo_bolsa_norm = 'REMUNERADA') AS remuneradas,
               count(*) FILTER (WHERE p.tipo_bolsa_norm = 'VOLUNTARIA') AS voluntarias,
               count(*) FILTER (WHERE p.is_cotista) AS cotistas,
               sum(p.valor_bolsa_anual_estimado) AS investimento
        FROM silver.pibic_bolsistas p
        LEFT JOIN gold.regras_harmonizacao_canonicas r ON r.origem_sigra = p.curso_pibic_norm
        WHERE p.curso_pibic_norm IS NOT NULL
        GROUP BY 1
    )
    SELECT m.curso,
           coalesce(m.depto, 'UNB'),
           coalesce(o.campus, 'DARCY RIBEIRO'),
           coalesce(o.turno, 'DIURNO'),
           coalesce(cat.area_conhecimento_norm, ar.area, 'OUTRA'),
           CASE WHEN misto.nome IS NOT NULL THEN 'MISTO (BACHARELADO + LICENCIATURA)'
                ELSE coalesce(cat.grau_academico_norm, 'BACHAREL') END,
           CASE WHEN misto.nome IS NOT NULL THEN 'MISTO'
                ELSE gold.categoria_grau(coalesce(cat.grau_academico_norm, 'BACHAREL')) END,
           m.sem_minimo, m.sem_ideal, m.sem_maximo, m.ch_total,
           m.total, m.formados, m.evadidos, m.ativos,
           m.taxa_formatura, m.taxa_evasao, m.pct_minimo, m.pct_ideal, m.pct_acima, m.pct_maximo,
           m.tempo_medio, m.tempo_mediano, m.desvio_medio,
           i.indice,
           CASE WHEN i.indice >= q.q75 THEN 'RETENÇÃO CRÍTICA'
                WHEN i.indice >= q.q50 THEN 'RETENÇÃO ALTA'
                WHEN i.indice >= q.q25 THEN 'RETENÇÃO MÉDIA'
                ELSE 'RETENÇÃO BAIXA' END,
           coalesce(pb.total, 0),
           pb.remuneradas, pb.voluntarias, pb.cotistas,
           coalesce(pb.investimento, 0),
           gold.arredondar(coalesce(pb.total, 0)::double precision / m.total * 100, 2),
           row_number() OVER (ORDER BY i.indice DESC, m.curso COLLATE "C")
    FROM metricas m
    JOIN irc i USING (curso)
    CROSS JOIN quartis q
    LEFT JOIN silver.v_catalogo_curso cat ON cat.nome_curso_norm = m.curso
    LEFT JOIN silver.v_area_curso ar ON ar.nome = m.curso
    LEFT JOIN silver.v_oferta_curso o ON o.nome = m.curso
    LEFT JOIN silver.v_curso_misto misto ON misto.nome = m.curso
    LEFT JOIN pibic pb ON pb.curso = m.curso;
END
$$;

COMMENT ON PROCEDURE gold.atualizar_retencao(integer) IS
  'Refaz gold.retencao_cursos_unb: retenção, evasão, IRC e quartis por curso canônico (coortes maduras, k >= 5).';

CREATE OR REPLACE PROCEDURE gold.atualizar_inep_benchmark(p_min_matriculas integer)
LANGUAGE plpgsql
AS $$
BEGIN
    TRUNCATE gold.inep_benchmark_cursos_unb;
    IF NOT EXISTS (SELECT 1 FROM silver.inep_censo_superior) THEN
        RAISE WARNING 'silver.inep_censo_superior está vazia. Benchmark INEP esvaziado.';
        RETURN;
    END IF;

    INSERT INTO gold.inep_benchmark_cursos_unb (
        curso_inep, qt_matriculas_unb, qt_ingressantes_unb, qt_concluintes_unb, qt_trancadas_unb,
        qt_desvinculados_unb, qt_vagas_unb, qt_inscritos_unb, taxa_trancamento_unb_pct,
        taxa_desvinculacao_unb_pct, concorrencia_vestibular_unb, n_ies_comparadas,
        mediana_trancamento_federais_pct, mediana_desvinculacao_federais_pct, gap_trancamento_pp,
        gap_desvinculacao_pp, razao_trancamento, razao_desvinculacao, _ordem)
    WITH por_ies AS (
        -- O Censo registra cada oferta (turno/campus) como um curso. Soma as ofertas da mesma
        -- instituição antes do corte e da taxa: UnB e demais federais na mesma unidade (curso x IES).
        SELECT "NO_CURSO" AS curso, "CO_IES" AS ies, is_unb,
               coalesce(sum("QT_MAT"), 0) AS mat,
               coalesce(sum("QT_ING"), 0) AS ing,
               coalesce(sum("QT_CONC"), 0) AS conc,
               coalesce(sum("QT_SIT_TRANCADA"), 0) AS tr,
               coalesce(sum("QT_SIT_DESVINCULADO"), 0) AS desv,
               coalesce(sum("QT_VG_TOTAL"), 0) AS vag,
               coalesce(sum("QT_INSCRITO_TOTAL"), 0) AS insc
        FROM silver.inep_censo_superior
        GROUP BY "NO_CURSO", "CO_IES", is_unb
        HAVING coalesce(sum("QT_MAT"), 0) >= p_min_matriculas
    ), taxas AS (
        SELECT *,
               tr::double precision / nullif(mat, 0) * 100 AS t_tr,
               desv::double precision / nullif(mat, 0) * 100 AS t_desv,
               insc::double precision / nullif(vag, 0) AS concorrencia
        FROM por_ies
    ), unb AS (
        SELECT curso, mat, ing, conc, tr, desv, vag, insc,
               gold.arredondar(t_tr, 2) AS t_tr, gold.arredondar(t_desv, 2) AS t_desv,
               gold.arredondar(concorrencia, 2) AS concorrencia
        FROM taxas WHERE is_unb
    ), pares AS (
        -- Mediana, e não média: uma instituição atípica não distorce o padrão de referência.
        SELECT curso,
               count(DISTINCT ies) AS n_ies,
               gold.arredondar(percentile_cont(0.5) WITHIN GROUP (ORDER BY t_tr), 2) AS m_tr,
               gold.arredondar(percentile_cont(0.5) WITHIN GROUP (ORDER BY t_desv), 2) AS m_desv
        FROM taxas WHERE NOT is_unb
        GROUP BY curso
    )
    SELECT u.curso, u.mat, u.ing, u.conc, u.tr, u.desv, u.vag, u.insc,
           u.t_tr, u.t_desv, u.concorrencia,
           p.n_ies, p.m_tr, p.m_desv,
           gold.arredondar(u.t_tr - p.m_tr, 2),
           gold.arredondar(u.t_desv - p.m_desv, 2),
           gold.arredondar(u.t_tr / nullif(p.m_tr, 0), 2),
           gold.arredondar(u.t_desv / nullif(p.m_desv, 0), 2),
           row_number() OVER (ORDER BY u.mat DESC, u.curso COLLATE "C")
    FROM unb u
    LEFT JOIN pares p USING (curso);
END
$$;

COMMENT ON PROCEDURE gold.atualizar_inep_benchmark(integer) IS
  'Refaz gold.inep_benchmark_cursos_unb: taxas da UnB contra a mediana das demais federais (Censo/INEP).';

CREATE OR REPLACE PROCEDURE gold.atualizar_pibic_social()
LANGUAGE plpgsql
AS $$
BEGIN
    TRUNCATE gold.pibic_social_unb;
    IF NOT EXISTS (SELECT 1 FROM silver.pibic_bolsistas) THEN
        RAISE WARNING 'silver.pibic_bolsistas está vazia. Gold do PIBIC esvaziada.';
        RETURN;
    END IF;

    INSERT INTO gold.pibic_social_unb (
        curso_pibic_norm, campus, area_conhecimento, total_projetos, total_remuneradas,
        total_voluntarias_pivic, total_cotistas, total_cotistas_ppi, total_baixa_renda,
        valor_total_investido, taxa_cotistas_pct, taxa_voluntario_pct, _ordem)
    WITH bolsas AS (
        SELECT coalesce(r.destino_estrutura, p.curso_pibic_norm) AS curso,
               gold.campus_nome(p.campus) AS campus,
               CASE WHEN EXISTS (SELECT 1 FROM silver.cursos_graduacao)
                    THEN coalesce(a.area, 'OUTRA') ELSE p.linha_pesquisa_norm END AS area,
               p.tipo_bolsa_norm, p.is_cotista, p.perfil_social_macro, p.faixa_renda, p.valor_bolsa_anual_estimado
        FROM silver.pibic_bolsistas p
        LEFT JOIN gold.regras_harmonizacao_canonicas r ON r.origem_sigra = p.curso_pibic_norm
        LEFT JOIN silver.v_area_curso a ON a.nome = coalesce(r.destino_estrutura, p.curso_pibic_norm)
    ), por_curso AS (
        SELECT curso, campus, area,
               count(*) AS total,
               count(*) FILTER (WHERE tipo_bolsa_norm = 'REMUNERADA') AS remuneradas,
               count(*) FILTER (WHERE tipo_bolsa_norm = 'VOLUNTARIA') AS voluntarias,
               count(*) FILTER (WHERE is_cotista) AS cotistas,
               count(*) FILTER (WHERE perfil_social_macro = 'PPI / ETNICO-RACIAL') AS ppi,
               count(*) FILTER (WHERE faixa_renda = 'BAIXA RENDA (<= 1.5 SM)') AS baixa_renda,
               sum(valor_bolsa_anual_estimado) AS investido
        FROM bolsas
        WHERE curso IS NOT NULL AND area IS NOT NULL
        GROUP BY curso, campus, area
        HAVING curso <> '' AND count(*) >= 5   -- supressão ética k < 5
    )
    SELECT curso, campus, area, total, remuneradas, voluntarias, cotistas, ppi, baixa_renda, investido,
           gold.arredondar(cotistas::double precision / total * 100, 1),
           gold.arredondar(voluntarias::double precision / total * 100, 1),
           row_number() OVER (ORDER BY total DESC, curso COLLATE "C", campus COLLATE "C", area COLLATE "C")
    FROM por_curso;
END
$$;

COMMENT ON PROCEDURE gold.atualizar_pibic_social() IS
  'Refaz gold.pibic_social_unb: bolsistas de IC por curso canônico e campus (k >= 5).';

-- Relatórios JSON consumidos pelo painel, pela auditoria e pelo export estático.
CREATE OR REPLACE PROCEDURE gold.atualizar_relatorios_retencao(p_anos_maturacao integer, p_cursos_tronco text[])
LANGUAGE plpgsql
AS $$
DECLARE
    v_total_harmonizados bigint;
    v_total bigint;
    v_casados bigint;
    v_nao_casados jsonb;
    v_taxa double precision;
BEGIN
    SELECT coalesce(sum(discentes_impactados), 0) INTO v_total_harmonizados FROM gold.regras_harmonizacao_canonicas;

    INSERT INTO gold.relatorios (nome, conteudo)
    SELECT 'regras_harmonizacao_canonicas',
           jsonb_build_object(
               'total_regras', count(*),
               'total_discentes_harmonizados', v_total_harmonizados,
               'metodologia', 'Entity Resolution e Harmonização Canônica (SIGRA/SIGAA -> Matrizes Curriculares Ativas)',
               'regras', coalesce(jsonb_agg(jsonb_build_object(
                   'origem_sigra', origem_sigra,
                   'destino_estrutura', destino_estrutura,
                   'categoria', categoria,
                   'justificativa', justificativa,
                   'discentes_impactados', discentes_impactados) ORDER BY _ordem), '[]'::jsonb))
    FROM gold.regras_harmonizacao_canonicas
    ON CONFLICT (nome) DO UPDATE SET conteudo = EXCLUDED.conteudo, _carregado_em = now();

    SELECT count(*), count(semestre_conclusao_ideal) INTO v_total, v_casados FROM silver.v_vinculo_estrutura;
    v_taxa := v_casados::double precision / v_total * 100;

    SELECT coalesce(jsonb_object_agg(curso_norm, n), '{}'::jsonb) INTO v_nao_casados
    FROM (SELECT curso_norm, count(*) AS n
          FROM silver.v_vinculo_estrutura
          WHERE semestre_conclusao_ideal IS NULL
          GROUP BY curso_norm
          ORDER BY n DESC, curso_norm COLLATE "C"
          LIMIT 10) t;

    INSERT INTO gold.relatorios (nome, conteudo)
    VALUES ('relatorio_casamento_joins', jsonb_build_object(
        'total_discentes_graduacao', v_total,
        'discentes_com_estrutura_casada', v_casados,
        'discentes_sem_casamento', v_total - v_casados,
        'taxa_de_casamento_pct', gold.arredondar(v_taxa, 2),
        'cursos_nao_casados_principais', v_nao_casados,
        'harmonizacao_ativa', true,
        'total_discentes_harmonizados', v_total_harmonizados,
        'justificativa_descartes', CASE WHEN v_total = v_casados THEN
            'Taxa de 100.00% alcançada através de Harmonização Canônica transparente '
            || 'e auditável de regras de equivalência entre os sistemas acadêmicos (SIGRA e SIGAA) e matrizes curriculares ativas. '
            || 'Zero registros descartados.'
            ELSE (v_total - v_casados) || ' registros não casados restantes.' END))
    ON CONFLICT (nome) DO UPDATE SET conteudo = EXCLUDED.conteudo, _carregado_em = now();

    WITH vinculos AS (
        SELECT * FROM silver.v_vinculo_estrutura
        WHERE semestre_conclusao_ideal IS NOT NULL
          AND ano_ingresso <= (SELECT max(ano_ingresso) - p_anos_maturacao FROM silver.v_vinculo_estrutura)
    ), glob AS (
        SELECT min(ano_ingresso) AS primeira,
               count(*) AS analisados,
               count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA') AS formados,
               count(permanencia) FILTER (WHERE tipo_saida_grupo = 'FORMATURA') AS com_prazo,
               count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA' AND permanencia <= semestre_conclusao_ideal) AS no_ideal,
               count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA' AND permanencia > semestre_conclusao_ideal) AS acima_ideal,
               (avg(permanencia::numeric) FILTER (WHERE tipo_saida_grupo = 'FORMATURA'))::double precision AS media,
               (avg(permanencia::numeric - semestre_conclusao_ideal)
                   FILTER (WHERE tipo_saida_grupo = 'FORMATURA'))::double precision AS desvio
        FROM vinculos
    ), ativos AS (
        SELECT coalesce(max(periodo_referencia), '') AS referencia,
               coalesce(sum(total_ativos_hoje), 0) AS total,
               coalesce(sum(ativos_acima_prazo_ideal), 0) AS acima_ideal,
               coalesce(sum(ativos_acima_prazo_maximo), 0) AS acima_maximo
        FROM gold.ativos_hoje_cursos_unb
    )
    INSERT INTO gold.relatorios (nome, conteudo)
    SELECT 'metricas_gerais_unb', jsonb_build_object(
        'coortes_ingresso_analisadas', g.primeira::text || '-'
            || (SELECT max(ano_ingresso) - p_anos_maturacao FROM silver.v_vinculo_estrutura)::text,
        'total_discentes_analisados', g.analisados,
        'total_formados_unb', g.formados,
        'taxa_conclusao_tempo_ideal_global_pct', gold.arredondar(g.no_ideal::double precision / g.com_prazo * 100, 2),
        'taxa_conclusao_acima_ideal_global_pct', gold.arredondar(g.acima_ideal::double precision / g.com_prazo * 100, 2),
        'tempo_medio_formatura_global_semestres', gold.arredondar(g.media, 2),
        'desvio_medio_global_semestres', gold.arredondar(g.desvio, 2),
        'top_5_cursos_maior_retencao', (
            SELECT coalesce(jsonb_agg(jsonb_build_object(
                       'curso', curso,
                       'tempo_medio_real_semestres', tempo_medio_real_semestres,
                       'taxa_evasao_pct', taxa_evasao_pct,
                       'indice_retencao_critica', indice_retencao_critica) ORDER BY _ordem), '[]'::jsonb)
            FROM (SELECT * FROM gold.retencao_cursos_unb ORDER BY _ordem LIMIT 5) t),
        'cursos_tronco', (SELECT coalesce(jsonb_agg(c ORDER BY c COLLATE "C"), '[]'::jsonb) FROM unnest(coalesce(p_cursos_tronco, '{}')) c),
        'ativos_hoje_referencia', a.referencia,
        'ativos_hoje_total', a.total,
        'ativos_hoje_acima_prazo_ideal', a.acima_ideal,
        'ativos_hoje_acima_prazo_maximo', a.acima_maximo,
        'top_5_cursos_maior_pontualidade', (
            SELECT coalesce(jsonb_agg(jsonb_build_object(
                       'curso', curso,
                       'formados_tempo_ideal_pct', formados_tempo_ideal_pct,
                       'tempo_medio_real_semestres', tempo_medio_real_semestres) ORDER BY formados_tempo_ideal_pct DESC, _ordem), '[]'::jsonb)
            FROM (SELECT * FROM gold.retencao_cursos_unb ORDER BY formados_tempo_ideal_pct DESC, _ordem LIMIT 5) t))
    FROM glob g CROSS JOIN ativos a
    ON CONFLICT (nome) DO UPDATE SET conteudo = EXCLUDED.conteudo, _carregado_em = now();
END
$$;

COMMENT ON PROCEDURE gold.atualizar_relatorios_retencao(integer, text[]) IS
  'Grava em gold.relatorios as regras de harmonização, o casamento dos joins e as métricas gerais da UnB.';

CREATE OR REPLACE PROCEDURE gold.atualizar_relatorio_pibic(p_valor_bolsa_ic numeric)
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM silver.pibic_bolsistas) THEN
        RETURN;
    END IF;

    WITH bolsas AS (
        SELECT b.ano, b.tipo_bolsa_norm, b.is_cotista, b.cota_detalhe, b.perfil_social_macro,
               b.valor_bolsa_anual_estimado AS valor,
               gold.campus_nome(b.campus) AS campus,
               CASE WHEN EXISTS (SELECT 1 FROM silver.cursos_graduacao)
                    THEN coalesce(a.area, 'OUTRA') ELSE b.linha_pesquisa_norm END AS area
        FROM silver.pibic_bolsistas b
        LEFT JOIN gold.regras_harmonizacao_canonicas r ON r.origem_sigra = b.curso_pibic_norm
        LEFT JOIN silver.v_area_curso a ON a.nome = coalesce(r.destino_estrutura, b.curso_pibic_norm)
    ), total AS (
        SELECT count(*) AS n,
               count(*) FILTER (WHERE tipo_bolsa_norm = 'REMUNERADA') AS remuneradas,
               count(*) FILTER (WHERE tipo_bolsa_norm = 'VOLUNTARIA') AS voluntarias,
               count(*) FILTER (WHERE is_cotista) AS cotistas,
               sum(valor) AS investido,
               count(perfil_social_macro) AS com_perfil
        FROM bolsas
    ), perfil AS (
        SELECT jsonb_object_agg(perfil_social_macro, gold.arredondar(n::double precision / (SELECT com_perfil FROM total) * 100, 2)) AS j
        FROM (SELECT perfil_social_macro, count(*) AS n FROM bolsas WHERE perfil_social_macro IS NOT NULL GROUP BY 1) t
    ), cota AS (
        SELECT jsonb_object_agg(cota_detalhe, n) AS j
        FROM (SELECT cota_detalhe, count(*) AS n FROM bolsas WHERE cota_detalhe IS NOT NULL GROUP BY 1) t
    ), campi AS (
        SELECT jsonb_agg(jsonb_build_object(
                   'campus', campus,
                   'total_projetos', n,
                   'total_remuneradas', remuneradas,
                   'total_cotistas', cotistas,
                   'valor_investido', investido,
                   'pct_projetos', gold.arredondar(n::double precision / (SELECT n FROM total) * 100, 2),
                   'pct_cotistas', gold.arredondar(cotistas::double precision / n * 100, 2)) ORDER BY campus COLLATE "C") AS j
        FROM (SELECT campus, count(*) AS n,
                     count(*) FILTER (WHERE tipo_bolsa_norm = 'REMUNERADA') AS remuneradas,
                     count(*) FILTER (WHERE is_cotista) AS cotistas,
                     sum(valor) AS investido
              FROM bolsas GROUP BY campus) t
    ), alunos AS (
        SELECT area_conhecimento AS area, sum(total_discentes_registrados) AS alunos_n
        FROM gold.retencao_cursos_unb GROUP BY area_conhecimento
    ), areas AS (
        SELECT jsonb_agg(
                   jsonb_build_object(
                       'area_conhecimento', t.area,
                       'total_projetos', t.n,
                       'total_remuneradas', t.remuneradas,
                       'total_cotistas', t.cotistas,
                       'valor_investido', t.investido,
                       'pct_projetos', gold.arredondar(t.n::double precision / (SELECT n FROM total) * 100, 2),
                       'pct_cotistas', gold.arredondar(t.cotistas::double precision / t.n * 100, 2))
                   -- Taxa de participação = projetos / alunos da área; só existe com a retenção gravada.
                   || CASE WHEN EXISTS (SELECT 1 FROM gold.retencao_cursos_unb) THEN jsonb_build_object(
                       'total_discentes_area', coalesce(al.alunos_n, 0),
                       'taxa_participacao_pibic_pct',
                           gold.arredondar(t.n::double precision / nullif(coalesce(al.alunos_n, 0), 0) * 100, 2))
                      ELSE '{}'::jsonb END
                   ORDER BY t.area COLLATE "C") AS j
        FROM (SELECT area, count(*) AS n,
                     count(*) FILTER (WHERE tipo_bolsa_norm = 'REMUNERADA') AS remuneradas,
                     count(*) FILTER (WHERE is_cotista) AS cotistas,
                     sum(valor) AS investido
              FROM bolsas WHERE area IS NOT NULL GROUP BY area) t
        LEFT JOIN alunos al ON al.area = t.area
    ), anos AS (
        SELECT jsonb_agg(jsonb_build_object(
                   'ano', ano,
                   'total_projetos', n,
                   'remuneradas', remuneradas,
                   'voluntarias', voluntarias,
                   'cotistas', cotistas,
                   'investimento_reais', investido) ORDER BY ano) AS j
        FROM (SELECT ano, count(*) AS n,
                     count(*) FILTER (WHERE tipo_bolsa_norm = 'REMUNERADA') AS remuneradas,
                     count(*) FILTER (WHERE tipo_bolsa_norm = 'VOLUNTARIA') AS voluntarias,
                     count(*) FILTER (WHERE is_cotista) AS cotistas,
                     sum(valor) AS investido
              FROM bolsas GROUP BY ano) t
    )
    INSERT INTO gold.relatorios (nome, conteudo)
    SELECT 'pibic_metricas_gerais', jsonb_build_object(
        'total_projetos_ic', t.n,
        'total_bolsas_remuneradas', t.remuneradas,
        'total_pesquisadores_voluntarios_pivic', t.voluntarias,
        'investimento_publico_total_estimado', t.investido,
        'total_cotistas', t.cotistas,
        'taxa_inclusao_cotistas_pct', gold.arredondar(t.cotistas::double precision / t.n * 100, 2),
        'taxa_trabalho_voluntario_pct', gold.arredondar(t.voluntarias::double precision / t.n * 100, 2),
        'distribuicao_perfil_social_pct', coalesce(perfil.j, '{}'::jsonb),
        'distribuicao_cota_detalhe', coalesce(cota.j, '{}'::jsonb),
        'distribuicao_campi', coalesce(campi.j, '[]'::jsonb),
        'distribuicao_grande_area', coalesce(areas.j, '[]'::jsonb),
        'evolucao_anual', coalesce(anos.j, '[]'::jsonb),
        -- Valor mensal em vigor na coleta mais recente da tabela do CNPq (simulador do painel).
        'valor_bolsa_ic_mensal_vigente', p_valor_bolsa_ic)
    FROM total t, perfil, cota, campi, areas, anos
    ON CONFLICT (nome) DO UPDATE SET conteudo = EXCLUDED.conteudo, _carregado_em = now();
END
$$;

COMMENT ON PROCEDURE gold.atualizar_relatorio_pibic(numeric) IS
  'Grava em gold.relatorios o pibic_metricas_gerais: custo total, inclusão social e distribuições.';

-- Orquestradora. A retenção vem antes do PIBIC e dos relatórios: a taxa de participação por área lê a retenção.
-- Sem discentes na Silver a Gold anterior é mantida (como o Pandas fazia).
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
  'ELT da Gold: refaz retenção, ativos, benchmark INEP, PIBIC e relatórios a partir da Silver, na transação de quem chama. Pré-requisito: gold.regras_harmonizacao_canonicas semeada.';

-- As procedures reescrevem a Gold e leem a Silver: só quem tem esses privilégios (o dono do pipeline) as chama.
REVOKE EXECUTE ON PROCEDURE
    gold.atualizar_regras(),
    gold.atualizar_ativos_hoje(text[]),
    gold.atualizar_retencao(integer),
    gold.atualizar_inep_benchmark(integer),
    gold.atualizar_pibic_social(),
    gold.atualizar_relatorios_retencao(integer, text[]),
    gold.atualizar_relatorio_pibic(numeric),
    gold.atualizar_gold(integer, text[], integer, numeric)
FROM PUBLIC;
