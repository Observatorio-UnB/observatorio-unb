"""
Povoamento do Star Schema da gold a partir da Silver 3NF, dentro do PostgreSQL.

  1. Silver 3NF (src/db/povoar_silver_3nf.py)
  2. gold.dim_campus        <- silver.cursos
  3. gold.dim_curso         <- silver.estruturas_curriculares + silver.cursos (chave natural nome_curso)
  4. gold.dim_tempo         <- anos de ingresso de silver.movimentacoes_vinculos até o ano corrente
  5. gold.dim_perfil_social <- silver.pibic_projetos
  6. gold.fato_retencao_curso <- silver.movimentacoes_vinculos (coortes maduras: contagens, taxas,
                                 % no tempo ideal, atraso médio, IRC e classificação)
  7. gold.fato_alunos_ativos  <- gold.ativos_hoje_cursos_unb
  8. gold.fato_pibic_perfil   <- silver.pibic_projetos (por curso e perfil social)
  9. REFRESH da gold.mv_dashboard_executivo

As dimensões são atualizadas por chave natural (upsert): a chave substituta de um curso não muda
quando outro curso entra. Os fatos são recriados por inteiro a cada execução.

Uso:
    python3 src/db/povoar_dimensional.py
"""

import logging
import sys
from pathlib import Path
from typing import Dict

import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar  # noqa: E402
from src.db.povoar_silver_3nf import povoar_silver_3nf, silver_carregada  # noqa: E402
from src.pipeline.build_gold import ANOS_MATURACAO_COORTE  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("povoar_dimensional")

DIMENSOES = ("gold.dim_campus", "gold.dim_curso", "gold.dim_tempo", "gold.dim_perfil_social")
FATOS = ("gold.fato_retencao_curso", "gold.fato_alunos_ativos", "gold.fato_pibic_perfil")
TABELAS_GOLD = DIMENSOES + FATOS

SQL_DIM_CAMPUS = """
INSERT INTO gold.dim_campus (campus, regiao_admin)
SELECT campus,
       CASE campus
           WHEN 'DARCY RIBEIRO' THEN 'Plano Piloto'
           WHEN 'FACULDADE DE CIENCIAS E TECNOLOGIAS EM ENGENHARIA (FCTE)' THEN 'Gama'
           WHEN 'FACULDADE DE CIENCIAS E TECNOLOGIAS EM SAUDE (FCTS)' THEN 'Ceilândia'
           WHEN 'FACULDADE DE PLANALTINA (FUP)' THEN 'Planaltina'
           ELSE 'Distrito Federal'
       END
FROM (SELECT DISTINCT campus FROM silver.cursos UNION SELECT 'MULTICAMPUS') c
ON CONFLICT (campus) DO UPDATE SET regiao_admin = EXCLUDED.regiao_admin
"""

# Mesmas regras de build_gold.py: os atributos vêm da oferta principal do nome (catálogo vigente,
# menor id_curso), e bacharelado + licenciatura com o mesmo nome vira MISTO. Sem oferta com o nome
# (ex.: COMUNICACAO SOCIAL), valem os do curso dono da matriz.
SQL_DIM_CURSO = """
WITH principal AS (
    SELECT DISTINCT ON (nome_curso_norm) *
    FROM silver.cursos
    ORDER BY nome_curso_norm, ativo DESC, id_curso
), misto AS (
    SELECT nome_curso_norm FROM silver.cursos GROUP BY nome_curso_norm HAVING count(DISTINCT categoria_grau) > 1
)
INSERT INTO gold.dim_curso (nome_curso, id_curso_origem, grau_academico, categoria_grau, area_conhecimento,
                            departamento, is_tronco_abi)
SELECT e.nome_curso_canonico,
       e.id_curso,
       CASE WHEN m.nome_curso_norm IS NOT NULL THEN 'MISTO (BACHARELADO + LICENCIATURA)'
            ELSE coalesce(p.grau_academico, dono.grau_academico) END,
       CASE WHEN m.nome_curso_norm IS NOT NULL THEN 'MISTO' ELSE coalesce(p.categoria_grau, dono.categoria_grau) END,
       coalesce(p.area_conhecimento, dono.area_conhecimento),
       coalesce(p.departamento, dono.departamento),
       coalesce(p.is_tronco_abi, dono.is_tronco_abi)
FROM silver.estruturas_curriculares e
JOIN silver.cursos dono ON dono.id_curso = e.id_curso
LEFT JOIN principal p ON p.nome_curso_norm = e.nome_curso_canonico
LEFT JOIN misto m ON m.nome_curso_norm = e.nome_curso_canonico
ON CONFLICT (nome_curso) DO UPDATE
SET id_curso_origem = EXCLUDED.id_curso_origem,
    grau_academico = EXCLUDED.grau_academico,
    categoria_grau = EXCLUDED.categoria_grau,
    area_conhecimento = EXCLUDED.area_conhecimento,
    departamento = EXCLUDED.departamento,
    is_tronco_abi = EXCLUDED.is_tronco_abi
"""

