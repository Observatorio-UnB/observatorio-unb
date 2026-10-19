-- ============================================================================
-- Migração 0022: agregações da gold em SQL nativo (ELT dentro do PostgreSQL)
--
-- Antes, src/pipeline/build_gold.py lia a silver para o pandas, agregava em memória e gravava o
-- resultado na gold. As mesmas regras viviam em Python e, em parte, em SQL
-- (src/db/povoar_dimensional.py). Aqui elas passam a existir só no banco:
--
--   gold.calcular_retencao(...)        -> linhas de gold.retencao_cursos_unb
--   gold.calcular_ativos_hoje(...)     -> linhas de gold.ativos_hoje_cursos_unb
--   gold.calcular_inep_benchmark(...)  -> linhas de gold.inep_benchmark_cursos_unb
--   gold.calcular_pibic_social()       -> linhas de gold.pibic_social_unb
--   gold.relatorio_*                   -> JSON de gold.relatorios
--   gold.materializar_gold(...)        -> procedure que grava tudo numa transação só
--
-- As tabelas gold continuam tabelas: têm CHECKs, são lidas pelo painel, pela view materializada,
-- pela sincronização com o Supabase e pelo CDC. O pipeline Python só carrega as regras de
-- harmonização (referência) e chama a procedure.
--
-- Paridade numérica com o pandas: os arredondamentos usam gold.arredondar_py (round() do Python,
-- meio para o par sobre o valor binário exato) e gold.arredondar_np (Series.round() do pandas),
-- e os percentis usam gold.quantil_linear (interpolação do numpy). Um round() do numeric
-- arredondaria 0,125 para 0,13 e o pandas, para 0,12.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Auxiliares de arredondamento e percentil
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION gold.arredondar_py(x double precision, casas integer)
RETURNS double precision
LANGUAGE plpgsql IMMUTABLE STRICT
AS $$
DECLARE
    b bytea;
    expoente integer;
    mantissa bigint;
    e integer;
    n numeric;
    d numeric;
    q numeric;
    r numeric;
BEGIN
    IF x = 'NaN'::float8 OR x = 'Infinity'::float8 OR x = '-Infinity'::float8 THEN
        RETURN NULL;
    END IF;
    IF x = 0 THEN
        RETURN 0;
    END IF;
    -- x = mantissa * 2^e, exato: os 8 bytes do IEEE 754 em ordem de rede.
    b := float8send(abs(x));
    expoente := ((get_byte(b, 0) & 127) << 4) | (get_byte(b, 1) >> 4);
    mantissa := ((get_byte(b, 1) & 15)::bigint << 48) | (get_byte(b, 2)::bigint << 40)
             | (get_byte(b, 3)::bigint << 32) | (get_byte(b, 4)::bigint << 24)
             | (get_byte(b, 5)::bigint << 16) | (get_byte(b, 6)::bigint << 8) | get_byte(b, 7)::bigint;
    IF expoente = 0 THEN
        e := -1074;
    ELSE
        mantissa := mantissa + (1::bigint << 52);
        e := expoente - 1075;
    END IF;
    n := mantissa::numeric * (10::numeric ^ casas);
    IF e >= 0 THEN
        q := n * (2::numeric ^ e);
    ELSE
        d := 2::numeric ^ (-e);
        q := div(n, d);
        r := n - q * d;
        IF 2 * r > d OR (2 * r = d AND mod(q, 2) = 1) THEN
            q := q + 1;
        END IF;
    END IF;
    RETURN sign(x) * (q / (10::numeric ^ casas))::double precision;
END
$$;
COMMENT ON FUNCTION gold.arredondar_py(double precision, integer) IS
  'Equivalente ao round(x, casas) do Python: arredonda o valor binário exato do double, empate para o par.';

CREATE OR REPLACE FUNCTION gold.arredondar_np(x double precision, casas integer)
RETURNS double precision
LANGUAGE sql IMMUTABLE STRICT
AS $$
    -- Series.round() do pandas: round(x * 10^casas) / 10^casas (round de double = rint, empate para o par).
    SELECT round(x * (10::double precision ^ casas)) / (10::double precision ^ casas)
$$;
COMMENT ON FUNCTION gold.arredondar_np(double precision, integer) IS
  'Equivalente ao Series.round(casas) do pandas (numpy.round).';

CREATE OR REPLACE FUNCTION gold.quantil_linear(valores double precision[], q double precision)
RETURNS double precision
LANGUAGE plpgsql IMMUTABLE
AS $$
DECLARE
    v double precision[];
    n integer;
    virtual double precision;
    anterior integer;
    gamma double precision;
    a double precision;
    b double precision;
    dif double precision;
BEGIN
    SELECT coalesce(array_agg(x ORDER BY x), '{}') INTO v FROM unnest(valores) AS x WHERE x IS NOT NULL;
    n := cardinality(v);
    IF n = 0 THEN
        RETURN NULL;
    END IF;
    virtual := (n - 1) * q;
    anterior := floor(virtual)::integer;
    gamma := virtual - anterior;
    a := v[anterior + 1];
    b := v[least(anterior + 1, n - 1) + 1];
    dif := b - a;
    IF gamma >= 0.5 THEN
        RETURN b - dif * (1 - gamma);
    END IF;
    RETURN a + dif * gamma;
END
$$;
COMMENT ON FUNCTION gold.quantil_linear(double precision[], double precision) IS
  'Quantil com interpolação linear, como o numpy.percentile (e o Series.quantile do pandas).';

-- ---------------------------------------------------------------------------
-- Normalizações de texto (ex-funções do build_gold.py)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION gold.turno_grupo(turno_norm text)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
    -- Matutino e vespertino viram DIURNO; noturno e integral são preservados.
    SELECT CASE WHEN coalesce(turno_norm, '') LIKE '%NOTURNO%' THEN 'NOTURNO'
                WHEN coalesce(turno_norm, '') LIKE '%INTEGRAL%' THEN 'INTEGRAL'
                ELSE 'DIURNO' END
$$;

CREATE OR REPLACE FUNCTION gold.categoria_grau(grau_norm text)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
    -- "LICENCIADO" no catálogo de 2022, "LICENCIATURA" nas versões seguintes.
    SELECT CASE WHEN coalesce(grau_norm, '') LIKE '%LICENCI%' THEN 'LICENCIATURA' ELSE 'BACHARELADO' END
$$;

CREATE OR REPLACE FUNCTION gold.campus_nome(campus_raw text)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
    -- Unifica as grafias de campus do SIGRA e do PIBIC nas denominações institucionais atuais.
    SELECT CASE WHEN coalesce(campus_raw, '') LIKE '%GAMA%' THEN 'FACULDADE DE CIENCIAS E TECNOLOGIAS EM ENGENHARIA (FCTE)'
                WHEN coalesce(campus_raw, '') LIKE '%CEILANDIA%' THEN 'FACULDADE DE CIENCIAS E TECNOLOGIAS EM SAUDE (FCTS)'
                WHEN coalesce(campus_raw, '') LIKE '%PLANALTINA%' THEN 'FACULDADE DE PLANALTINA (FUP)'
                ELSE 'DARCY RIBEIRO' END
