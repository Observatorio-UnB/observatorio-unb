"""
Testes da camada de banco (PostgreSQL + pgvector).

Verificam o contrato do esquema, a reconciliação entre camadas, o controle de
acesso e a busca semântica. Sem banco acessível (DATABASE_URL ou o padrão do
docker-compose), os testes que dependem dele são pulados.
"""

import sys
import unittest
from pathlib import Path

import pandas as pd
import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent
SILVER_DIR = BASE_DIR / "data" / "silver"
GOLD_DIR = BASE_DIR / "data" / "gold"

sys.path.insert(0, str(BASE_DIR))
from src.db.carregar import Coluna, ErroDeContrato, carregar, preparar
from src.db.conexao import conectar
from src.db.migrar import MIGRATIONS_DIR


class TestContratoDeCarga(unittest.TestCase):
    """Regras do carregador que não dependem do banco."""

    COLUNAS = [
        Coluna("id", "bigint", False, True, True),
        Coluna("curso", "text", False, False, False),
        Coluna("total", "integer", True, False, False),
        Coluna("_carregado_em", "timestamp with time zone", False, True, False),
    ]

    def test_coluna_fora_do_esquema_interrompe_a_carga(self):
        df = pd.DataFrame({"curso": ["DIREITO"], "total": [10], "coluna_nova": [1]})
        with self.assertRaises(ErroDeContrato):
            preparar(df, self.COLUNAS, "gold.teste")

    def test_coluna_obrigatoria_ausente_interrompe_a_carga(self):
        with self.assertRaises(ErroDeContrato):
            preparar(pd.DataFrame({"total": [10]}), self.COLUNAS, "gold.teste")

    def test_inteiro_com_casa_decimal_nao_e_truncado(self):
        df = pd.DataFrame({"curso": ["DIREITO"], "total": [8.5]})
        with self.assertRaises(TypeError):
            preparar(df, self.COLUNAS, "gold.teste")

    def test_identidade_e_default_ficam_com_o_banco(self):
        saida = preparar(pd.DataFrame({"curso": ["DIREITO"], "total": [8.0]}), self.COLUNAS, "gold.teste")
        self.assertEqual(list(saida.columns), ["curso", "total"])
        self.assertEqual(saida["total"].iloc[0], 8)


