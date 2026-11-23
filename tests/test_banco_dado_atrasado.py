"""
Testes de integração do registro das cargas e do dado atrasado (precisam de PostgreSQL).

Dois grupos:
  - TestChegadasPorCarga: classificação da view silver.chegadas_por_carga sobre retratos montados
    no teste. Só precisa das migrações: tudo numa transação desfeita no fim.
  - TestRegistroDaCarga: a carga da Silver 3NF grava o retrato, a recarga igual não acusa chegada
    nem muda os ids, e uma formatura atrasada aparece como ATRASADA na coorte já publicada. São
    pulados se a silver não foi carregada.

Pulados se o banco não estiver no ar.

Uso:
    python3 -m unittest tests/test_banco_dado_atrasado.py
"""

import sys
import unittest
from pathlib import Path

import psycopg
from psycopg import Rollback

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar  # noqa: E402
from src.db.migrar import aplicar_migracoes  # noqa: E402
from src.db.povoar_silver_3nf import povoar_silver_3nf, silver_carregada  # noqa: E402

SQL_CHEGADAS = """
SELECT ano_ingresso, tipo_saida_grupo, periodo_saida, diferenca, chegada, coorte_publicada
FROM silver.chegadas_por_carga
WHERE id_carga = %s
ORDER BY ano_ingresso, tipo_saida_grupo, periodo_saida NULLS FIRST
"""

SQL_ULTIMA_CARGA = "SELECT max(id_carga) FROM silver.cargas_vinculos"

# Conteúdo da 3NF com os ids: muda se a recarga renumerar os vínculos.
SQL_IMPRESSAO_DIGITAL = "SELECT md5(string_agg(m::text, '|' ORDER BY id_vinculo)) FROM silver.movimentacoes_vinculos m"


def _conectar() -> psycopg.Connection:
    try:
        conn = conectar(autocommit=True, connect_timeout=3)
    except psycopg.OperationalError as erro:
        raise unittest.SkipTest(f"Banco indisponível ({erro}). Suba com: docker compose up -d db")
    aplicar_migracoes()
    return conn


class TestChegadasPorCarga(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.conn = _conectar()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def carga(self, marca_dagua: int, retrato: list) -> int:
        id_carga = self.conn.execute(
            """
            INSERT INTO silver.cargas_vinculos (publicada_em, marca_dagua, ultima_coorte_madura, total_vinculos)
            VALUES ('2024-07-15', %s, 2016, %s) RETURNING id_carga
            """,
            (marca_dagua, sum(total for *_, total in retrato)),
        ).fetchone()[0]
        self.conn.cursor().executemany(
            """
            INSERT INTO silver.cargas_vinculos_retrato (id_carga, ano_ingresso, tipo_saida_grupo, periodo_saida, total)
            VALUES (%s, %s, %s, %s, %s)
            """,
            [(id_carga, *janela) for janela in retrato],
        )
        return id_carga

    def test_01_chegada_classificada_pela_marca_da_carga_anterior(self):
        with self.conn.transaction():
            self.carga(20232, [
                (2012, "ATIVO", None, 5),
                (2012, "FORMATURA", 20222, 10),
                (2016, "EVASAO", None, 2),
                (2019, "FORMATURA", 20241, 3),
            ])
            # A marca d'água desta carga (2024/1) não classifica as próprias chegadas: vale a da anterior.
            atual = self.carga(20241, [
                (2012, "ATIVO", None, 3),
                (2012, "FORMATURA", 20222, 12),
                (2019, "FORMATURA", 20232, 1),
                (2019, "FORMATURA", 20241, 4),
            ])
            self.assertEqual(self.conn.execute(SQL_CHEGADAS, (atual,)).fetchall(), [
                (2012, "ATIVO", None, -2, "SEM_PERIODO", True),
                (2012, "FORMATURA", 20222, 2, "ATRASADA", True),
                (2016, "EVASAO", None, -2, "SEM_PERIODO", True),
                (2019, "FORMATURA", 20232, 1, "ATRASADA", False),
                (2019, "FORMATURA", 20241, 1, "NO_PRAZO", False),
            ])
            raise Rollback()

    def test_02_carga_igual_a_anterior_nao_tem_chegada(self):
        retrato = [(2012, "FORMATURA", 20222, 10), (2012, "ATIVO", None, 5)]
        with self.conn.transaction():
            self.carga(20240, retrato)
            atual = self.carga(20240, retrato)
            self.assertEqual(self.conn.execute(SQL_CHEGADAS, (atual,)).fetchall(), [])
            raise Rollback()


class TestRegistroDaCarga(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.conn = _conectar()
        if not silver_carregada(cls.conn):
            cls.conn.close()
            raise unittest.SkipTest("silver não carregada (rode scripts/rodar_pipeline.sh)")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def um(self, sql: str, params=None):
        return self.conn.execute(sql, params).fetchone()[0]

    def test_01_recarga_igual_registra_retrato_sem_chegada_e_mantem_ids(self):
        with self.conn.transaction():
            povoar_silver_3nf(self.conn)
            primeira = self.um(SQL_ULTIMA_CARGA)
            impressao = self.um(SQL_IMPRESSAO_DIGITAL)
            vinculos = self.um("SELECT count(*) FROM silver.movimentacoes_vinculos")
            self.assertEqual(self.um("SELECT total_vinculos FROM silver.cargas_vinculos WHERE id_carga = %s",
                                     (primeira,)), vinculos)
            self.assertEqual(self.um("SELECT sum(total) FROM silver.cargas_vinculos_retrato WHERE id_carga = %s",
                                     (primeira,)), vinculos)

            povoar_silver_3nf(self.conn)
            segunda = self.um(SQL_ULTIMA_CARGA)
            self.assertGreater(segunda, primeira)
            self.assertEqual(self.conn.execute(SQL_CHEGADAS, (segunda,)).fetchall(), [])
            self.assertEqual(self.um(SQL_IMPRESSAO_DIGITAL), impressao)
            raise Rollback()

    def test_02_formatura_atrasada_revisa_coorte_publicada(self):
        """Diploma de 2022/2 que só aparece na carga seguinte: ATRASADA na coorte 2012, já na gold."""
        with self.conn.transaction():
            id_vinculo = self.conn.execute(
                """
                SELECT id FROM silver.discentes_graduacao
                WHERE fonte = 'SIGAA' AND tipo_saida_grupo = 'ATIVO' AND ano_ingresso = 2012
                ORDER BY id LIMIT 1
                """
            ).fetchone()
            if id_vinculo is None:
                raise unittest.SkipTest("sem vínculo ativo do SIGAA na coorte 2012")
            povoar_silver_3nf(self.conn)
            self.conn.execute(
                """
                UPDATE silver.discentes_graduacao
                SET status_aluno = 'CONCLUÍDO', tipo_saida_grupo = 'FORMATURA', data_registro_diploma = '2023-03-10',
                    ano_saida = 2022, semestre_saida = 2, periodo_saida_estimado = true,
                    semestres_permanencia = 22, semestres_permanencia_valida = 22
                WHERE id = %s
                """,
                id_vinculo,
            )
            povoar_silver_3nf(self.conn)
            chegadas = self.conn.execute(SQL_CHEGADAS, (self.um(SQL_ULTIMA_CARGA),)).fetchall()
            self.assertEqual(chegadas, [
                (2012, "ATIVO", None, -1, "SEM_PERIODO", True),
                (2012, "FORMATURA", 20222, 1, "ATRASADA", True),
            ])
            raise Rollback()


if __name__ == "__main__":
    unittest.main()
