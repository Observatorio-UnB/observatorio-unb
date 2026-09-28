"""
Testes de Integridade da Modelagem 3NF (Silver) e Star Schema (Gold).

Valida os requisitos acadêmicos da disciplina de Banco de Dados 2:
  1. Integridade Referencial estrita (rejeição de FK órfã em silver.movimentacoes_vinculos).
  2. Unicidade de entidades (silver.discentes).
  3. Particionamento declarativo de tabelas (silver.movimentacoes_vinculos).
  4. Garantia de k-anonimato (k >= 5) na Gold via restrição CHECK.
  5. Consistência dimensional e integridade do Star Schema.
  6. Atualização concorrente da View Materializada (gold.mv_dashboard_executivo).

Uso:
    python3 -m unittest tests/test_banco_3nf_star.py
"""

import sys
import unittest
from pathlib import Path
import psycopg
from psycopg import errors

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar
from src.db.povoar_dimensional import executar_elt_dimensional


class TestBanco3NFStarSchema(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            cls.conn = conectar(autocommit=True, connect_timeout=3)
        except psycopg.OperationalError as erro:
            raise unittest.SkipTest(f"Banco indisponível ({erro}). Suba com: docker compose up -d db")
        
        # Garante que o esquema dimensional esteja povoado para os testes analíticos
        executar_elt_dimensional()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    # =========================================================================
    # 1. TESTES DA CAMADA SILVER (3NF)
    # =========================================================================

    def test_01_3nf_rejeita_discente_duplicado(self):
        """Verifica a chave candidata única (pseudônimo) na entidade discente."""
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO silver.discentes (pseudonimo) VALUES ('ALUNO_TESTE_UNICO_01') ON CONFLICT DO NOTHING;")
            with self.assertRaises(errors.UniqueViolation):
                with self.conn.transaction():
                    cur.execute("INSERT INTO silver.discentes (pseudonimo) VALUES ('ALUNO_TESTE_UNICO_01');")

    def test_02_3nf_rejeita_vinculo_com_curso_inexistente(self):
        """Verifica integridade referencial: FK deve bloquear curso inexistente."""
        with self.conn.cursor() as cur:
            # Cria discente temporário
            cur.execute("INSERT INTO silver.discentes (pseudonimo) VALUES ('ALUNO_FK_TESTE') ON CONFLICT DO NOTHING;")
            id_discente = cur.execute("SELECT id_discente FROM silver.discentes WHERE pseudonimo = 'ALUNO_FK_TESTE'").fetchone()[0]
            
            with self.assertRaises(errors.ForeignKeyViolation):
                with self.conn.transaction():
                    cur.execute(
                        """
                        INSERT INTO silver.movimentacoes_vinculos (
                            id_discente, id_curso, ano_ingresso, semestre_ingresso, tipo_saida_grupo, fonte
                        ) VALUES (%s, 999999, 2018, 1, 'FORMATURA', 'SIGRA')
                        """,
                        (id_discente,),
                    )

    def test_03_3nf_particionamento_ativo_no_catalogo(self):
        """Verifica se a tabela de movimentações possui partições declarativas ativas."""
        with self.conn.cursor() as cur:
            particoes = cur.execute(
                """
                SELECT inhrelid::regclass::text
                FROM pg_inherits
                WHERE inhparent = 'silver.movimentacoes_vinculos'::regclass;
                """
            ).fetchall()
            nomes_particoes = {p[0] for p in particoes}
            self.assertIn("silver.movimentacoes_p2000_2015", nomes_particoes)
            self.assertIn("silver.movimentacoes_p2016_2020", nomes_particoes)
            self.assertIn("silver.movimentacoes_p2021_atual", nomes_particoes)

    # =========================================================================
    # 2. TESTES DA CAMADA GOLD (STAR SCHEMA)
    # =========================================================================

    def test_04_star_schema_k_anonimato_rejeita_turma_pequena(self):
        """Verifica se o CHECK (total_ingressantes >= 5) bloqueia violação da LGPD na Gold."""
        with self.conn.cursor() as cur:
            sk_curso = cur.execute("SELECT sk_curso FROM gold.dim_curso LIMIT 1").fetchone()[0]
            sk_campus = cur.execute("SELECT sk_campus FROM gold.dim_campus LIMIT 1").fetchone()[0]

            with self.assertRaises(errors.CheckViolation):
                with self.conn.transaction():
                    cur.execute(
                        """
                        INSERT INTO gold.fato_retencao_curso (
                            sk_curso, sk_campus, total_ingressantes, total_formados, total_evadidos
                        ) VALUES (%s, %s, 3, 2, 1)
                        """,
                        (sk_curso, sk_campus),
                    )

    def test_05_star_schema_dimensoes_populadas_e_consistentes(self):
        """Verifica se as dimensões Curso, Campus e Tempo contêm registros consistentes."""
        with self.conn.cursor() as cur:
            n_campi = cur.execute("SELECT count(*) FROM gold.dim_campus").fetchone()[0]
            n_cursos = cur.execute("SELECT count(*) FROM gold.dim_curso").fetchone()[0]
            n_tempos = cur.execute("SELECT count(*) FROM gold.dim_tempo").fetchone()[0]

            self.assertGreaterEqual(n_campi, 4, "Devem existir ao menos os 4 campi da UnB")
            self.assertGreaterEqual(n_cursos, 80, "Devem existir ao menos 80 cursos canônicos")
            self.assertGreaterEqual(n_tempos, 30, "Dimensão tempo deve cobrir mais de 30 semestres")

    def test_06_star_schema_fatos_referenciam_dimensoes_validas(self):
        """Verifica integridade referencial dimensional: nenhum fato pode ter chave órfã."""
        with self.conn.cursor() as cur:
            orfãos_curso = cur.execute(
                """
                SELECT count(*) 
                FROM gold.fato_retencao_curso f
                LEFT JOIN gold.dim_curso c ON f.sk_curso = c.sk_curso
                WHERE c.sk_curso IS NULL;
                """
            ).fetchone()[0]
            self.assertEqual(orfãos_curso, 0, "Nenhum fato deve ter sk_curso órfão")

            orfãos_campus = cur.execute(
                """
                SELECT count(*) 
                FROM gold.fato_retencao_curso f
                LEFT JOIN gold.dim_campus camp ON f.sk_campus = camp.sk_campus
                WHERE camp.sk_campus IS NULL;
                """
            ).fetchone()[0]
            self.assertEqual(orfãos_campus, 0, "Nenhum fato deve ter sk_campus órfão")

    # =========================================================================
    # 3. TESTE DA VIEW MATERIALIZADA
    # =========================================================================

    def test_07_refresh_concorrente_view_materializada(self):
        """Verifica se o REFRESH CONCURRENTLY executa com sucesso na View Materializada."""
        with self.conn.cursor() as cur:
            cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_dashboard_executivo;")
            total_linhas = cur.execute("SELECT count(*) FROM gold.mv_dashboard_executivo").fetchone()[0]
            self.assertGreater(total_linhas, 80, "View materializada deve conter mais de 80 cursos consolidados")


if __name__ == "__main__":
    unittest.main()
