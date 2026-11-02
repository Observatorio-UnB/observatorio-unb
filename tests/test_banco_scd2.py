"""
Testes de integração da gold.dim_curso como SCD tipo 2 (migração 0025). Precisam de PostgreSQL.

  - TestRestricoesScd2: regras do esquema, numa transação desfeita no fim. Só precisam das migrações.
  - TestCargaScd2: reclassificação e renomeação de um curso na silver seguidas da carga do Star
    Schema (src/db/povoar_dimensional.py). Pulados se a silver não foi carregada.

Pulados se o banco não estiver no ar.

Uso:
    python3 -m unittest tests/test_banco_scd2.py
"""

import sys
import unittest
from pathlib import Path

import psycopg
from psycopg import Rollback, errors

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar  # noqa: E402
from src.db.migrar import aplicar_migracoes  # noqa: E402
from src.db.povoar_dimensional import povoar_gold_dimensional  # noqa: E402
from src.db.povoar_silver_3nf import silver_carregada  # noqa: E402

CURSO = "MATEMATICA"

SQL_VERSOES = """
SELECT sk_curso, departamento, vigente_de, vigente_ate, is_atual
FROM gold.dim_curso
WHERE nome_curso = %s
ORDER BY vigente_de
"""


def _conectar() -> psycopg.Connection:
    try:
        conn = conectar(autocommit=True, connect_timeout=3)
    except psycopg.OperationalError as erro:
        raise unittest.SkipTest(f"Banco indisponível ({erro}). Suba com: docker compose up -d db")
    aplicar_migracoes()
    return conn


