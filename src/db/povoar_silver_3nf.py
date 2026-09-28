"""
Povoamento da camada Silver normalizada (3NF) a partir das tabelas silver da carga.

Recria por inteiro, dentro do banco:
  1. silver.cursos                  <- silver.cursos_graduacao (uma linha por id_curso do catálogo)
  2. silver.estruturas_curriculares <- silver.estrutura_curricular (uma linha por curso canônico)
  3. silver.discentes               <- silver.discentes_graduacao (uma linha por pseudônimo)
  4. silver.movimentacoes_vinculos  <- silver.discentes_graduacao (uma linha por vínculo)
  5. silver.pibic_projetos          <- silver.pibic_bolsistas (uma linha por plano de trabalho)

O curso de cada vínculo e de cada plano de IC passa pela mesma harmonização de nomes da gold
(gold.regras_harmonizacao_canonicas) e aponta para a matriz do curso canônico. As tabelas
são esvaziadas antes da carga: rodar duas vezes dá o mesmo resultado.

Uso:
    python3 src/db/povoar_silver_3nf.py
"""

import logging
import sys
from pathlib import Path
from typing import Dict

import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("povoar_silver_3nf")

TABELAS_3NF = (
    "silver.cursos",
    "silver.estruturas_curriculares",
    "silver.discentes",
    "silver.movimentacoes_vinculos",
    "silver.pibic_projetos",
)

# Mesmas regras de build_gold.py: normalize_turno_grupo, normalize_categoria_grau,
# normalize_campus_nome e EXCLUDED_GENERIC_COURSES.
SQL_CURSOS = """
INSERT INTO silver.cursos (id_curso, codigo_sigaa, nome_curso_norm, campus, turno, grau_academico,
                           categoria_grau, area_conhecimento, departamento, is_tronco_abi, ativo)
SELECT
    id_curso,
    id_curso::text,
    nome_curso_norm,
    CASE
        WHEN campus_norm LIKE '%GAMA%' THEN 'FACULDADE DE CIENCIAS E TECNOLOGIAS EM ENGENHARIA (FCTE)'
        WHEN campus_norm LIKE '%CEILANDIA%' THEN 'FACULDADE DE CIENCIAS E TECNOLOGIAS EM SAUDE (FCTS)'
        WHEN campus_norm LIKE '%PLANALTINA%' THEN 'FACULDADE DE PLANALTINA (FUP)'
        ELSE 'DARCY RIBEIRO'
    END,
    CASE
        WHEN turno_norm LIKE '%NOTURNO%' THEN 'NOTURNO'
        WHEN turno_norm LIKE '%INTEGRAL%' THEN 'INTEGRAL'
        ELSE 'DIURNO'
    END,
    grau_academico_norm,
    CASE WHEN grau_academico_norm LIKE '%LICENCI%' THEN 'LICENCIATURA' ELSE 'BACHARELADO' END,
    area_conhecimento_norm,
    unidade_responsavel_norm,
    nome_curso_norm IN ('ENGENHARIA', 'EDUCACAO FISICA - CICLO BASICO'),
    no_catalogo_vigente
FROM silver.cursos_graduacao
"""

SQL_ESTRUTURAS = """
INSERT INTO silver.estruturas_curriculares (id_curso, nome_curso_canonico, semestre_minimo, semestre_ideal,
                                            semestre_maximo, ch_total_minima, cr_total_minimo)
SELECT id_curso, nome_curso_norm, semestre_conclusao_minimo, semestre_conclusao_ideal,
       semestre_conclusao_maximo, ch_total_minima, cr_total_minimo
FROM silver.estrutura_curricular
"""

# Um pseudônimo com mais de um vínculo fica com os atributos do vínculo mais recente.
SQL_DISCENTES = """
INSERT INTO silver.discentes (pseudonimo, data_nascimento, sexo, raca_cor)
SELECT DISTINCT ON (aluno) aluno, data_nascimento, sexo, raca_cor
FROM silver.discentes_graduacao
ORDER BY aluno, id DESC
"""

