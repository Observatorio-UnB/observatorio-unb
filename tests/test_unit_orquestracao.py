"""
Estrutura do grafo do Dagster (orquestracao/definicoes.py), sem banco: a ordem das etapas, o retry
de cada uma, as partições do backfill e a ligação dos modelos do dbt ao star schema.

Pulado sem o Dagster ou sem o dbt instalados (pip install -r requirements-orquestracao.txt): o grafo
só monta com o manifest do dbt, gerado por `dbt parse` quando falta ou está desatualizado.

Uso:
    python3 -m unittest tests/test_unit_orquestracao.py
"""

import os
import re
import subprocess
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
except subprocess.CalledProcessError as erro:  # sem dbt para gerar o manifest
    raise unittest.SkipTest(f"dbt indisponível para gerar o manifest ({erro.stderr or erro}).")


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

    def test_06_mesmos_scripts_no_grafo_e_no_rodar_pipeline(self):
        """O grafo é a fonte da verdade, e o rodar_pipeline.sh (Docker, sem Dagster) tem de chamar as
        mesmas etapas: script novo num lado só faz este teste falhar."""
        shell = set(re.findall(r'"\$PYTHON" (src/[\w/]+\.py)', (BASE_DIR / "scripts" / "rodar_pipeline.sh").read_text()))
        grafo = set(re.findall(r'rodar\(context, "(src/[\w/]+\.py)"', (BASE_DIR / "orquestracao" / "definicoes.py").read_text()))
        self.assertTrue(shell)
        self.assertEqual(grafo, shell)
        # O dbt entra pelo dagster-dbt no grafo e pelo scripts/dbt.sh no shell.
        self.assertIn("scripts/dbt.sh build", (BASE_DIR / "scripts" / "rodar_pipeline.sh").read_text())
        self.assertTrue(d.camadas_dbt.keys)

    def test_07_manifest_desatualizado_quando_um_modelo_muda(self):
        modelo = BASE_DIR / "transform" / "models" / "marts" / "dim_curso.sql"
        manifest = d.MANIFEST.stat().st_mtime
        original = modelo.stat().st_mtime
        try:
            os.utime(modelo, (original, manifest + 10))
            self.assertTrue(d.manifest_desatualizado())
        finally:
            os.utime(modelo, (original, original))
        self.assertFalse(d.manifest_desatualizado())

    def test_08_intervalo_do_backfill_acompanha_as_particoes(self):
        particoes = d.QUINQUENIOS.get_partition_keys()
        self.assertEqual(d.INTERVALO_BACKFILL, f"{particoes[0]}...{particoes[-1]}")

    def test_05_job_mensal_cobre_tudo_menos_o_backfill(self):
        selecionados = d.pipeline_mensal.selection.resolve(self.grafo)
        todos = self.grafo.get_all_asset_keys()
        self.assertEqual(todos - selecionados, {chave("lago_vinculos_por_quinquenio")})


if __name__ == "__main__":
    unittest.main()
