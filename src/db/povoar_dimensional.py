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

As dimensões são atualizadas por chave natural (upsert): a chave substituta de um curso não muda
quando outro curso entra. Os fatos são recriados por inteiro a cada execução.

O refresh da gold.mv_dashboard_executivo fica em src/db/atualizar_view_painel.py, etapa seguinte.

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

# A regra de retenção (coortes maduras, k >= 5, IRC e quartis) mora em gold.atualizar_retencao
# (db/migrations/0022): o fato lê a gold.retencao_cursos_unb já calculada, sem repetir o cálculo.
SQL_FATO_RETENCAO = """
INSERT INTO gold.fato_retencao_curso (
    sk_curso, sk_campus, total_ingressantes, total_formados, total_evadidos, total_ainda_ativos,
    taxa_formatura_pct, taxa_evasao_pct, formados_tempo_ideal_pct, atraso_medio_semestres,
    indice_retencao_critica, classificacao_retencao)
SELECT dc.sk_curso, camp.sk_campus, r.total_discentes_registrados, r.total_formados,
       r.total_evadidos_desligados, r.total_ainda_ativos, r.taxa_formatura_pct, r.taxa_evasao_pct,
       r.formados_tempo_ideal_pct, r.desvio_medio_semestres, r.indice_retencao_critica,
       r.classificacao_retencao
FROM gold.retencao_cursos_unb r
JOIN gold.dim_curso dc ON dc.nome_curso = r.curso
JOIN gold.dim_campus camp ON camp.campus = r.campus
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
    conn.execute(SQL_FATO_RETENCAO)
    conn.execute(SQL_FATO_ATIVOS)
    conn.execute(SQL_FATO_PIBIC_PERFIL)
    return {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in TABELAS_GOLD}


def executar_elt_dimensional() -> Dict[str, int]:
    with conectar(autocommit=True) as conn:
        if not silver_carregada(conn):
            logger.warning("silver.discentes_graduacao vazia (banco só com a gold?): Star Schema não atualizado.")
            return {}
        if not conn.execute("SELECT EXISTS (SELECT 1 FROM gold.retencao_cursos_unb)").fetchone()[0]:
            raise RuntimeError("gold.retencao_cursos_unb vazia: o fato de retenção copia essa tabela. "
                               "Rode antes: python src/pipeline/build_gold.py")
        with conn.transaction():
            contagens = povoar_silver_3nf(conn)
            contagens.update(povoar_gold_dimensional(conn))
    for tabela, n in contagens.items():
        logger.info(f"{tabela}: {n:,} linhas.")
    return contagens


if __name__ == "__main__":
    executar_elt_dimensional()
