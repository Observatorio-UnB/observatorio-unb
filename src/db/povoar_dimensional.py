"""
Povoamento do Star Schema da gold a partir da Silver 3NF, dentro do PostgreSQL.

  1. Silver 3NF (src/db/povoar_silver_3nf.py)
  2. gold.dim_campus        <- silver.cursos
  3. gold.dim_curso         <- silver.estruturas_curriculares + silver.cursos (chave natural nome_curso)
  4. gold.dim_tempo         <- anos de ingresso de silver.movimentacoes_vinculos até o ano corrente
  5. gold.dim_perfil_social <- silver.pibic_projetos
  6. gold.fato_retencao_curso <- silver.movimentacoes_vinculos (contagens e taxas das coortes maduras)
                                 + gold.retencao_cursos_unb (IRC, classificação, % no tempo ideal e
                                 atraso médio, que dependem dos percentis calculados em build_gold.py)
  7. gold.fato_alunos_ativos  <- gold.ativos_hoje_cursos_unb
  8. REFRESH da gold.mv_dashboard_executivo

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

TABELAS_GOLD = (
    "gold.dim_campus",
    "gold.dim_curso",
    "gold.dim_tempo",
    "gold.dim_perfil_social",
    "gold.fato_retencao_curso",
    "gold.fato_alunos_ativos",
)

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

# Mesmo corte de coorte e mesma regra de campus (MULTICAMPUS) de build_gold.py.
SQL_FATO_RETENCAO = """
WITH corte AS (
    SELECT max(ano_ingresso) - %(anos_maturacao)s AS ano FROM silver.movimentacoes_vinculos
), coortes AS (
    SELECT e.nome_curso_canonico AS curso,
           count(*) AS ingressantes,
           count(*) FILTER (WHERE m.tipo_saida_grupo = 'FORMATURA') AS formados,
           count(*) FILTER (WHERE m.tipo_saida_grupo = 'EVASAO') AS evadidos,
           count(*) FILTER (WHERE m.tipo_saida_grupo = 'ATIVO') AS ativos
    FROM silver.movimentacoes_vinculos m
    JOIN silver.estruturas_curriculares e USING (id_estrutura)
    WHERE m.ano_ingresso <= (SELECT ano FROM corte)
    GROUP BY e.nome_curso_canonico
    HAVING count(*) >= 5
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
SELECT dc.sk_curso, camp.sk_campus, c.ingressantes, c.formados, c.evadidos, c.ativos,
       round(100.0 * c.formados / c.ingressantes, 2), round(100.0 * c.evadidos / c.ingressantes, 2),
       r.formados_tempo_ideal_pct, r.desvio_medio_semestres, r.indice_retencao_critica, r.classificacao_retencao
FROM coortes c
JOIN gold.dim_curso dc ON dc.nome_curso = c.curso
JOIN campus_do_curso cc ON cc.curso = c.curso
JOIN gold.dim_campus camp ON camp.campus = cc.campus
LEFT JOIN gold.retencao_cursos_unb r ON r.curso = c.curso
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
    conn.execute("TRUNCATE gold.fato_retencao_curso, gold.fato_alunos_ativos RESTART IDENTITY")
    conn.execute(SQL_FATO_RETENCAO, {"anos_maturacao": ANOS_MATURACAO_COORTE})
    conn.execute(SQL_FATO_ATIVOS)
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