SQL_DIM_TEMPO = """
INSERT INTO gold.dim_tempo (sk_tempo, ano, semestre, rotulo, decada)
SELECT ano * 10 + sem, ano, sem, ano || '/' || sem, ano / 10 * 10
FROM generate_series((SELECT min(ano_ingresso) FROM silver.movimentacoes_vinculos),
                     extract(year FROM current_date)::int) AS ano
CROSS JOIN (VALUES (1), (2)) AS s(sem)
ON CONFLICT (sk_tempo) DO NOTHING
"""

SQL_DIM_PERFIL_SOCIAL = """
INSERT INTO gold.dim_perfil_social (perfil_macro, categoria_cota, faixa_renda, is_cotista)
SELECT DISTINCT coalesce(perfil_social_macro, 'NAO INFORMADO'), coalesce(cota_detalhe, 'NAO INFORMADO'),
       faixa_renda, is_cotista
FROM silver.pibic_projetos
ON CONFLICT ON CONSTRAINT uk_dim_perfil_social DO NOTHING
"""

# Port de build_gold.py (seções 6 a 8) para SQL, com as mesmas regras:
#  - coortes com ingresso até (último ano de ingresso - ANOS_MATURACAO_COORTE), k >= 5;
#  - % no tempo ideal e atraso médio só sobre formados com permanência calculável;
#  - IRC = (0,3 x atraso + 0,7 x evasão) x 100, cada um saturado nos percentis 5 e 95 e
#    normalizado min-max entre os cursos; classificação pelos quartis do IRC;
#  - campus MULTICAMPUS quando o nome tem ofertas em mais de um campus.
# percentile_cont interpola como o quantile do pandas. O arredondamento pode diferir em 0,01
# (taxas) ou 0,1 (IRC) nos empates de meio: o numeric do PostgreSQL arredonda 0,5 para cima.
SQL_FATO_RETENCAO = """
WITH corte AS (
    SELECT max(ano_ingresso) - %(anos_maturacao)s AS ano FROM silver.movimentacoes_vinculos
), coortes AS (
    SELECT e.nome_curso_canonico AS curso,
           count(*) AS ingressantes,
           count(*) FILTER (WHERE m.tipo_saida_grupo = 'FORMATURA') AS formados,
           count(*) FILTER (WHERE m.tipo_saida_grupo = 'EVASAO') AS evadidos,
           count(*) FILTER (WHERE m.tipo_saida_grupo = 'ATIVO') AS ativos,
           count(m.semestres_permanencia_valida) FILTER (WHERE m.tipo_saida_grupo = 'FORMATURA') AS formados_com_prazo,
           count(*) FILTER (WHERE m.tipo_saida_grupo = 'FORMATURA'
                              AND m.semestres_permanencia_valida <= e.semestre_ideal) AS formados_no_ideal,
           avg(m.semestres_permanencia_valida - e.semestre_ideal)
               FILTER (WHERE m.tipo_saida_grupo = 'FORMATURA') AS atraso
    FROM silver.movimentacoes_vinculos m
    JOIN silver.estruturas_curriculares e USING (id_estrutura)
    WHERE m.ano_ingresso <= (SELECT ano FROM corte)
    GROUP BY e.nome_curso_canonico
    HAVING count(*) >= 5
), metricas AS (
    SELECT *,
           round(100.0 * formados / ingressantes, 2) AS taxa_formatura,
           round(100.0 * evadidos / ingressantes, 2) AS taxa_evasao,
           CASE WHEN formados_com_prazo > 0 THEN round(100.0 * formados_no_ideal / formados_com_prazo, 2)
                ELSE 0 END AS pct_tempo_ideal,
           round(atraso, 2) AS atraso_medio
    FROM coortes
), entradas AS (
    SELECT curso, greatest(coalesce(atraso_medio, 0), 0)::float8 AS x_atraso, taxa_evasao::float8 AS x_evasao
    FROM metricas
), limites AS (
    SELECT percentile_cont(0.05) WITHIN GROUP (ORDER BY x_atraso) AS a05,
           percentile_cont(0.95) WITHIN GROUP (ORDER BY x_atraso) AS a95,
           percentile_cont(0.05) WITHIN GROUP (ORDER BY x_evasao) AS e05,
           percentile_cont(0.95) WITHIN GROUP (ORDER BY x_evasao) AS e95
    FROM entradas
), saturados AS (
    SELECT curso,
           least(greatest(x_atraso, a05), a95) AS s_atraso,
           least(greatest(x_evasao, e05), e95) AS s_evasao
    FROM entradas, limites
), irc AS (
    SELECT curso,
           round(((0.3 * (s_atraso - min(s_atraso) OVER ()) / (max(s_atraso) OVER () - min(s_atraso) OVER () + 1e-6)
                 + 0.7 * (s_evasao - min(s_evasao) OVER ()) / (max(s_evasao) OVER () - min(s_evasao) OVER () + 1e-6))
                 * 100)::numeric, 1) AS indice
    FROM saturados
), quartis AS (
    SELECT percentile_cont(0.25) WITHIN GROUP (ORDER BY indice) AS q25,
           percentile_cont(0.50) WITHIN GROUP (ORDER BY indice) AS q50,
           percentile_cont(0.75) WITHIN GROUP (ORDER BY indice) AS q75
    FROM irc
), campus_do_curso AS (
    SELECT e.nome_curso_canonico AS curso,
           CASE WHEN count(DISTINCT o.campus) > 1 THEN 'MULTICAMPUS'
                ELSE coalesce(min(o.campus), dono.campus) END AS campus
    FROM silver.estruturas_curriculares e
    JOIN silver.cursos dono ON dono.id_curso = e.id_curso
    LEFT JOIN silver.cursos o ON o.nome_curso_norm = e.nome_curso_canonico
    GROUP BY e.nome_curso_canonico, dono.campus
)
INSERT INTO gold.fato_retencao_curso (
    sk_curso, sk_campus, total_ingressantes, total_formados, total_evadidos, total_ainda_ativos,
    taxa_formatura_pct, taxa_evasao_pct, formados_tempo_ideal_pct, atraso_medio_semestres,
    indice_retencao_critica, classificacao_retencao)
SELECT dc.sk_curso, camp.sk_campus, m.ingressantes, m.formados, m.evadidos, m.ativos,
       m.taxa_formatura, m.taxa_evasao, m.pct_tempo_ideal, m.atraso_medio, i.indice,
       CASE WHEN i.indice >= q.q75 THEN 'RETENÇÃO CRÍTICA'
            WHEN i.indice >= q.q50 THEN 'RETENÇÃO ALTA'
            WHEN i.indice >= q.q25 THEN 'RETENÇÃO MÉDIA'
            ELSE 'RETENÇÃO BAIXA' END
FROM metricas m
JOIN irc i USING (curso)
CROSS JOIN quartis q
JOIN gold.dim_curso dc ON dc.nome_curso = m.curso
JOIN campus_do_curso cc ON cc.curso = m.curso
JOIN gold.dim_campus camp ON camp.campus = cc.campus
"""

