"""
Testes unitários da exportação para o Delta Lake (sem PostgreSQL).

Vínculos sintéticos são gravados num lago temporário: confere que regravar não duplica, que o
reprocessamento de um quinquênio só toca a partição dele e que cada partição fica num arquivo.

Uso:
    python3 -m unittest tests/test_unit_lago.py
"""

import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from deltalake import DeltaTable

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db import exportar_lago as lago  # noqa: E402

COLUNAS = [
    ("id_vinculo", "bigint"),
    ("ano_ingresso", "smallint"),
    ("tipo_saida_grupo", "text"),
    ("ano_saida", "smallint"),
    ("semestre_minimo", "numeric"),
]


def _vinculos(anos, tipo="FORMATURA", ano_saida=None):
    return [(i, ano, tipo, ano_saida, 8.0) for i, ano in enumerate(anos, start=1)]


def _tabela(linhas):
    return lago.montar_tabela_arrow(COLUNAS, linhas, particionada=True)


class TestLago(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.destino = Path(self._tmp.name) / "silver" / "movimentacoes_vinculos"
        self.anos = [2008, 2012, 2016, 2019, 2021, 2023] * 50

    def tearDown(self):
        self._tmp.cleanup()

    def _gravar(self, linhas, quinquenios=None):
        return lago.gravar_no_lago(_tabela(linhas), self.destino, particionada=True, quinquenios=quinquenios)

    def _ler(self):
        return DeltaTable(str(self.destino)).to_pyarrow_table().to_pandas()

    def test_quinquenio(self):
        self.assertEqual([lago.quinquenio(a) for a in (2000, 2004, 2005, 2023)], [2000, 2000, 2005, 2020])

    def test_regravar_nao_duplica(self):
        primeira = self._gravar(_vinculos(self.anos))
        segunda = self._gravar(_vinculos(self.anos))
        self.assertEqual(len(self._ler()), len(self.anos))
        self.assertEqual(segunda.version(), primeira.version() + 1)
        self.assertEqual(len(segunda.file_uris()), len(primeira.file_uris()))

    def test_um_arquivo_por_particao(self):
        for _ in range(3):
            delta = self._gravar(_vinculos(self.anos))
        particoes = Counter(Path(uri).parent.name for uri in delta.file_uris())
        self.assertEqual(
            particoes,
            Counter({f"{lago.COLUNA_QUINQUENIO}={q}": 1 for q in (2005, 2010, 2015, 2020)}),
        )

    def test_reprocessar_quinquenio_so_toca_a_particao(self):
        antes = self._gravar(_vinculos(self.anos))
        outras = {uri for uri in antes.file_uris() if "=2020" not in uri}
        # A janela 2020 volta do banco com os vínculos evadidos e um a menos.
        janela = [ano for ano in self.anos if lago.quinquenio(ano) == 2020][:-1]
        depois = self._gravar(_vinculos(janela, tipo="EVASAO", ano_saida=2024), quinquenios=[2020])

        df = self._ler()
        reprocessado = df[df[lago.COLUNA_QUINQUENIO] == 2020]
        self.assertEqual(len(reprocessado), len(janela))
        self.assertEqual(set(reprocessado["tipo_saida_grupo"]), {"EVASAO"})
        self.assertEqual(set(df.loc[df[lago.COLUNA_QUINQUENIO] != 2020, "tipo_saida_grupo"]), {"FORMATURA"})
        self.assertTrue(outras <= set(depois.file_uris()))

    def test_janela_vazia_esvazia_a_particao(self):
        self._gravar(_vinculos(self.anos))
        self._gravar([], quinquenios=[2020])
        self.assertNotIn(2020, set(self._ler()[lago.COLUNA_QUINQUENIO]))

    def test_coluna_toda_nula_mantem_o_tipo(self):
        self._gravar(_vinculos(self.anos, ano_saida=2020))
        self._gravar(_vinculos(self.anos, ano_saida=None))
        esquema = DeltaTable(str(self.destino)).to_pyarrow_table().schema
        self.assertEqual(esquema.field("ano_saida").type, pa.int16())

    def test_parquet_com_zstd(self):
        delta = self._gravar(_vinculos(self.anos))
        meta = pq.ParquetFile(delta.file_uris()[0]).metadata
        self.assertEqual(meta.row_group(0).column(0).compression, "ZSTD")

    def test_quinquenio_em_tabela_nao_particionada_recusado(self):
        tabela = lago.montar_tabela_arrow(COLUNAS, _vinculos(self.anos), particionada=False)
        with self.assertRaises(ValueError):
            lago.gravar_no_lago(tabela, self.destino, quinquenios=[2020])


if __name__ == "__main__":
    unittest.main()
