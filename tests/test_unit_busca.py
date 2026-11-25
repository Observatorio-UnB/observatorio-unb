"""
Testes unitários da busca semântica sem banco e sem modelo: como a documentação vira trechos e
como a consulta vira a busca por texto.

Uso:
    python3 -m unittest tests/test_unit_busca.py
"""

import sys
import tempfile
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.busca.buscar import (  # noqa: E402
    _montar_filtros_sql,
    consulta_de_cobertura,
    expandir_consulta,
    sem_acento,
)
from src.busca.vetorizar import (  # noqa: E402
    SOBREPOSICAO_TRECHO,
    TAMANHO_MAX_TRECHO,
    _limpar_markdown,
    _trechos,
    documentos_da_documentacao,
    normalizar_campus,
)


class TestTrechos(unittest.TestCase):

    def test_paragrafo_longo_e_cortado_em_espaco_sem_passar_do_limite(self):
        texto = " ".join(f"palavra{i}" for i in range(300))
        trechos = _trechos(texto)
        self.assertGreater(len(trechos), 1)
        palavras = set(texto.split())
        for trecho in trechos:
            self.assertLessEqual(len(trecho), TAMANHO_MAX_TRECHO)
            self.assertTrue(set(trecho.split()) <= palavras, "palavra cortada ao meio")

    def test_trechos_seguidos_se_sobrepoem(self):
        texto = " ".join(f"palavra{i}" for i in range(300))
        primeiro, segundo = _trechos(texto)[:2]
        fim_do_primeiro = primeiro[-(SOBREPOSICAO_TRECHO // 2):].split()[-1]
        self.assertIn(fim_do_primeiro, segundo.split())

    def test_paragrafos_curtos_ficam_juntos_e_inteiros(self):
        self.assertEqual(_trechos("um\n\ndois\n\ntrês"), ["um\ndois\ntrês"])

    def test_palavra_sem_espaco_maior_que_o_trecho_e_cortada_seca(self):
        trechos = _trechos("x" * (TAMANHO_MAX_TRECHO * 2 + 10))
        self.assertTrue(all(len(t) <= TAMANHO_MAX_TRECHO for t in trechos))
        self.assertEqual(sum(len(t) for t in trechos), TAMANHO_MAX_TRECHO * 2 + 10)


class TestDocumentacao(unittest.TestCase):

    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp())
        docs = self.raiz / "docs"
        (docs / "adr").mkdir(parents=True)
        (docs / "guia.md").write_text("# Guia\nComo rodar o pipeline do começo ao fim.\n", encoding="utf-8")
        (docs / "adr" / "0028-scd.md").write_text("# ADR 0028: SCD tipo 2\nVersões com vigência.\n",
                                                   encoding="utf-8")
        (docs / "diagrama.md").write_text("# Diagrama\n" + "+----+----+\n|    |    |\n" * 20, encoding="utf-8")
        (docs / "adr" / "0014-janela.md").write_text(
            "# ADR 0014: Janela de maturação de 8 anos\n- **Status:** Aceita\n- **Data:** 2026-09-28\n",
            encoding="utf-8")
        (self.raiz / "README.md").write_text("# Projeto\nObservatório de retenção.\n", encoding="utf-8")
        self.docs = documentos_da_documentacao(docs, self.raiz / "README.md")
        self.por_arquivo = {d.metadados["arquivo"]: d for d in self.docs}

    def test_subpastas_e_readme_entram(self):
        self.assertIn("docs/adr/0028-scd.md", self.por_arquivo)
        self.assertIn("README.md", self.por_arquivo)

    def test_chave_da_raiz_de_docs_continua_o_nome_do_arquivo(self):
        """Mesma chave de antes das subpastas: o que não mudou não é vetorizado de novo."""
        self.assertTrue(self.por_arquivo["docs/guia.md"].chave.startswith("guia.md#"))
        self.assertTrue(self.por_arquivo["docs/adr/0028-scd.md"].chave.startswith("adr/0028-scd.md#"))

    def test_titulo_leva_o_caminho_e_a_secao(self):
        self.assertEqual(self.por_arquivo["docs/adr/0028-scd.md"].titulo, "adr/0028-scd.md › ADR 0028: SCD tipo 2")

    def test_desenho_em_ascii_fica_de_fora(self):
        self.assertNotIn("docs/diagrama.md", self.por_arquivo)

    def test_secao_de_corpo_curto_entra_pelo_titulo(self):
        """A abertura de um ADR é o título e a data: poucas letras no corpo, mas o título conta."""
        self.assertIn("docs/adr/0014-janela.md", self.por_arquivo)


class TestConsultaPorTexto(unittest.TestCase):

    def test_metade_dos_termos_arredondada_para_cima(self):
        self.assertEqual(consulta_de_cobertura(["a", "b", "c"]),
                         "('a' & 'b') | ('a' & 'c') | ('b' & 'c')")
        self.assertEqual(consulta_de_cobertura(["a", "b"]), "('a') | ('b')")

    def test_cobertura_zero_e_qualquer_termo(self):
        self.assertEqual(consulta_de_cobertura(["b", "a"], 0), "('a') | ('b')")

    def test_sem_termos_nao_casa_com_nada(self):
        self.assertIsNone(consulta_de_cobertura([]))

    def test_apostrofo_no_termo_e_escapado(self):
        self.assertEqual(consulta_de_cobertura(["d'agua"]), "('d''agua')")

    def test_termos_demais_sao_limitados(self):
        consulta = consulta_de_cobertura([f"t{i:02d}" for i in range(20)])
        self.assertNotIn("t19", consulta)

    def test_sem_acento(self):
        self.assertEqual(sem_acento("Evasão em Ciência da Computação"), "Evasao em Ciencia da Computacao")

    def test_expandir_consulta_siglas_unb(self):
        expandida, expansoes = expandir_consulta("cursos na FGA com alto IRC")
        self.assertIn("gama", expandida)
        self.assertIn("fcte", expandida)
        self.assertIn("retencao", expandida)
        self.assertEqual([orig for orig, _ in expansoes], ["FGA", "IRC"])

    def test_expandir_consulta_sem_sigla_nao_altera(self):
        expandida, expansoes = expandir_consulta("medicina veterinaria")
        self.assertEqual(expandida, "medicina veterinaria")
        self.assertEqual(expansoes, [])

    def test_normalizar_campus_unifica_gold_e_pibic(self):
        self.assertEqual(
            normalizar_campus("FACULDADE DE CIENCIAS E TECNOLOGIAS EM ENGENHARIA (FCTE)"),
            "GAMA (FGA/FCTE)",
        )
        self.assertEqual(normalizar_campus("FGA - GAMA"), "GAMA (FGA/FCTE)")
        self.assertEqual(
            normalizar_campus("FACULDADE DE CIENCIAS E TECNOLOGIAS EM SAUDE (FCTS)"),
            "CEILÂNDIA (FCE/FCTS)",
        )
        self.assertEqual(normalizar_campus("FCE - CEILANDIA"), "CEILÂNDIA (FCE/FCTS)")
        self.assertEqual(normalizar_campus("FUP - PLANALTINA"), "PLANALTINA (FUP)")
        self.assertEqual(normalizar_campus("DARCY RIBEIRO"), "DARCY RIBEIRO")

    def test_montar_filtros_sql_facetados(self):
        clausula, params = _montar_filtros_sql(
            tipo=None,
            tipos=("curso", "projeto_pibic"),
            filtros={"campus": "FGA - GAMA", "turno": "NOTURNO", "evasao_min": 50, "ano_min": 2021},
        )
        sql_txt = clausula.as_string(None)
        self.assertIn("tipo = ANY", sql_txt)
        self.assertIn("campus_norm", sql_txt)
        self.assertIn("turno", sql_txt)
        self.assertIn("taxa_evasao_pct", sql_txt)
        self.assertEqual(params["tipos"], ["curso", "projeto_pibic"])
        self.assertEqual(params["campus_norm"], "GAMA (FGA/FCTE)")
        self.assertEqual(params["evasao_min"], 50.0)
        self.assertEqual(params["ano_min"], 2021)

    def test_limpar_markdown_remove_urls_e_separadores_tabela(self):
        bruto = "Veja [ADR 0011](docs/adr/0011.md).\n| a | b |\n|---|---|\n| 1 | 2 |"
        limpo = _limpar_markdown(bruto)
        self.assertIn("Veja ADR 0011.", limpo)
        self.assertNotIn("docs/adr/0011.md", limpo)
        self.assertNotIn("|---|---|", limpo)


if __name__ == "__main__":
    unittest.main()