$$;

COMMENT ON FUNCTION gold.turno_grupo(text) IS 'Unifica matutino/vespertino em DIURNO; preserva NOTURNO e INTEGRAL.';
COMMENT ON FUNCTION gold.categoria_grau(text) IS 'Agrupa a titulação em BACHARELADO ou LICENCIATURA.';
COMMENT ON FUNCTION gold.campus_nome(text) IS 'Unifica os nomes de campus entre SIGRA e PIBIC.';

-- ---------------------------------------------------------------------------
-- Views de apoio. Têm registro por vínculo ou por plano de IC: security_invoker faz valer o
-- privilégio de quem consulta (observatorio_leitura não lê silver), e não o do dono da view.
-- ---------------------------------------------------------------------------

-- Um vínculo por linha, já com o curso canônico e a matriz curricular (join com a estrutura).
CREATE OR REPLACE VIEW gold.vw_vinculos_canonicos WITH (security_invoker = true) AS
SELECT d.id,
       d._ordem,
       d.curso_norm,
       coalesce(r.destino_estrutura, d.curso_norm) AS curso_canonico,
       d.departamento_norm,
       d.ano_ingresso,
       d.tipo_saida_grupo,
       d.semestres_permanencia_valida AS permanencia,
       e.semestre_conclusao_minimo AS semestre_minimo,
       e.semestre_conclusao_ideal AS semestre_ideal,
       e.semestre_conclusao_maximo AS semestre_maximo,
       e.ch_total_minima,
       e.nome_curso_norm IS NOT NULL AS casou_estrutura
FROM silver.discentes_graduacao d
LEFT JOIN gold.regras_harmonizacao_canonicas r ON r.origem_sigra = d.curso_norm
LEFT JOIN silver.estrutura_curricular e ON e.nome_curso_norm = coalesce(r.destino_estrutura, d.curso_norm);
COMMENT ON VIEW gold.vw_vinculos_canonicos IS
  'Vínculos de silver.discentes_graduacao com o curso canônico (harmonização) e os prazos da matriz. Registro individual: sem acesso para observatorio_leitura.';

CREATE OR REPLACE VIEW gold.vw_catalogo_por_nome AS
SELECT nome_curso_norm,
       -- Primeiro valor não nulo na ordem catálogo vigente, menor id_curso (GroupBy.first do pandas).
       (array_agg(grau_academico_norm ORDER BY no_catalogo_vigente DESC, id_curso)
            FILTER (WHERE grau_academico_norm IS NOT NULL))[1] AS grau_academico,
       (array_agg(area_conhecimento_norm ORDER BY no_catalogo_vigente DESC, id_curso)
            FILTER (WHERE area_conhecimento_norm IS NOT NULL))[1] AS area_conhecimento,
       -- Bacharelado e licenciatura sob o mesmo nome (ver docs/dicionario_dados_gold.md, seção 2.1).
       count(DISTINCT gold.categoria_grau(grau_academico_norm)) > 1 AS misto
FROM silver.cursos_graduacao
GROUP BY nome_curso_norm;
COMMENT ON VIEW gold.vw_catalogo_por_nome IS
  'Catálogo de cursos deduplicado por nome: atributos da oferta principal e marca de curso com bacharelado e licenciatura (MISTO).';

-- Grande Área por nome de curso: a mais frequente no catálogo (empate: a primeira em ordem
-- alfabética). Curso-tronco sem entrada própria (ex.: COMUNICACAO SOCIAL) herda a área das
-- habilitações ("<tronco> - ..."), quando todas concordam.
CREATE OR REPLACE VIEW gold.vw_area_por_curso AS
WITH contagem AS (
    SELECT nome_curso_norm AS nome, area_conhecimento_norm AS area, count(*) AS n
    FROM silver.cursos_graduacao
    WHERE area_conhecimento_norm IS NOT NULL
    GROUP BY nome_curso_norm, area_conhecimento_norm
), propria AS (
    SELECT DISTINCT ON (nome) nome, area
    FROM contagem
    ORDER BY nome, n DESC, area COLLATE "C"
), troncos AS (
    SELECT curso_canonico AS nome FROM gold.vw_vinculos_canonicos
    UNION
    SELECT coalesce(r.destino_estrutura, p.curso_pibic_norm)
    FROM silver.pibic_bolsistas p
    LEFT JOIN gold.regras_harmonizacao_canonicas r ON r.origem_sigra = p.curso_pibic_norm
), herdada AS (
    SELECT t.nome, min(p.area) AS area
    FROM troncos t
    JOIN propria p ON left(p.nome, length(t.nome) + 3) = t.nome || ' - '
    WHERE t.nome <> ''
      AND NOT EXISTS (SELECT 1 FROM propria x WHERE x.nome = t.nome)
    GROUP BY t.nome
    HAVING count(DISTINCT p.area) = 1
)
SELECT nome, area FROM propria
UNION ALL
SELECT nome, area FROM herdada;
COMMENT ON VIEW gold.vw_area_por_curso IS
  'Grande Área (CNPq/MEC) por nome de curso, com herança das habilitações para os cursos-tronco.';

-- Nenhuma fonte liga o discente à oferta (turno/campus) em que estudou. Nome com oferta diurna e
-- noturna vira "DIURNO E NOTURNO"; com mais de um campus, "MULTICAMPUS".
CREATE OR REPLACE VIEW gold.vw_oferta_por_curso AS
WITH ofertas AS (
    SELECT nome_curso_norm AS nome,
           CASE WHEN turno_norm IS NOT NULL THEN gold.turno_grupo(turno_norm) END AS turno,
           CASE WHEN campus_norm IS NOT NULL THEN gold.campus_nome(campus_norm) END AS campus
    FROM silver.cursos_graduacao
)
SELECT nome,
       -- ponytail: hoje só há DIURNO+NOTURNO; outra combinação (ex.: com INTEGRAL) quebra o CHECK
       -- de gold.retencao_cursos_unb.turno de propósito, para ser tratada quando aparecer.
       coalesce(string_agg(DISTINCT turno, ' E ' ORDER BY turno), 'DIURNO') AS turno,
       CASE WHEN count(DISTINCT campus) > 1 THEN 'MULTICAMPUS'
            ELSE coalesce(min(campus), 'DARCY RIBEIRO') END AS campus
FROM ofertas
GROUP BY nome;
COMMENT ON VIEW gold.vw_oferta_por_curso IS
  'Turno e campus de cada nome de curso, considerando todas as ofertas do catálogo.';

