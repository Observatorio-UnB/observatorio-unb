"""
Testes unitários da rotina de auditoria e reconciliação do Supabase (sem PostgreSQL).
Uso:
    python3 -m unittest tests/test_unit_reconciliar_supabase.py
"""

import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.reconciliar_supabase import (  # noqa: E402
    formatar_relatorio_markdown,
    reconciliar_contagens,
    verificar_controle_acesso,
    verificar_extensao_vector,
    verificar_limites_recursos,
    verificar_migracoes,
    verificar_privacidade_lgpd,
)


class ConexaoFalsaVector:
    def __init__(self, versao="0.8.2"):
        self.versao = versao

    def execute(self, sql, params=None):
        return self

    def fetchone(self):
        return (self.versao,) if self.versao else None


class ConexaoFalsaAcesso:
    def __init__(self, papel_existe=True, esquemas=None):
        self.papel_existe = papel_existe
        self.esquemas = esquemas or {
            "bronze": False,
            "silver": False,
            "gold": True,
            "busca": True,
            "public": True,
        }
        self._last_schema = None

    def execute(self, sql, params=None):
        if "WHERE rolname = 'observatorio_leitura'" in sql:
            self._resposta = (self.papel_existe,)
        elif "has_schema_privilege" in sql:
            schema = params[0]
            self._resposta = (self.esquemas.get(schema, False),)
        else:
            self._resposta = (False,)
        return self

    def fetchone(self):
        return self._resposta


class ConexaoFalsaLGPD:
    def __init__(self, linhas_por_tabela=None):
        self.linhas = linhas_por_tabela or {}

    def execute(self, sql, params=None):
        if "information_schema.tables" in sql:
            self._resposta = (True,)
        elif "SELECT count(*) FROM" in sql:
            tabela = sql.split("FROM")[1].strip()
            self._resposta = (self.linhas.get(tabela, 0),)
        else:
            self._resposta = (0,)
        return self

    def fetchone(self):
        return self._resposta


class ConexaoFalsaLimites:
    def __init__(self, bytes_ocupados=144703488):
        self.bytes_ocupados = bytes_ocupados

    def execute(self, sql, params=None):
        if "pg_size_pretty" in sql:
            self._resposta = ("138 MB",)
        elif "pg_database_size" in sql:
            self._resposta = (self.bytes_ocupados,)
        elif "pg_stat_activity" in sql:
            self._resposta = (5,)
        else:
            self._resposta = (0,)
        return self

    def fetchone(self):
        return self._resposta


class TestAuditoriaSupabase(unittest.TestCase):
    def test_extensao_vector_instalada(self):
        conn = ConexaoFalsaVector("0.8.2")
        res = verificar_extensao_vector(conn)
        self.assertTrue(res["instalada"])
        self.assertEqual(res["versao"], "0.8.2")
        self.assertEqual(res["status"], "OK")

    def test_extensao_vector_ausente(self):
        conn = ConexaoFalsaVector(None)
        res = verificar_extensao_vector(conn)
        self.assertFalse(res["instalada"])
        self.assertEqual(res["status"], "FALHA")

    def test_controle_de_acesso_seguro(self):
        conn = ConexaoFalsaAcesso(papel_existe=True)
        res = verificar_controle_acesso(conn)
        self.assertTrue(res["papel_existe"])
        self.assertTrue(res["isolamento_ok"])
        self.assertEqual(res["status"], "OK")

    def test_controle_de_acesso_inseguro_se_bronze_tiver_usage(self):
        conn = ConexaoFalsaAcesso(papel_existe=True, esquemas={"bronze": True, "silver": False, "gold": True})
        res = verificar_controle_acesso(conn)
        self.assertFalse(res["isolamento_ok"])
        self.assertEqual(res["status"], "ALERTA")

    def test_privacidade_lgpd_conforme_sem_microdados(self):
        conn = ConexaoFalsaLGPD(linhas_por_tabela={})
        res = verificar_privacidade_lgpd(conn)
        self.assertEqual(res["status"], "OK")
        self.assertEqual(res["linhas_vazadas"], 0)

    def test_privacidade_lgpd_detecta_vazamento_se_houver_linhas(self):
        conn = ConexaoFalsaLGPD(linhas_por_tabela={"bronze.sigra_discentes": 100})
        res = verificar_privacidade_lgpd(conn)
        self.assertEqual(res["status"], "FALHA_CRITICA")
        self.assertEqual(res["linhas_vazadas"], 100)

    def test_limites_recursos_calcula_percentual_da_cota(self):
        # 138 MB de 500 MB = ~27.6%
        conn = ConexaoFalsaLimites(bytes_ocupados=138 * 1024 * 1024)
        res = verificar_limites_recursos(conn)
        self.assertEqual(res["status"], "OK")
        self.assertEqual(res["cota_mb"], 500.0)
        self.assertAlmostEqual(res["tamanho_mb"], 138.0, places=1)
        self.assertAlmostEqual(res["pct_uso"], 27.6, places=1)

    def test_formatar_relatorio_markdown(self):
        auditoria_mock = {
            "data_execucao": "2026-11-02T20:00:00Z",
            "status_geral": "APROVADO",
            "extensao_vector": {"instalada": True, "versao": "0.8.2"},
            "migracoes": {"total_locais": 23, "total_aplicadas": 23, "pendentes": []},
            "controle_acesso": {
                "papel_existe": True,
                "isolamento_ok": True,
                "esquemas": {"gold": True, "busca": True, "bronze": False, "silver": False},
            },
            "privacidade_lgpd": {
                "linhas_vazadas": 0,
                "tabelas_auditadas": {
                    "bronze.sigra_discentes": {"existe": True, "linhas": 0, "status": "OK"}
                },
            },
            "limites": {
                "tamanho_legivel": "138 MB",
                "tamanho_mb": 138.0,
                "cota_mb": 500.0,
                "pct_uso": 27.6,
                "conexoes_ativas": 5,
                "status": "OK",
            },
            "reconciliacao": [
                {"tabela": "gold.retencao_cursos_unb", "qtd_remota": 95, "qtd_local": 95, "status": "RECONCILIADO"}
            ],
        }
        md = formatar_relatorio_markdown(auditoria_mock)
        self.assertIn("Relatório de Auditoria e Reconciliação do Banco Online", md)
        self.assertIn("APROVADO", md)
        self.assertIn("pgvector", md)
        self.assertIn("gold.retencao_cursos_unb", md)


if __name__ == "__main__":
    unittest.main()
