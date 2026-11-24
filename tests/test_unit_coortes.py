"""
Testes unitários de src/dashboard/coortes.py, sem banco nem Streamlit.

Uso:
    python3 -m unittest tests/test_unit_coortes.py
"""

import re
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src" / "dashboard"))
from coortes import (  # noqa: E402
    anos_disponiveis,
    comparar_periodos,
    ic_wilson_pct,
    intervalo_oficial,
    limites_funil,
    matriz_heatmap_coortes,
    narrativa_executiva,
    reagregar_por_coortes,
)

DECIMAL_COM_PONTO = re.compile(r"(?<![\d.\w/])\d+\.\d{1,2}(?![\d.\w])")


def _df_coortes_exemplo():
    return pd.DataFrame([
        # Curso A: melhora de 50% para 20% de evasão entre 2010-2013 e 2014-2016
        {"curso": "CURSO A", "ano_ingresso": 2010, "coorte_madura": True, "semestre_ideal_previsto": 8.0,
         "total_discentes_registrados": 100, "total_formados": 50, "total_evadidos_desligados": 50, "total_ainda_ativos": 0,
         "taxa_formatura_pct": 50.0, "taxa_evasao_pct": 50.0, "formados_tempo_ideal_pct": 60.0,
         "tempo_medio_real_semestres": 9.0, "faixa_minimo_pct": 10.0, "faixa_ideal_pct": 50.0, "faixa_acima_pct": 30.0, "faixa_limite_pct": 10.0},
        {"curso": "CURSO A", "ano_ingresso": 2015, "coorte_madura": True, "semestre_ideal_previsto": 8.0,
         "total_discentes_registrados": 100, "total_formados": 80, "total_evadidos_desligados": 20, "total_ainda_ativos": 0,
         "taxa_formatura_pct": 80.0, "taxa_evasao_pct": 20.0, "formados_tempo_ideal_pct": 70.0,
         "tempo_medio_real_semestres": 8.5, "faixa_minimo_pct": 15.0, "faixa_ideal_pct": 55.0, "faixa_acima_pct": 25.0, "faixa_limite_pct": 5.0},
        {"curso": "CURSO A", "ano_ingresso": 2020, "coorte_madura": False, "semestre_ideal_previsto": 8.0,
         "total_discentes_registrados": 100, "total_formados": 5, "total_evadidos_desligados": 15, "total_ainda_ativos": 80,
         "taxa_formatura_pct": 5.0, "taxa_evasao_pct": 15.0, "formados_tempo_ideal_pct": 100.0,
         "tempo_medio_real_semestres": 7.0, "faixa_minimo_pct": 100.0, "faixa_ideal_pct": 0.0, "faixa_acima_pct": 0.0, "faixa_limite_pct": 0.0},
        # Curso B: só aparece em 2010 e 2015 (sem 2020 -> NaN no heatmap)
        {"curso": "CURSO B", "ano_ingresso": 2010, "coorte_madura": True, "semestre_ideal_previsto": 10.0,
         "total_discentes_registrados": 50, "total_formados": 20, "total_evadidos_desligados": 30, "total_ainda_ativos": 0,
         "taxa_formatura_pct": 40.0, "taxa_evasao_pct": 60.0, "formados_tempo_ideal_pct": 30.0,
         "tempo_medio_real_semestres": 12.0, "faixa_minimo_pct": 5.0, "faixa_ideal_pct": 25.0, "faixa_acima_pct": 50.0, "faixa_limite_pct": 20.0},
        {"curso": "CURSO B", "ano_ingresso": 2015, "coorte_madura": True, "semestre_ideal_previsto": 10.0,
         "total_discentes_registrados": 50, "total_formados": 15, "total_evadidos_desligados": 35, "total_ainda_ativos": 0,
         "taxa_formatura_pct": 30.0, "taxa_evasao_pct": 70.0, "formados_tempo_ideal_pct": 20.0,
         "tempo_medio_real_semestres": 13.0, "faixa_minimo_pct": 0.0, "faixa_ideal_pct": 20.0, "faixa_acima_pct": 55.0, "faixa_limite_pct": 25.0},
        # Curso-tronco (deve ser excluído pela ADR 0022)
        {"curso": "ENGENHARIA", "ano_ingresso": 2010, "coorte_madura": True, "semestre_ideal_previsto": 10.0,
         "total_discentes_registrados": 200, "total_formados": 10, "total_evadidos_desligados": 190, "total_ainda_ativos": 0,
         "taxa_formatura_pct": 5.0, "taxa_evasao_pct": 95.0, "formados_tempo_ideal_pct": 10.0,
         "tempo_medio_real_semestres": 14.0, "faixa_minimo_pct": 0.0, "faixa_ideal_pct": 10.0, "faixa_acima_pct": 60.0, "faixa_limite_pct": 30.0},
    ])