-- Um plano de IC por linha, com campus padronizado, curso canônico e Grande Área.
CREATE OR REPLACE VIEW gold.vw_pibic_planos WITH (security_invoker = true) AS
SELECT p.id,
       p.ano,
       p.tipo_bolsa_norm,
       gold.campus_nome(p.campus) AS campus,
       coalesce(r.destino_estrutura, p.curso_pibic_norm) AS curso_canonico,
       CASE WHEN EXISTS (SELECT 1 FROM silver.cursos_graduacao)
            THEN coalesce(a.area, 'OUTRA')
            ELSE p.linha_pesquisa_norm END AS area_conhecimento,
       p.perfil_social_macro,
       p.cota_detalhe,
       p.faixa_renda,
       p.is_cotista,
       p.valor_bolsa_anual_estimado
FROM silver.pibic_bolsistas p
LEFT JOIN gold.regras_harmonizacao_canonicas r ON r.origem_sigra = p.curso_pibic_norm
LEFT JOIN gold.vw_area_por_curso a ON a.nome = coalesce(r.destino_estrutura, p.curso_pibic_norm);
COMMENT ON VIEW gold.vw_pibic_planos IS
  'Planos de IC (silver.pibic_bolsistas) com campus padronizado, curso canônico e Grande Área. Registro individual: sem acesso para observatorio_leitura.';

-- Vínculos das coortes que já tiveram tempo de concluir: ingresso até (último ano de ingresso -
-- p_anos_maturacao) e com matriz curricular casada.
CREATE OR REPLACE FUNCTION gold.vinculos_coortes_maduras(p_anos_maturacao integer)
RETURNS SETOF gold.vw_vinculos_canonicos
LANGUAGE sql STABLE
AS $$
    SELECT v.*
    FROM gold.vw_vinculos_canonicos v
    WHERE v.casou_estrutura
      AND v.ano_ingresso <= (SELECT max(ano_ingresso) FROM silver.discentes_graduacao) - p_anos_maturacao
$$;
COMMENT ON FUNCTION gold.vinculos_coortes_maduras(integer) IS
  'Vínculos com matriz casada e ingresso até (último ano de ingresso - p_anos_maturacao).';

-- ---------------------------------------------------------------------------
-- gold.retencao_cursos_unb
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION gold.calcular_retencao(p_anos_maturacao integer)
RETURNS SETOF gold.retencao_cursos_unb
LANGUAGE sql STABLE
AS $$
WITH por_curso AS (
    SELECT curso_canonico AS curso,
           count(*) AS total,
           count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA') AS n_formados,
           count(*) FILTER (WHERE tipo_saida_grupo = 'EVASAO') AS n_evadidos,
           count(*) FILTER (WHERE tipo_saida_grupo = 'ATIVO') AS n_ativos,
           -- Percentuais de prazo só sobre formados com permanência calculável (há formados do
           -- SIGAA sem data_registro_diploma); assim tempo ideal + acima do ideal somam 100%.
           count(permanencia) FILTER (WHERE tipo_saida_grupo = 'FORMATURA') AS n_com_prazo,
           count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA' AND permanencia <= semestre_minimo) AS c_minimo,
           count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA' AND permanencia <= semestre_ideal) AS c_ideal,
           count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA' AND permanencia > semestre_ideal) AS c_acima,
           count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA' AND permanencia >= semestre_maximo) AS c_maximo,
           avg(permanencia::double precision) FILTER (WHERE tipo_saida_grupo = 'FORMATURA') AS tempo_medio,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY permanencia::double precision)
               FILTER (WHERE tipo_saida_grupo = 'FORMATURA') AS tempo_mediano,
           avg((permanencia - semestre_ideal)::double precision)
               FILTER (WHERE tipo_saida_grupo = 'FORMATURA') AS desvio_medio,
           min(semestre_minimo) AS semestre_minimo,
           min(semestre_ideal) AS semestre_ideal,
           min(semestre_maximo) AS semestre_maximo,
           min(ch_total_minima) AS ch_total_minima,
           (array_agg(departamento_norm ORDER BY _ordem, id)
               FILTER (WHERE departamento_norm IS NOT NULL))[1] AS departamento
    FROM gold.vinculos_coortes_maduras(p_anos_maturacao)
    GROUP BY curso_canonico
    -- Supressão ética de grupos muito pequenos (k-anonimato, k < 5)
    HAVING count(*) >= 5
), taxas AS (
    -- A taxa de formatura usa round() do Python sobre int/int; as demais saem de contagens e médias do
    -- numpy, cujo round() é o do pandas (arredondar_np). Os dois diferem nos empates de meio.
    SELECT c.*,
           gold.arredondar_py(n_formados::double precision / total * 100, 2) AS taxa_formatura,
           gold.arredondar_np(n_evadidos::double precision / total * 100, 2) AS taxa_evasao,
           CASE WHEN n_com_prazo > 0 THEN gold.arredondar_np(c_minimo::double precision / n_com_prazo * 100, 2) ELSE 0 END AS pct_minimo,
           CASE WHEN n_com_prazo > 0 THEN gold.arredondar_np(c_ideal::double precision / n_com_prazo * 100, 2) ELSE 0 END AS pct_ideal,
           CASE WHEN n_com_prazo > 0 THEN gold.arredondar_np(c_acima::double precision / n_com_prazo * 100, 2) ELSE 0 END AS pct_acima,
           CASE WHEN n_com_prazo > 0 THEN gold.arredondar_np(c_maximo::double precision / n_com_prazo * 100, 2) ELSE 0 END AS pct_maximo,
           CASE WHEN n_com_prazo > 0 THEN gold.arredondar_np(tempo_medio, 2) END AS tempo_medio_r,
           CASE WHEN n_com_prazo > 0 THEN gold.arredondar_np(tempo_mediano, 2) END AS tempo_mediano_r,
           CASE WHEN n_com_prazo > 0 THEN gold.arredondar_np(desvio_medio, 2) END AS desvio_medio_r
    FROM por_curso c
), entradas AS (
    -- IRC combina atraso médio (desvio, sem valores negativos) e taxa de evasão, já arredondados.
    SELECT t.*,
           greatest(coalesce(desvio_medio_r, 0), 0) AS x_atraso,
           taxa_evasao AS x_evasao
    FROM taxas t
), limites AS (
    -- Normalização min-max robusta: satura nos percentis 5/95 antes de normalizar, para que um
    -- único curso outlier (ex.: Engenharia com 93% de evasão) não comprima a escala dos demais.
    SELECT gold.quantil_linear(array_agg(x_atraso), 0.05) AS a05,
           gold.quantil_linear(array_agg(x_atraso), 0.95) AS a95,
           gold.quantil_linear(array_agg(x_evasao), 0.05) AS e05,
           gold.quantil_linear(array_agg(x_evasao), 0.95) AS e95
    FROM entradas
), saturados AS (
    SELECT e.*,
           least(greatest(x_atraso, a05), a95) AS s_atraso,
           least(greatest(x_evasao, e05), e95) AS s_evasao
    FROM entradas e CROSS JOIN limites
), irc AS (
    -- Evasão pesa mais que atraso: perder o aluno é mais grave para o DEG do que ele se formar
    -- mais devagar, que ainda é uma conclusão bem-sucedida.
    SELECT s.*,
           gold.arredondar_np(
               (0.3 * ((s_atraso - min(s_atraso) OVER ()) / (max(s_atraso) OVER () - min(s_atraso) OVER () + 1e-6))
              + 0.7 * ((s_evasao - min(s_evasao) OVER ()) / (max(s_evasao) OVER () - min(s_evasao) OVER () + 1e-6)))
               * 100, 1) AS indice
    FROM saturados s
), quartis AS (
    SELECT gold.quantil_linear(array_agg(indice), 0.25) AS q25,
           gold.quantil_linear(array_agg(indice), 0.50) AS q50,
           gold.quantil_linear(array_agg(indice), 0.75) AS q75
    FROM irc
), pibic AS (
    SELECT coalesce(r.destino_estrutura, p.curso_pibic_norm) AS curso,
           count(*) AS projetos,
           count(*) FILTER (WHERE p.tipo_bolsa_norm = 'REMUNERADA') AS remuneradas,
           count(*) FILTER (WHERE p.tipo_bolsa_norm = 'VOLUNTARIA') AS voluntarias,
           count(*) FILTER (WHERE p.is_cotista) AS cotistas,
           sum(p.valor_bolsa_anual_estimado) AS investimento
    FROM silver.pibic_bolsistas p
    LEFT JOIN gold.regras_harmonizacao_canonicas r ON r.origem_sigra = p.curso_pibic_norm
    GROUP BY 1
), com_metadados AS (
    SELECT i.*,
           q.q25, q.q50, q.q75,
           coalesce(o.turno, 'DIURNO') AS turno,
           coalesce(o.campus, 'DARCY RIBEIRO') AS campus,
           coalesce(cat.area_conhecimento, ar.area, 'OUTRA') AS area,
           coalesce(cat.grau_academico, 'BACHAREL') AS grau_raw,
           coalesce(cat.misto, false) AS misto,
           coalesce(i.departamento, 'UNB') AS depto,
           pb.projetos, pb.remuneradas, pb.voluntarias, pb.cotistas, pb.investimento,
           EXISTS (SELECT 1 FROM silver.pibic_bolsistas) AS tem_pibic
    FROM irc i
    CROSS JOIN quartis q
    LEFT JOIN gold.vw_oferta_por_curso o ON o.nome = i.curso
    LEFT JOIN gold.vw_catalogo_por_nome cat ON cat.nome_curso_norm = i.curso
    LEFT JOIN gold.vw_area_por_curso ar ON ar.nome = i.curso
    LEFT JOIN pibic pb ON pb.curso = i.curso
)
SELECT curso,
       depto,
       campus,
       turno,
       area,
       -- Curso com Bacharelado e Licenciatura sob o mesmo nome, mas sem forma confiável de separar os
       -- discentes: não assume um grau único arbitrário.
       CASE WHEN misto THEN 'MISTO (BACHARELADO + LICENCIATURA)' ELSE grau_raw END,
       CASE WHEN misto THEN 'MISTO' ELSE gold.categoria_grau(grau_raw) END,
       semestre_minimo::numeric(4,1),
       semestre_ideal::numeric(4,1),
       semestre_maximo::numeric(4,1),
       ch_total_minima::integer,
       total::integer,
       n_formados::integer,
       n_evadidos::integer,
       taxa_formatura::numeric(5,2),
       taxa_evasao::numeric(5,2),
       pct_minimo::numeric(5,2),
       pct_ideal::numeric(5,2),
       pct_acima::numeric(5,2),
       pct_maximo::numeric(5,2),
       tempo_medio_r::numeric(5,2),
       tempo_mediano_r::numeric(5,2),
       desvio_medio_r::numeric(5,2),
       indice::numeric(4,1),
       CASE WHEN indice >= q75 THEN 'RETENÇÃO CRÍTICA'
            WHEN indice >= q50 THEN 'RETENÇÃO ALTA'
            WHEN indice >= q25 THEN 'RETENÇÃO MÉDIA'
            ELSE 'RETENÇÃO BAIXA' END,
       CASE WHEN tem_pibic THEN coalesce(projetos, 0) END::integer,
       remuneradas::integer,
       voluntarias::integer,
       cotistas::integer,
       CASE WHEN tem_pibic THEN coalesce(investimento, 0) END::numeric(14,2),
       CASE WHEN tem_pibic THEN gold.arredondar_np(coalesce(projetos, 0)::double precision / total * 100, 2) END::numeric(7,2),
       n_ativos::integer,
       (row_number() OVER (ORDER BY indice DESC, curso COLLATE "C"))::integer
