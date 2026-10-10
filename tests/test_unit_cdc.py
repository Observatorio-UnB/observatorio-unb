"""
Testes unitários do destino da captura de mudanças (sem Kafka nem PostgreSQL).

Eventos sintéticos no formato do Debezium são aplicados num lago temporário: confere a
idempotência do MERGE pela posição no WAL, a marca de exclusão e o tratamento do TRUNCATE.

Uso:
    python3 -m unittest tests/test_unit_cdc.py
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.cdc import lago  # noqa: E402

CURSOS = lago.Tabela(
    "silver.cursos",
    colunas=(("id_curso", "integer"), ("nome_curso_norm", "text"), ("ativo", "boolean")),
    chave=("id_curso",),
)
VINCULOS = lago.Tabela(
    "silver.movimentacoes_vinculos",
    colunas=(("id_vinculo", "bigint"), ("ano_ingresso", "smallint"), ("tipo_saida_grupo", "text")),
    chave=("id_vinculo", "ano_ingresso"),
    particionada=True,
)


def _mensagem(op, linha, commit, lsn):
    """Valor JSON como o Debezium publica (JsonConverter sem schema)."""
    return {
        "before": linha if op == "d" else None,
        "after": None if op in ("d", "t") else linha,
        "op": op,
        "source": {"ts_ms": 1_760_000_000_000, "lsn": lsn, "sequence": json.dumps([str(commit), str(lsn)])},
    }


def _evento(op, linha, commit, lsn):
    return lago.decodificar(_mensagem(op, linha, commit, lsn))


def _curso(id_curso, nome, ativo=True):
    return {"id_curso": id_curso, "nome_curso_norm": nome, "ativo": ativo}


class TestCdc(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.lake = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _estado(self, tabela=CURSOS, com_excluidas=False):
        dados = lago.ler(tabela, self.lake, com_excluidas=com_excluidas).to_pylist()
        return sorted(dados, key=lambda r: tuple(r[c] for c in tabela.chave))

    def _nomes(self):
        return {r["id_curso"]: r["nome_curso_norm"] for r in self._estado()}

    def test_decodifica_sequencia_do_debezium(self):
        e = _evento("u", _curso(1, "A"), 900, 950)
        self.assertEqual((e.op, e.commit_lsn, e.lsn), ("u", 900, 950))
        snapshot = lago.decodificar({
            "op": "r", "after": _curso(1, "A"), "before": None,
            "source": {"ts_ms": 0, "lsn": 500, "sequence": "[null,\"500\"]"},
        })
        self.assertEqual(snapshot.posicao, (500, 500))

    def test_snapshot_refeito_passa_por_cima_do_lago_antigo(self):
        lago.aplicar(CURSOS, [_evento("u", _curso(1, "ANTIGO"), 200, 201)], self.lake)
        # Tópicos recriados: snapshot novo (sequence sem commit) num ponto do WAL posterior.
        refeito = lago.decodificar({
            "op": "r", "after": _curso(1, "ATUAL"), "before": None,
            "source": {"ts_ms": 0, "lsn": 900, "sequence": "[null,\"900\"]"},
        })
        lago.aplicar(CURSOS, [refeito], self.lake)
        self.assertEqual(self._nomes(), {1: "ATUAL"})

    def test_insert_update_delete(self):
        lago.aplicar(CURSOS, [_evento("c", _curso(1, "ADMINISTRACAO"), 100, 101)], self.lake)
        lago.aplicar(CURSOS, [_evento("u", _curso(1, "ADMINISTRACAO PUBLICA"), 200, 201)], self.lake)
        self.assertEqual(self._nomes(), {1: "ADMINISTRACAO PUBLICA"})

        lago.aplicar(CURSOS, [_evento("d", {"id_curso": 1}, 300, 301)], self.lake)
        self.assertEqual(self._nomes(), {})
        excluida = self._estado(com_excluidas=True)[0]
        self.assertTrue(excluida["_deletado"])
        self.assertEqual(excluida["nome_curso_norm"], "ADMINISTRACAO PUBLICA")

    def test_reprocessar_o_topico_nao_muda_nada(self):
        topico = [
            _evento("r", _curso(1, "A"), 0, 50),
            _evento("r", _curso(2, "B"), 0, 50),
            _evento("c", _curso(3, "C"), 100, 101),
            _evento("u", _curso(1, "A2"), 200, 201),
            _evento("d", {"id_curso": 2}, 300, 301),
        ]
        lago.aplicar(CURSOS, topico, self.lake)
        antes = self._estado(com_excluidas=True)
        # Do início, e de novo só a metade final (lote cujo offset não foi confirmado).
        lago.aplicar(CURSOS, topico, self.lake)
        lago.aplicar(CURSOS, topico[3:], self.lake)
        depois = self._estado(com_excluidas=True)
        sem_gravado_em = lambda linhas: [{k: v for k, v in r.items() if k != "_gravado_em"} for r in linhas]
        self.assertEqual(sem_gravado_em(depois), sem_gravado_em(antes))
        self.assertEqual(self._nomes(), {1: "A2", 3: "C"})

    def test_evento_antigo_nao_sobrescreve_o_novo(self):
        lago.aplicar(CURSOS, [_evento("u", _curso(1, "NOVO"), 200, 201)], self.lake)
        lago.aplicar(CURSOS, [_evento("c", _curso(1, "VELHO"), 100, 101)], self.lake)
        self.assertEqual(self._nomes(), {1: "NOVO"})

    def test_insert_antigo_nao_ressuscita_linha_excluida(self):
        lago.aplicar(CURSOS, [_evento("c", _curso(1, "A"), 100, 101), _evento("d", {"id_curso": 1}, 200, 201)],
                     self.lake)
        lago.aplicar(CURSOS, [_evento("c", _curso(1, "A"), 100, 101)], self.lake)
        self.assertEqual(self._nomes(), {})

    def test_varias_mudancas_da_mesma_chave_no_lote(self):
        lago.aplicar(CURSOS, [
            _evento("c", _curso(1, "A"), 100, 101),
            _evento("u", _curso(1, "B"), 100, 102),
            _evento("u", _curso(1, "C"), 100, 103),
        ], self.lake)
        self.assertEqual(self._nomes(), {1: "C"})

    def test_truncate_seguido_de_recarga_na_mesma_transacao(self):
        lago.aplicar(CURSOS, [_evento("c", _curso(i, f"C{i}"), 100, 100 + i) for i in (1, 2, 3)], self.lake)
        # Recarga da Silver 3NF: TRUNCATE e INSERTs no mesmo commit, só os cursos 1 e 4 voltam.
        recarga = [
            _evento("t", None, 500, 501),
            _evento("c", _curso(1, "C1"), 500, 502),
            _evento("c", _curso(4, "C4"), 500, 503),
        ]
        lago.aplicar(CURSOS, recarga, self.lake)
        self.assertEqual(self._nomes(), {1: "C1", 4: "C4"})
        # Reprocessar a recarga não marca como excluídas as linhas inseridas depois do TRUNCATE.
        lago.aplicar(CURSOS, recarga, self.lake)
        self.assertEqual(self._nomes(), {1: "C1", 4: "C4"})

    def test_tabela_particionada_por_quinquenio(self):
        lago.aplicar(VINCULOS, [
            _evento("c", {"id_vinculo": 1, "ano_ingresso": 2012, "tipo_saida_grupo": "ATIVO"}, 100, 101),
            _evento("c", {"id_vinculo": 2, "ano_ingresso": 2021, "tipo_saida_grupo": "ATIVO"}, 100, 102),
            _evento("u", {"id_vinculo": 1, "ano_ingresso": 2012, "tipo_saida_grupo": "FORMATURA"}, 200, 201),
        ], self.lake)
        linhas = self._estado(VINCULOS)
        self.assertEqual([(r["id_vinculo"], r["quinquenio_ingresso"], r["tipo_saida_grupo"]) for r in linhas],
                         [(1, 2010, "FORMATURA"), (2, 2020, "ATIVO")])

    def test_manutencao_junta_arquivos_pequenos(self):
        for i in range(1, 6):
            lago.aplicar(CURSOS, [_evento("c", _curso(i, f"C{i}"), 100 * i, 100 * i + 1)], self.lake)
        delta = lago.DeltaTable(str(CURSOS.caminho(self.lake)))
        self.assertGreater(len(delta.file_uris()), 1)
        lago.manter(CURSOS, self.lake)
        delta = lago.DeltaTable(str(CURSOS.caminho(self.lake)))
        self.assertEqual(len(delta.file_uris()), 1)
        self.assertEqual(len(self._nomes()), 5)


if __name__ == "__main__":
    unittest.main()
