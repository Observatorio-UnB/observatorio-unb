"""
Testes unitários do pool de conexões (src/db/conexao.py), sem PostgreSQL: o ConnectionPool e a
conexão de teste são substituídos por dublês.

Uso:
    python3 -m unittest tests/test_unit_pool.py
"""

import os
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

from psycopg_pool import ConnectionPool, PoolTimeout

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db import conexao  # noqa: E402

URL = "postgresql://ninguem:x@localhost:1/teste"


class TestPool(unittest.TestCase):

    def setUp(self):
        conexao.fechar_pools()
        self.pool_falso = mock.patch.object(conexao, "ConnectionPool", autospec=True)
        self.construtor = self.pool_falso.start()
        self.construtor.check_connection = ConnectionPool.check_connection
        self.teste = mock.patch.object(conexao, "conectar")
        self.conectar = self.teste.start()

    def tearDown(self):
        self.pool_falso.stop()
        self.teste.stop()
        conexao._pools.clear()

    def test_01_um_pool_por_url_mesmo_com_20_threads_ao_mesmo_tempo(self):
        pools = []
        largada = threading.Barrier(20)

        def pedir():
            largada.wait()
            pools.append(conexao.pool(URL))

        threads = [threading.Thread(target=pedir) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(self.construtor.call_count, 1)
        self.assertEqual(len({id(p) for p in pools}), 1)
        conexao.pool("postgresql://outro/banco")
        self.assertEqual(self.construtor.call_count, 2)

    def test_02_limites_tempos_e_opcoes_de_conexao(self):
        conexao.pool(URL, conexao.ConfigPool(minimo=2, maximo=7, espera=3, ociosa=60, vida_maxima=600))
        args = self.construtor.call_args
        self.assertEqual(args.args, (URL,))
        self.assertEqual(
            {k: args.kwargs[k] for k in ("min_size", "max_size", "timeout", "max_idle", "max_lifetime")},
            {"min_size": 2, "max_size": 7, "timeout": 3, "max_idle": 60, "max_lifetime": 600},
        )
        self.assertIs(args.kwargs["check"], ConnectionPool.check_connection)
        self.assertIsNone(args.kwargs["kwargs"]["prepare_threshold"])  # pooler transacional do Supabase
        self.assertEqual(args.kwargs["kwargs"]["application_name"], conexao.NOME_DO_POOL)

    def test_03_configuracao_pelo_ambiente(self):
        with mock.patch.dict(os.environ, {"POOL_MAXIMO": "4", "POOL_ESPERA_S": "2.5"}):
            config = conexao.ConfigPool.do_ambiente()
        self.assertEqual((config.maximo, config.espera, config.minimo), (4, 2.5, conexao.ConfigPool().minimo))

    def test_04_sem_banco_falha_ja_e_nao_guarda_o_pool(self):
        self.conectar.side_effect = conexao.psycopg.OperationalError("connection refused")
        with self.assertRaises(conexao.psycopg.OperationalError):
            conexao.pool(URL)
        self.construtor.assert_not_called()
        self.assertNotIn(URL, conexao._pools)

    def test_05_tempo_esgotado_com_o_banco_fora_descarta_o_pool(self):
        instancia = self.construtor.return_value
        instancia.connection.side_effect = PoolTimeout("sem conexão livre")
        conexao.pool(URL)
        self.conectar.side_effect = conexao.psycopg.OperationalError("connection refused")
        with self.assertRaises(PoolTimeout):
            with conexao.conexao_do_pool(URL):
                pass
        self.assertNotIn(URL, conexao._pools)
        instancia.close.assert_called_once()

    def test_06_tempo_esgotado_com_o_banco_no_ar_mantem_o_pool(self):
        """Pool cheio não é banco fora: um pool novo abriria conexões além do teto."""
        instancia = self.construtor.return_value
        instancia.connection.side_effect = PoolTimeout("sem conexão livre")
        with self.assertRaises(PoolTimeout):
            with conexao.conexao_do_pool(URL):
                pass
        self.assertIn(URL, conexao._pools)
        instancia.close.assert_not_called()

    def test_07_fechar_pools_fecha_todos(self):
        conexao.pool(URL)
        conexao.pool("postgresql://outro/banco")
        conexao.fechar_pools()
        self.assertEqual(self.construtor.return_value.close.call_count, 2)
        self.assertEqual(conexao._pools, {})


if __name__ == "__main__":
    unittest.main()
