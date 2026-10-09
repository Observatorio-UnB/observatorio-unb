"""
Testes unitários da leitura em blocos do Censo da Educação Superior (sem PostgreSQL nem rede).

Um zip sintético imita o pacote do INEP: confere o tamanho dos blocos e que o recorte de
federais por bloco dá o mesmo resultado que o recorte do arquivo inteiro.

Uso:
    python3 -m unittest tests/test_unit_inep_streaming.py
"""

import io
import sys
import unittest
import zipfile
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.ingestion import inep_censo_superior as inep  # noqa: E402

TOTAL_CURSOS = 120_001


def _zip_sintetico() -> zipfile.ZipFile:
    cursos = pd.DataFrame({c: 0 for c in inep.COLUNAS_CURSO}, index=range(TOTAL_CURSOS))
    cursos["CO_CURSO"] = range(TOTAL_CURSOS)
    cursos["CO_IES"] = cursos["CO_CURSO"] % 4           # IES 0 e 1 são universidades federais
    cursos["TP_MODALIDADE_ENSINO"] = 1 + cursos["CO_CURSO"] % 2  # metade presencial
    cursos["NO_CURSO"] = "CURSO"
    ies = pd.DataFrame({
        "CO_IES": [0, 1, 2, 3],
        "NO_IES": ["A", "B", "C", "D"],
        "TP_CATEGORIA_ADMINISTRATIVA": [1, 1, 2, 1],
        "TP_ORGANIZACAO_ACADEMICA": [1, 1, 1, 3],
    })
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("dados/SUP_CURSOS_2019.CSV", cursos.to_csv(sep=";", index=False).encode("latin-1"))
        zf.writestr("dados/SUP_IES_2019.CSV", ies.to_csv(sep=";", index=False).encode("latin-1"))
    return zipfile.ZipFile(buffer)


class TestLeituraEmBlocos(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.zf = _zip_sintetico()

    def test_blocos_tem_no_maximo_50_mil_linhas(self):
        tamanhos = [len(b) for b in inep.ler_cursos_em_blocos(self.zf)]
        self.assertEqual(tamanhos, [50_000, 50_000, 20_001])

    def test_recorte_por_bloco_igual_ao_do_arquivo_inteiro(self):
        ies = inep._ler_ies_federais(self.zf)
        por_bloco = pd.concat(inep.recortar_federais(b, ies) for b in inep.ler_cursos_em_blocos(self.zf))
        inteiro = inep.recortar_federais(next(inep.ler_cursos_em_blocos(self.zf, TOTAL_CURSOS)), ies)
        pd.testing.assert_frame_equal(por_bloco.reset_index(drop=True), inteiro.reset_index(drop=True))
        # Só presenciais (CO_CURSO par) de IES federais universitárias (CO_IES 0 ou 1).
        self.assertTrue(set(por_bloco["CO_IES"]) == {0} and (por_bloco["CO_CURSO"] % 2 == 0).all())


if __name__ == "__main__":
    unittest.main()
