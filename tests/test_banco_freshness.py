"""
Testes do SLA de freshness contra o banco do pipeline (precisam de PostgreSQL com a gold carregada).

Pulados se o banco não estiver no ar ou se a view do painel estiver vazia.

Uso:
    python3 -m unittest tests/test_banco_freshness.py
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db import freshness  # noqa: E402
from src.db.conexao import conectar  # noqa: E402


class TestFreshnessNoBanco(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            cls.conn = conectar(autocommit=True, connect_timeout=3)
        except psycopg.OperationalError as erro:
            raise unittest.SkipTest(f"Banco indisponível ({erro}). Suba com: docker compose up -d db")
        try:
            cls.atualizada_em = freshness.atualizacao_da_view(cls.conn)
        except (RuntimeError, psycopg.Error) as erro:
            cls.conn.close()
            raise unittest.SkipTest(f"View do painel sem carga ({erro}). Rode o pipeline.")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_view_recem_atualizada_cumpre_o_sla(self):
        """No CI os testes rodam logo depois do pipeline: a view tem minutos."""
        idade = datetime.now(timezone.utc) - self.atualizada_em
        if not os.environ.get("CI") and idade > timedelta(days=freshness.SLA_DIAS):
            self.skipTest(f"banco local com a view de {idade.days} dias: rode o pipeline para testar")
        verificacoes = freshness.verificar()
        self.assertEqual(len(verificacoes), 1)
        self.assertTrue(verificacoes[0].ok, verificacoes[0])

    def test_mesma_view_viola_o_sla_36_dias_depois(self):
        agora = self.atualizada_em + timedelta(days=36)
        self.assertFalse(freshness.verificar(agora=agora)[0].ok)

    def test_resumo_para_o_painel(self):
        resumo = freshness.resumo_para_o_painel(self.conn)
        self.assertEqual(resumo["tabela"], "gold.mv_dashboard_executivo")
        self.assertEqual(resumo["sla_dias"], freshness.SLA_DIAS)
        self.assertLess(datetime.now(timezone.utc) - datetime.fromisoformat(resumo["atualizada_em"]),
                        timedelta(days=freshness.SLA_DIAS))


if __name__ == "__main__":
    unittest.main()
