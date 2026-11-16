"""
Teste de carga concorrente do pool de conexões (src/db/conexao.py). Precisa de PostgreSQL.

20 requisições em paralelo, como 20 sessões do painel abertas ao mesmo tempo, num pool de até 5
conexões: todas respondem, e o banco nunca vê mais de 5 conexões do pool. Também confere que o
pool troca uma conexão derrubada pelo servidor e que, sem conexão livre, a espera termina em
PoolTimeout em vez de abrir conexões além do teto.

Pulados se o banco não estiver no ar.

Uso:
    python3 -m unittest tests/test_banco_pool.py
"""

import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg
from psycopg_pool import PoolTimeout

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db import conexao  # noqa: E402
from src.db.tabelas import consultar  # noqa: E402

REQUISICOES = 20
MAXIMO = 5


class TestPoolSobCarga(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            conexao.conectar(connect_timeout=3).close()
        except psycopg.OperationalError as erro:
            raise unittest.SkipTest(f"Banco indisponível ({erro}). Suba com: docker compose up -d db")
        cls.monitor = conexao.conectar(autocommit=True)

    @classmethod
    def tearDownClass(cls):
        cls.monitor.close()
        conexao.fechar_pools()

    def setUp(self):
        conexao.fechar_pools()
        self.pool = conexao.pool(config=conexao.ConfigPool(minimo=1, maximo=MAXIMO, espera=10))
        self.pool.wait(timeout=10)

    def conexoes_do_pool_no_banco(self) -> int:
        return self.monitor.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE application_name = %s AND pid <> pg_backend_pid()",
            (conexao.NOME_DO_POOL,),
        ).fetchone()[0]

    def test_01_vinte_requisicoes_paralelas_com_no_maximo_cinco_conexoes(self):
        pico = []
        parar = threading.Event()

        def medir():
            while not parar.is_set():
                pico.append(self.conexoes_do_pool_no_banco())
                time.sleep(0.01)

        def requisicao(i):
            # pg_sleep segura a conexão o bastante para as 20 se sobreporem.
            return consultar("SELECT %s::int AS i, pg_sleep(0.2) IS NULL AS dormiu", (i,)).iloc[0]["i"]

        medidor = threading.Thread(target=medir)
        medidor.start()
        try:
            with ThreadPoolExecutor(max_workers=REQUISICOES) as executor:
                respostas = list(executor.map(requisicao, range(REQUISICOES)))
        finally:
            parar.set()
            medidor.join()

        self.assertEqual(sorted(respostas), list(range(REQUISICOES)))
        self.assertLessEqual(max(pico), MAXIMO)
        estatisticas = self.pool.get_stats()
        self.assertGreaterEqual(estatisticas.get("requests_num", 0), REQUISICOES)
        self.assertEqual(estatisticas.get("requests_errors", 0), 0)
        # Com 20 pedidos para 5 conexões, parte esperou na fila em vez de abrir conexão nova.
        self.assertGreater(estatisticas.get("requests_queued", 0), 0)

    def test_02_conexao_derrubada_pelo_servidor_e_trocada(self):
        with conexao.conexao_do_pool() as conn:
            pid = conn.info.backend_pid
        self.monitor.execute("SELECT pg_terminate_backend(%s)", (pid,))
        with conexao.conexao_do_pool() as conn:
            self.assertEqual(conn.execute("SELECT 1").fetchone()[0], 1)
            self.assertNotEqual(conn.info.backend_pid, pid)

    def test_03_sem_conexao_livre_a_espera_termina_em_pool_timeout(self):
        conexao.fechar_pools()
        conexao.pool(config=conexao.ConfigPool(minimo=1, maximo=1, espera=0.5))
        with conexao.conexao_do_pool():
            with self.assertRaises(PoolTimeout):
                with conexao.conexao_do_pool():
                    pass
        self.assertLessEqual(self.conexoes_do_pool_no_banco(), 1)
        self.assertIn(conexao.database_url(), conexao._pools)  # pool cheio, banco no ar: fica

    def test_04_numeric_continua_float_e_a_conexao_volta_sem_o_loader(self):
        valor = consultar("SELECT 1.5::numeric AS x").iloc[0]["x"]
        self.assertIsInstance(valor, float)
        with conexao.conexao_do_pool() as conn:
            self.assertEqual(type(conn.execute("SELECT 1.5::numeric").fetchone()[0]).__name__, "Decimal")


if __name__ == "__main__":
    unittest.main()