FROM com_metadados
ORDER BY indice DESC, curso COLLATE "C"
$$;
COMMENT ON FUNCTION gold.calcular_retencao(integer) IS
  'Retenção, formatura e evasão por curso canônico nas coortes maduras (k >= 5), com IRC, quartis e PIBIC. Substitui a agregação em pandas do build_gold.py.';

-- ---------------------------------------------------------------------------
-- gold.ativos_hoje_cursos_unb
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION gold.calcular_ativos_hoje(p_cursos_excluidos text[])
RETURNS SETOF gold.ativos_hoje_cursos_unb
LANGUAGE sql STABLE
AS $$
WITH referencia AS (
    SELECT (array_agg(periodo_referencia ORDER BY _ordem, id))[1] AS periodo FROM silver.sigaa_ativos
), ativos AS (
    SELECT coalesce(r.destino_estrutura, a.curso_norm) AS curso, a.semestres_cursados,
           e.semestre_conclusao_ideal AS ideal, e.semestre_conclusao_maximo AS maximo
    FROM silver.sigaa_ativos a
    LEFT JOIN gold.regras_harmonizacao_canonicas r ON r.origem_sigra = a.curso_norm
    JOIN silver.estrutura_curricular e ON e.nome_curso_norm = coalesce(r.destino_estrutura, a.curso_norm)
    -- Cursos-tronco ficam de fora: o aluno escolhe a habilitação no meio do curso, e o prazo máximo
    -- do tronco de Engenharia (3) é menor que o ideal (5), o que não mede atraso.
    WHERE NOT coalesce(r.destino_estrutura, a.curso_norm) = ANY (p_cursos_excluidos)
), por_curso AS (
    SELECT curso,
           min(ideal) AS ideal,
           min(maximo) AS maximo,
           count(*) AS total,
           count(*) FILTER (WHERE semestres_cursados > ideal) AS acima_ideal,
           count(*) FILTER (WHERE semestres_cursados > maximo) AS acima_maximo
    FROM ativos
    GROUP BY curso
    -- k-anonimato, como na tabela de retenção
    HAVING count(*) >= 5
)
SELECT curso,
       (SELECT periodo FROM referencia),
       ideal::numeric(4,1),
       maximo::numeric(4,1),
       total::integer,
       acima_ideal::integer,
       acima_maximo::integer,
       gold.arredondar_np(acima_ideal::double precision / total * 100, 2)::numeric(5,2),
       (row_number() OVER (ORDER BY gold.arredondar_np(acima_ideal::double precision / total * 100, 2) DESC,
                                    curso COLLATE "C"))::integer
