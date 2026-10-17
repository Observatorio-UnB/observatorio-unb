"""
Testes unitários do tratamento de dado atrasado (sem PostgreSQL).

Confere a marca d'água calculada da publicação e da tolerância, e a detecção das janelas do lago
que diferem do banco: só a janela que recebeu o dado atrasado é regravada, e as outras ficam com
os mesmos arquivos.

Uso:
    python3 -m unittest tests/test_unit_dado_atrasado.py
"""

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
from deltalake import DeltaTable

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db import exportar_lago as lago  # noqa: E402
from src.db.dado_atrasado import _menos_meses, fim_do_periodo, marca_dagua, rotulo  # noqa: E402

COLUNAS = [
    ("id_vinculo", "bigint"),
    ("ano_ingresso", "smallint"),
    ("tipo_saida_grupo", "text"),
    ("ano_saida", "smallint"),
    ("semestre_saida", "smallint"),
]

ANOS = [2011, 2012, 2016, 2019, 2021, 2023] * 20


def _vinculos(anos=ANOS):
    return [(i, ano, "ATIVO", None, None) for i, ano in enumerate(anos, start=1)]


def _formar(linhas, coorte, quantos, ano_saida, semestre_saida):
    """Os `quantos` primeiros ativos da coorte viram formados no período dado."""
    novas, restam = [], quantos
    for linha in linhas:
        id_vinculo, ano, tipo = linha[:3]
        if ano == coorte and tipo == "ATIVO" and restam:
            novas.append((id_vinculo, ano, "FORMATURA", ano_saida, semestre_saida))
            restam -= 1
        else:
            novas.append(linha)
    return novas


def _tabela(linhas, particionada=True):
    return lago.montar_tabela_arrow(COLUNAS, linhas, particionada=particionada)


class TestMarcaDagua(unittest.TestCase):

    def test_fim_do_periodo(self):
        self.assertEqual(fim_do_periodo(20230), date(2023, 2, 28))
        self.assertEqual(fim_do_periodo(20240), date(2024, 2, 29))
        self.assertEqual(fim_do_periodo(20231), date(2023, 7, 31))
        self.assertEqual(fim_do_periodo(20232), date(2023, 12, 31))

    def test_menos_meses_ajusta_o_dia(self):
        self.assertEqual(_menos_meses(date(2024, 7, 31), 5), date(2024, 2, 29))
        self.assertEqual(_menos_meses(date(2024, 3, 15), 4), date(2023, 11, 15))

    def test_publicacao_do_sigaa(self):
        """O SIGAA publicado em 15/07/2024: com 4 meses de tolerância, 2024/1 ainda está aberto."""
        self.assertEqual(marca_dagua(date(2024, 7, 15), tolerancia_meses=4), 20240)

    def test_tolerancia_maior_recua_a_marca(self):
        self.assertEqual(marca_dagua(date(2024, 7, 15), tolerancia_meses=6), 20232)
        self.assertEqual(marca_dagua(date(2024, 7, 15), tolerancia_meses=0), 20240)

    def test_periodo_fecha_quando_fim_mais_tolerancia_passa(self):
        self.assertEqual(marca_dagua(date(2024, 11, 30), tolerancia_meses=4), 20240)
        self.assertEqual(marca_dagua(date(2024, 12, 1), tolerancia_meses=4), 20241)

    def test_rotulo(self):
        self.assertEqual(rotulo(20232), "2023/2")


class TestJanelasAlteradas(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.destino = Path(self._tmp.name) / "silver" / "movimentacoes_vinculos"
        self.linhas = _vinculos()
        lago.gravar_no_lago(_tabela(self.linhas), self.destino, particionada=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_banco_igual_ao_lago_nao_tem_janela_alterada(self):
        self.assertEqual(lago.janelas_alteradas(_tabela(self.linhas), self.destino), [])

    def test_formatura_atrasada_altera_so_a_janela_da_coorte(self):
        atrasada = _formar(self.linhas, coorte=2012, quantos=3, ano_saida=2022, semestre_saida=2)
        self.assertEqual(lago.janelas_alteradas(_tabela(atrasada), self.destino), [2010])

    def test_ids_renumerados_alteram_a_janela(self):
        """A mesma coorte com outros ids é outra janela: o lago não pode guardar id de uma carga anterior."""
        renumerada = [(i + 1000 if ano == 2019 else i, ano, *resto) for i, ano, *resto in self.linhas]
        self.assertEqual(lago.janelas_alteradas(_tabela(renumerada), self.destino), [2015])

    def test_janela_que_sumiu_do_banco_e_alterada(self):
        sem_2020 = [linha for linha in self.linhas if lago.quinquenio(linha[1]) != 2020]
        self.assertEqual(lago.janelas_alteradas(_tabela(sem_2020), self.destino), [2020])

    def test_janela_nova_e_alterada(self):
        com_2025 = self.linhas + [(999, 2026, "ATIVO", None, None)]
        self.assertEqual(lago.janelas_alteradas(_tabela(com_2025), self.destino), [2025])

    def test_sem_tabela_no_lago_todas_as_janelas_entram(self):
        outro = Path(self._tmp.name) / "vazio"
        self.assertEqual(lago.janelas_alteradas(_tabela(self.linhas), outro), [2010, 2015, 2020])

    def test_reprocessar_as_janelas_alteradas_deixa_as_outras_intactas(self):
        antes = {uri for uri in DeltaTable(str(self.destino)).file_uris() if "=2010" not in uri}
        atrasada = _tabela(_formar(self.linhas, coorte=2012, quantos=3, ano_saida=2022, semestre_saida=2))
        janelas = lago.janelas_alteradas(atrasada, self.destino)
        janela = atrasada.filter(pc.is_in(atrasada[lago.COLUNA_QUINQUENIO], pa.array(janelas, pa.int16())))
        depois = lago.gravar_no_lago(janela, self.destino, particionada=True, quinquenios=janelas)

        self.assertTrue(antes <= set(depois.file_uris()))
        self.assertEqual(lago.janelas_alteradas(atrasada, self.destino), [])
        formados = depois.to_pyarrow_table().to_pandas().query("tipo_saida_grupo == 'FORMATURA'")
        self.assertEqual(len(formados), 3)
        self.assertEqual(set(formados["ano_ingresso"]), {2012})


class TestExportar(unittest.TestCase):

    def test_quinquenio_e_janelas_alteradas_juntos_recusado(self):
        """Com só parte dos vínculos lida, as outras janelas seriam esvaziadas no lago."""
        with self.assertRaises(ValueError):
            lago.exportar(quinquenios=[2020], so_alteradas=True)


class TestTabelaAlterada(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.destino = Path(self._tmp.name) / "silver" / "cursos"

    def tearDown(self):
        self._tmp.cleanup()

    def test_tabela_nao_particionada(self):
        linhas = _vinculos()
        self.assertTrue(lago.tabela_alterada(_tabela(linhas, particionada=False), self.destino))
        lago.gravar_no_lago(_tabela(linhas, particionada=False), self.destino)
        self.assertFalse(lago.tabela_alterada(_tabela(list(reversed(linhas)), particionada=False), self.destino))
        mudou = _formar(linhas, coorte=2016, quantos=1, ano_saida=2023, semestre_saida=1)
        self.assertTrue(lago.tabela_alterada(_tabela(mudou, particionada=False), self.destino))


if __name__ == "__main__":
    unittest.main()
