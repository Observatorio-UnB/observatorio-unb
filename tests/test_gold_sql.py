"""
Testes da Gold em SQL nativo (db/migrations/0022_gold_agregacoes_sql.sql).

Funções e views são testadas com linhas fictícias numa transação que sofre rollback.
A reconciliação recalcula a retenção em Pandas, de forma independente, e compara com a
gold.retencao_cursos_unb que o banco calculou. Precisam do PostgreSQL com o pipeline rodado.
"""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar
from src.db.tabelas import ler
from src.pipeline.build_gold import (
    CANONICAL_RULES_METADATA,
    build_gold,
    ANOS_MATURACAO_COORTE,
    EXCLUDED_GENERIC_COURSES,
    MIN_MATRICULAS_BENCHMARK,
    valor_bolsa_ic_vigente,
)

TABELAS_CALCULADAS = (
    "gold.retencao_cursos_unb",
    "gold.ativos_hoje_cursos_unb",
    "gold.inep_benchmark_cursos_unb",
    "gold.pibic_social_unb",
    "gold.regras_harmonizacao_canonicas",
)


class BancoComGold(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            cls.conn = conectar(connect_timeout=3)
        except psycopg.OperationalError as erro:
            raise unittest.SkipTest(f"Banco indisponível ({erro}). Suba com: docker compose up -d db")
        procedure = cls.conn.execute("SELECT to_regprocedure('gold.atualizar_gold(integer,text[],integer,numeric)')").fetchone()[0]
        if procedure is None or not cls.conn.execute("SELECT EXISTS (SELECT 1 FROM gold.retencao_cursos_unb)").fetchone()[0]:
            cls.conn.close()
            raise unittest.SkipTest("Gold não calculada. Rode: bash scripts/rodar_pipeline.sh")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def tearDown(self):
        self.conn.rollback()

    def um(self, sql, params=None):
        return self.conn.execute(sql, params).fetchone()[0]


class TestFuncoesPuras(BancoComGold):

    def test_turno_unifica_matutino_vespertino_em_diurno(self):
        for turno in ("MATUTINO E VESPERTINO", "MATUTINO", "VESPERTINO", "DIURNO"):
            self.assertEqual(self.um("SELECT gold.turno_grupo(%s)", (turno,)), "DIURNO", turno)

    def test_turno_preserva_noturno_e_integral(self):
        self.assertEqual(self.um("SELECT gold.turno_grupo('NOTURNO')"), "NOTURNO")
        self.assertEqual(self.um("SELECT gold.turno_grupo('INTEGRAL')"), "INTEGRAL")

    def test_categoria_grau(self):
        for grau in ("LICENCIADO", "LICENCIATURA"):
            self.assertEqual(self.um("SELECT gold.categoria_grau(%s)", (grau,)), "LICENCIATURA", grau)
        for grau in ("BACHAREL", "ENGENHEIRO CIVIL", "MEDICO", "ARQUITETO E URBANISTA", None):
            self.assertEqual(self.um("SELECT gold.categoria_grau(%s)", (grau,)), "BACHARELADO", grau)

    def test_campus_nome(self):
        self.assertEqual(self.um("SELECT gold.campus_nome('FGA - GAMA')"),
                         "FACULDADE DE CIENCIAS E TECNOLOGIAS EM ENGENHARIA (FCTE)")
        self.assertEqual(self.um("SELECT gold.campus_nome('FCE - CEILANDIA')"),
                         "FACULDADE DE CIENCIAS E TECNOLOGIAS EM SAUDE (FCTS)")
        self.assertEqual(self.um("SELECT gold.campus_nome('FUP - PLANALTINA')"), "FACULDADE DE PLANALTINA (FUP)")
        self.assertEqual(self.um("SELECT gold.campus_nome('DARCY RIBEIRO')"), "DARCY RIBEIRO")

    def test_arredondar_empata_para_o_par_como_o_numpy(self):
        self.assertEqual(self.um("SELECT gold.arredondar(8.125, 2)"), 8.12)
        self.assertEqual(self.um("SELECT gold.arredondar(8.375, 2)"), 8.38)
        self.assertEqual(self.um("SELECT gold.arredondar(12.35, 1)"), float(np.round(12.35, 1)))
        self.assertIsNone(self.um("SELECT gold.arredondar(NULL, 2)"))


class TestViewsAuxiliares(BancoComGold):
    """Catálogo fictício (ids altos) inserido na transação do teste e desfeito no rollback."""

    def catalogo(self, linhas):
        for i, (nome, turno, campus, grau, area) in enumerate(linhas):
            self.conn.execute(
                """
                INSERT INTO silver.cursos_graduacao (id_curso, nome, nome_curso_norm, turno_norm, campus_norm,
                                                     grau_academico_norm, area_conhecimento_norm, no_catalogo_vigente)
                VALUES (%s, %s, %s, %s, %s, %s, %s, true)
                """,
                (990_000 + i, nome, nome, turno, campus, grau, area),
            )

    def pibic(self, curso):
        self.conn.execute(
            """
            INSERT INTO silver.pibic_bolsistas (ano, tipo_bolsa_norm, campus, curso_pibic_norm, is_cotista,
                                                valor_bolsa_anual_estimado)
            VALUES (2020, 'REMUNERADA', 'DARCY RIBEIRO', %s, false, 0)
            """,
            (curso,),
        )

    def area(self, nome):
        linha = self.conn.execute("SELECT area FROM silver.v_area_curso WHERE nome = %s", (nome,)).fetchone()
        return linha[0] if linha else None

    def test_area_usa_a_entrada_propria_do_catalogo(self):
        self.catalogo([("ZZ FISICA TESTE", "DIURNO", "DARCY RIBEIRO", "BACHAREL", "CIENCIAS EXATAS E DA TERRA")])
        self.assertEqual(self.area("ZZ FISICA TESTE"), "CIENCIAS EXATAS E DA TERRA")

    def test_area_herda_das_habilitacoes_quando_concordam(self):
        self.catalogo([("ZZ COM SOCIAL - JORNALISMO", "DIURNO", "DARCY RIBEIRO", "BACHAREL", "CIENCIAS SOCIAIS APLICADAS"),
                       ("ZZ COM SOCIAL - AUDIOVISUAL", "DIURNO", "DARCY RIBEIRO", "BACHAREL", "CIENCIAS SOCIAIS APLICADAS")])
        self.pibic("ZZ COM SOCIAL")
        self.assertEqual(self.area("ZZ COM SOCIAL"), "CIENCIAS SOCIAIS APLICADAS")

    def test_area_nao_herda_quando_habilitacoes_divergem(self):
        self.catalogo([("ZZ CURSO X - A", "DIURNO", "DARCY RIBEIRO", "BACHAREL", "CIENCIAS EXATAS E DA TERRA"),
                       ("ZZ CURSO X - B", "DIURNO", "DARCY RIBEIRO", "BACHAREL", "LINGUISTICA, LETRAS E ARTES")])
        self.pibic("ZZ CURSO X")
        self.assertIsNone(self.area("ZZ CURSO X"))

    def test_oferta_nao_escolhe_turno_nem_campus_arbitrario(self):
        self.catalogo([("ZZ DIREITO", "DIURNO", "DARCY RIBEIRO", "BACHAREL", None),
                       ("ZZ DIREITO", "NOTURNO", "DARCY RIBEIRO", "BACHAREL", None),
                       ("ZZ ENFERMAGEM", "DIURNO", "DARCY RIBEIRO", "BACHAREL", None),
                       ("ZZ ENFERMAGEM", "MATUTINO", "CEILANDIA", "BACHAREL", None)])
        oferta = {nome: (turno, campus) for nome, turno, campus in self.conn.execute(
            "SELECT nome, turno, campus FROM silver.v_oferta_curso WHERE nome LIKE 'ZZ %'")}
        self.assertEqual(oferta["ZZ DIREITO"], ("DIURNO E NOTURNO", "DARCY RIBEIRO"))
        self.assertEqual(oferta["ZZ ENFERMAGEM"], ("DIURNO", "MULTICAMPUS"))

    def test_curso_com_bacharelado_e_licenciatura_e_misto(self):
        self.catalogo([("ZZ QUIMICA", "DIURNO", "DARCY RIBEIRO", "BACHAREL", None),
                       ("ZZ QUIMICA", "NOTURNO", "DARCY RIBEIRO", "LICENCIATURA", None),
                       ("ZZ FILOSOFIA", "DIURNO", "DARCY RIBEIRO", "BACHAREL", None)])
        misto = {n for (n,) in self.conn.execute("SELECT nome FROM silver.v_curso_misto WHERE nome LIKE 'ZZ %'")}
        self.assertEqual(misto, {"ZZ QUIMICA"})


class TestProcedureDaGold(BancoComGold):

    ARGS = (ANOS_MATURACAO_COORTE, sorted(EXCLUDED_GENERIC_COURSES), MIN_MATRICULAS_BENCHMARK, valor_bolsa_ic_vigente())
    CALL = "CALL gold.atualizar_gold(%s::integer, %s::text[], %s::integer, %s::numeric)"

    def foto(self):
        return {t: self.conn.execute(f"SELECT * FROM {t} ORDER BY _ordem").fetchall() for t in TABELAS_CALCULADAS} | {
            "relatorios": self.conn.execute(
                "SELECT nome, conteudo::text FROM gold.relatorios WHERE nome <> 'qualidade_dados' ORDER BY nome").fetchall()
        }

    def test_regravar_da_o_mesmo_resultado(self):
        antes = self.foto()
        self.conn.execute(self.CALL, self.ARGS)
        self.assertEqual(self.foto(), antes)
        self.conn.execute(self.CALL, self.ARGS)
        self.assertEqual(self.foto(), antes)

    def test_build_gold_semeia_as_regras_e_refaz_a_gold(self):
        """O caminho do pipeline (Python semeia e dispara o CALL) deixa a Gold igual à da procedure."""
        antes = self.foto()
        self.conn.rollback()
        build_gold()
        self.assertEqual(self.foto(), antes)
        self.assertEqual(self.um("SELECT count(*) FROM gold.regras_harmonizacao_canonicas"),
                         len(CANONICAL_RULES_METADATA))

    def test_relatorios_gravados(self):
        nomes = {n for (n,) in self.conn.execute("SELECT nome FROM gold.relatorios")}
        self.assertTrue({"metricas_gerais_unb", "relatorio_casamento_joins",
                         "regras_harmonizacao_canonicas", "pibic_metricas_gerais"} <= nomes)
        metricas = self.um("SELECT conteudo FROM gold.relatorios WHERE nome = 'metricas_gerais_unb'")
        self.assertEqual(sorted(metricas["cursos_tronco"]), sorted(EXCLUDED_GENERIC_COURSES))
        self.assertEqual(len(metricas["top_5_cursos_maior_retencao"]), 5)

    def test_retencao_bate_com_calculo_independente_em_pandas(self):
        """Reimplementa a regra em Pandas (sem olhar o SQL) e exige igualdade curso a curso."""
        discentes = ler("silver.discentes_graduacao")
        estrutura = ler("silver.estrutura_curricular")
        regras = ler("gold.regras_harmonizacao_canonicas")
        discentes["curso"] = discentes["curso_norm"].replace(dict(zip(regras["origem_sigra"], regras["destino_estrutura"])))
        corte = int(discentes["ano_ingresso"].max()) - ANOS_MATURACAO_COORTE
        base = discentes.merge(estrutura, left_on="curso", right_on="nome_curso_norm")
        base = base[base["ano_ingresso"] <= corte]
        formado = base["tipo_saida_grupo"] == "FORMATURA"
        base = base.assign(
            formado=formado,
            evadido=base["tipo_saida_grupo"] == "EVASAO",
            ativo=base["tipo_saida_grupo"] == "ATIVO",
            no_ideal=formado & (base["semestres_permanencia_valida"] <= base["semestre_conclusao_ideal"]),
            desvio=np.where(formado, base["semestres_permanencia_valida"] - base["semestre_conclusao_ideal"], np.nan),
            tempo=np.where(formado, base["semestres_permanencia_valida"], np.nan),
            com_prazo=formado & base["semestres_permanencia_valida"].notna(),
        )
        g = base.groupby("curso").agg(
            total=("curso", "size"), formados=("formado", "sum"), evadidos=("evadido", "sum"),
            ativos=("ativo", "sum"), no_ideal=("no_ideal", "sum"), com_prazo=("com_prazo", "sum"),
            tempo=("tempo", "mean"), desvio=("desvio", "mean"))
        g = g[g["total"] >= 5].copy()
        g["taxa_formatura_pct"] = (g["formados"] / g["total"] * 100).round(2)
        g["taxa_evasao_pct"] = (g["evadidos"] / g["total"] * 100).round(2)
        g["formados_tempo_ideal_pct"] = (g["no_ideal"] / g["com_prazo"].replace(0, np.nan) * 100).round(2).fillna(0.0)
        g["tempo_medio_real_semestres"] = g["tempo"].round(2)
        g["desvio_medio_semestres"] = g["desvio"].round(2)

        def norm(serie):
            p05, p95 = serie.quantile(0.05), serie.quantile(0.95)
            sat = serie.clip(lower=p05, upper=p95)
            return (sat - sat.min()) / (sat.max() - sat.min() + 1e-6)

        g["irc"] = ((0.3 * norm(g["desvio_medio_semestres"].fillna(0).clip(lower=0))
                     + 0.7 * norm(g["taxa_evasao_pct"])) * 100).round(1)
        q25, q50, q75 = (g["irc"].quantile(q) for q in (0.25, 0.5, 0.75))
        g["classe"] = np.select([g["irc"] >= q75, g["irc"] >= q50, g["irc"] >= q25],
                                ["RETENÇÃO CRÍTICA", "RETENÇÃO ALTA", "RETENÇÃO MÉDIA"], "RETENÇÃO BAIXA")

        gold = ler("gold.retencao_cursos_unb").set_index("curso")
        self.assertEqual(set(gold.index), set(g.index))
        g = g.loc[gold.index]
        for esperado, obtido in (("total", "total_discentes_registrados"), ("formados", "total_formados"),
                                 ("evadidos", "total_evadidos_desligados"), ("ativos", "total_ainda_ativos")):
            pd.testing.assert_series_equal(g[esperado].astype(int), gold[obtido].astype(int), check_names=False)
        for col in ("taxa_formatura_pct", "taxa_evasao_pct", "formados_tempo_ideal_pct", "tempo_medio_real_semestres",
                    "desvio_medio_semestres"):
            pd.testing.assert_series_equal(g[col], gold[col], check_names=False, atol=1e-9)
        pd.testing.assert_series_equal(g["irc"], gold["indice_retencao_critica"], check_names=False, atol=1e-9)
        self.assertEqual(g["classe"].tolist(), gold["classificacao_retencao"].tolist())


if __name__ == "__main__":
    unittest.main()