FROM por_curso
ORDER BY 8 DESC, curso COLLATE "C"
$$;
COMMENT ON FUNCTION gold.calcular_ativos_hoje(text[]) IS
  'Discentes ativos no semestre mais recente publicado, por curso, e quem já passou do prazo ideal e do máximo (k >= 5).';

-- ---------------------------------------------------------------------------
-- gold.inep_benchmark_cursos_unb
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION gold.calcular_inep_benchmark(p_min_matriculas integer)
RETURNS SETOF gold.inep_benchmark_cursos_unb
LANGUAGE sql STABLE
AS $$
WITH por_ies AS (
    -- O Censo registra cada oferta (turno/campus) como um curso distinto. Somar as ofertas da
    -- mesma instituição compara UnB e federais na mesma unidade (curso x instituição). O corte de
    -- tamanho vale para o curso já somado: aplicado por oferta, descartaria turnos pequenos.
    SELECT "NO_CURSO" AS curso, "CO_IES" AS ies, is_unb,
           coalesce(sum("QT_MAT"), 0) AS matriculas,
           coalesce(sum("QT_ING"), 0) AS ingressantes,
           coalesce(sum("QT_CONC"), 0) AS concluintes,
           coalesce(sum("QT_SIT_TRANCADA"), 0) AS trancadas,
           coalesce(sum("QT_SIT_DESVINCULADO"), 0) AS desvinculados,
           coalesce(sum("QT_VG_TOTAL"), 0) AS vagas,
           coalesce(sum("QT_INSCRITO_TOTAL"), 0) AS inscritos
    FROM silver.inep_censo_superior
    GROUP BY "NO_CURSO", "CO_IES", is_unb
    HAVING coalesce(sum("QT_MAT"), 0) >= p_min_matriculas
), taxas AS (
    SELECT *,
           trancadas::double precision / nullif(matriculas, 0) * 100 AS taxa_trancamento,
           desvinculados::double precision / nullif(matriculas, 0) * 100 AS taxa_desvinculacao,
           inscritos::double precision / nullif(vagas, 0) AS concorrencia
    FROM por_ies
), unb AS (
    SELECT curso, matriculas, ingressantes, concluintes, trancadas, desvinculados, vagas, inscritos,
           gold.arredondar_np(taxa_trancamento, 2) AS taxa_trancamento,
           gold.arredondar_np(taxa_desvinculacao, 2) AS taxa_desvinculacao,
           gold.arredondar_np(concorrencia, 2) AS concorrencia
    FROM taxas
    WHERE is_unb
), pares AS (
    -- Mediana, e não média, para uma instituição atípica não distorcer o padrão do curso.
    SELECT curso,
           count(DISTINCT ies) AS n_ies,
           gold.arredondar_np(percentile_cont(0.5) WITHIN GROUP (ORDER BY taxa_trancamento), 2) AS mediana_trancamento,
           gold.arredondar_np(percentile_cont(0.5) WITHIN GROUP (ORDER BY taxa_desvinculacao), 2) AS mediana_desvinculacao
    FROM taxas
    WHERE NOT is_unb
    GROUP BY curso
)
SELECT u.curso,
       u.matriculas::integer,
       u.ingressantes::integer,
       u.concluintes::integer,
       u.trancadas::integer,
       u.desvinculados::integer,
       u.vagas::integer,
       u.inscritos::integer,
       u.taxa_trancamento::numeric(6,2),
       u.taxa_desvinculacao::numeric(6,2),
       u.concorrencia::numeric(8,2),
       p.n_ies::integer,
       p.mediana_trancamento::numeric(6,2),
       p.mediana_desvinculacao::numeric(6,2),
       -- A diferença em pontos percentuais achata a gravidade relativa (+6 pp sobre um curso que já
       -- perde 24% pesa menos que +7 pp sobre um que perde 8%); a razão expõe isso.
       gold.arredondar_np(u.taxa_trancamento - p.mediana_trancamento, 2)::numeric(6,2),
       gold.arredondar_np(u.taxa_desvinculacao - p.mediana_desvinculacao, 2)::numeric(6,2),
       CASE WHEN p.mediana_trancamento <> 0
            THEN gold.arredondar_np(u.taxa_trancamento / p.mediana_trancamento, 2) END::numeric(8,2),
       CASE WHEN p.mediana_desvinculacao <> 0
            THEN gold.arredondar_np(u.taxa_desvinculacao / p.mediana_desvinculacao, 2) END::numeric(8,2),
       (row_number() OVER (ORDER BY u.matriculas DESC, u.curso COLLATE "C"))::integer
FROM unb u
LEFT JOIN pares p ON p.curso = u.curso
ORDER BY u.matriculas DESC, u.curso COLLATE "C"
$$;
COMMENT ON FUNCTION gold.calcular_inep_benchmark(integer) IS
  'Cada curso da UnB contra a mediana do mesmo curso nas demais federais (Censo da Educação Superior/INEP).';

-- ---------------------------------------------------------------------------
-- gold.pibic_social_unb
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION gold.calcular_pibic_social()
RETURNS SETOF gold.pibic_social_unb
LANGUAGE sql STABLE
AS $$
WITH por_curso AS (
    SELECT curso_canonico AS curso, campus, area_conhecimento AS area,
           count(*) AS projetos,
           count(*) FILTER (WHERE tipo_bolsa_norm = 'REMUNERADA') AS remuneradas,
           count(*) FILTER (WHERE tipo_bolsa_norm = 'VOLUNTARIA') AS voluntarias,
           count(*) FILTER (WHERE is_cotista) AS cotistas,
           count(*) FILTER (WHERE perfil_social_macro = 'PPI / ETNICO-RACIAL') AS cotistas_ppi,
           count(*) FILTER (WHERE faixa_renda = 'BAIXA RENDA (<= 1.5 SM)') AS baixa_renda,
           sum(valor_bolsa_anual_estimado) AS investido
    FROM gold.vw_pibic_planos
    WHERE curso_canonico IS NOT NULL AND area_conhecimento IS NOT NULL
    GROUP BY curso_canonico, campus, area_conhecimento
)
SELECT curso, campus, area,
       projetos::integer,
       remuneradas::integer,
       voluntarias::integer,
       cotistas::integer,
       cotistas_ppi::integer,
       baixa_renda::integer,
       investido::numeric(14,2),
       gold.arredondar_np(cotistas::double precision / projetos * 100, 1)::numeric(5,2),
       gold.arredondar_np(voluntarias::double precision / projetos * 100, 1)::numeric(5,2),
       (row_number() OVER (ORDER BY projetos DESC, curso COLLATE "C", campus COLLATE "C", area COLLATE "C"))::integer
