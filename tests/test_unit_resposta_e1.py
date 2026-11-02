"""
Resposta do painel à pergunta da E1 (src/dashboard/resposta_e1.py), sem banco nem Streamlit.

Uso:
    python3 -m unittest tests/test_unit_resposta_e1.py
"""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src" / "dashboard"))
from resposta_e1 import (  # noqa: E402
    COLUNAS, FONTE_DBT, FONTE_GOLD, FONTE_GOLD_MART_ANTIGO, SLA_DIAS, frescor, ranking_cursos_criticos)


def linha_mart(posicao, curso, irc, classificacao="RETENÇÃO CRÍTICA"):
    return {"posicao": posicao, "nome_curso": curso, "campus": "DARCY RIBEIRO", "area_conhecimento": "X",
            "categoria_grau": "BACHARELADO", "classificacao_retencao": classificacao,
            "indice_retencao_critica": irc, "taxa_evasao_pct": 50.0, "atraso_medio_semestres": 1.0,
            "taxa_formatura_pct": 40.0, "formados_tempo_ideal_pct": 30.0, "total_ingressantes": 100,
            "total_formados": 40, "total_evadidos": 50}


def gold(curso, irc):
    return {"curso": curso, "campus": "DARCY RIBEIRO", "classificacao_retencao": "RETENÇÃO ALTA",
            "indice_retencao_critica": irc, "taxa_evasao_pct": 40.0, "desvio_medio_semestres": 2.0,
            "formados_tempo_ideal_pct": 20.0, "total_discentes_registrados": 80}


class TestRanking(unittest.TestCase):

    def test_01_vem_do_mart_do_dbt_na_ordem_da_posicao(self):
        painel = [linha_mart(2, "B", 80.0), linha_mart(1, "A", 90.0), linha_mart(3, "C", 70.0)]
        ranking, fonte = ranking_cursos_criticos({"painel_cursos_criticos": painel}, None)
        self.assertEqual(fonte, FONTE_DBT)
        self.assertEqual(ranking["nome_curso"].tolist(), ["A", "B", "C"])
        self.assertEqual(list(ranking.columns), list(COLUNAS))

    def test_02_sem_o_mart_cai_na_gold_sem_os_cursos_tronco(self):
        df_gold = pd.DataFrame([gold("A", 50.0), gold("ENGENHARIA", 99.0), gold("B", 70.0), gold("C", 70.0)])
        ranking, fonte = ranking_cursos_criticos({}, df_gold, cursos_tronco=["ENGENHARIA"])
        self.assertEqual(fonte, FONTE_GOLD)
        self.assertEqual(ranking["nome_curso"].tolist(), ["B", "C", "A"])
        # Empate no IRC divide a posição, como o rank() do mart.
        self.assertEqual(ranking["posicao"].tolist(), [1, 1, 3])
        self.assertEqual(list(ranking.columns), list(COLUNAS))

    def test_04_mart_da_mesma_carga_da_gold_e_usado(self):
        painel = [linha_mart(1, "A", 90.0), linha_mart(2, "B", 80.0)]
        df_gold = pd.DataFrame([gold("A", 90.0), gold("B", 80.0), gold("ENGENHARIA", 99.0)])
        _, fonte = ranking_cursos_criticos({"painel_cursos_criticos": painel}, df_gold, ["ENGENHARIA"])
        self.assertEqual(fonte, FONTE_DBT)

    def test_05_mart_de_outra_carga_e_descartado(self):
        """Pipeline rodou sem o dbt: o mart que ficou no banco tem outro IRC, e o ranking sai da gold."""
        painel = [linha_mart(1, "A", 90.0), linha_mart(2, "B", 80.0)]
        df_gold = pd.DataFrame([gold("A", 70.0), gold("B", 85.0)])
        ranking, fonte = ranking_cursos_criticos({"painel_cursos_criticos": painel}, df_gold)
        self.assertEqual(fonte, FONTE_GOLD_MART_ANTIGO)
        self.assertEqual(ranking["nome_curso"].tolist(), ["B", "A"])

    def test_03_sem_dado_nenhum(self):
        self.assertEqual(ranking_cursos_criticos({}, None), (None, FONTE_GOLD))


class TestFrescor(unittest.TestCase):
    CARGA = "2026-10-01T06:00:00+00:00"

    def agora_mais(self, **delta):
        return datetime.fromisoformat(self.CARGA) + timedelta(**delta)

    def test_01_dentro_do_sla_ate_o_ultimo_segundo(self):
        _, dias, ok = frescor(self.CARGA, self.agora_mais(days=SLA_DIAS))
        self.assertEqual((dias, ok), (SLA_DIAS, True))

    def test_02_fora_do_sla_logo_depois(self):
        _, dias, ok = frescor(self.CARGA, self.agora_mais(days=SLA_DIAS, hours=1))
        self.assertEqual((dias, ok), (SLA_DIAS, False))

    def test_03_data_sem_fuso_vale_como_utc(self):
        data, _, _ = frescor("2026-10-01T06:00:00", self.agora_mais(days=1))
        self.assertEqual(data.tzinfo, timezone.utc)

    def test_04_sem_data_de_carga(self):
        self.assertIsNone(frescor(None))


if __name__ == "__main__":
    unittest.main()
