"""
Controle de acesso por linha e por coluna (migração 0030), com o papel secretaria_campus. Precisa de
PostgreSQL e da Silver 3NF carregada.

Cada teste cria os usuários de exemplo numa transação desfeita no fim: nada fica no banco.

Uso:
    python3 -m unittest tests/test_banco_controle_de_acesso.py
"""

import sys
import unittest
from pathlib import Path

import psycopg
from psycopg import Rollback

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar  # noqa: E402
from src.db.migrar import aplicar_migracoes  # noqa: E402

FCTE = "FACULDADE DE CIENCIAS E TECNOLOGIAS EM ENGENHARIA (FCTE)"
FUP = "FACULDADE DE PLANALTINA (FUP)"

POR_CAMPUS = """
    SELECT c.campus, count(*) FROM silver.movimentacoes_vinculos v
    JOIN silver.cursos c USING (id_curso) GROUP BY 1
"""


class TestAcessoPorCampus(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            cls.conn = conectar(autocommit=True, connect_timeout=3)
        except psycopg.OperationalError as erro:
            raise unittest.SkipTest(f"Banco indisponível ({erro}). Suba com: docker compose up -d db")
        aplicar_migracoes()
        cls.total = dict(cls.conn.execute(POR_CAMPUS).fetchall())
        if not cls.total.get(FCTE) or not cls.total.get(FUP):
            cls.conn.close()
            raise unittest.SkipTest("Silver 3NF sem vínculos da FCTE e da FUP: rode o pipeline.")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def setUp(self):
        self.transacao = self.conn.transaction()
        self.transacao.__enter__()
        for usuario, campi in {"t_sec_fcte": [FCTE], "t_sec_fcte_fup": [FCTE, FUP], "t_sec_sem": [],
                               "t_sec_outro": [FUP]}.items():
            self.conn.execute(f'CREATE ROLE "{usuario}" NOLOGIN IN ROLE secretaria_campus')
            for campus in campi:
                self.conn.execute("INSERT INTO acesso.lotacao_campus (usuario, campus) VALUES (%s, %s)",
                                  (usuario, campus))

    def tearDown(self):
        self.conn.execute("RESET ROLE")
        self.transacao.__exit__(Rollback, Rollback(), None)

    def como(self, usuario):
        self.conn.execute(f'SET ROLE "{usuario}"')

    def negado(self, sql):
        with self.assertRaises(psycopg.errors.InsufficientPrivilege), self.conn.transaction():
            self.conn.execute(sql)

    def test_01_linha_so_os_vinculos_do_campus_lotado(self):
        self.como("t_sec_fcte")
        self.assertEqual(dict(self.conn.execute(POR_CAMPUS).fetchall()), {FCTE: self.total[FCTE]})

    def test_02_lotado_em_dois_campi_ve_os_dois(self):
        self.como("t_sec_fcte_fup")
        self.assertEqual(dict(self.conn.execute(POR_CAMPUS).fetchall()),
                         {FCTE: self.total[FCTE], FUP: self.total[FUP]})

    def test_03_sem_lotacao_nao_ve_nada(self):
        self.como("t_sec_sem")
        self.assertEqual(self.conn.execute("SELECT count(*) FROM silver.movimentacoes_vinculos").fetchone()[0], 0)

    def test_04_revogar_a_lotacao_tira_o_acesso_na_hora(self):
        self.conn.execute("DELETE FROM acesso.lotacao_campus WHERE usuario = 't_sec_fcte'")
        self.como("t_sec_fcte")
        self.assertEqual(self.conn.execute("SELECT count(*) FROM silver.movimentacoes_vinculos").fetchone()[0], 0)

    def test_05_coluna_id_discente_negada_e_as_demais_liberadas(self):
        self.como("t_sec_fcte")
        self.negado("SELECT id_discente FROM silver.movimentacoes_vinculos LIMIT 1")
        self.negado("SELECT * FROM silver.movimentacoes_vinculos LIMIT 1")
        linha = self.conn.execute("""SELECT id_vinculo, id_curso, ano_ingresso, tipo_saida_grupo,
                                            semestres_permanencia_valida, fonte
                                     FROM silver.movimentacoes_vinculos LIMIT 1""").fetchone()
        self.assertIsNotNone(linha)

    def test_06_sem_atalho_pela_particao_nem_pelos_dados_pessoais(self):
        self.como("t_sec_fcte")
        for particao in ("movimentacoes_p2000_2015", "movimentacoes_p2016_2020", "movimentacoes_p2021_atual",
                         "movimentacoes_p_default"):
            with self.subTest(particao=particao):
                self.negado(f"SELECT count(*) FROM silver.{particao}")
        self.negado("SELECT count(*) FROM silver.discentes")
        self.negado("SELECT count(*) FROM bronze.ingestoes")

    def test_07_so_leitura(self):
        self.como("t_sec_fcte")
        self.negado("UPDATE silver.movimentacoes_vinculos SET status_aluno = 'X' WHERE false")
        self.negado("DELETE FROM silver.movimentacoes_vinculos WHERE false")
        self.negado("INSERT INTO acesso.lotacao_campus (usuario, campus) VALUES ('t_sec_fcte', 'DARCY RIBEIRO')")

    def test_08_nao_ve_a_lotacao_dos_outros(self):
        self.como("t_sec_fcte")
        usuarios = {r[0] for r in self.conn.execute("SELECT usuario FROM acesso.lotacao_campus").fetchall()}
        self.assertEqual(usuarios, {"t_sec_fcte"})

    def test_09_dono_do_banco_continua_vendo_tudo(self):
        """O pipeline, o dbt e o CDC gravam e leem como dono: a RLS não pode mudar a carga."""
        self.assertEqual(dict(self.conn.execute(POR_CAMPUS).fetchall()), self.total)

    def test_10_politica_usa_o_indice(self):
        """A lista de cursos do usuário vira condição de índice (InitPlan), e não filtro linha a linha."""
        self.como("t_sec_fcte")
        plano = "\n".join(r[0] for r in self.conn.execute(
            "EXPLAIN SELECT count(*) FROM silver.movimentacoes_vinculos").fetchall())
        self.assertIn("Index Cond: (id_curso = ANY", plano)
        self.assertNotIn("hashed SubPlan", plano)


if __name__ == "__main__":
    unittest.main()