FROM por_curso
-- Exclui registros sem nome de curso e aplica a supressão ética k < 5
WHERE curso <> '' AND projetos >= 5
ORDER BY projetos DESC, curso COLLATE "C", campus COLLATE "C", area COLLATE "C"
$$;
COMMENT ON FUNCTION gold.calcular_pibic_social() IS
  'Iniciação científica por curso, campus e Grande Área: volume, bolsas e perfil social (k >= 5).';

-- ---------------------------------------------------------------------------
-- Relatórios JSON (gold.relatorios)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION gold.relatorio_regras_harmonizacao()
RETURNS jsonb
LANGUAGE sql STABLE
AS $$
    SELECT jsonb_build_object(
        'total_regras', count(*),
        'total_discentes_harmonizados', coalesce(sum(discentes_impactados), 0),
        'metodologia', 'Entity Resolution e Harmonização Canônica (SIGRA/SIGAA -> Matrizes Curriculares Ativas)',
        'regras', coalesce(jsonb_agg(jsonb_build_object(
            'origem_sigra', origem_sigra,
            'destino_estrutura', destino_estrutura,
            'categoria', categoria,
            'justificativa', justificativa,
            'discentes_impactados', discentes_impactados
        ) ORDER BY discentes_impactados DESC, _ordem), '[]'::jsonb))
    FROM gold.regras_harmonizacao_canonicas
$$;

CREATE OR REPLACE FUNCTION gold.relatorio_casamento_joins()
RETURNS jsonb
LANGUAGE sql STABLE
AS $$
WITH totais AS (
    SELECT count(*) AS total,
           count(*) FILTER (WHERE casou_estrutura) AS casados
    FROM gold.vw_vinculos_canonicos
), nao_casados AS (
    SELECT coalesce(jsonb_object_agg(curso_norm, n), '{}'::jsonb) AS cursos
    FROM (SELECT curso_norm, count(*) AS n
          FROM gold.vw_vinculos_canonicos
          WHERE NOT casou_estrutura
          GROUP BY curso_norm
          ORDER BY n DESC, curso_norm COLLATE "C"
          LIMIT 10) t
), harmonizados AS (
    SELECT coalesce(sum(discentes_impactados), 0) AS total FROM gold.regras_harmonizacao_canonicas
)
SELECT jsonb_build_object(
    'total_discentes_graduacao', t.total,
    'discentes_com_estrutura_casada', t.casados,
    'discentes_sem_casamento', t.total - t.casados,
    'taxa_de_casamento_pct', gold.arredondar_py(t.casados::double precision / t.total * 100, 2),
    'cursos_nao_casados_principais', n.cursos,
    'harmonizacao_ativa', true,
    'total_discentes_harmonizados', h.total,
    'justificativa_descartes', CASE WHEN t.total = t.casados THEN
        'Taxa de 100.00% alcançada através de Harmonização Canônica transparente '
        'e auditável de regras de equivalência entre os sistemas acadêmicos (SIGRA e SIGAA) e matrizes curriculares ativas. '
        'Zero registros descartados.'
        ELSE (t.total - t.casados) || ' registros não casados restantes.' END
)
FROM totais t, nao_casados n, harmonizados h
$$;

CREATE OR REPLACE FUNCTION gold.relatorio_metricas_gerais(
    p_anos_maturacao integer, p_cursos_excluidos text[], p_periodo_ativos text)
RETURNS jsonb
LANGUAGE sql STABLE
AS $$
WITH v AS (
    SELECT * FROM gold.vinculos_coortes_maduras(p_anos_maturacao)
), g AS (
    SELECT min(ano_ingresso) AS primeira,
           (SELECT max(ano_ingresso) FROM silver.discentes_graduacao) - p_anos_maturacao AS ultima,
           count(*) AS total,
           count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA') AS formados,
           count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA' AND permanencia <= semestre_ideal) AS no_ideal,
           count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA' AND permanencia > semestre_ideal) AS acima,
           count(permanencia) FILTER (WHERE tipo_saida_grupo = 'FORMATURA') AS com_prazo,
           avg(permanencia::double precision) FILTER (WHERE tipo_saida_grupo = 'FORMATURA') AS tempo_medio,
           avg((permanencia - semestre_ideal)::double precision) FILTER (WHERE tipo_saida_grupo = 'FORMATURA') AS desvio_medio
    FROM v
), ativos AS (
    SELECT coalesce(sum(total_ativos_hoje), 0) AS total,
           coalesce(sum(ativos_acima_prazo_ideal), 0) AS acima_ideal,
           coalesce(sum(ativos_acima_prazo_maximo), 0) AS acima_maximo
    FROM gold.ativos_hoje_cursos_unb
    WHERE p_periodo_ativos <> ''
), maior_retencao AS (
    SELECT coalesce(jsonb_agg(jsonb_build_object(
               'curso', curso,
               'tempo_medio_real_semestres', tempo_medio_real_semestres,
               'taxa_evasao_pct', taxa_evasao_pct,
               'indice_retencao_critica', indice_retencao_critica) ORDER BY _ordem), '[]'::jsonb) AS lista
    FROM (SELECT * FROM gold.retencao_cursos_unb ORDER BY _ordem LIMIT 5) t
), mais_pontuais AS (
    SELECT coalesce(jsonb_agg(jsonb_build_object(
               'curso', curso,
               'formados_tempo_ideal_pct', formados_tempo_ideal_pct,
               'tempo_medio_real_semestres', tempo_medio_real_semestres) ORDER BY formados_tempo_ideal_pct DESC, _ordem), '[]'::jsonb) AS lista
    FROM (SELECT * FROM gold.retencao_cursos_unb ORDER BY formados_tempo_ideal_pct DESC, _ordem LIMIT 5) t
)
SELECT jsonb_build_object(
    'coortes_ingresso_analisadas', g.primeira || '-' || g.ultima,
    'total_discentes_analisados', g.total,
    'total_formados_unb', g.formados,
    'taxa_conclusao_tempo_ideal_global_pct', gold.arredondar_py(g.no_ideal::double precision / nullif(g.com_prazo, 0) * 100, 2),
    'taxa_conclusao_acima_ideal_global_pct', gold.arredondar_py(g.acima::double precision / nullif(g.com_prazo, 0) * 100, 2),
    'tempo_medio_formatura_global_semestres', gold.arredondar_np(g.tempo_medio, 2),
    'desvio_medio_global_semestres', gold.arredondar_np(g.desvio_medio, 2),
    'top_5_cursos_maior_retencao', m.lista,
    'cursos_tronco', (SELECT coalesce(jsonb_agg(c ORDER BY c COLLATE "C"), '[]'::jsonb) FROM unnest(p_cursos_excluidos) c),
    'ativos_hoje_referencia', p_periodo_ativos,
    'ativos_hoje_total', a.total,
    'ativos_hoje_acima_prazo_ideal', a.acima_ideal,
    'ativos_hoje_acima_prazo_maximo', a.acima_maximo,
    'top_5_cursos_maior_pontualidade', p.lista
)
FROM g, ativos a, maior_retencao m, mais_pontuais p
$$;

