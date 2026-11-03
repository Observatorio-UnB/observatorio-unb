"""
Testes do SLA de frescor (src/db/frescor.py), sem banco nem rede.

Uso:
    python3 -m unittest tests/test_unit_frescor.py
"""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db import frescor  # noqa: E402
from src.ingestion import ckan_client  # noqa: E402

ATUALIZADA = datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc)


class TestProcessamento(unittest.TestCase):

    def test_view_dentro_do_sla(self):
        v = frescor.verificar_processamento(ATUALIZADA, ATUALIZADA + timedelta(days=35))
        self.assertTrue(v.ok)
        self.assertEqual(v.dias, 35.0)

    def test_view_fora_do_sla(self):
        """A atualização mensal que falha (como em 01/10 e 01/11/2026) estoura o SLA no mês seguinte."""
        v = frescor.verificar_processamento(ATUALIZADA, ATUALIZADA + timedelta(days=35, hours=1))
        self.assertFalse(v.ok)

    def test_relogio_adiantado_nao_da_idade_negativa(self):
        self.assertEqual(frescor.verificar_processamento(ATUALIZADA, ATUALIZADA - timedelta(minutes=5)).dias, 0.0)


class TestFonte(unittest.TestCase):

    def verificar(self, publicada_em: datetime, agora: datetime) -> frescor.Verificacao:
        return frescor.verificar_fonte(ATUALIZADA, {"sigaa": publicada_em}, agora)[0]

    def test_publicacao_ja_processada_nao_conta(self):
        """A idade do dado na origem não é do pipeline: o SIGAA de 2024 processado hoje está em dia."""
        v = self.verificar(datetime(2024, 7, 15, tzinfo=timezone.utc), ATUALIZADA + timedelta(days=30))
        self.assertTrue(v.ok)
        self.assertEqual(v.dias, 0.0)

    def test_publicacao_nova_pendente_dentro_do_sla(self):
        publicada = ATUALIZADA + timedelta(days=2)
        self.assertTrue(self.verificar(publicada, publicada + timedelta(days=20)).ok)

    def test_publicacao_nova_pendente_fora_do_sla(self):
        publicada = ATUALIZADA + timedelta(days=2)
        v = self.verificar(publicada, publicada + timedelta(days=36))
        self.assertFalse(v.ok)
        self.assertIn("depois da última atualização", v.detalhe)


class TestPublicacoesDoPortal(unittest.TestCase):

    def test_escolhe_o_mesmo_recurso_que_a_ingestao(self):
        """O check confere a publicação do arquivo que a ingestão baixaria, e não de qualquer recurso."""
        recursos = [
            {"url": "https://x/sigaa_2023.csv", "last_modified": "2024-01-10T10:00:00"},
            {"url": "https://x/sigaa.csv", "last_modified": "2024-07-15T09:00:00"},
            {"url": "https://x/SIGAA_Concluintes_2024.csv", "last_modified": "2025-03-01T00:00:00"},
        ]
        with mock.patch.object(ckan_client, "fetch_package_metadata", return_value={"resources": recursos}):
            publicacoes = frescor.publicacoes_do_portal(("sigaa",))
        self.assertEqual(publicacoes["sigaa"], datetime(2024, 7, 15, 9, tzinfo=timezone.utc))

    def test_fonte_sem_recurso_no_portal_e_erro(self):
        with mock.patch.object(ckan_client, "fetch_package_metadata", return_value={"resources": []}):
            with self.assertRaises(RuntimeError):
                frescor.publicacoes_do_portal(("sigaa",))


class TestSaida(unittest.TestCase):

    def test_sla_violado_sai_com_erro(self):
        violada = frescor.Verificacao("processamento", 40, 35, "")
        with mock.patch.object(frescor, "verificar", return_value=[violada]), self.assertLogs("frescor", "ERROR"):
            self.assertEqual(frescor.main([]), 1)

    def test_sla_cumprido_sai_sem_erro(self):
        cumprida = frescor.Verificacao("processamento", 3, 35, "")
        with mock.patch.object(frescor, "verificar", return_value=[cumprida]):
            self.assertEqual(frescor.main([]), 0)


if __name__ == "__main__":
    unittest.main()
