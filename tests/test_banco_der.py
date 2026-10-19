"""
Teste de integração dos diagramas DER (precisa de PostgreSQL com as migrações aplicadas).

Renderiza os SVGs de silver e gold a partir do catálogo do banco e exige que sejam idênticos
aos versionados em docs/arquitetura/assets/: migração nova sem `python3 scripts/gerar_svg_der.py`
deixa o diagrama desatualizado e este teste falha.

Pulado se o banco não estiver no ar.

Uso:
    python3 -m unittest tests/test_banco_der.py
"""

import sys
import tempfile
import unittest
from pathlib import Path

import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "scripts"))
from src.db.conexao import conectar  # noqa: E402
import gerar_svg_der as der  # noqa: E402


class TestDerSincronizado(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            with conectar() as conn, conn.cursor() as cur:
                cls.silver = der.get_schema_metadata(cur, "silver")
                cls.gold = der.get_schema_metadata(cur, "gold")
        except psycopg.OperationalError as erro:
            raise unittest.SkipTest(f"PostgreSQL indisponível: {erro}")

    def _comparar(self, renderizar, metadados, nome):
        with tempfile.TemporaryDirectory() as pasta:
            gerado = Path(pasta) / nome
            renderizar(*metadados, gerado)
            versionado = der.ASSETS_DIR / nome
            self.assertEqual(
                gerado.read_text(encoding="utf-8").splitlines(),
                versionado.read_text(encoding="utf-8").splitlines(),
                f"{nome} desatualizado: rode python3 scripts/gerar_svg_der.py",
            )

    def test_silver_confere_com_o_catalogo(self):
        self._comparar(der.render_silver_svg, self.silver, "der_silver_3nf.svg")

    def test_gold_confere_com_o_catalogo(self):
        self._comparar(der.render_gold_svg, self.gold, "der_gold_star_schema.svg")


if __name__ == "__main__":
    unittest.main()