CREATE OR REPLACE FUNCTION gold.relatorio_pibic(p_valor_bolsa_mensal numeric)
RETURNS jsonb
LANGUAGE sql STABLE
AS $$
WITH planos AS (
    SELECT * FROM gold.vw_pibic_planos
), g AS (
    SELECT count(*) AS total,
           count(*) FILTER (WHERE tipo_bolsa_norm = 'REMUNERADA') AS remuneradas,
           count(*) FILTER (WHERE tipo_bolsa_norm = 'VOLUNTARIA') AS voluntarias,
           count(*) FILTER (WHERE is_cotista) AS cotistas,
           sum(valor_bolsa_anual_estimado) AS investido
    FROM planos
), social AS (
    -- Proporção sobre os planos com perfil informado (value_counts(normalize=True) descarta nulos).
    SELECT coalesce(jsonb_object_agg(perfil_social_macro, pct), '{}'::jsonb) AS dist
    FROM (SELECT perfil_social_macro,
                 gold.arredondar_np(n::double precision / sum(n) OVER () * 100, 2) AS pct
          FROM (SELECT perfil_social_macro, count(*) AS n FROM planos
                WHERE perfil_social_macro IS NOT NULL GROUP BY 1) c) t
), cotas AS (
    SELECT coalesce(jsonb_object_agg(cota_detalhe, n), '{}'::jsonb) AS dist
    FROM (SELECT cota_detalhe, count(*) AS n FROM planos WHERE cota_detalhe IS NOT NULL GROUP BY 1) t
), campi AS (
    SELECT coalesce(jsonb_agg(jsonb_build_object(
               'campus', campus,
               'total_projetos', projetos,
               'total_remuneradas', remuneradas,
               'total_cotistas', cotistas,
               'valor_investido', investido,
               'pct_projetos', gold.arredondar_np(projetos::double precision / (SELECT total FROM g) * 100, 2),
               'pct_cotistas', gold.arredondar_np(cotistas::double precision / projetos * 100, 2)
           ) ORDER BY campus COLLATE "C"), '[]'::jsonb) AS lista
    FROM (SELECT campus, count(*) AS projetos,
                 count(*) FILTER (WHERE tipo_bolsa_norm = 'REMUNERADA') AS remuneradas,
                 count(*) FILTER (WHERE is_cotista) AS cotistas,
                 sum(valor_bolsa_anual_estimado) AS investido
          FROM planos GROUP BY campus) t
), alunos AS (
    SELECT area_conhecimento AS area, sum(total_discentes_registrados) AS alunos
    FROM gold.retencao_cursos_unb GROUP BY area_conhecimento
), areas AS (
    SELECT coalesce(jsonb_agg(
               jsonb_build_object(
                   'area_conhecimento', t.area,
                   'total_projetos', t.projetos,
                   'total_remuneradas', t.remuneradas,
                   'total_cotistas', t.cotistas,
                   'valor_investido', t.investido,
                   'pct_projetos', gold.arredondar_np(t.projetos::double precision / (SELECT total FROM g) * 100, 2),
                   'pct_cotistas', gold.arredondar_np(t.cotistas::double precision / t.projetos * 100, 2))
               -- Taxa de participação: projetos de IC / alunos matriculados na área (não só a composição
               -- do programa). "OUTRA" (curso não classificado) não tem alunos; vira null, e não 0%.
               || CASE WHEN EXISTS (SELECT 1 FROM gold.retencao_cursos_unb) THEN
                      jsonb_build_object(
                          'total_discentes_area', coalesce(al.alunos, 0),
                          'taxa_participacao_pibic_pct',
                          CASE WHEN coalesce(al.alunos, 0) > 0
                               THEN gold.arredondar_np(t.projetos::double precision / al.alunos * 100, 2) END)
                  ELSE '{}'::jsonb END
               ORDER BY t.area COLLATE "C"), '[]'::jsonb) AS lista
    FROM (SELECT area_conhecimento AS area, count(*) AS projetos,
                 count(*) FILTER (WHERE tipo_bolsa_norm = 'REMUNERADA') AS remuneradas,
                 count(*) FILTER (WHERE is_cotista) AS cotistas,
                 sum(valor_bolsa_anual_estimado) AS investido
          FROM planos WHERE area_conhecimento IS NOT NULL GROUP BY area_conhecimento) t
    LEFT JOIN alunos al ON al.area = t.area
), anos AS (
    SELECT coalesce(jsonb_agg(jsonb_build_object(
               'ano', ano,
               'total_projetos', projetos,
               'remuneradas', remuneradas,
               'voluntarias', voluntarias,
               'cotistas', cotistas,
               'investimento_reais', investido) ORDER BY ano), '[]'::jsonb) AS lista
    FROM (SELECT ano, count(*) AS projetos,
                 count(*) FILTER (WHERE tipo_bolsa_norm = 'REMUNERADA') AS remuneradas,
                 count(*) FILTER (WHERE tipo_bolsa_norm = 'VOLUNTARIA') AS voluntarias,
                 count(*) FILTER (WHERE is_cotista) AS cotistas,
                 sum(valor_bolsa_anual_estimado) AS investido
          FROM planos GROUP BY ano) t
)
SELECT jsonb_build_object(
    'total_projetos_ic', g.total,
    'total_bolsas_remuneradas', g.remuneradas,
    'total_pesquisadores_voluntarios_pivic', g.voluntarias,
    'investimento_publico_total_estimado', g.investido,
    'total_cotistas', g.cotistas,
    'taxa_inclusao_cotistas_pct', gold.arredondar_py(g.cotistas::double precision / g.total * 100, 2),
    'taxa_trabalho_voluntario_pct', gold.arredondar_py(g.voluntarias::double precision / g.total * 100, 2),
    'distribuicao_perfil_social_pct', s.dist,
    'distribuicao_cota_detalhe', c.dist,
    'distribuicao_campi', ca.lista,
    'distribuicao_grande_area', ar.lista,
    'evolucao_anual', an.lista,
    -- Valor mensal em vigor na coleta mais recente da tabela do CNPq (simulador do painel).
    'valor_bolsa_ic_mensal_vigente', p_valor_bolsa_mensal
)
FROM g, social s, cotas c, campi ca, areas ar, anos an
$$;

COMMENT ON FUNCTION gold.relatorio_regras_harmonizacao() IS 'JSON do relatório regras_harmonizacao_canonicas.';
COMMENT ON FUNCTION gold.relatorio_casamento_joins() IS 'JSON do relatório relatorio_casamento_joins (taxa de casamento dos joins).';
COMMENT ON FUNCTION gold.relatorio_metricas_gerais(integer, text[], text) IS 'JSON do relatório metricas_gerais_unb.';
COMMENT ON FUNCTION gold.relatorio_pibic(numeric) IS 'JSON do relatório pibic_metricas_gerais.';

-- ---------------------------------------------------------------------------
-- Procedure de materialização
-- ---------------------------------------------------------------------------

CREATE OR REPLACE PROCEDURE gold.materializar_gold(
    p_anos_maturacao integer,
    p_cursos_excluidos text[],
    p_min_matriculas_benchmark integer,
    p_valor_bolsa_ic_mensal numeric DEFAULT NULL)