def _df_gold_base_exemplo():
    return pd.DataFrame([
        {"curso": "CURSO A", "campus": "DARCY RIBEIRO", "turno": "DIURNO", "categoria_grau": "BACHARELADO",
         "semestre_ideal_previsto": 8.0, "pibic_total_projetos": 20},
        {"curso": "CURSO B", "campus": "FCTE - GAMA", "turno": "NOTURNO", "categoria_grau": "LICENCIATURA",
         "semestre_ideal_previsto": 10.0, "pibic_total_projetos": 5},
    ])


class TestCoortes(unittest.TestCase):

    def test_01_intervalo_e_anos_disponiveis(self):
        self.assertEqual(intervalo_oficial({"coortes_ingresso_analisadas": "2010-2016"}), (2010, 2016))
        self.assertEqual(intervalo_oficial({}), (2010, 2016))
        anos, ultimo_maduro = anos_disponiveis(_df_coortes_exemplo())
        self.assertEqual(anos, [2010, 2015, 2020])
        self.assertEqual(ultimo_maduro, 2015)

    def test_02_reagregar_exclui_tronco_e_calcula_taxas_e_irc(self):
        df = reagregar_por_coortes(
            _df_coortes_exemplo(),
            _df_gold_base_exemplo(),
            2010,
            2015,
            cursos_tronco=["ENGENHARIA"],
        )
        self.assertEqual(sorted(df["curso"].tolist()), ["CURSO A", "CURSO B"])
        row_a = df[df["curso"] == "CURSO A"].iloc[0]
        self.assertEqual(row_a["total_discentes_registrados"], 200)
        self.assertAlmostEqual(row_a["taxa_evasao_pct"], 35.0, places=2)
        self.assertAlmostEqual(row_a["taxa_formatura_pct"], 65.0, places=2)
        self.assertEqual(row_a["campus"], "DARCY RIBEIRO")
        self.assertEqual(row_a["turno"], "DIURNO")
        # Curso B tem maior evasão (65%) e maior atraso -> IRC maior que Curso A
        row_b = df[df["curso"] == "CURSO B"].iloc[0]
        self.assertGreater(row_b["indice_retencao_critica"], row_a["indice_retencao_critica"])

    def test_03_ic_wilson_limites_e_largura(self):
        inf_pq, sup_pq, marg_pq = ic_wilson_pct(5, 10)
        inf_gd, sup_gd, marg_gd = ic_wilson_pct(500, 1000)
        self.assertGreaterEqual(inf_pq, 0.0)
        self.assertLessEqual(sup_pq, 100.0)
        self.assertGreater(marg_pq, marg_gd)

    def test_04_limites_funil_estreitam_com_n(self):
        inf, sup = limites_funil(40.0, [10, 100, 1000])
        larguras = sup - inf
        self.assertGreater(larguras[0], larguras[1])
        self.assertGreater(larguras[1], larguras[2])

    def test_05_comparar_periodos(self):
        comp = comparar_periodos(
            _df_coortes_exemplo(),
            periodo_a=(2010, 2013),
            periodo_b=(2014, 2016),
            cursos_tronco=["ENGENHARIA"],
            min_alunos=15,
        )
        self.assertEqual(len(comp), 2)
        row_a = comp[comp["curso"] == "CURSO A"].iloc[0]
        row_b = comp[comp["curso"] == "CURSO B"].iloc[0]
        self.assertAlmostEqual(row_a["delta_evasao_pp"], -30.0, places=2)
        self.assertAlmostEqual(row_b["delta_evasao_pp"], 10.0, places=2)

    def test_06_heatmap_preserva_nan_para_celulas_ausentes(self):
        piv_val, piv_n, anos = matriz_heatmap_coortes(
            _df_coortes_exemplo(),
            metrica="taxa_evasao_pct",
            cursos_tronco=["ENGENHARIA"],
        )
        self.assertEqual(anos, [2010, 2015, 2020])
        self.assertTrue(pd.isna(piv_val.loc["CURSO B", 2020]))
        self.assertTrue(pd.isna(piv_n.loc["CURSO B", 2020]))
        self.assertNotIn("ENGENHARIA", piv_val.index)

    def test_07_narrativa_executiva_sem_ponto_decimal(self):
        df = reagregar_por_coortes(
            _df_coortes_exemplo(),
            _df_gold_base_exemplo(),
            2010,
            2015,
            cursos_tronco=["ENGENHARIA"],
        )
        bullets = narrativa_executiva(df, df, "2010–2015", eh_oficial=True)
        self.assertGreaterEqual(len(bullets), 2)
        for b in bullets:
            self.assertEqual(DECIMAL_COM_PONTO.findall(b), [], f"Ponto decimal encontrado em: {b}")


if __name__ == "__main__":
    unittest.main()
