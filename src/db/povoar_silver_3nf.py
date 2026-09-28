"""
Procedimento ELT in-Database: Carga e Povoamento da Camada Silver Normalizada (3NF).

Normaliza e popula as relações em 3ª Forma Normal a partir dos dados do SGBD:
  1. silver.cursos (Catálogo canônico em 3NF com restrição de integridade)
  2. silver.estruturas_curriculares (Prazos regulamentares por curso)
  3. silver.discentes (Pessoas físicas únicas com minimização de dados)
  4. silver.movimentacoes_vinculos (Fato operacional com particionamento temporal)
  5. silver.pibic_projetos (Planos de pesquisa de Iniciação Científica)

Uso:
    python3 src/db/povoar_silver_3nf.py
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
logger = logging.getLogger("povoar_silver_3nf")


def povoar_cursos_e_estruturas(conn) -> tuple[int, int]:
    """Popula silver.cursos e silver.estruturas_curriculares."""
    # 1. Cursos
    n_cursos_grad = conn.execute("SELECT count(*) FROM silver.cursos_graduacao").fetchone()[0]
    
    if n_cursos_grad > 0:
        logger.info(f"Populando silver.cursos a partir de silver.cursos_graduacao ({n_cursos_grad} registros)...")
        conn.execute("""
            INSERT INTO silver.cursos (
                id_curso,
                codigo_sigaa,
                nome_curso_norm,
                campus,
                turno,
                grau_academico,
                categoria_grau,
                area_conhecimento,
                departamento,
                is_tronco_abi,
                ativo
            )
            SELECT 
                cg.id_curso,
                cg.codigo_inep::text,
                cg.nome_curso_norm,
                COALESCE(cg.campus_norm, 'DARCY RIBEIRO'),
                CASE 
                    WHEN cg.turno_norm LIKE '%NOTURNO%' AND (cg.turno_norm LIKE '%MATUTINO%' OR cg.turno_norm LIKE '%VESPERTINO%' OR cg.turno_norm LIKE '%DIURNO%') THEN 'DIURNO E NOTURNO'
                    WHEN cg.turno_norm LIKE '%NOTURNO%' THEN 'NOTURNO'
                    WHEN cg.turno_norm LIKE '%INTEGRAL%' THEN 'INTEGRAL'
                    ELSE 'DIURNO'
                END,
                COALESCE(cg.grau_academico_norm, 'BACHARELADO'),
                CASE 
                    WHEN cg.grau_academico_norm LIKE '%LICENCIATURA%' THEN 'LICENCIATURA'
                    WHEN cg.grau_academico_norm LIKE '%MISTO%' THEN 'MISTO'
                    ELSE 'BACHARELADO'
                END,
                COALESCE(cg.area_conhecimento_norm, 'CIENCIAS EXATAS E DA TERRA'),
                cg.unidade_responsavel_norm,
                (cg.nome_curso_norm IN ('ENGENHARIA', 'EDUCACAO FISICA - CICLO BASICO')),
                true
            FROM silver.cursos_graduacao cg
            ON CONFLICT (id_curso) DO UPDATE
            SET nome_curso_norm = EXCLUDED.nome_curso_norm,
                campus = EXCLUDED.campus,
                turno = EXCLUDED.turno,
                grau_academico = EXCLUDED.grau_academico,
                categoria_grau = EXCLUDED.categoria_grau,
                area_conhecimento = EXCLUDED.area_conhecimento,
                departamento = EXCLUDED.departamento,
                is_tronco_abi = EXCLUDED.is_tronco_abi;
        """)
    else:
        logger.info("silver.cursos_graduacao vazio; consolidando silver.cursos via gold.retencao_cursos_unb...")
        conn.execute("""
            INSERT INTO silver.cursos (
                id_curso,
                codigo_sigaa,
                nome_curso_norm,
                campus,
                turno,
                grau_academico,
                categoria_grau,
                area_conhecimento,
                departamento,
                is_tronco_abi,
                ativo
            )
            SELECT 
                DENSE_RANK() OVER (ORDER BY r.curso)::integer AS id_curso,
                NULL,
                r.curso,
                r.campus,
                r.turno,
                r.grau_academico,
                r.categoria_grau,
                r.area_conhecimento,
                r.departamento,
                (r.curso IN ('ENGENHARIA', 'EDUCACAO FISICA', 'EDUCACAO FISICA - CICLO BASICO')),
                true
            FROM gold.retencao_cursos_unb r
            ON CONFLICT (id_curso) DO UPDATE
            SET nome_curso_norm = EXCLUDED.nome_curso_norm,
                campus = EXCLUDED.campus,
                turno = EXCLUDED.turno,
                grau_academico = EXCLUDED.grau_academico,
                categoria_grau = EXCLUDED.categoria_grau,
                area_conhecimento = EXCLUDED.area_conhecimento,
                departamento = EXCLUDED.departamento,
                is_tronco_abi = EXCLUDED.is_tronco_abi;
        """)

    # 2. Estruturas Curriculares
    n_est = conn.execute("SELECT count(*) FROM silver.estrutura_curricular").fetchone()[0]
    if n_est > 0:
        logger.info(f"Populando silver.estruturas_curriculares a partir de silver.estrutura_curricular ({n_est} matrizes)...")
        conn.execute("""
            INSERT INTO silver.estruturas_curriculares (
                id_curso,
                semestre_minimo,
                semestre_ideal,
                semestre_maximo,
                ch_total_minima,
                cr_total_minimo
            )
            SELECT 
                c.id_curso,
                ec.semestre_conclusao_minimo,
                ec.semestre_conclusao_ideal,
                ec.semestre_conclusao_maximo,
                ec.ch_total_minima,
                ec.cr_total_minimo
            FROM silver.estrutura_curricular ec
            JOIN silver.cursos c ON ec.id_curso = c.id_curso
            ON CONFLICT (id_curso, semestre_ideal) DO UPDATE
            SET semestre_minimo = EXCLUDED.semestre_minimo,
                semestre_maximo = EXCLUDED.semestre_maximo,
                ch_total_minima = EXCLUDED.ch_total_minima;
        """)
    else:
        logger.info("silver.estrutura_curricular vazio; consolidando silver.estruturas_curriculares via gold.retencao_cursos_unb...")
        conn.execute("""
            INSERT INTO silver.estruturas_curriculares (
                id_curso,
                semestre_minimo,
                semestre_ideal,
                semestre_maximo,
                ch_total_minima,
                cr_total_minimo
            )
            SELECT 
                c.id_curso,
                r.semestre_minimo_previsto,
                r.semestre_ideal_previsto,
                r.semestre_maximo_previsto,
                COALESCE(r.carga_horaria_minima, 3000),
                NULL
            FROM gold.retencao_cursos_unb r
            JOIN silver.cursos c ON r.curso = c.nome_curso_norm
            ON CONFLICT (id_curso, semestre_ideal) DO UPDATE
            SET semestre_minimo = EXCLUDED.semestre_minimo,
                semestre_maximo = EXCLUDED.semestre_maximo,
                ch_total_minima = EXCLUDED.ch_total_minima;
        """)

    tot_cursos = conn.execute("SELECT count(*) FROM silver.cursos").fetchone()[0]
    tot_est = conn.execute("SELECT count(*) FROM silver.estruturas_curriculares").fetchone()[0]
    return tot_cursos, tot_est


def povoar_discentes_e_movimentacoes(conn) -> tuple[int, int]:
    """Popula silver.discentes e silver.movimentacoes_vinculos se houver dados de discentes carregados."""
    # Descobre se existe silver.discentes_graduacao (PR #4) ou silver.sigra_graduacao
    tabela_origem = None
    for cand in ("discentes_graduacao", "sigra_graduacao"):
        existe = conn.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'silver' AND table_name = %s",
            (cand,),
        ).fetchone()[0]
        if existe > 0:
            count = conn.execute(f'SELECT count(*) FROM silver."{cand}"').fetchone()[0]
            if count > 0:
                tabela_origem = cand
                break

    if not tabela_origem:
        logger.info("Nenhuma tabela de discentes brutos (discentes_graduacao / sigra_graduacao) contém dados no momento. Pulando vínculos.")
        return 0, 0

    logger.info(f"Populando silver.discentes a partir de silver.{tabela_origem}...")
    conn.execute(f"""
        INSERT INTO silver.discentes (pseudonimo, data_nascimento, sexo, raca_cor)
        SELECT DISTINCT 
            aluno AS pseudonimo,
            data_nascimento,
            CASE WHEN sexo IN ('F', 'M') THEN sexo ELSE NULL END,
            raca_cor
        FROM silver."{tabela_origem}"
        WHERE aluno IS NOT NULL
        ON CONFLICT (pseudonimo) DO NOTHING;
    """)

    logger.info(f"Populando silver.movimentacoes_vinculos particionada...")
    conn.execute(f"""
        INSERT INTO silver.movimentacoes_vinculos (
            id_discente,
            id_curso,
            id_estrutura,
            ano_ingresso,
            semestre_ingresso,
            forma_saida,
            tipo_saida_grupo,
            ano_saida,
            semestre_saida,
            semestres_permanencia,
            semestres_permanencia_valida,
            periodo_saida_estimado,
            status_aluno,
            fonte
        )
        SELECT 
            d.id_discente,
            c.id_curso,
            e.id_estrutura,
            COALESCE(dg.ano_ingresso, 2015)::smallint,
            1::smallint,
            dg.forma_saida,
            CASE 
                WHEN dg.tipo_saida_grupo IN ('FORMATURA', 'EVASAO', 'ATIVO') THEN dg.tipo_saida_grupo
                WHEN dg.tipo_saida_grupo IN ('EVASAO_DESLIGAMENTO', 'MUDANCA_INTERNA') THEN 'EVASAO'
                ELSE 'OUTROS'
            END,
            dg.ano_saida::smallint,
            dg.semestre_saida::smallint,
            dg.semestres_permanencia::smallint,
            dg.semestres_permanencia_valida::smallint,
            COALESCE(dg.periodo_saida_estimado, false),
            dg.status_aluno,
            COALESCE(dg.fonte, 'SIGRA')
        FROM silver."{tabela_origem}" dg
        JOIN silver.discentes d ON dg.aluno = d.pseudonimo
        JOIN silver.cursos c ON dg.curso_norm = c.nome_curso_norm
        LEFT JOIN silver.estruturas_curriculares e ON c.id_curso = e.id_curso
        ON CONFLICT DO NOTHING;
    """)

    tot_disc = conn.execute("SELECT count(*) FROM silver.discentes").fetchone()[0]
    tot_mov = conn.execute("SELECT count(*) FROM silver.movimentacoes_vinculos").fetchone()[0]
    return tot_disc, tot_mov


def povoar_pibic_projetos(conn) -> int:
    """Popula silver.pibic_projetos se silver.pibic_bolsistas contiver dados."""
    n_pibic = conn.execute("SELECT count(*) FROM silver.pibic_bolsistas").fetchone()[0]
    if n_pibic == 0:
        return 0

    logger.info(f"Populando silver.pibic_projetos a partir de silver.pibic_bolsistas ({n_pibic} registros)...")
    conn.execute("""
        INSERT INTO silver.pibic_projetos (
            id_discente,
            id_curso,
            ano_edital,
            tipo_bolsa,
            linha_pesquisa,
            is_cotista,
            cota_detalhe,
            faixa_renda,
            valor_bolsa_total,
            titulo_pesquisa,
            status_projeto
        )
        SELECT 
            d.id_discente,
            c.id_curso,
            COALESCE(pb.ano, 2022)::smallint,
            CASE 
                WHEN pb.tipo_bolsa_norm IN ('REMUNERADA', 'VOLUNTARIA') THEN pb.tipo_bolsa_norm
                ELSE 'NAO INFORMADO'
            END,
            pb.linha_pesquisa_norm,
            COALESCE(pb.is_cotista, false),
            pb.cota_detalhe,
            pb.faixa_renda,
            COALESCE(pb.valor_bolsa_anual_estimado, 0.0),
            COALESCE(pb.titulo_norm, 'PLANO DE TRABALHO PIBIC'),
            pb.status_norm
        FROM silver.pibic_bolsistas pb
        LEFT JOIN silver.discentes d ON pb.matricula_mascarada = d.pseudonimo
        LEFT JOIN silver.cursos c ON pb.curso_pibic_norm = c.nome_curso_norm
        ON CONFLICT DO NOTHING;
    """)
    return conn.execute("SELECT count(*) FROM silver.pibic_projetos").fetchone()[0]


def executar_elt_silver_3nf():
    """Executa a transformação e povoamento da camada Silver 3NF."""
    logger.info("Iniciando procedimento ELT da Camada Silver 3NF...")
    with conectar(autocommit=True) as conn:
        with conn.transaction():
            tot_cursos, tot_est = povoar_cursos_e_estruturas(conn)
            tot_disc, tot_mov = povoar_discentes_e_movimentacoes(conn)
            tot_pibic = povoar_pibic_projetos(conn)
            
    logger.info(
        f"Silver 3NF Concluída: {tot_cursos} cursos, {tot_est} matrizes, {tot_disc} discentes, {tot_mov} vínculos, {tot_pibic} projetos PIBIC."
    )


if __name__ == "__main__":
    executar_elt_silver_3nf()
