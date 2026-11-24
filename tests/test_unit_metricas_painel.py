"""
Camada semântica no painel (src/dashboard/metricas.py) e regras puras do ETL reverso
(src/etl_reverso/fila_intervencao.py), sem banco nem Streamlit.

Uso:
    python3 -m unittest tests/test_unit_metricas_painel.py
"""

import sys
import unittest
from pathlib import Path

import pandas as pd
import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src" / "dashboard"))
sys.path.insert(0, str(BASE_DIR))
from metricas import FONTE_GOLD, FONTE_SEMANTICA, definicoes, metricas_da_unb, metricas_por_recorte  # noqa: E402
from src.etl_reverso.coordenacao import alteracoes  # noqa: E402
from src.etl_reverso.fila_intervencao import (  # noqa: E402
    METRICAS_GRAVADAS, OrigemInvalida, com_retentativas, versao_metricas)


def gold(curso, turno, ingressantes, evadidos, formados, taxa_evasao):
    return {"curso": curso, "turno": turno, "campus": "DARCY RIBEIRO", "categoria_grau": "BACHARELADO",
            "area_conhecimento": "X", "total_discentes_registrados": ingressantes,
            "total_evadidos_desligados": evadidos, "total_formados": formados, "taxa_evasao_pct": taxa_evasao}


class TestRecortes(unittest.TestCase):

    def test_01_vem_da_camada_semantica_quando_ha_o_mart(self):
        tabelas = {"metricas_por_recorte": [
            {"recorte": "TURNO", "valor": "NOTURNO", "cursos": 2, "ingressantes": 120, "formados": 40,
             "evadidos": 60, "taxa_formatura_pct": 33.33, "taxa_evasao_pct": 50.0,
             "formados_tempo_ideal_pct": 20.0, "atraso_medio_semestres": 2.0,
             "tempo_medio_formatura_semestres": 11.0, "prazo_ideal_medio_semestres": 9.0},
            {"recorte": "CAMPUS", "valor": "FUP", "cursos": 1, "ingressantes": 10, "formados": 1, "evadidos": 1,
             "taxa_formatura_pct": 10.0, "taxa_evasao_pct": 10.0, "formados_tempo_ideal_pct": 0,
             "atraso_medio_semestres": None, "tempo_medio_formatura_semestres": None,
             "prazo_ideal_medio_semestres": None},
        ]}
        df, fonte = metricas_por_recorte(tabelas, None, "TURNO")
        self.assertEqual(fonte, FONTE_SEMANTICA)
        self.assertEqual(df["valor"].tolist(), ["NOTURNO"])
        self.assertEqual(df.iloc[0]["taxa_evasao_pct"], 50.0)

    def test_02_sem_o_mart_e_a_razao_das_somas_e_nao_a_media_das_taxas(self):
        """Um curso de 1.000 ingressantes com 20% de evasão e um de 10 com 80%: a evasão do grupo é
        (200 + 8) / 1.010 = 20,59%, e não a média das taxas (50%), que era o que o painel mostrava."""
        df_gold = pd.DataFrame([gold("A", "NOTURNO", 1000, 200, 600, 20.0),
                                gold("B", "NOTURNO", 10, 8, 2, 80.0)])
        df, fonte = metricas_por_recorte({}, df_gold, "TURNO")
        self.assertEqual(fonte, FONTE_GOLD)
        self.assertAlmostEqual(df.iloc[0]["taxa_evasao_pct"], 20.59)
        self.assertNotAlmostEqual(df.iloc[0]["taxa_evasao_pct"], df_gold["taxa_evasao_pct"].mean())

    def test_03_sem_o_mart_fica_no_mesmo_universo_sem_os_cursos_tronco(self):
        df_gold = pd.DataFrame([gold("A", "DIURNO", 100, 10, 80, 10.0),
                                gold("ENGENHARIA", "DIURNO", 500, 400, 50, 80.0)])
        df, _ = metricas_por_recorte({}, df_gold, "TURNO", cursos_tronco=["ENGENHARIA"])
        self.assertEqual(df.iloc[0]["cursos"], 1)
        self.assertAlmostEqual(df.iloc[0]["taxa_evasao_pct"], 10.0)

    def test_04_sem_o_mart_nao_inventa_as_metricas_que_dependem_dos_vinculos(self):
        df_gold = pd.DataFrame([gold("A", "DIURNO", 100, 10, 80, 10.0)])
        df, _ = metricas_por_recorte({}, df_gold, "TURNO")
        self.assertTrue(pd.isna(df.iloc[0]["tempo_medio_formatura_semestres"]))

    def test_05_definicoes_filtradas_e_com_versao(self):
        tabelas = {"metricas_definicoes": [
            {"metrica": "taxa_evasao_pct", "rotulo": "Taxa de evasão", "definicao": "d", "formula": "f",
             "unidade": "%", "versao": "1.0.0", "vigente_desde": "2026-09-26", "adr": "0013"},
            {"metrica": "ingressantes", "rotulo": "Ingressantes", "definicao": "d", "formula": "f",
             "unidade": "vínculos", "versao": "1.0.0", "vigente_desde": "2026-09-26", "adr": "0014"},
        ]}
        df = definicoes(tabelas, ["taxa_evasao_pct"])
        self.assertEqual(df["Métrica"].tolist(), ["Taxa de evasão"])
        self.assertEqual(df.iloc[0]["Versão"], "1.0.0")
        self.assertIsNone(definicoes({}))