# Um grupo por curso canônico e perfil social; grupos com menos de 5 planos ficam de fora.
SQL_FATO_PIBIC_PERFIL = """
INSERT INTO gold.fato_pibic_perfil (sk_curso, sk_perfil, total_projetos, total_remuneradas, total_voluntarias,
                                    valor_total_investido)
SELECT dc.sk_curso, ps.sk_perfil, count(*),
       count(*) FILTER (WHERE p.tipo_bolsa = 'REMUNERADA'),
       count(*) FILTER (WHERE p.tipo_bolsa = 'VOLUNTARIA'),
       sum(p.valor_bolsa_total)
FROM silver.pibic_projetos p
JOIN silver.estruturas_curriculares e USING (id_estrutura)
JOIN gold.dim_curso dc ON dc.nome_curso = e.nome_curso_canonico
JOIN gold.dim_perfil_social ps
  ON ps.perfil_macro = coalesce(p.perfil_social_macro, 'NAO INFORMADO')
 AND ps.categoria_cota = coalesce(p.cota_detalhe, 'NAO INFORMADO')
 AND ps.faixa_renda IS NOT DISTINCT FROM p.faixa_renda
 AND ps.is_cotista = p.is_cotista
GROUP BY dc.sk_curso, ps.sk_perfil
HAVING count(*) >= 5
"""

