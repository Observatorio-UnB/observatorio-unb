"""
Estrutura do grafo do Dagster (orquestracao/definicoes.py), sem banco: a ordem das etapas, o retry
de cada uma, as partições do backfill e a ligação dos modelos do dbt ao star schema.

Pulado sem o Dagster instalado (pip install -r requirements-orquestracao.txt).

Uso:
    python3 -m unittest tests/test_unit_orquestracao.py
"""

import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

try:
    from dagster import AssetKey

    from orquestracao import definicoes as d
except ImportError as erro:  # sem dagster/dagster-dbt
    raise unittest.SkipTest(f"Dagster não instalado ({erro}).")


def chave(nome: str) -> AssetKey:
    return AssetKey(nome.split("/"))


class TestGrafo(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.grafo = d.defs.resolve_asset_graph()

    def depende_de(self, asset: str, upstream: str) -> bool:
        return chave(upstream) in self.grafo.get(chave(asset)).parent_keys

    def test_01_etapas_na_ordem_do_pipeline(self):
        for asset, upstream in [
            ("bronze_ckan", "migracoes"),
            ("silver", "bronze_ckan"),
            ("gold_tabular", "silver"),
            ("gold/dim_curso", "gold_tabular"),
            ("view_painel", "gold/fato_retencao_curso"),
            ("supabase", "view_painel"),
        ]:
            with self.subTest(asset=asset):
                self.assertTrue(self.depende_de(asset, upstream), f"{asset} deveria depender de {upstream}")

    def test_02_modelos_do_dbt_ligados_ao_star_schema(self):
        """As fontes do dbt são as tabelas que o star_schema grava: o dbt só roda depois dele."""
        self.assertTrue(self.depende_de("dbt_staging/stg_vinculos", "silver/movimentacoes_vinculos"))
        self.assertTrue(self.depende_de("dbt_marts/painel_cursos_criticos", "dbt_marts/fct_retencao_curso"))

    def test_03_toda_etapa_tem_retry(self):
        for asset in self.grafo.get_all_asset_keys():
            with self.subTest(asset=asset.to_user_string()):
                politica = self.grafo.get(asset).assets_def.op.retry_policy
                self.assertIsNotNone(politica)
                self.assertGreaterEqual(politica.max_retries, 1)

    def test_04_backfill_por_quinquenio(self):
        particoes = d.QUINQUENIOS.get_partition_keys()
        self.assertEqual(particoes[:3], ["2000", "2005", "2010"])
        self.assertTrue(all(int(p) % 5 == 0 for p in particoes))
        self.assertIs(self.grafo.get(chave("lago_vinculos_por_quinquenio")).partitions_def, d.QUINQUENIOS)

    def test_05_job_mensal_cobre_tudo_menos_o_backfill(self):
        selecionados = d.pipeline_mensal.selection.resolve(self.grafo)
        todos = self.grafo.get_all_asset_keys()
        self.assertEqual(todos - selecionados, {chave("lago_vinculos_por_quinquenio")})


if __name__ == "__main__":
    unittest.main()
