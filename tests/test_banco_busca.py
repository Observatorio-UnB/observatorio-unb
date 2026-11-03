"""
Qualidade da busca semântica (src/busca/buscar.py) sobre busca.documentos. Precisa de PostgreSQL com
a busca vetorizada (python3 src/busca/vetorizar.py) e do modelo de embedding.

Cada caso é uma consulta e o documento que precisa aparecer entre os 5 primeiros. O teste exige
recall@5 mínimo por tipo, e não acerto em todos: a nota mede a busca como um todo e acusa a
regressão quando o modelo, o texto dos documentos ou o ranking mudam.

Os casos de iniciação científica só rodam onde os planos foram vetorizados (o CI usa
VETORIZAR_TIPOS=curso,documentacao).

Uso:
    python3 -m unittest tests/test_banco_busca.py
"""

import sys
import unittest
from collections import defaultdict
from pathlib import Path
from typing import Callable, Dict, List, NamedTuple

import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar  # noqa: E402

K = 5
RECALL_MINIMO = 0.8


class Caso(NamedTuple):
    consulta: str
    tipo: str
    esperado: Callable[[Dict], bool]
    descricao: str


def curso(nome: str) -> Callable[[Dict], bool]:
    return lambda r: r["titulo"] == nome


def arquivo(*trechos: str) -> Callable[[Dict], bool]:
    """Documento de um dos arquivos de docs/ (caminho relativo, ex.: 'adr/0028')."""
    return lambda r: any(t in (r["metadados"] or {}).get("arquivo", "") for t in trechos)


def plano(inicio_do_titulo: str) -> Callable[[Dict], bool]:
    return lambda r: r["titulo"].lower().startswith(inicio_do_titulo.lower())


CASOS: List[Caso] = [
    Caso("curso de medicina", "curso", curso("MEDICINA"), "MEDICINA"),
    Caso("engenharia de software", "curso", curso("ENGENHARIA DE SOFTWARE"), "ENGENHARIA DE SOFTWARE"),
    Caso("faculdade de direito", "curso", curso("DIREITO"), "DIREITO"),
    Caso("ciência da computação", "curso", curso("CIENCIA DA COMPUTACAO"), "CIENCIA DA COMPUTACAO"),
    Caso("física computacional", "curso", curso("FISICA COMPUTACIONAL"), "FISICA COMPUTACIONAL"),
    Caso("curso de odontologia", "curso", curso("ODONTOLOGIA"), "ODONTOLOGIA"),

    Caso("risco de reidentificação dos alunos e k-anonimato", "documentacao",
         arquivo("registro_privacidade_lgpd", "0005-privacidade"), "registro de privacidade ou ADR 0005"),
    Caso("dimensão de variação lenta tipo 2 com vigência", "documentacao",
         arquivo("adr/0028"), "ADR 0028 (SCD)"),
    Caso("ADR 0028", "documentacao", arquivo("adr/0028"), "ADR 0028 pelo número"),
    Caso("por que as transformações da gold foram para o dbt", "documentacao",
         arquivo("adr/0029", "adr/0030"), "ADR 0029 ou 0030 (dbt)"),
    Caso("orquestração com Dagster, retry e backfill", "documentacao",
         arquivo("orquestracao.md", "adr/0030"), "orquestracao.md ou ADR 0030"),
    Caso("SLA de frescor da view do painel", "documentacao", arquivo("frescor_sla"), "frescor_sla.md"),
    Caso("janela de maturação de 8 anos das coortes", "documentacao",
         arquivo("adr/0014"), "ADR 0014 (janela de 8 anos)"),
    Caso("teste de distribuição que pega salto de série entre coortes", "documentacao",
         arquivo("testes_de_dados"), "testes_de_dados.md"),
    Caso("índice para acelerar a distribuição de semestres até a formatura", "documentacao",
         arquivo("03_ENGENHARIA_FISICA", "0024"), "documento 03 (EXPLAIN antes e depois)"),
    Caso("pergunta de gestão do decanato no challenge canvas", "documentacao",
         arquivo("challenge_canvas"), "challenge_canvas.md"),

    Caso("evasão fiscal com aprendizado profundo em notas fiscais", "projeto_pibic",
         plano("Mineracao de texto da nfc-e"), "mineração da NFC-e"),
    Caso("testes de software num projeto real", "projeto_pibic",
         plano("Engenharia de software aplicada"), "testes de software no projeto Mia Ajuda"),
    Caso("realidade virtual na marcha de idosos", "projeto_pibic",
         plano("Avaliacao da marcha de idosos"), "marcha de idosos com realidade virtual"),
    Caso("microalgas e espectroscopia raman", "projeto_pibic",
         plano("Caracterizacao de microalgas"), "microalgas e espectroscopia Raman"),
]


def avaliar(buscar, casos: List[Caso] = CASOS) -> Dict[str, List[tuple]]:
    """Posição (1 a K, ou None) do documento esperado em cada caso, agrupada por tipo."""
    resultado = defaultdict(list)
    for caso in casos:
        achados = buscar(caso.consulta, k=K, tipo=caso.tipo)
        posicao = next((i for i, r in enumerate(achados, start=1) if caso.esperado(r)), None)
        resultado[caso.tipo].append((caso, posicao))
    return resultado


class TestQualidadeDaBusca(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            with conectar(connect_timeout=3) as conn:
                cls.tipos = {t for (t,) in conn.execute("SELECT DISTINCT tipo FROM busca.documentos").fetchall()}
        except psycopg.OperationalError as erro:
            raise unittest.SkipTest(f"Banco indisponível ({erro}). Suba com: docker compose up -d db")
        if not cls.tipos:
            raise unittest.SkipTest("Sem documentos vetorizados. Rode: python3 src/busca/vetorizar.py")
        try:
            from src.busca.buscar import buscar
            buscar("teste", k=1)
        except Exception as erro:  # modelo não baixado, sem rede
            raise unittest.SkipTest(f"Busca indisponível: {erro}")
        cls.buscar = staticmethod(buscar)
        cls.resultado = avaliar(buscar, [c for c in CASOS if c.tipo in cls.tipos])

    def test_recall_por_tipo(self):
        for tipo, casos in self.resultado.items():
            with self.subTest(tipo=tipo):
                acertos = sum(1 for _, posicao in casos if posicao)
                faltaram = [c.descricao for c, posicao in casos if not posicao]
                self.assertGreaterEqual(acertos / len(casos), RECALL_MINIMO,
                                        f"{tipo}: {acertos}/{len(casos)} no top {K}; faltaram {faltaram}")

    def test_consulta_sem_sentido_nao_devolve_nada(self):
        self.assertEqual(self.buscar("xyzw qwerty zzkq", k=5), [])

    def test_resultados_em_ordem_de_relevancia(self):
        resultados = self.buscar("evasão nos cursos de engenharia", k=8)
        self.assertTrue(resultados)
        notas = [r["relevancia"] for r in resultados]
        self.assertEqual(notas, sorted(notas, reverse=True))


def main():
    """Relatório por caso: python3 tests/test_banco_busca.py --relatorio"""
    from src.busca.buscar import buscar
    resultado = avaliar(buscar)
    for tipo, casos in resultado.items():
        acertos = sum(1 for _, p in casos if p)
        print(f"\n{tipo}: recall@{K} = {acertos}/{len(casos)}")
        for caso, posicao in casos:
            print(f"  {'✔ ' + str(posicao) if posicao else '✘  '}  {caso.consulta!r} -> {caso.descricao}")


if __name__ == "__main__":
    if "--relatorio" in sys.argv:
        main()
    else:
        unittest.main()
