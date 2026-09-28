"""
Testes de Integridade da Modelagem 3NF (Silver) e Star Schema (Gold).

Valida os requisitos formais de banco de dados e contratos arquiteturais:
  1. Integridade Referencial estrita (rejeição de FK órfã em silver.movimentacoes_vinculos).
  2. Unicidade de entidades com isolamento transacional e rollback (silver.discentes).
  3. Particionamento declarativo por intervalo + partição DEFAULT (silver.movimentacoes_p_default).
  4. Garantia de k-anonimato (k >= 5) na Gold via restrição CHECK.
  5. Chave natural estável em gold.dim_curso (preservação de surrogate key após updates).
  6. Povoamento e integridade de dimensões (dim_campus, dim_tempo, dim_perfil_social).
  7. Tabela Fato de alunos ativos e consistência da View Materializada com multicampus.

Uso:
    python3 -m unittest tests/test_banco_3nf_star.py
"""

import sys
import unittest
from pathlib import Path
import psycopg
from psycopg import errors, Rollback

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar


class TestBanco3NFStarSchema(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            cls.conn = conectar(autocommit=True, connect_timeout=3)
        except psycopg.OperationalError as erro:
            raise unittest.SkipTest(f"Banco indisponível ({erro}). Suba com: docker compose up -d db")
        
        # Se as tabelas analíticas estiverem vazias, executa o povoamento para inicializar o esquema
        with cls.conn.cursor() as cur:
            n_cursos = cur.execute("SELECT count(*) FROM gold.dim_curso").fetchone()[0]
            if n_cursos == 0:
                from src.db.povoar_dimensional import executar_elt_dimensional
                executar_elt_dimensional()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    # =========================================================================
    # 1. TESTES DA CAMADA SILVER (3NF) COM ISOLAMENTO TRANSACIONAL
    # =========================================================================

    def test_01_3nf_rejeita_discente_duplicado_com_rollback(self):
        """Verifica a chave candidata única (pseudônimo) com rollback para não poluir o banco."""
        with self.conn.cursor() as cur:
            with self.conn.transaction():
                cur.execute("INSERT INTO silver.discentes (pseudonimo) VALUES ('TESTE_DISCENTE_ISO_01');")
                with self.assertRaises(errors.UniqueViolation):
                    with self.conn.transaction():
                        cur.execute("INSERT INTO silver.discentes (pseudonimo) VALUES ('TESTE_DISCENTE_ISO_01');")
                raise Rollback()

    def test_02_3nf_rejeita_vinculo_com_curso_inexistente_com_rollback(self):
        """Verifica integridade referencial: FK deve bloquear curso inexistente sem deixar dados órfãos."""
        with self.conn.cursor() as cur:
            with self.conn.transaction():
                cur.execute("INSERT INTO silver.discentes (pseudonimo) VALUES ('TESTE_DISCENTE_FK');")
                id_discente = cur.execute("SELECT id_discente FROM silver.discentes WHERE pseudonimo = 'TESTE_DISCENTE_FK'").fetchone()[0]
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
                raise Rollback()

    def test_03_3nf_particionamento_ativo_com_particao_default(self):
        """Verifica partições declarativas temporais e partição DEFAULT para anos legados ou futuros."""
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
            self.assertIn("silver.movimentacoes_p_default", nomes_particoes, "Partição DEFAULT deve estar ativa")

            # Testa inserção de ano legado (< 2000) na partição DEFAULT com rollback
            with self.conn.transaction():
                cur.execute("INSERT INTO silver.discentes (pseudonimo) VALUES ('TESTE_DISCENTE_LEGADO');")
                id_discente = cur.execute("SELECT id_discente FROM silver.discentes WHERE pseudonimo = 'TESTE_DISCENTE_LEGADO'").fetchone()[0]
                id_curso = cur.execute("SELECT id_curso FROM silver.cursos LIMIT 1").fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO silver.movimentacoes_vinculos (
                        id_discente, id_curso, ano_ingresso, semestre_ingresso, tipo_saida_grupo, fonte
                    ) VALUES (%s, %s, 1995, 1, 'FORMATURA', 'SIGRA')
                    """,
                    (id_discente, id_curso),
                )
                part_dest = cur.execute(
                    "SELECT tableoid::regclass::text FROM silver.movimentacoes_vinculos WHERE id_discente = %s",
                    (id_discente,),
                ).fetchone()[0]
                self.assertEqual(part_dest, "silver.movimentacoes_p_default", "Ingresso de 1995 deve cair na partição DEFAULT")
                raise Rollback()

    # =========================================================================
    # 2. TESTES DA CAMADA GOLD (STAR SCHEMA)
    # =========================================================================

    def test_04_star_schema_k_anonimato_rejeita_turma_pequena(self):
        """Verifica se o CHECK (total_ingressantes >= 5) bloqueia violação da LGPD na Gold."""
        with self.conn.cursor() as cur:
            with self.conn.transaction():
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
                raise Rollback()

    def test_05_star_schema_chave_natural_estavel_em_dim_curso(self):
        """Verifica se a surrogate key (sk_curso) permanece imutável ao atualizar atributos do curso."""
        with self.conn.cursor() as cur:
            with self.conn.transaction():
                cur.execute("""
                    INSERT INTO gold.dim_curso (nome_curso, grau_academico, categoria_grau, area_conhecimento, departamento)
                    VALUES ('CURSO_TESTE_ESTABILIDADE', 'BACHARELADO', 'BACHARELADO', 'EXATAS', 'DEP_TESTE');
                """)
                sk_inicial = cur.execute("SELECT sk_curso FROM gold.dim_curso WHERE nome_curso = 'CURSO_TESTE_ESTABILIDADE'").fetchone()[0]
                
                # Executa update via ON CONFLICT da chave natural
                cur.execute("""
                    INSERT INTO gold.dim_curso (nome_curso, grau_academico, categoria_grau, area_conhecimento, departamento)
                    VALUES ('CURSO_TESTE_ESTABILIDADE', 'BACHARELADO', 'BACHARELADO', 'EXATAS', 'DEP_ATUALIZADO')
                    ON CONFLICT (nome_curso) DO UPDATE SET departamento = EXCLUDED.departamento;
                """)
                sk_final = cur.execute("SELECT sk_curso FROM gold.dim_curso WHERE nome_curso = 'CURSO_TESTE_ESTABILIDADE'").fetchone()[0]
                self.assertEqual(sk_inicial, sk_final, "A SK da dimensão não pode mudar com a entrada ou atualização de cursos")
                raise Rollback()

    def test_06_star_schema_dimensoes_populadas_e_consistentes(self):
        """Verifica se as dimensões Curso, Campus, Tempo e Perfil Social contêm dados íntegros."""
        with self.conn.cursor() as cur:
            n_campi = cur.execute("SELECT count(*) FROM gold.dim_campus").fetchone()[0]
            n_cursos = cur.execute("SELECT count(*) FROM gold.dim_curso").fetchone()[0]
            n_tempos = cur.execute("SELECT count(*) FROM gold.dim_tempo").fetchone()[0]
            n_perfil = cur.execute("SELECT count(*) FROM gold.dim_perfil_social").fetchone()[0]

            self.assertGreater(n_campi, 0, "Dimensão campus deve conter registros")
            self.assertGreater(n_cursos, 0, "Dimensão curso deve conter registros")
            self.assertGreater(n_tempos, 0, "Dimensão tempo deve conter registros")
            self.assertGreater(n_perfil, 0, "Dimensão perfil social deve conter registros")

    def test_07_star_schema_fatos_referenciam_dimensoes_validas(self):
        """Verifica integridade referencial dimensional: nenhum fato pode ter chave órfã."""
        with self.conn.cursor() as cur:
            orfaos_curso = cur.execute(
                """
                SELECT count(*) 
                FROM gold.fato_retencao_curso f
                LEFT JOIN gold.dim_curso c ON f.sk_curso = c.sk_curso
                WHERE c.sk_curso IS NULL;
                """
            ).fetchone()[0]
            self.assertEqual(orfaos_curso, 0, "Nenhum fato deve ter sk_curso órfão")

            orfaos_campus = cur.execute(
                """
                SELECT count(*) 
                FROM gold.fato_retencao_curso f
                LEFT JOIN gold.dim_campus camp ON f.sk_campus = camp.sk_campus
                WHERE camp.sk_campus IS NULL;
                """
            ).fetchone()[0]
            self.assertEqual(orfaos_campus, 0, "Nenhum fato deve ter sk_campus órfão")

            orfaos_ativos = cur.execute(
                """
                SELECT count(*)
                FROM gold.fato_alunos_ativos fa
                LEFT JOIN gold.dim_curso c ON fa.sk_curso = c.sk_curso
                WHERE c.sk_curso IS NULL;
                """
            ).fetchone()[0]
            self.assertEqual(orfaos_ativos, 0, "Fato alunos ativos não pode ter sk_curso órfão")

    # =========================================================================
    # 3. TESTE DA VIEW MATERIALIZADA
    # =========================================================================

    def test_08_refresh_concorrente_view_materializada(self):
        """Verifica se o REFRESH CONCURRENTLY executa com sucesso na View Materializada multicampus."""
        with self.conn.cursor() as cur:
            cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_dashboard_executivo;")
            total_linhas = cur.execute("SELECT count(*) FROM gold.mv_dashboard_executivo").fetchone()[0]
            self.assertGreater(total_linhas, 0, "View materializada deve conter registros consolidados")


if __name__ == "__main__":
    unittest.main()
