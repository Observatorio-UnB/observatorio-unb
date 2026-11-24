"""
ETL reverso para a fila de intervenção e definição única das métricas (precisam de PostgreSQL).

  - TestSincronizacao: o comportamento da sincronização sobre cursos montados no teste, numa
    transação desfeita no fim: idempotência, andamento da coordenação preservado, saída e volta à
    fila, ciclo antigo recusado e o privilégio por coluna do papel coordenacao_academica.
  - TestMesmoNumero: a fila, o painel e a camada semântica dão o mesmo número para o mesmo curso.
    Pulado se as camadas do dbt não foram construídas.

Pulados se o banco não estiver no ar.

Uso:
    python3 -m unittest tests/test_banco_etl_reverso.py
"""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import psycopg
from psycopg import Rollback
from psycopg.rows import dict_row

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar  # noqa: E402
from src.db.migrar import aplicar_migracoes  # noqa: E402
from src.etl_reverso.fila_intervencao import OrigemInvalida, ler_origem, sincronizar  # noqa: E402

CICLO = datetime(2026, 11, 1, 6, 0, tzinfo=timezone.utc)
VERSAO = "indice_retencao_critica@1.0.0;taxa_evasao_pct@1.0.0"


def curso(nome, irc, evasao=50.0, posicao=1):
    return {"nome_curso": nome, "campus": "DARCY RIBEIRO", "area_conhecimento": "X", "posicao": posicao,
            "classificacao_retencao": "RETENÇÃO CRÍTICA", "indice_retencao_critica": Decimal(str(irc)),
            "taxa_evasao_pct": Decimal(str(evasao)), "atraso_medio_semestres": Decimal("2.5"),
            "formados_tempo_ideal_pct": Decimal("20"), "total_ingressantes": 300}


def _conectar() -> psycopg.Connection:
    try:
        conn = conectar(autocommit=True, connect_timeout=3)
    except psycopg.OperationalError as erro:
        raise unittest.SkipTest(f"Banco indisponível ({erro}). Suba com: docker compose up -d db")
    aplicar_migracoes()
    return conn


