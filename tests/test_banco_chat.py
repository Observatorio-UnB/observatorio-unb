"""
O usuário do chat (migração 0027) lê gold, não lê silver e não escreve. Precisa de PostgreSQL migrado.

Uso:
    python3 -m unittest tests/test_banco_chat.py
"""

import sys
import unittest
from pathlib import Path

import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.chat.ferramentas import consultar_sql, descrever_esquema, url_chat  # noqa: E402


class TestUsuarioChat(unittest.TestCase):

    def test_le_a_gold(self):
        r = consultar_sql("SELECT count(*) AS n FROM gold.dim_curso")
        self.assertEqual(r["colunas"], ["n"])

    def test_banco_barra_silver_e_escrita_sem_a_validacao_de_texto(self):
        # Vai direto ao banco, contornando validar_sql: quem barra é o papel observatorio_chat.
        with psycopg.connect(url_chat()) as conn:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                conn.execute("SELECT 1 FROM silver.cursos LIMIT 1")
            conn.rollback()
            with self.assertRaises(psycopg.errors.ReadOnlySqlTransaction):
                conn.execute("CREATE TABLE gold.x_chat (a int)")

    def test_esquema_so_tem_camadas_permitidas(self):
        texto = descrever_esquema()
        tabelas = [l.split()[0] for l in texto.splitlines() if l and not l.startswith(" ")]
        self.assertIn("gold.dim_curso", tabelas)
        # Os COMMENT ON citam a silver como origem; o que não pode aparecer é tabela dela.
        self.assertFalse([t for t in tabelas if t.split(".")[0] not in ("gold", "dbt_marts", "busca")])


if __name__ == "__main__":
    unittest.main()