class TestRestricoesScd2(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.conn = _conectar()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def versao(self, vigente_de: str, vigente_ate=None) -> None:
        self.conn.execute(
            """
            INSERT INTO gold.dim_curso (nome_curso, grau_academico, categoria_grau, area_conhecimento,
                                        vigente_de, vigente_ate, is_atual)
            VALUES ('CURSO TESTE', 'BACHARELADO', 'BACHARELADO', 'TESTE', %s, %s, %s)
            """,
            (vigente_de, vigente_ate, vigente_ate is None),
        )

    def test_01_primeira_versao_vale_desde_o_inicio_da_serie(self):
        with self.conn.transaction():
            self.conn.execute(
                "INSERT INTO gold.dim_curso (nome_curso, grau_academico, categoria_grau, area_conhecimento) "
                "VALUES ('CURSO TESTE', 'BACHARELADO', 'BACHARELADO', 'TESTE')"
            )
            linha = self.conn.execute(
                "SELECT vigente_de = TIMESTAMPTZ '1962-04-21 00:00:00-03', vigente_ate, is_atual "
                "FROM gold.dim_curso WHERE nome_curso = 'CURSO TESTE'"
            ).fetchone()
            self.assertEqual(linha, (True, None, True))
            raise Rollback()

    def test_02_duas_versoes_atuais_do_mesmo_curso_sao_recusadas(self):
        with self.conn.transaction():
            self.versao("1962-04-21")
            self.versao("2026-01-01")
            # A restrição é adiada para o commit; IMMEDIATE confere agora.
            with self.assertRaises(errors.ExclusionViolation), self.conn.transaction():
                self.conn.execute("SET CONSTRAINTS gold.ex_dim_curso_uma_atual IMMEDIATE")
            raise Rollback()

    def test_03_versao_fechada_precisa_terminar_depois_de_comecar(self):
        with self.conn.transaction():
            with self.assertRaises(errors.CheckViolation), self.conn.transaction():
                self.versao("2026-01-01", "2025-01-01")
            raise Rollback()

    def test_04_fechar_e_abrir_no_mesmo_comando_em_qualquer_ordem(self):
        """Como a sincronização com o Supabase faz: um INSERT ... ON CONFLICT com a versão nova
        antes da antiga fechada não pode esbarrar na regra de uma versão atual por curso."""
        with self.conn.transaction():
            self.versao("1962-04-21")
            self.conn.execute(
                """
                INSERT INTO gold.dim_curso AS t (nome_curso, grau_academico, categoria_grau, area_conhecimento,
                                                 vigente_de, vigente_ate, is_atual)
                VALUES ('CURSO TESTE', 'LICENCIATURA', 'LICENCIATURA', 'TESTE', '2026-01-01', NULL, true),
                       ('CURSO TESTE', 'BACHARELADO', 'BACHARELADO', 'TESTE', '1962-04-21', '2026-01-01', false)
                ON CONFLICT (nome_curso, vigente_de) DO UPDATE
                SET vigente_ate = EXCLUDED.vigente_ate, is_atual = EXCLUDED.is_atual
                """
            )
            self.conn.execute("SET CONSTRAINTS gold.ex_dim_curso_uma_atual IMMEDIATE")
            atuais = self.conn.execute(
                "SELECT categoria_grau FROM gold.dim_curso WHERE nome_curso = 'CURSO TESTE' AND is_atual"
            ).fetchall()
            self.assertEqual(atuais, [("LICENCIATURA",)])
            raise Rollback()


class TestCargaScd2(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.conn = _conectar()
        if not silver_carregada(cls.conn):
            cls.conn.close()
            raise unittest.SkipTest("Silver não carregada: rode scripts/rodar_pipeline.sh.")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_01_reclassificacao_abre_versao_sem_apagar_a_anterior(self):
        with self.conn.transaction():
            povoar_gold_dimensional(self.conn)
            [(sk_antigo, departamento_antigo, vigente_de, _, _)] = self.conn.execute(SQL_VERSOES, (CURSO,)).fetchall()
            total_antes = self.conn.execute("SELECT count(*) FROM gold.dim_curso").fetchone()[0]

            self.conn.execute(
                "UPDATE silver.cursos SET departamento = 'DEPARTAMENTO TESTE' WHERE nome_curso_norm = %s", (CURSO,))
            povoar_gold_dimensional(self.conn)
            agora = self.conn.execute("SELECT now()").fetchone()[0]

            versoes = self.conn.execute(SQL_VERSOES, (CURSO,)).fetchall()
            self.assertEqual(versoes, [
                (sk_antigo, departamento_antigo, vigente_de, agora, False),
                (versoes[1][0], "DEPARTAMENTO TESTE", agora, None, True),
            ])
            sk_novo = versoes[1][0]
            self.assertNotEqual(sk_novo, sk_antigo)
            # Só o curso reclassificado ganhou versão.
            self.assertEqual(self.conn.execute("SELECT count(*) FROM gold.dim_curso").fetchone()[0], total_antes + 1)

            # Os fatos recriados apontam para a versão atual, e o painel mostra o curso uma vez.
            for fato in ("gold.fato_retencao_curso", "gold.fato_alunos_ativos"):
                with self.subTest(fato=fato):
                    sks = self.conn.execute(
                        f"SELECT f.sk_curso FROM {fato} f JOIN gold.dim_curso c USING (sk_curso) "
                        "WHERE c.nome_curso = %s", (CURSO,)).fetchall()
                    self.assertEqual(sks, [(sk_novo,)])
            self.conn.execute("REFRESH MATERIALIZED VIEW gold.mv_dashboard_executivo")
            self.assertEqual(
                self.conn.execute("SELECT sk_curso FROM gold.mv_dashboard_executivo WHERE nome_curso = %s",
                                  (CURSO,)).fetchall(),
                [(sk_novo,)],
            )
            raise Rollback()

    def test_02_mudanca_de_atributo_tipo_1_nao_abre_versao(self):
        with self.conn.transaction():
            povoar_gold_dimensional(self.conn)
            antes = self.conn.execute(SQL_VERSOES, (CURSO,)).fetchall()
            id_origem = self.conn.execute(
                "SELECT id_curso_origem FROM gold.dim_curso WHERE nome_curso = %s AND is_atual", (CURSO,)).fetchone()
            self.conn.execute(
                "UPDATE gold.dim_curso SET id_curso_origem = -1 WHERE nome_curso = %s AND is_atual", (CURSO,))
            povoar_gold_dimensional(self.conn)
            self.assertEqual(self.conn.execute(SQL_VERSOES, (CURSO,)).fetchall(), antes)
            self.assertEqual(
                self.conn.execute(
                    "SELECT id_curso_origem FROM gold.dim_curso WHERE nome_curso = %s AND is_atual", (CURSO,)
                ).fetchone(),
                id_origem,
            )
            raise Rollback()

    def test_03_renomeacao_preserva_o_nome_antigo_e_leva_os_fatos_ao_novo(self):
        """O curso renomeado na matriz (o nome canônico, ADR 0003) vira uma chave natural nova: o nome
        antigo continua na dimensão com o histórico, e os fatos recriados passam para o nome novo.

        O nome canônico sai da mesma fonte para a Silver 3NF (de onde vem a dim_curso) e para a
        gold.retencao_cursos_unb (de onde o fato copia as medidas, migração 0022). Uma renomeação real
        chega aos dois, e o teste renomeia nos dois."""
        novo_nome = "MATEMATICA (RENOMEADO NO TESTE)"
        with self.conn.transaction():
            povoar_gold_dimensional(self.conn)
            antigo = self.conn.execute(SQL_VERSOES, (CURSO,)).fetchall()
            self.conn.execute(
                "UPDATE silver.estruturas_curriculares SET nome_curso_canonico = %s WHERE nome_curso_canonico = %s",
                (novo_nome, CURSO))
            self.conn.execute("UPDATE gold.retencao_cursos_unb SET curso = %s WHERE curso = %s", (novo_nome, CURSO))
            povoar_gold_dimensional(self.conn)

            self.assertEqual(self.conn.execute(SQL_VERSOES, (CURSO,)).fetchall(), antigo)
            [(sk_novo, _, vigente_de, vigente_ate, atual)] = self.conn.execute(SQL_VERSOES, (novo_nome,)).fetchall()
            self.assertEqual((vigente_ate, atual), (None, True))
            self.assertEqual(vigente_de, antigo[0][2])  # primeira versão do nome novo: início da série
            fatos = self.conn.execute(
                "SELECT c.nome_curso FROM gold.fato_retencao_curso f JOIN gold.dim_curso c USING (sk_curso) "
                "WHERE c.nome_curso IN (%s, %s)", (CURSO, novo_nome)).fetchall()
            self.assertEqual(fatos, [(novo_nome,)])
            self.assertNotEqual(sk_novo, antigo[0][0])
            raise Rollback()

    def test_04_recarga_sem_mudanca_nao_abre_versao(self):
        with self.conn.transaction():
            povoar_gold_dimensional(self.conn)
            antes = self.conn.execute("SELECT sk_curso, vigente_de, is_atual FROM gold.dim_curso ORDER BY 1").fetchall()
            povoar_gold_dimensional(self.conn)
            depois = self.conn.execute("SELECT sk_curso, vigente_de, is_atual FROM gold.dim_curso ORDER BY 1").fetchall()
            self.assertEqual(antes, depois)
            raise Rollback()


if __name__ == "__main__":
    unittest.main()
