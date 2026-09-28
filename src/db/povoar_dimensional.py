"""
Procedimento ELT in-Database: Carga e Povoamento da Camada Gold Dimensional (Star Schema).

Transforma e estrutura os dados analíticos dentro do próprio PostgreSQL via SQL puro:
  1. gold.dim_campus (Dimensão Campus da UnB)
  2. gold.dim_curso (Dimensão Cursos e Classificações Acadêmicas)
  3. gold.dim_tempo (Dimensão Temporal em Semestres Letivos)
  4. gold.fato_retencao_curso (Fato de Integralização Curricular e IRC com k >= 5)
  5. gold.mv_dashboard_executivo (View Materializada Indexada para o Dashboard DEG)

Uso:
    python3 src/db/povoar_dimensional.py
"""

import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("povoar_dimensional")


SQL_POVOAR_DIMENSOES = """
-- 1. Dimensão Campus
INSERT INTO gold.dim_campus (campus, regiao_admin, municipio)
SELECT DISTINCT 
    campus,
    CASE 
        WHEN campus = 'DARCY RIBEIRO' THEN 'Plano Piloto'
        WHEN campus = 'GAMA' THEN 'Gama'
        WHEN campus = 'PLANALTINA' THEN 'Planaltina'
        WHEN campus = 'CEILANDIA' THEN 'Ceilândia'
        ELSE 'Distrito Federal'
    END AS regiao_admin,
    'Brasília' AS municipio
FROM gold.retencao_cursos_unb
ON CONFLICT (campus) DO NOTHING;

-- 2. Dimensão Curso
INSERT INTO gold.dim_curso (id_curso_origem, nome_curso, grau_academico, categoria_grau, area_conhecimento, departamento, is_tronco_abi)
SELECT 
    ROW_NUMBER() OVER (ORDER BY curso)::integer AS id_curso_origem,
    curso,
    grau_academico,
    categoria_grau,
    area_conhecimento,
    departamento,
    (curso IN ('ENGENHARIA', 'EDUCACAO FISICA')) AS is_tronco_abi
FROM gold.retencao_cursos_unb
ON CONFLICT (id_curso_origem) DO UPDATE 
SET nome_curso = EXCLUDED.nome_curso,
    grau_academico = EXCLUDED.grau_academico,
    categoria_grau = EXCLUDED.categoria_grau,
    area_conhecimento = EXCLUDED.area_conhecimento,
    departamento = EXCLUDED.departamento,
    is_tronco_abi = EXCLUDED.is_tronco_abi;

-- 3. Dimensão Tempo (Semestres 2010 a 2026)
INSERT INTO gold.dim_tempo (sk_tempo, ano, semestre, rotulo, decada)
SELECT 
    (ano * 10 + sem)::integer AS sk_tempo,
    ano::smallint,
    sem::smallint,
    ano || '/' || sem AS rotulo,
    (ano / 10 * 10)::smallint AS decada
FROM generate_series(2010, 2026) AS ano
CROSS JOIN (VALUES (1), (2)) AS s(sem)
ON CONFLICT (sk_tempo) DO NOTHING;

-- 4. Tabela Fato: Retenção e Formatura por Curso
INSERT INTO gold.fato_retencao_curso (
    sk_curso,
    sk_campus,
    total_ingressantes,
    total_formados,
    total_evadidos,
    total_ainda_ativos,
    taxa_formatura_pct,
    taxa_evasao_pct,
    formados_tempo_ideal_pct,
    atraso_medio_semestres,
    indice_retencao_critica,
    classificacao_retencao
)
SELECT 
    c.sk_curso,
    camp.sk_campus,
    r.total_discentes_registrados,
    r.total_formados,
    r.total_evadidos_desligados,
    0,
    r.taxa_formatura_pct,
    r.taxa_evasao_pct,
    r.formados_tempo_ideal_pct,
    r.desvio_medio_semestres,
    r.indice_retencao_critica,
    r.classificacao_retencao
FROM gold.retencao_cursos_unb r
JOIN gold.dim_curso c ON r.curso = c.nome_curso
JOIN gold.dim_campus camp ON r.campus = camp.campus
ON CONFLICT (sk_curso, sk_campus) DO UPDATE 
SET total_ingressantes = EXCLUDED.total_ingressantes,
    total_formados = EXCLUDED.total_formados,
    total_evadidos = EXCLUDED.total_evadidos,
    taxa_formatura_pct = EXCLUDED.taxa_formatura_pct,
    taxa_evasao_pct = EXCLUDED.taxa_evasao_pct,
    formados_tempo_ideal_pct = EXCLUDED.formados_tempo_ideal_pct,
    atraso_medio_semestres = EXCLUDED.atraso_medio_semestres,
    indice_retencao_critica = EXCLUDED.indice_retencao_critica,
    classificacao_retencao = EXCLUDED.classificacao_retencao,
    atualizado_em = now();
"""


def executar_elt_dimensional():
    """Executa a transformação e povoamento da modelagem dimensional no PostgreSQL."""
    logger.info("Iniciando procedimento ELT dimensional no PostgreSQL...")
    with conectar(autocommit=True) as conn:
        with conn.transaction():
            conn.execute(SQL_POVOAR_DIMENSOES)
        
        # Refresh concorrente na view materializada
        logger.info("Atualizando View Materializada gold.mv_dashboard_executivo...")
        conn.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_dashboard_executivo")
        
        # Coleta contagens para log
        n_cursos = conn.execute("SELECT count(*) FROM gold.dim_curso").fetchone()[0]
        n_campi = conn.execute("SELECT count(*) FROM gold.dim_campus").fetchone()[0]
        n_fatos = conn.execute("SELECT count(*) FROM gold.fato_retencao_curso").fetchone()[0]
        n_view = conn.execute("SELECT count(*) FROM gold.mv_dashboard_executivo").fetchone()[0]
        
    logger.info(
        f"ELT Concluído: {n_campi} campi, {n_cursos} cursos, {n_fatos} fatos de retenção, {n_view} linhas na view materializada."
    )


if __name__ == "__main__":
    executar_elt_dimensional()
