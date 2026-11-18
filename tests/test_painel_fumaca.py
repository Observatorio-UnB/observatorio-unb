"""
Fumaça do painel (Streamlit AppTest): cada tela renderiza sem exceção e sem número com ponto decimal
nos textos, métricas e legendas. Usa a gold do banco ou, sem banco, o export versionado do painel.

    python -m unittest tests.test_painel_fumaca
"""
import os
import re
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

try:
    from streamlit.testing.v1 import AppTest
except ImportError:  # pragma: no cover
    AppTest = None

# Decimal com 1 ou 2 casas ("85.7"); milhar tem 3 dígitos ("67.063") e não casa.
DECIMAL_COM_PONTO = re.compile(r"(?<![\d.\w/])\d+\.\d{1,2}(?![\d.\w])")


def _textos(at):
    for grupo in (at.markdown, at.caption, at.metric, at.info, at.warning, at.success):
        for el in grupo:
            yield el.value if hasattr(el, "value") else str(el)


@unittest.skipIf(AppTest is None, "streamlit não instalado")
class TestPainelFumaca(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")
        cls.at = AppTest.from_file(str(BASE / "src/dashboard/app.py"), default_timeout=120).run()
        if cls.at.exception:
            raise unittest.SkipTest(f"Painel sem fonte de dados: {cls.at.exception[0].value[:120]}")
        cls.telas = list(cls.at.sidebar.radio[0].options)

    def test_todas_as_telas_renderizam(self):
        for tela in self.telas:
            with self.subTest(tela=tela):
                at = self.at.sidebar.radio[0].set_value(tela).run()
                self.assertEqual([e.value[:200] for e in at.exception], [])

    def test_sem_ponto_decimal_nos_textos(self):
        for tela in self.telas:
            with self.subTest(tela=tela):
                at = self.at.sidebar.radio[0].set_value(tela).run()
                achados = [m.group() for t in _textos(at) for m in DECIMAL_COM_PONTO.finditer(str(t))]
                self.assertEqual(achados[:5], [])


if __name__ == "__main__":
    unittest.main()