SQL_MOVIMENTACOES = """
INSERT INTO silver.movimentacoes_vinculos (
    id_discente, id_curso, id_estrutura, ano_ingresso, forma_saida, tipo_saida_grupo, ano_saida,
    semestre_saida, semestres_permanencia, semestres_permanencia_valida, periodo_saida_estimado,
    status_aluno, fonte)
SELECT d.id_discente, e.id_curso, e.id_estrutura, dg.ano_ingresso, dg.forma_saida, dg.tipo_saida_grupo,
       dg.ano_saida, dg.semestre_saida, dg.semestres_permanencia, dg.semestres_permanencia_valida,
       dg.periodo_saida_estimado, dg.status_aluno, dg.fonte
FROM silver.discentes_graduacao dg
JOIN silver.discentes d ON d.pseudonimo = dg.aluno
LEFT JOIN gold.regras_harmonizacao_canonicas r ON r.origem_sigra = dg.curso_norm
JOIN silver.estruturas_curriculares e ON e.nome_curso_canonico = coalesce(r.destino_estrutura, dg.curso_norm)
"""

# A matrícula do bolsista não é gravada (0010_pibic.sql): o plano não se liga ao discente.
SQL_PIBIC = """
INSERT INTO silver.pibic_projetos (
    id_curso, ano_edital, tipo_bolsa, linha_pesquisa, is_cotista, perfil_social_macro, cota_detalhe,
    faixa_renda, valor_bolsa_total, titulo_pesquisa, status_projeto)
SELECT e.id_curso, pb.ano, pb.tipo_bolsa_norm, pb.linha_pesquisa_norm, pb.is_cotista, pb.perfil_social_macro,
       pb.cota_detalhe, pb.faixa_renda, pb.valor_bolsa_anual_estimado, pb.titulo_norm, pb.status_norm
FROM silver.pibic_bolsistas pb
LEFT JOIN gold.regras_harmonizacao_canonicas r ON r.origem_sigra = pb.curso_pibic_norm
LEFT JOIN silver.estruturas_curriculares e
       ON e.nome_curso_canonico = coalesce(r.destino_estrutura, pb.curso_pibic_norm)
"""


def silver_carregada(conn: psycopg.Connection) -> bool:
    """A 3NF só é derivável com os vínculos na silver (um banco só com a gold não os tem)."""
    return conn.execute("SELECT EXISTS (SELECT 1 FROM silver.discentes_graduacao)").fetchone()[0]


def povoar_silver_3nf(conn: psycopg.Connection) -> Dict[str, int]:
    """Recria as tabelas 3NF na transação de `conn` e devolve o número de linhas por tabela."""
    conn.execute(f"TRUNCATE {', '.join(TABELAS_3NF)} RESTART IDENTITY")
    for sql in (SQL_CURSOS, SQL_ESTRUTURAS, SQL_DISCENTES, SQL_MOVIMENTACOES, SQL_PIBIC):
        conn.execute(sql)

    contagens = {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in TABELAS_3NF}
    sem_matriz = conn.execute("SELECT count(*) FROM silver.discentes_graduacao").fetchone()[0] \
        - contagens["silver.movimentacoes_vinculos"]
    if sem_matriz:
        logger.warning(f"{sem_matriz:,} vínculos sem matriz curricular ficaram fora de silver.movimentacoes_vinculos.")
    return contagens


def executar_elt_silver_3nf() -> Dict[str, int]:
    with conectar(autocommit=True) as conn:
        if not silver_carregada(conn):
            logger.warning("silver.discentes_graduacao vazia: nada a normalizar. Rode src/db/carregar.py antes.")
            return {}
        with conn.transaction():
            contagens = povoar_silver_3nf(conn)
    for tabela, n in contagens.items():
        logger.info(f"{tabela}: {n:,} linhas.")
    return contagens


if __name__ == "__main__":
    executar_elt_silver_3nf()