class TestSincronizacao(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.conn = _conectar()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def setUp(self):
        # Cada teste numa transação desfeita no fim, sobre uma fila vazia.
        self.transacao = self.conn.transaction()
        self.transacao.__enter__()
        self.conn.execute("DELETE FROM operacional.fila_intervencao")
        self.conn.execute("DELETE FROM operacional.fila_intervencao_execucoes")

    def tearDown(self):
        self.transacao.__exit__(Rollback, Rollback(), None)

    def fila(self):
        with self.conn.cursor(row_factory=dict_row) as cur:
            return {r["nome_curso"]: r for r in cur.execute(
                "SELECT * FROM operacional.fila_intervencao ORDER BY nome_curso").fetchall()}

    def test_01_primeira_carga_e_reexecucao_sem_efeito(self):
        r1 = sincronizar(self.conn, [curso("A", 90), curso("B", 80, posicao=2)], VERSAO, CICLO)
        antes = self.fila()
        r2 = sincronizar(self.conn, [curso("A", 90), curso("B", 80, posicao=2)], VERSAO, CICLO)
        self.assertEqual((r1.inseridos, r1.atualizados, r1.sairam_da_fila), (2, 0, 0))
        self.assertEqual((r2.inseridos, r2.atualizados, r2.sairam_da_fila), (0, 0, 0))
        self.assertEqual(self.fila(), antes, "reexecutar o mesmo ciclo não pode mudar nenhuma linha")

    def test_02_andamento_da_coordenacao_sobrevive_a_novo_ciclo(self):
        sincronizar(self.conn, [curso("A", 90)], VERSAO, CICLO)
        self.conn.execute("""UPDATE operacional.fila_intervencao
                             SET status = 'PLANO_EM_EXECUCAO', responsavel = 'coord.a', plano_de_acao = 'tutoria'
                             WHERE nome_curso = 'A'""")
        r = sincronizar(self.conn, [curso("A", 95, evasao=55.0)], VERSAO, CICLO + timedelta(days=30))
        linha = self.fila()["A"]
        self.assertEqual(r.atualizados, 1)
        self.assertEqual(linha["indice_retencao_critica"], Decimal("95"))
        self.assertEqual((linha["status"], linha["responsavel"], linha["plano_de_acao"]),
                         ("PLANO_EM_EXECUCAO", "coord.a", "tutoria"))

    def test_03_curso_que_sai_fica_com_a_data_e_volta_com_entrada_nova(self):
        sincronizar(self.conn, [curso("A", 90), curso("B", 80)], VERSAO, CICLO)
        r = sincronizar(self.conn, [curso("A", 90)], VERSAO, CICLO + timedelta(days=30))
        b = self.fila()["B"]
        self.assertEqual(r.sairam_da_fila, 1)
        self.assertFalse(b["na_fila"])
        self.assertIsNotNone(b["saiu_da_fila_em"])
        sincronizar(self.conn, [curso("A", 90), curso("B", 85)], VERSAO, CICLO + timedelta(days=60))
        b = self.fila()["B"]
        self.assertTrue(b["na_fila"])
        self.assertIsNone(b["saiu_da_fila_em"])

    def test_04_ciclo_mais_antigo_que_o_destino_e_recusado(self):
        sincronizar(self.conn, [curso("A", 90)], VERSAO, CICLO)
        with self.assertRaises(OrigemInvalida):
            sincronizar(self.conn, [curso("B", 80)], VERSAO, CICLO - timedelta(days=30))
        self.assertEqual(list(self.fila()), ["A"])

    def test_05_coordenacao_so_grava_o_andamento(self):
        sincronizar(self.conn, [curso("A", 90)], VERSAO, CICLO)
        self.conn.execute("SET LOCAL ROLE coordenacao_academica")
        self.conn.execute("UPDATE operacional.fila_intervencao SET status = 'EM_ANALISE' WHERE nome_curso = 'A'")
        with self.assertRaises(psycopg.errors.InsufficientPrivilege), self.conn.transaction():
            self.conn.execute("UPDATE operacional.fila_intervencao SET taxa_evasao_pct = 0 WHERE nome_curso = 'A'")
        with self.assertRaises(psycopg.errors.InsufficientPrivilege), self.conn.transaction():
            self.conn.execute("DELETE FROM operacional.fila_intervencao")
        self.conn.execute("RESET ROLE")
        self.assertEqual(self.fila()["A"]["status"], "EM_ANALISE")


class TestMesmoNumero(unittest.TestCase):
    """O teste da E4: duas telas não podem mostrar valores diferentes para a mesma métrica."""

    @classmethod
    def setUpClass(cls):
        cls.conn = _conectar()
        existe = cls.conn.execute("SELECT to_regclass('dbt_marts.metricas_por_recorte')").fetchone()[0]
        if existe is None:
            cls.conn.close()
            raise unittest.SkipTest("Camadas do dbt não construídas (bash scripts/dbt.sh build).")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_01_fila_igual_ao_painel_curso_a_curso(self):
        with self.conn.transaction():
            cursos, versao, ciclo = ler_origem(self.conn)
            self.conn.execute("DELETE FROM operacional.fila_intervencao")
            self.conn.execute("DELETE FROM operacional.fila_intervencao_execucoes")
            sincronizar(self.conn, cursos, versao, ciclo)
            diferentes = self.conn.execute("""
                WITH p AS (SELECT * FROM dbt_marts.painel_cursos_criticos
                           WHERE classificacao_retencao = 'RETENÇÃO CRÍTICA'),
                     f AS (SELECT * FROM operacional.fila_intervencao WHERE na_fila)
                SELECT coalesce(p.nome_curso, f.nome_curso)
                FROM p FULL JOIN f ON f.nome_curso = p.nome_curso
                WHERE p.nome_curso IS NULL OR f.nome_curso IS NULL
                   OR (p.indice_retencao_critica, p.taxa_evasao_pct, p.atraso_medio_semestres,
                       p.formados_tempo_ideal_pct, p.total_ingressantes, p.posicao)
                      IS DISTINCT FROM
                      (f.indice_retencao_critica, f.taxa_evasao_pct, f.atraso_medio_semestres,
                       f.formados_tempo_ideal_pct, f.total_ingressantes, f.posicao)
            """).fetchall()
            raise Rollback()
        self.assertEqual(diferentes, [])

    def test_02_painel_e_semantica_dao_a_mesma_evasao_da_unb(self):
        """A evasão da UnB pela camada semântica é a razão das somas do ranking do painel."""
        unb, painel = self.conn.execute("""
            SELECT (SELECT taxa_evasao_pct FROM dbt_marts.metricas_por_recorte WHERE recorte = 'UNB'),
                   round(sum(total_evadidos)::numeric / sum(total_ingressantes) * 100, 2)
            FROM dbt_marts.painel_cursos_criticos
        """).fetchone()
        self.assertEqual(round(float(unb), 2), float(painel))


if __name__ == "__main__":
    unittest.main()
