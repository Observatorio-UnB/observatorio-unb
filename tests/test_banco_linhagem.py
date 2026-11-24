"""
Linhagem contra o banco: toda coluna das trilhas (src/governanca/linhagem.py) existe, e toda tabela
bronze registrada em bronze.ingestoes tem fonte pública no catálogo. Precisa de PostgreSQL com o
pipeline e o dbt rodados.

Uso:
    python3 -m unittest tests/test_banco_linhagem.py
"""

import sys
import unittest
from pathlib import Path

import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar  # noqa: E402
from src.governanca import linhagem as L  # noqa: E402


class TestLinhagemNoBanco(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            cls.conn = conectar(autocommit=True, connect_timeout=3)
        except psycopg.OperationalError as erro:
            raise unittest.SkipTest(f"Banco indisponível ({erro}). Suba com: docker compose up -d db")
        if cls.conn.execute("SELECT to_regclass('dbt_marts.painel_cursos_criticos')").fetchone()[0] is None:
            cls.conn.close()
            raise unittest.SkipTest("Camadas do dbt não construídas (bash scripts/dbt.sh build).")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_01_colunas_das_trilhas_existem(self):
        existentes = {(f"{e}.{t}", c) for e, t, c in self.conn.execute(
            "SELECT table_schema, table_name, column_name FROM information_schema.columns").fetchall()}
        faltando = sorted(par for par in L.colunas_das_trilhas() if par not in existentes)
        self.assertEqual(faltando, [], "colunas citadas na linhagem que não existem no banco")

    def test_02_toda_tabela_ingerida_tem_fonte_publica(self):
        ingeridas = {r[0] for r in self.conn.execute("SELECT tabela FROM bronze.ingestoes").fetchall()}
        declaradas = {f.grava_em for f in L.fontes_publicas()}
        self.assertEqual(ingeridas - declaradas, set())


if __name__ == "__main__":
    unittest.main()
