"""
Testes de integração da Silver 3NF e do Star Schema da gold (precisam de PostgreSQL).

Dois grupos:
  - TestRestricoes3NFStar: restrições do esquema (unicidade, FK, partição DEFAULT, k >= 5, chave
    natural da dim_curso). Só precisam das migrações: cada teste cria as próprias linhas numa
    transação desfeita no fim, e roda num banco vazio.
  - TestCarga3NFStar: conferem o resultado de src/db/povoar_dimensional.py contra as tabelas de
    origem. São pulados se a silver não foi carregada (ex.: banco só com a gold).

Pulados se o banco não estiver no ar.

Uso:
    python3 -m unittest tests/test_banco_3nf_star.py
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
from src.db.povoar_silver_3nf import povoar_silver_3nf, silver_carregada  # noqa: E402


# Chaves substitutas de dim_curso e dim_perfil_social, que a recarga não pode mudar.
SQL_CHAVES = """
    SELECT 'curso', nome_curso, sk_curso FROM gold.dim_curso
    UNION ALL
    SELECT 'perfil', concat_ws('|', perfil_macro, categoria_cota, faixa_renda, is_cotista), sk_perfil
    FROM gold.dim_perfil_social
    ORDER BY 1, 2
"""


def _conectar() -> psycopg.Connection:
    try:
        conn = conectar(autocommit=True, connect_timeout=3)
    except psycopg.OperationalError as erro:
        raise unittest.SkipTest(f"Banco indisponível ({erro}). Suba com: docker compose up -d db")
    aplicar_migracoes()
    return conn


class TestRestricoes3NFStar(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.conn = _conectar()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def inserir_vinculo(self, ano_ingresso: int, id_curso: int, id_estrutura: int) -> int:
        """Cria discente e vínculo de teste; devolve o id do discente."""
        id_discente = self.conn.execute(
            "INSERT INTO silver.discentes (pseudonimo) VALUES ('TESTE_3NF') RETURNING id_discente").fetchone()[0]
        self.conn.execute(
            """
            INSERT INTO silver.movimentacoes_vinculos (id_discente, id_curso, id_estrutura, ano_ingresso,
                                                       tipo_saida_grupo, fonte)
            VALUES (%s, %s, %s, %s, 'FORMATURA', 'SIGRA')
            """,
            (id_discente, id_curso, id_estrutura, ano_ingresso),
        )
        return id_discente

    def criar_curso(self) -> int:
        """Cria curso e matriz de teste (id_curso -1); devolve o id da matriz."""
        self.conn.execute(
            """
            INSERT INTO silver.cursos (id_curso, nome_curso_norm, campus, turno, grau_academico, categoria_grau,
                                       area_conhecimento)
            VALUES (-1, 'CURSO TESTE', 'DARCY RIBEIRO', 'DIURNO', 'BACHARELADO', 'BACHARELADO', 'TESTE')
            """
        )
        return self.conn.execute(
            """
            INSERT INTO silver.estruturas_curriculares (id_curso, nome_curso_canonico, semestre_minimo,
                                                        semestre_ideal, semestre_maximo)
            VALUES (-1, 'CURSO TESTE', 6, 8, 14) RETURNING id_estrutura
            """
        ).fetchone()[0]

    def test_01_discente_duplicado_e_rejeitado(self):
        with self.conn.transaction():
            self.conn.execute("INSERT INTO silver.discentes (pseudonimo) VALUES ('TESTE_3NF')")
            with self.assertRaises(errors.UniqueViolation), self.conn.transaction():
                self.conn.execute("INSERT INTO silver.discentes (pseudonimo) VALUES ('TESTE_3NF')")
            raise Rollback()

    def test_02_vinculo_com_curso_inexistente_e_rejeitado(self):
        with self.conn.transaction():
            id_estrutura = self.criar_curso()
            with self.assertRaises(errors.ForeignKeyViolation), self.conn.transaction():
                self.inserir_vinculo(2018, 999_999, id_estrutura)
            raise Rollback()

    def test_03_ingresso_fora_das_particoes_cai_na_default(self):
        with self.conn.transaction():
            id_discente = self.inserir_vinculo(1995, -1, self.criar_curso())
            particao = self.conn.execute(
                "SELECT tableoid::regclass::text FROM silver.movimentacoes_vinculos WHERE id_discente = %s",
                (id_discente,),
            ).fetchone()[0]
            self.assertEqual(particao, "silver.movimentacoes_p_default")
            raise Rollback()

    def test_04_fato_com_menos_de_5_ingressantes_e_rejeitado(self):
        with self.conn.transaction():
            sk_curso = self.conn.execute(
                """
                INSERT INTO gold.dim_curso (nome_curso, grau_academico, categoria_grau, area_conhecimento)
                VALUES ('CURSO TESTE', 'BACHARELADO', 'BACHARELADO', 'TESTE') RETURNING sk_curso
                """
            ).fetchone()[0]
            sk_campus = self.conn.execute(
                "INSERT INTO gold.dim_campus (campus, regiao_admin) VALUES ('CAMPUS TESTE', 'TESTE') RETURNING sk_campus"
            ).fetchone()[0]
            with self.assertRaises(errors.CheckViolation), self.conn.transaction():
                self.conn.execute(
                    """
                    INSERT INTO gold.fato_retencao_curso (sk_curso, sk_campus, total_ingressantes, total_formados,
                                                          total_evadidos)
                    VALUES (%s, %s, 3, 2, 1)
                    """,
                    (sk_curso, sk_campus),
                )
            raise Rollback()

    def test_05_curso_novo_nao_muda_a_chave_dos_existentes(self):
        """A chave substituta segue a chave natural: um curso que entra antes na ordem alfabética não desloca as outras."""
        upsert = """
            INSERT INTO gold.dim_curso (nome_curso, grau_academico, categoria_grau, area_conhecimento)
            VALUES (%s, 'BACHARELADO', 'BACHARELADO', 'TESTE')
            ON CONFLICT (nome_curso) DO UPDATE SET area_conhecimento = EXCLUDED.area_conhecimento
            RETURNING sk_curso
        """
        with self.conn.transaction():
            sk_antes = self.conn.execute(upsert, ("ZZ CURSO TESTE",)).fetchone()[0]
            self.conn.execute(upsert, ("AA CURSO TESTE",))
            sk_depois = self.conn.execute(upsert, ("ZZ CURSO TESTE",)).fetchone()[0]
            self.assertEqual(sk_antes, sk_depois)
            raise Rollback()


class TestCarga3NFStar(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.conn = _conectar()
        if not silver_carregada(cls.conn):
            cls.conn.close()
            raise unittest.SkipTest("silver não carregada (rode src/db/carregar.py)")
        if not cls.um("SELECT EXISTS (SELECT 1 FROM gold.fato_retencao_curso)"):
            cls.conn.close()
            raise unittest.SkipTest("Star Schema vazio (rode src/db/povoar_dimensional.py)")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    @classmethod
    def um(cls, sql: str):
        return cls.conn.execute(sql).fetchone()[0]

    def test_01_cada_vinculo_da_silver_vira_um_vinculo_3nf(self):
        self.assertEqual(self.um("SELECT count(*) FROM silver.movimentacoes_vinculos"),
                         self.um("SELECT count(*) FROM silver.discentes_graduacao"))
        self.assertEqual(self.um("SELECT count(*) FROM silver.discentes"),
                         self.um("SELECT count(DISTINCT aluno) FROM silver.discentes_graduacao"))

    def test_02_fato_retencao_reconcilia_com_a_gold_do_pipeline(self):
        """Métricas recalculadas da 3NF batem, curso a curso, com gold.retencao_cursos_unb.

        Tolerâncias só para o arredondamento de meio (numeric do PostgreSQL arredonda 0,5 para cima).
        """
        divergentes = self.conn.execute(
            """
            SELECT coalesce(r.curso, dc.nome_curso)
            FROM gold.retencao_cursos_unb r
            FULL JOIN (gold.fato_retencao_curso f JOIN gold.dim_curso dc USING (sk_curso)
                       JOIN gold.dim_campus camp USING (sk_campus)) ON dc.nome_curso = r.curso
            WHERE f.total_ingressantes IS DISTINCT FROM r.total_discentes_registrados
               OR f.total_formados IS DISTINCT FROM r.total_formados
               OR f.total_evadidos IS DISTINCT FROM r.total_evadidos_desligados
               OR f.total_ainda_ativos IS DISTINCT FROM r.total_ainda_ativos
               OR camp.campus IS DISTINCT FROM r.campus
               OR dc.categoria_grau IS DISTINCT FROM r.categoria_grau
               OR dc.area_conhecimento IS DISTINCT FROM r.area_conhecimento
               OR abs(f.taxa_formatura_pct - r.taxa_formatura_pct) > 0.01
               OR abs(f.taxa_evasao_pct - r.taxa_evasao_pct) > 0.01
               OR abs(f.formados_tempo_ideal_pct - r.formados_tempo_ideal_pct) > 0.01
               OR abs(f.atraso_medio_semestres - r.desvio_medio_semestres) > 0.01
               OR abs(f.indice_retencao_critica - r.indice_retencao_critica) > 0.1
               OR f.classificacao_retencao IS DISTINCT FROM r.classificacao_retencao
            """
        ).fetchall()
        self.assertEqual(divergentes, [])

    def test_03_fato_alunos_ativos_cobre_a_gold_do_pipeline(self):
        self.assertGreater(self.um("SELECT count(*) FROM gold.fato_alunos_ativos"), 0)
        self.assertEqual(self.um("SELECT sum(total_ativos) FROM gold.fato_alunos_ativos"),
                         self.um("SELECT sum(total_ativos_hoje) FROM gold.ativos_hoje_cursos_unb"))
        self.assertGreater(self.um("SELECT sum(ativos_hoje_total) FROM gold.mv_dashboard_executivo"), 0)

    def test_04_perfil_social_vem_dos_planos_de_ic(self):
        faltantes = self.um(
            """
            SELECT count(*) FROM (
              SELECT DISTINCT coalesce(perfil_social_macro, 'NAO INFORMADO') AS perfil_macro,
                     coalesce(cota_detalhe, 'NAO INFORMADO') AS categoria_cota, faixa_renda, is_cotista
              FROM silver.pibic_projetos
              EXCEPT
              SELECT perfil_macro, categoria_cota, faixa_renda, is_cotista FROM gold.dim_perfil_social
            ) x
            """
        )
        self.assertEqual(faltantes, 0)

    def test_05_fato_pibic_perfil_respeita_k_anonimato(self):
        self.assertGreater(self.um("SELECT count(*) FROM gold.fato_pibic_perfil"), 0)
        self.assertEqual(self.um("SELECT count(*) FROM gold.fato_pibic_perfil WHERE total_projetos < 5"), 0)
        self.assertLessEqual(self.um("SELECT sum(total_projetos) FROM gold.fato_pibic_perfil"),
                             self.um("SELECT count(*) FROM silver.pibic_projetos"))

    def test_06_view_materializada_tem_um_curso_terminal_por_fato(self):
        self.conn.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_dashboard_executivo")
        self.assertEqual(
            self.um("SELECT count(*) FROM gold.mv_dashboard_executivo"),
            self.um("SELECT count(*) FROM gold.fato_retencao_curso JOIN gold.dim_curso USING (sk_curso) "
                    "WHERE NOT is_tronco_abi"),
        )

    def test_07_recarga_e_idempotente(self):
        """Rodar o povoamento de novo não duplica linhas nem muda chaves (desfeito no fim)."""
        with self.conn.transaction():
            antes = povoar_silver_3nf(self.conn) | povoar_gold_dimensional(self.conn)
            sks = self.conn.execute(SQL_CHAVES).fetchall()
            depois = povoar_silver_3nf(self.conn) | povoar_gold_dimensional(self.conn)
            self.assertEqual(antes, depois)
            self.assertEqual(sks, self.conn.execute(SQL_CHAVES).fetchall())
            raise Rollback()


if __name__ == "__main__":
    unittest.main()
