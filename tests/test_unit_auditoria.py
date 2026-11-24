"""
Testes da auditoria de qualidade (src/audit/quality_auditor.py), sem banco.

Uso:
    python3 -m unittest tests/test_unit_auditoria.py
"""

import sys
import unittest
from collections import Counter
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.audit import quality_auditor  # noqa: E402


class TestAtivosDaLista(unittest.TestCase):

    def test_grau_nulo_fica_fora_como_none_e_como_nan(self):
        """O pandas 2 lê o nulo do banco como None; o pandas 3, como NaN, que é verdadeiro."""
        linhas = [
            ("2022", "Bacharelado"), ("2022", None), ("2022", float("nan")), ("2022", "Mestrado"),
            ("2022", "Doutorado"), ("2023", "Licenciatura"), ("2023", " "),
        ]
        self.assertEqual(quality_auditor.ativos_de_graduacao_por_coorte(linhas),
                         Counter({"2022": 1, "2023": 1}))

    def test_le_o_dataframe_com_coluna_de_texto(self):
        """Mesmo resultado com a coluna no tipo de texto do pandas, em que o nulo é pd.NA."""
        df = pd.DataFrame({
            "ano_ingresso": ["2022", "2022", "2022"],
            "grau": pd.array(["Engenheiro Civil", None, "Médico"], dtype="string"),
        })
        self.assertEqual(quality_auditor.ativos_de_graduacao_por_coorte(df.itertuples(index=False)),
                         Counter({"2022": 2}))


if __name__ == "__main__":
    unittest.main()