SQL_FATO_ATIVOS = """
INSERT INTO gold.fato_alunos_ativos (sk_curso, sk_tempo_referencia, total_ativos, ativos_acima_prazo_ideal,
                                     ativos_acima_prazo_maximo, pct_acima_prazo_ideal)
SELECT dc.sk_curso, replace(a.periodo_referencia, '/', '')::int, a.total_ativos_hoje,
       a.ativos_acima_prazo_ideal, a.ativos_acima_prazo_maximo, a.pct_acima_prazo_ideal
FROM gold.ativos_hoje_cursos_unb a
JOIN gold.dim_curso dc ON dc.nome_curso = a.curso
"""


def povoar_gold_dimensional(conn: psycopg.Connection) -> Dict[str, int]:
    """Atualiza dimensões e recria fatos na transação de `conn`; devolve o número de linhas por tabela."""
    for sql in (SQL_DIM_CAMPUS, SQL_DIM_CURSO, SQL_DIM_TEMPO, SQL_DIM_PERFIL_SOCIAL):
        conn.execute(sql)
    conn.execute(f"TRUNCATE {', '.join(FATOS)} RESTART IDENTITY")
    conn.execute(SQL_FATO_RETENCAO, {"anos_maturacao": ANOS_MATURACAO_COORTE})
    conn.execute(SQL_FATO_ATIVOS)
    conn.execute(SQL_FATO_PIBIC_PERFIL)
    return {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in TABELAS_GOLD}


def executar_elt_dimensional() -> Dict[str, int]:
    with conectar(autocommit=True) as conn:
        if not silver_carregada(conn):
            logger.warning("silver.discentes_graduacao vazia (banco só com a gold?): Star Schema não atualizado.")
            return {}
        with conn.transaction():
            contagens = povoar_silver_3nf(conn)
            contagens.update(povoar_gold_dimensional(conn))
        # CONCURRENTLY não roda dentro de transação; mantém a view legível durante o refresh.
        conn.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_dashboard_executivo")
        contagens["gold.mv_dashboard_executivo"] = conn.execute(
            "SELECT count(*) FROM gold.mv_dashboard_executivo").fetchone()[0]
    for tabela, n in contagens.items():
        logger.info(f"{tabela}: {n:,} linhas.")
    return contagens


if __name__ == "__main__":
    executar_elt_dimensional()