LANGUAGE plpgsql
AS $$
DECLARE
    v_periodo_ativos text := '';
    v_total bigint;
    v_casados bigint;
    v_primeira smallint;
    v_ultima integer;
    v_n bigint;
    v_vinculos bigint;
BEGIN
    -- Regras de harmonização: o pipeline as carrega (ordem de cadastro em _ordem); aqui entram as
    -- contagens de vínculos afetados por cada uma.
    UPDATE gold.regras_harmonizacao_canonicas r
    SET discentes_impactados = coalesce(c.n, 0)
    FROM (SELECT r2.origem_sigra, count(d.id) AS n
          FROM gold.regras_harmonizacao_canonicas r2
          LEFT JOIN silver.discentes_graduacao d ON d.curso_norm = r2.origem_sigra
          GROUP BY r2.origem_sigra) c
    WHERE c.origem_sigra = r.origem_sigra;

    -- A tabela fica na ordem do relatório: mais vínculos afetados primeiro, empate na ordem de cadastro.
    UPDATE gold.regras_harmonizacao_canonicas r
    SET _ordem = o.nova
    FROM (SELECT origem_sigra,
                 (row_number() OVER (ORDER BY discentes_impactados DESC, _ordem))::integer AS nova
          FROM gold.regras_harmonizacao_canonicas) o
    WHERE o.origem_sigra = r.origem_sigra;

    IF NOT EXISTS (SELECT 1 FROM silver.discentes_graduacao) THEN
        RAISE WARNING 'silver.discentes_graduacao está vazia. Pulando construção da camada Gold.';
    ELSE
        INSERT INTO gold.relatorios (nome, conteudo)
        VALUES ('regras_harmonizacao_canonicas', gold.relatorio_regras_harmonizacao())
        ON CONFLICT (nome) DO UPDATE SET conteudo = EXCLUDED.conteudo, _carregado_em = now();

        INSERT INTO gold.relatorios (nome, conteudo)
        VALUES ('relatorio_casamento_joins', gold.relatorio_casamento_joins())
        ON CONFLICT (nome) DO UPDATE SET conteudo = EXCLUDED.conteudo, _carregado_em = now();
        SELECT count(*), count(*) FILTER (WHERE casou_estrutura) INTO v_total, v_casados
        FROM gold.vw_vinculos_canonicos;
        RAISE NOTICE 'Taxa de Casamento dos Joins: % (%/% discentes)',
            round(v_casados * 100.0 / v_total, 2) || '%', v_casados, v_total;

        -- Retrato dos ativos no semestre mais recente publicado
        IF EXISTS (SELECT 1 FROM silver.sigaa_ativos) THEN
            SELECT (array_agg(periodo_referencia ORDER BY _ordem, id))[1] INTO v_periodo_ativos
            FROM silver.sigaa_ativos;
            TRUNCATE gold.ativos_hoje_cursos_unb;
            INSERT INTO gold.ativos_hoje_cursos_unb SELECT * FROM gold.calcular_ativos_hoje(p_cursos_excluidos);
            GET DIAGNOSTICS v_n = ROW_COUNT;
            RAISE NOTICE 'Ativos hoje (%) gravados em gold.ativos_hoje_cursos_unb: % cursos.', v_periodo_ativos, v_n;
        ELSE
            RAISE WARNING 'silver.sigaa_ativos está vazia. Pulando Ativos Hoje.';
        END IF;

        TRUNCATE gold.retencao_cursos_unb;
        INSERT INTO gold.retencao_cursos_unb SELECT * FROM gold.calcular_retencao(p_anos_maturacao);
        GET DIAGNOSTICS v_n = ROW_COUNT;
        RAISE NOTICE 'Tabela analítica Gold gravada em gold.retencao_cursos_unb com % cursos.', v_n;
        SELECT min(ano_ingresso), count(*) INTO v_primeira, v_vinculos FROM gold.vinculos_coortes_maduras(p_anos_maturacao);
        SELECT max(ano_ingresso) - p_anos_maturacao INTO v_ultima FROM silver.discentes_graduacao;
        RAISE NOTICE 'Coortes analisadas: %-% (% vínculos).', v_primeira, v_ultima, v_vinculos;

        -- Benchmark nacional (Censo da Educação Superior / INEP)
        TRUNCATE gold.inep_benchmark_cursos_unb;
        IF EXISTS (SELECT 1 FROM silver.inep_censo_superior) THEN
            INSERT INTO gold.inep_benchmark_cursos_unb SELECT * FROM gold.calcular_inep_benchmark(p_min_matriculas_benchmark);
            GET DIAGNOSTICS v_n = ROW_COUNT;
            RAISE NOTICE 'Benchmark INEP gravado em gold.inep_benchmark_cursos_unb: % cursos da UnB.', v_n;
        ELSE
            RAISE WARNING 'silver.inep_censo_superior está vazia. Pulando benchmark INEP.';
        END IF;

        INSERT INTO gold.relatorios (nome, conteudo)
        VALUES ('metricas_gerais_unb',
                gold.relatorio_metricas_gerais(p_anos_maturacao, p_cursos_excluidos, v_periodo_ativos))
        ON CONFLICT (nome) DO UPDATE SET conteudo = EXCLUDED.conteudo, _carregado_em = now();
    END IF;

    -- PIBIC (lê gold.retencao_cursos_unb para a taxa de participação por área)
    TRUNCATE gold.pibic_social_unb;
    IF EXISTS (SELECT 1 FROM silver.pibic_bolsistas) THEN
        INSERT INTO gold.pibic_social_unb SELECT * FROM gold.calcular_pibic_social();
        GET DIAGNOSTICS v_n = ROW_COUNT;
        INSERT INTO gold.relatorios (nome, conteudo)
        VALUES ('pibic_metricas_gerais', gold.relatorio_pibic(p_valor_bolsa_ic_mensal))
        ON CONFLICT (nome) DO UPDATE SET conteudo = EXCLUDED.conteudo, _carregado_em = now();
        RAISE NOTICE 'Tabela Gold PIBIC gravada em gold.pibic_social_unb com % cursos agregados.', v_n;
    ELSE
        RAISE WARNING 'silver.pibic_bolsistas está vazia. Pulando Gold do PIBIC.';
    END IF;
END
$$;
COMMENT ON PROCEDURE gold.materializar_gold(integer, text[], integer, numeric) IS
  'Recalcula e grava a gold analítica (retenção, ativos, benchmark INEP, PIBIC e relatórios) a partir da silver, na transação de quem chama. Pré-requisito: gold.regras_harmonizacao_canonicas carregada.';

-- ---------------------------------------------------------------------------
-- Privilégios: as views com registro individual não saem do banco de carga.
-- ---------------------------------------------------------------------------

REVOKE ALL ON gold.vw_vinculos_canonicos, gold.vw_pibic_planos FROM observatorio_leitura;
