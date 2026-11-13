"""
O checksum das migrações não depende do fim de linha (CRLF do Windows com autocrlf, LF do Linux/CI).

Uso:
    python3 -m unittest tests/test_unit_migrar.py
"""

import sys
import tempfile
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.migrar import _checksum  # noqa: E402


class TestChecksum(unittest.TestCase):

    def test_crlf_e_lf_dao_o_mesmo_checksum(self):
        with tempfile.TemporaryDirectory() as d:
            lf, crlf, outro = Path(d, "a.sql"), Path(d, "b.sql"), Path(d, "c.sql")
            lf.write_bytes(b"SELECT 1;\nSELECT 2;\n")
            crlf.write_bytes(b"SELECT 1;\r\nSELECT 2;\r\n")
            outro.write_bytes(b"SELECT 1;\nSELECT 3;\n")
            self.assertEqual(_checksum(lf), _checksum(crlf))
            self.assertNotEqual(_checksum(lf), _checksum(outro))


if __name__ == "__main__":
    unittest.main()
