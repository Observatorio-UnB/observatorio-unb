"""
Catálogo e linhagem (src/governanca/linhagem.py), sem banco: a declaração confere com o código e o
manifest, a verificação acusa linhagem quebrada, e o documento publicado está em dia.

Pulado sem o manifest do dbt (pip install -r requirements-dbt.txt).

Uso:
    python3 -m unittest tests/test_unit_linhagem.py
"""

import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.governanca import linhagem as L  # noqa: E402

MANIFEST = L.carregar_manifest()
if MANIFEST is None:
    raise unittest.SkipTest("Manifest do dbt indisponível (pip install -r requirements-dbt.txt).")


class TestLinhagem(unittest.TestCase):

    def setUp(self):
        self.grafo = L.montar_grafo(MANIFEST)

    def test_01_declaracao_confere_com_o_codigo(self):
        self.assertEqual(L.verificar_declaracao(self.grafo), [])

    def test_02_documento_publicado_em_dia(self):
        self.assertEqual(L.SAIDA.read_text(encoding="utf-8"), L.documento(self.grafo),
                         "rode python3 src/governanca/linhagem.py")

    def test_03_todo_consumidor_chega_ao_portal_passando_pelo_oltp(self):
        for consumidor in self.grafo.consumidores:
            with self.subTest(consumidor=consumidor):
                acima = L.ancestrais(self.grafo, consumidor)
                self.assertTrue(any(a.startswith("portal:") for a in acima))
                self.assertTrue(any(a.startswith("bronze.") for a in acima))

    def test_04_painel_e_fila_passam_pela_silver_3nf(self):
        """A linhagem do ranking não pula o OLTP: painel e fila vêm da Silver 3NF."""
        for consumidor in ("consumo:painel_visao_executiva", "consumo:fila_intervencao"):
            self.assertIn("silver.movimentacoes_vinculos", L.ancestrais(self.grafo, consumidor))

    def test_05_toda_fonte_do_portal_configurada_entra_no_catalogo(self):
        chaves = {f.chave for f in L.fontes_publicas()}
        for chave in L.DATASETS_CONFIG:
            self.assertIn(f"portal:{chave}", chaves)

    def test_06_acusa_fonte_do_dbt_sem_etapa(self):
        sem_cursos = tuple(e for e in L.ETAPAS if e.destino != "silver.cursos")
        with mock.patch.object(L, "ETAPAS", sem_cursos):
            problemas = L.verificar_declaracao(L.montar_grafo(MANIFEST))
        self.assertTrue(any("silver.cursos" in p and "sem etapa" in p for p in problemas), problemas)

    def test_07_acusa_origem_que_o_script_nao_le(self):
        etapas = tuple(replace(e, origens=(*e.origens, "bronze.sigaa_ativos"))
                       if e.destino == "silver.cursos" else e for e in L.ETAPAS)
        with mock.patch.object(L, "ETAPAS", etapas):
            problemas = L.verificar_declaracao(L.montar_grafo(MANIFEST))
        self.assertTrue(any("bronze.sigaa_ativos" in p for p in problemas), problemas)

    def test_08_acusa_consumidor_que_nao_chega_ao_portal(self):
        grafo = L.montar_grafo(MANIFEST)
        grafo.consumidores["consumo:orfao"] = {"name": "orfao", "type": "dashboard"}
        grafo.arestas.add(("gold.tabela_sem_origem", "consumo:orfao"))
        self.assertTrue(any("orfao" in p for p in L.verificar_declaracao(grafo)))

    def test_09_trilhas_terminam_no_portal(self):
        for trilha in L.TRILHAS:
            with self.subTest(trilha=trilha.rotulo):
                if trilha.rotulo == "IRC e Classificação":
                    continue  # remete às trilhas da Evasão e do Atraso
                self.assertTrue(trilha.passos[-1].ativo.startswith("portal:"))
                self.assertTrue(trilha.passos[0].ativo.startswith(("dbt_marts.", "operacional.")))

    def test_10_fila_passa_pela_tabela_operacional(self):
        """A linhagem do ETL reverso não pula a tabela que a coordenação lê."""
        acima = L.ancestrais(self.grafo, "consumo:fila_intervencao")
        self.assertIn("operacional.fila_intervencao", acima)
        self.assertIn("dbt_marts.painel_cursos_criticos", L.ancestrais(self.grafo, "operacional.fila_intervencao"))


if __name__ == "__main__":
    unittest.main()