class TestUnbEFila(unittest.TestCase):

    def test_01_numeros_da_unb_vem_do_recorte_unb(self):
        tabelas = {"metricas_por_recorte": [{"recorte": "TURNO", "valor": "UNB"},
                                            {"recorte": "UNB", "valor": "UNB", "taxa_evasao_pct": 43.14}]}
        self.assertEqual(metricas_da_unb(tabelas)["taxa_evasao_pct"], 43.14)
        self.assertIsNone(metricas_da_unb({}))

    def test_02_tela_da_fila_so_envia_o_que_mudou(self):
        antes = pd.DataFrame([{"nome_curso": "A", "status": "NOVO", "responsavel": None, "plano_de_acao": None},
                              {"nome_curso": "B", "status": "NOVO", "responsavel": None, "plano_de_acao": None}])
        depois = antes.copy()
        depois.loc[1, ["status", "responsavel"]] = ["EM_ANALISE", "coord.b"]
        self.assertEqual(alteracoes(antes, depois),
                         [{"nome_curso": "B", "status": "EM_ANALISE", "responsavel": "coord.b", "plano_de_acao": ""}])
        self.assertEqual(alteracoes(antes, antes.copy()), [])


class TestEtlReversoSemBanco(unittest.TestCase):

    def test_01_versao_metricas_lista_cada_metrica_com_a_sua_versao(self):
        versao = versao_metricas({m: "1.0.0" for m in METRICAS_GRAVADAS} | {"taxa_evasao_pct": "1.1.0"})
        self.assertIn("taxa_evasao_pct@1.1.0", versao.split(";"))
        self.assertEqual(len(versao.split(";")), len(METRICAS_GRAVADAS))

    def test_02_metrica_sem_definicao_e_recusada(self):
        with self.assertRaises(OrigemInvalida):
            versao_metricas({"taxa_evasao_pct": "1.0.0"})

    def test_03_retenta_e_depois_desiste_com_o_erro_do_destino(self):
        tentativas, esperas = [], []

        def falha():
            tentativas.append(1)
            raise psycopg.OperationalError("connection refused")

        with self.assertRaises(psycopg.OperationalError):
            com_retentativas(falha, esperas=(2, 4, 8), dormir=esperas.append)
        self.assertEqual(len(tentativas), 4)
        self.assertEqual(esperas, [2, 4, 8])

    def test_04_destino_que_volta_no_meio_das_tentativas(self):
        respostas = iter([psycopg.OperationalError("fora"), "ok"])

        def operacao():
            resposta = next(respostas)
            if isinstance(resposta, Exception):
                raise resposta
            return resposta

        self.assertEqual(com_retentativas(operacao, esperas=(1,), dormir=lambda _: None), "ok")


if __name__ == "__main__":
    unittest.main()
