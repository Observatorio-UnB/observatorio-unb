"""
O painel abre na Visão Executiva com a resposta à pergunta da E1, lida do mart do dbt.

Roda o app.py com o AppTest do Streamlit contra o banco do pipeline. Pulado sem banco ou sem as
camadas do dbt (bash scripts/dbt.sh build).

Uso:
    python3 -m unittest tests/test_painel_e1.py
"""

import sys
import unittest
from pathlib import Path

import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar  # noqa: E402


class TestPainelE1(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            with conectar(connect_timeout=3) as conn:
                if conn.execute("SELECT to_regclass('dbt_marts.painel_cursos_criticos')").fetchone()[0] is None:
                    raise unittest.SkipTest("Sem as camadas do dbt: rode bash scripts/dbt.sh build.")
                cls.primeiro = conn.execute(
                    "SELECT nome_curso FROM dbt_marts.painel_cursos_criticos ORDER BY posicao, nome_curso LIMIT 1"
                ).fetchone()[0]
                cls.total = conn.execute("SELECT count(*) FROM dbt_marts.painel_cursos_criticos").fetchone()[0]
        except psycopg.OperationalError as erro:
            raise unittest.SkipTest(f"Banco indisponível ({erro}).")
        from streamlit.testing.v1 import AppTest

        cls.app = AppTest.from_file(str(BASE_DIR / "src" / "dashboard" / "app.py"), default_timeout=120).run()

    def test_01_abre_sem_erro(self):
        self.assertEqual([e.value for e in self.app.exception], [])

    def test_02_pergunta_e_resposta_no_topo_da_visao_executiva(self):
        self.assertTrue(self.app.subheader[0].value.startswith("❓ Pergunta da E1"))
        resposta = next(m.value for m in self.app.markdown if m.value.startswith("**Resposta:**"))
        self.assertIn(f"**{self.primeiro}**", resposta)

    def test_03_ranking_vem_do_mart_do_dbt(self):
        ranking = self.app.dataframe[0].value
        self.assertEqual(ranking["Curso"].iloc[0], self.primeiro)
        self.assertEqual(ranking["Posição"].iloc[0], 1)
        legenda = next(c.value for c in self.app.caption if c.value.startswith("Ranking completo"))
        self.assertIn("dbt_marts.painel_cursos_criticos", legenda)
        self.assertIn(f"{self.total} cursos", legenda)
        self.assertIn("SLA de frescor", legenda)


if __name__ == "__main__":
    unittest.main()
