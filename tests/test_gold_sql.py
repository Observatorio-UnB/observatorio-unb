"""
Testes das regras da gold que rodam em SQL (db/migrations/0022_gold_sql_nativo.sql).

As funções puras (normalização, arredondamento, percentil) são checadas com valores conhecidos do
pandas/numpy. As views de catálogo (área e oferta) são checadas com linhas de teste inseridas numa
transação que termina em rollback: a base não é alterada. Sem banco acessível, os testes são pulados.
"""

import sys
import unittest
from pathlib import Path

import numpy as np
import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar


class TestFuncoesDeNormalizacao(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            cls.conn = conectar(autocommit=True, connect_timeout=3)
        except psycopg.OperationalError as erro:
            raise unittest.SkipTest(f"Banco indisponível ({erro}). Suba com: docker compose up -d db")
        if cls.conn.execute("SELECT to_regproc('gold.turno_grupo')").fetchone()[0] is None:
            cls.conn.close()
            raise unittest.SkipTest("Migração 0022 não aplicada. Rode: python src/db/migrar.py")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def um(self, sql, params=None):
        return self.conn.execute(sql, params).fetchone()[0]

    def test_turno_unifica_matutino_vespertino_em_diurno(self):
        for turno in ["MATUTINO E VESPERTINO", "MATUTINO", "VESPERTINO", "DIURNO"]:
            self.assertEqual(self.um("SELECT gold.turno_grupo(%s)", (turno,)), "DIURNO", turno)

    def test_turno_preserva_noturno_e_integral(self):
        self.assertEqual(self.um("SELECT gold.turno_grupo('NOTURNO')"), "NOTURNO")
        self.assertEqual(self.um("SELECT gold.turno_grupo('INTEGRAL')"), "INTEGRAL")

    def test_categoria_grau_licenciatura(self):
        for grau in ["LICENCIADO", "LICENCIATURA"]:
            self.assertEqual(self.um("SELECT gold.categoria_grau(%s)", (grau,)), "LICENCIATURA", grau)

    def test_categoria_grau_bacharelado_inclui_titulacoes_profissionais(self):
        for grau in ["BACHAREL", "ENGENHEIRO CIVIL", "MEDICO", "ARQUITETO E URBANISTA"]:
            self.assertEqual(self.um("SELECT gold.categoria_grau(%s)", (grau,)), "BACHARELADO", grau)

    def test_campus_nome_unifica_grafias(self):
        esperado = {
            "FGA - GAMA": "FACULDADE DE CIENCIAS E TECNOLOGIAS EM ENGENHARIA (FCTE)",
            "FCE - CEILANDIA": "FACULDADE DE CIENCIAS E TECNOLOGIAS EM SAUDE (FCTS)",
            "FUP - PLANALTINA": "FACULDADE DE PLANALTINA (FUP)",
            "DARCY RIBEIRO": "DARCY RIBEIRO",
        }
        for bruto, canonico in esperado.items():
            self.assertEqual(self.um("SELECT gold.campus_nome(%s)", (bruto,)), canonico, bruto)

    def test_arredondar_py_e_o_round_do_python(self):
        """Empate para o par sobre o valor binário exato: 0,125 -> 0,12 e 2,675 (na verdade 2,67499...) -> 2,67."""
        for valor, casas in [(0.125, 2), (2.675, 2), (12.475, 2), (499 / 40, 2), (-1.005, 2), (0.5, 0), (2.5, 0), (1234.5678, 2)]:
            self.assertEqual(self.um("SELECT gold.arredondar_py(%s::float8, %s)", (valor, casas)), round(valor, casas), valor)
        self.assertIsNone(self.um("SELECT gold.arredondar_py('NaN'::float8, 2)"))

    def test_arredondar_np_e_o_round_do_pandas(self):
        """12,475 é 12,4749999... em binário: o Python dá 12,47, o numpy (x*100, rint, /100) dá 12,48."""
        for valor in [0.125, 2.675, 12.475, 499 / 40, -1.005, 33.333333]:
            self.assertEqual(self.um("SELECT gold.arredondar_np(%s::float8, 2)", (valor,)), float(np.round(valor, 2)), valor)
        self.assertIsNone(self.um("SELECT gold.arredondar_np(NULL, 2)"))

    def test_quantil_linear_e_o_do_numpy(self):
        amostra = [3.0, 1.0, 7.5, 2.0, 9.0, 4.25, 0.5, 6.0]
        for q in [0.05, 0.25, 0.5, 0.75, 0.95]:
            self.assertAlmostEqual(
                self.um("SELECT gold.quantil_linear(%s::float8[], %s)", (amostra, q)),
                float(np.percentile(amostra, q * 100)), places=12, msg=q)
        self.assertIsNone(self.um("SELECT gold.quantil_linear('{}'::float8[], 0.5)"))


class TestViewsDeCatalogo(unittest.TestCase):
    """Insere cursos e um plano de IC de teste e consulta as views; o rollback devolve a base ao que era."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.conn = conectar(connect_timeout=3)
        except psycopg.OperationalError as erro:
            raise unittest.SkipTest(f"Banco indisponível ({erro}). Suba com: docker compose up -d db")
        if cls.conn.execute("SELECT to_regclass('gold.vw_oferta_por_curso')").fetchone()[0] is None:
            cls.conn.close()
            raise unittest.SkipTest("Migração 0022 não aplicada. Rode: python src/db/migrar.py")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def setUp(self):
        self.conn.rollback()

    def tearDown(self):
        self.conn.rollback()

    def curso(self, id_curso, nome, area=None, turno=None, campus=None, grau="BACHAREL", vigente=True):
        self.conn.execute(
            """
            INSERT INTO silver.cursos_graduacao (id_curso, nome, nome_curso_norm, area_conhecimento_norm, turno_norm,
                                                 campus_norm, grau_academico_norm, no_catalogo_vigente)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (id_curso, nome, nome, area, turno, campus, grau, vigente),
        )

    def plano_de_ic(self, curso):
        self.conn.execute(
            """
            INSERT INTO silver.pibic_bolsistas (ano, tipo_bolsa_norm, campus, curso_pibic_norm, is_cotista,
                                                valor_bolsa_anual_estimado)
            VALUES (2024, 'REMUNERADA', 'DARCY RIBEIRO', %s, false, 0)
            """,
            (curso,),
        )

    def area(self, nome):
        linha = self.conn.execute("SELECT area FROM gold.vw_area_por_curso WHERE nome = %s", (nome,)).fetchone()
        return linha[0] if linha else None

    def test_area_usa_entrada_propria_do_catalogo(self):
        self.curso(990001, "TESTE FISICA", area="CIENCIAS EXATAS E DA TERRA")
        self.assertEqual(self.area("TESTE FISICA"), "CIENCIAS EXATAS E DA TERRA")

    def test_area_prefere_a_mais_frequente_e_desempata_em_ordem_alfabetica(self):
        self.curso(990001, "TESTE QUIMICA", area="B AREA")
        self.curso(990002, "TESTE QUIMICA", area="A AREA")
        self.assertEqual(self.area("TESTE QUIMICA"), "A AREA")
        self.curso(990003, "TESTE QUIMICA", area="B AREA")
        self.assertEqual(self.area("TESTE QUIMICA"), "B AREA")

    def test_area_herda_das_habilitacoes_do_curso_tronco(self):
        self.curso(990001, "TESTE COMUNICACAO - JORNALISMO", area="CIENCIAS SOCIAIS APLICADAS")
        self.curso(990002, "TESTE COMUNICACAO - AUDIOVISUAL", area="CIENCIAS SOCIAIS APLICADAS")
        self.plano_de_ic("TESTE COMUNICACAO")
        self.assertEqual(self.area("TESTE COMUNICACAO"), "CIENCIAS SOCIAIS APLICADAS")

    def test_area_nao_herda_quando_habilitacoes_divergem(self):
        self.curso(990001, "TESTE CURSO X - A", area="CIENCIAS EXATAS E DA TERRA")
        self.curso(990002, "TESTE CURSO X - B", area="LINGUISTICA, LETRAS E ARTES")
        self.plano_de_ic("TESTE CURSO X")
        self.assertIsNone(self.area("TESTE CURSO X"))

    def oferta(self, nome):
        return self.conn.execute("SELECT turno, campus FROM gold.vw_oferta_por_curso WHERE nome = %s", (nome,)).fetchone()

    def test_oferta_nao_escolhe_oferta_arbitraria(self):
        self.curso(990001, "TESTE DIREITO", turno="DIURNO", campus="DARCY RIBEIRO")
        self.curso(990002, "TESTE DIREITO", turno="NOTURNO", campus="DARCY RIBEIRO")
        self.curso(990003, "TESTE ENFERMAGEM", turno="DIURNO", campus="DARCY RIBEIRO")
        self.curso(990004, "TESTE ENFERMAGEM", turno="MATUTINO", campus="CEILANDIA")
        self.assertEqual(self.oferta("TESTE DIREITO"), ("DIURNO E NOTURNO", "DARCY RIBEIRO"))
        self.assertEqual(self.oferta("TESTE ENFERMAGEM"), ("DIURNO", "MULTICAMPUS"))

    def test_oferta_sem_turno_nem_campus_usa_o_padrao(self):
        self.curso(990001, "TESTE SEM OFERTA")
        self.assertEqual(self.oferta("TESTE SEM OFERTA"), ("DIURNO", "DARCY RIBEIRO"))

    def test_curso_com_bacharelado_e_licenciatura_e_misto(self):
        self.curso(990001, "TESTE LETRAS", grau="BACHAREL")
        self.curso(990002, "TESTE LETRAS", grau="LICENCIADO")
        self.curso(990003, "TESTE HISTORIA", grau="BACHAREL")
        misto = dict(self.conn.execute(
            "SELECT nome_curso_norm, misto FROM gold.vw_catalogo_por_nome WHERE nome_curso_norm LIKE 'TESTE %'").fetchall())
        self.assertEqual(misto, {"TESTE LETRAS": True, "TESTE HISTORIA": False})


if __name__ == "__main__":
    unittest.main()
