"""
Faixas de tempo de formatura do painel (src/dashboard/faixas.py) e as colunas da gold que as alimentam.

Uso:
    python3 -m unittest tests/test_unit_faixas.py
"""

import sys
import unittest
from pathlib import Path

import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src" / "dashboard"))
sys.path.insert(0, str(BASE_DIR))
from faixas import faixas_exclusivas  # noqa: E402
from src.pipeline.build_gold import ANOS_MATURACAO_COORTE  # noqa: E402


class FaixasExclusivas(unittest.TestCase):

    def test_le_as_colunas_da_gold_na_ordem_do_grafico(self):
        row = {"faixa_minimo_pct": 10.0, "faixa_ideal_pct": 90.0, "faixa_acima_pct": 0.0, "faixa_limite_pct": 0.0}
        self.assertEqual(faixas_exclusivas(row), [10.0, 90.0, 0.0, 0.0])


class ColunasDaGold(unittest.TestCase):
    """No banco: as colunas cumulativas obedecem às relações que a separação em faixas supõe."""

    @classmethod
    def setUpClass(cls):
        from src.db.conexao import conectar
        try:
            cls.conn = conectar(connect_timeout=3)
        except psycopg.OperationalError as erro:
            raise unittest.SkipTest(f"Banco indisponível ({erro})")
        existe = cls.conn.execute("SELECT to_regclass('gold.retencao_cursos_coorte')").fetchone()[0]
        if existe is None or not cls.conn.execute(
                "SELECT EXISTS (SELECT 1 FROM gold.retencao_cursos_coorte)").fetchone()[0]:
            cls.conn.close()
            raise unittest.SkipTest("Gold por coorte não calculada. Rode: bash scripts/rodar_pipeline.sh")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def faixa(self, p, minimo, ideal, maximo):
        return self.conn.execute("SELECT gold.faixa_tempo(%s, %s, %s, %s)", (p, minimo, ideal, maximo)).fetchone()[0]

    def test_limites_das_faixas(self):
        # Matriz de 8 (mínimo), 10 (ideal) e 15 (máximo) semestres.
        esperado = {1: "MINIMO", 8: "MINIMO", 9: "IDEAL", 10: "IDEAL", 11: "ACIMA", 14: "ACIMA", 15: "LIMITE", 20: "LIMITE"}
        for p, faixa in esperado.items():
            self.assertEqual(self.faixa(p, 8, 10, 15), faixa, f"permanência {p}")
        self.assertIsNone(self.faixa(None, 8, 10, 15))

    def test_maximo_igual_ao_ideal_o_limite_prevalece(self):
        self.assertEqual(self.faixa(10, 6, 10, 10), "LIMITE")
        self.assertEqual(self.faixa(9, 6, 10, 10), "IDEAL")

    def test_faixas_somam_100(self):
        for tabela in ("gold.retencao_cursos_unb", "gold.retencao_cursos_coorte"):
            ruins = self.conn.execute(f"""
                SELECT count(*) FROM {tabela}
                WHERE faixa_minimo_pct IS NULL
                   OR faixa_minimo_pct + faixa_ideal_pct + faixa_acima_pct + faixa_limite_pct NOT BETWEEN 99.95 AND 100.05
                      AND formados_tempo_ideal_pct + formados_acima_ideal_pct <> 0""").fetchone()[0]
            self.assertEqual(ruins, 0, tabela)

    def test_faixas_batem_com_calculo_independente_em_pandas(self):
        """Refaz as faixas em Pandas a partir da Silver e exige igualdade curso a curso e coorte a coorte."""
        import numpy as np
        import pandas as pd
        from src.db.tabelas import ler
        d = ler("silver.discentes_graduacao")
        e = ler("silver.estrutura_curricular")
        r = ler("gold.regras_harmonizacao_canonicas")
        d["curso"] = d["curso_norm"].replace(dict(zip(r["origem_sigra"], r["destino_estrutura"])))
        base = d.merge(e, left_on="curso", right_on="nome_curso_norm")
        base = base[(base["tipo_saida_grupo"] == "FORMATURA") & base["semestres_permanencia_valida"].notna()]
        p = base["semestres_permanencia_valida"]
        base = base.assign(faixa=np.select(
            [p >= base["semestre_conclusao_maximo"], p <= base["semestre_conclusao_minimo"],
             p <= base["semestre_conclusao_ideal"]], ["LIMITE", "MINIMO", "IDEAL"], "ACIMA"))
        colunas = {"MINIMO": "faixa_minimo_pct", "IDEAL": "faixa_ideal_pct",
                   "ACIMA": "faixa_acima_pct", "LIMITE": "faixa_limite_pct"}

        def esperado(chaves, filtro=None):
            b = base if filtro is None else base[filtro(base)]
            t = pd.crosstab([b[c] for c in chaves], b["faixa"]).reindex(columns=list(colunas), fill_value=0)
            return (t.div(t.sum(axis=1), axis=0) * 100).round(2).rename(columns=colunas)

        corte = int(d["ano_ingresso"].max()) - ANOS_MATURACAO_COORTE
        por_curso = ler("gold.retencao_cursos_unb").set_index("curso")
        exp = esperado(["curso"], lambda b: b["ano_ingresso"] <= corte).reindex(por_curso.index).fillna(0)
        for col in colunas.values():
            pd.testing.assert_series_equal(exp[col], por_curso[col].astype(float), check_names=False, atol=0.011)

        por_coorte = ler("gold.retencao_cursos_coorte").set_index(["curso", "ano_ingresso"])
        exp = esperado(["curso", "ano_ingresso"]).reindex(por_coorte.index).fillna(0)
        for col in colunas.values():
            pd.testing.assert_series_equal(exp[col], por_coorte[col].astype(float), check_names=False, atol=0.011)

    def test_coortes_nao_passam_do_total_do_curso(self):
        # Coortes com menos de 5 alunos ficam de fora (k-anonimato): a soma nunca passa do total do curso.
        linhas = self.conn.execute("""
            SELECT r.total_discentes_registrados, c.n
            FROM gold.retencao_cursos_unb r
            JOIN (SELECT curso, sum(total_discentes_registrados) AS n
                  FROM gold.retencao_cursos_coorte WHERE coorte_madura GROUP BY curso) c USING (curso)
        """).fetchall()
        self.assertTrue(all(c <= total for total, c in linhas))
        self.assertTrue(any(c == total for total, c in linhas))


if __name__ == "__main__":
    unittest.main()