class TestBanco(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            cls.conn = conectar(autocommit=True, connect_timeout=3)
        except psycopg.OperationalError as erro:
            raise unittest.SkipTest(f"Banco indisponível ({erro}). Suba com: docker compose up -d db")
        existe = cls.conn.execute("SELECT to_regclass('gold.retencao_cursos_unb')").fetchone()[0]
        if existe is None or cls.um("SELECT count(*) FROM gold.retencao_cursos_unb") == 0:
            cls.conn.close()
            raise unittest.SkipTest("Banco sem carga. Rode: python3 src/db/carregar.py")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    @classmethod
    def um(cls, sql, params=None):
        return cls.conn.execute(sql, params).fetchone()[0]

    def silver_carregada(self) -> bool:
        return self.um("SELECT count(*) FROM silver.sigra_graduacao") > 0

    def test_01_todas_as_migracoes_aplicadas(self):
        arquivos = {p.name for p in MIGRATIONS_DIR.glob("*.sql")}
        aplicadas = {r[0] for r in self.conn.execute("SELECT versao FROM public.schema_migrations").fetchall()}
        self.assertEqual(arquivos, aplicadas)

    def test_02_contagens_batem_com_os_arquivos(self):
        pares = {"gold.retencao_cursos_unb": GOLD_DIR / "retencao_cursos_unb.csv",
                 "gold.pibic_social_unb": GOLD_DIR / "pibic_social_unb.csv"}
        if self.silver_carregada():
            pares.update({
                "silver.sigra_graduacao": SILVER_DIR / "sigra_graduacao_silver.csv",
                "silver.estrutura_curricular": SILVER_DIR / "estrutura_curricular_silver.csv",
                "silver.cursos_graduacao": SILVER_DIR / "cursos_graduacao_silver.csv",
                "silver.pibic_bolsistas": SILVER_DIR / "pibic_bolsistas_silver.csv",
            })
        for tabela, arquivo in pares.items():
            if arquivo.exists():
                self.assertEqual(self.um(f"SELECT count(*) FROM {tabela}"), len(pd.read_csv(arquivo)), tabela)

    def test_03_volume_minimo(self):
        """A gold precisa cobrir a graduação da UnB, não uma amostra."""
        self.assertGreaterEqual(self.um("SELECT count(*) FROM gold.retencao_cursos_unb"), 80)
        self.assertGreater(self.um("SELECT sum(total_discentes_registrados) FROM gold.retencao_cursos_unb"), 50_000)

    def test_04_gold_reconcilia_com_a_silver(self):
        """Recalcula em SQL, a partir da silver, os vínculos e formados de cada curso da gold."""
        if not self.silver_carregada():
            self.skipTest("silver não carregada")
        divergentes = self.conn.execute(
            """
            WITH canon AS (
              SELECT coalesce(r.destino_estrutura, s.curso_norm) AS curso, s.tipo_saida_grupo
              FROM silver.sigra_graduacao s
              LEFT JOIN gold.regras_harmonizacao_canonicas r ON r.origem_sigra = s.curso_norm
            ), agregado AS (
              SELECT curso, count(*) AS vinculos,
                     count(*) FILTER (WHERE tipo_saida_grupo = 'FORMATURA') AS formados
              FROM canon GROUP BY curso
            )
            SELECT g.curso FROM gold.retencao_cursos_unb g
            LEFT JOIN agregado a ON a.curso = g.curso
            WHERE a.vinculos IS DISTINCT FROM g.total_discentes_registrados
               OR a.formados IS DISTINCT FROM g.total_formados
            """
        ).fetchall()
        self.assertEqual(divergentes, [], "Cursos da gold que não batem com a silver")

    def test_05_integridade_referencial_entre_camadas(self):
        if not self.silver_carregada():
            self.skipTest("silver não carregada")
        orfaos_gold = self.um(
            "SELECT count(*) FROM gold.retencao_cursos_unb g "
            "WHERE NOT EXISTS (SELECT 1 FROM silver.estrutura_curricular e WHERE e.nome_curso_norm = g.curso)"
        )
        orfaos_regras = self.um(
            "SELECT count(*) FROM gold.regras_harmonizacao_canonicas r WHERE NOT EXISTS "
            "(SELECT 1 FROM silver.estrutura_curricular e WHERE e.nome_curso_norm = r.destino_estrutura)"
        )
        self.assertEqual(orfaos_gold, 0, "Curso da gold sem matriz curricular")
        self.assertEqual(orfaos_regras, 0, "Regra de harmonização aponta para matriz inexistente")

    def test_06_banco_recusa_grupo_menor_que_5(self):
        """k-anonimato é garantia do esquema, não só do pipeline."""
        with self.assertRaises(psycopg.errors.CheckViolation):
            with self.conn.transaction():
                self.conn.execute(
                    "INSERT INTO gold.retencao_cursos_unb (curso, total_discentes_registrados, total_formados, "
                    "total_evadidos_desligados) VALUES ('CURSO TESTE', 4, 1, 1)"
                )

    def test_07_so_a_anomalia_conhecida_de_prazo_maximo(self):
        """Prazo máximo menor que o ideal só é tolerado no curso-tronco ENGENHARIA (erro da fonte)."""
        if not self.silver_carregada():
            self.skipTest("silver não carregada")
        cursos = {r[0] for r in self.conn.execute(
            "SELECT nome_curso_norm FROM silver.estrutura_curricular "
            "WHERE semestre_conclusao_maximo < semestre_conclusao_ideal"
        ).fetchall()}
        self.assertTrue(cursos <= {"ENGENHARIA"}, f"Nova anomalia de prazo na fonte: {cursos - {'ENGENHARIA'}}")

    def test_08_distribuicao_da_evasao(self):
        """Pega erro silencioso de cálculo: evasão média fora da faixa histórica da UnB."""
        media = float(self.um("SELECT avg(taxa_evasao_pct) FROM gold.retencao_cursos_unb"))
        self.assertTrue(20 <= media <= 60, f"Evasão média de {media:.1f}% fora da faixa esperada (20-60%)")

    def test_09_papel_de_leitura_nao_ve_dado_individual(self):
        def pode(esquema):
            return self.um("SELECT has_schema_privilege('observatorio_leitura', %s, 'USAGE')", (esquema,))
        self.assertTrue(pode("gold"))
        self.assertTrue(pode("busca"))
        self.assertFalse(pode("silver"))
        self.assertFalse(pode("bronze"))
        self.assertTrue(self.um(
            "SELECT has_table_privilege('observatorio_leitura', 'gold.retencao_cursos_unb', 'SELECT')"))

    def test_10_carga_e_idempotente(self):
        antes = self.um("SELECT count(*) FROM gold.retencao_cursos_unb")
        carregar(("gold",))
        carregar(("gold",))
        self.assertEqual(self.um("SELECT count(*) FROM gold.retencao_cursos_unb"), antes)


class TestBuscaSemantica(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            cls.conn = conectar(autocommit=True, connect_timeout=3)
        except psycopg.OperationalError as erro:
            raise unittest.SkipTest(f"Banco indisponível ({erro})")
        tabela = cls.conn.execute("SELECT to_regclass('busca.documentos')").fetchone()[0]
        if tabela is None or cls.conn.execute(
                "SELECT count(*) FROM busca.documentos WHERE tipo = 'curso'").fetchone()[0] == 0:
            cls.conn.close()
            raise unittest.SkipTest("Sem documentos vetorizados. Rode: python3 src/busca/vetorizar.py")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_um_documento_por_curso_da_gold(self):
        faltando = self.conn.execute(
            "SELECT curso FROM gold.retencao_cursos_unb EXCEPT "
            "SELECT chave FROM busca.documentos WHERE tipo = 'curso'"
        ).fetchall()
        self.assertEqual(faltando, [])

    def test_vetores_tem_a_dimensao_do_modelo_e_norma_1(self):
        dims, norma_min, norma_max = self.conn.execute(
            "SELECT min(vector_dims(embedding)), min(vector_norm(embedding)), max(vector_norm(embedding)) "
            "FROM busca.documentos"
        ).fetchone()
        self.assertEqual(dims, 384)
        self.assertAlmostEqual(norma_min, 1.0, places=3)
        self.assertAlmostEqual(norma_max, 1.0, places=3)

    def test_busca_encontra_o_curso_pelo_nome(self):
        from src.busca.buscar import buscar

        resultados = buscar("curso de medicina", k=3, tipo="curso")
        self.assertEqual(len(resultados), 3, "O filtro por tipo precisa devolver k resultados")
        self.assertIn("MEDICINA", [r["titulo"] for r in resultados])

    def test_busca_pela_duvida_encontra_a_documentacao_de_privacidade(self):
        from src.busca.buscar import buscar

        resultados = buscar("risco de reidentificação dos alunos e k-anonimato", k=3, tipo="documentacao")
        arquivos = {r["metadados"]["arquivo"] for r in resultados}
        self.assertIn("docs/registro_privacidade_lgpd.md", arquivos)


if __name__ == "__main__":
    unittest.main()
