"""
Testes unitários do destino da captura de mudanças (sem Kafka nem PostgreSQL).

Eventos sintéticos no formato do Debezium são aplicados num lago temporário: confere a
idempotência do MERGE pela posição no WAL, a marca de exclusão, o tratamento do TRUNCATE e a
reconciliação no fim do snapshot. O consumidor roda com um Consumer do Kafka simulado: confere
o offset confirmado só depois da gravação, o tópico ainda inexistente, o --do-inicio e a
guarda contra o WAL que volta para trás.

Uso:
    python3 -m unittest tests/test_unit_cdc.py
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from confluent_kafka import OFFSET_BEGINNING, KafkaError, TopicPartition

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.cdc import consumidor, lago  # noqa: E402

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


def _snapshot(linha, lsn, marca="true"):
    """Linha do snapshot: sequence sem commit, e source.snapshot marca a última da tabela."""
    return lago.decodificar({
        "op": "r", "after": linha, "before": None,
        "source": {"ts_ms": 0, "lsn": lsn, "sequence": f'[null,"{lsn}"]', "snapshot": marca},
    })


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

    def test_decodifica_sem_sequence(self):
        e = lago.decodificar({"op": "c", "after": _curso(1, "A"), "before": None,
                              "source": {"ts_ms": 0, "lsn": 700}})
        self.assertEqual(e.posicao, (700, 700))
        self.assertFalse(e.fim_snapshot)

    def test_snapshot_refeito_passa_por_cima_do_lago_antigo(self):
        lago.aplicar(CURSOS, [_evento("u", _curso(1, "ANTIGO"), 200, 201)], self.lake)
        # Tópicos recriados: snapshot novo (sequence sem commit) num ponto do WAL posterior.
        refeito = lago.decodificar({
            "op": "r", "after": _curso(1, "ATUAL"), "before": None,
            "source": {"ts_ms": 0, "lsn": 900, "sequence": "[null,\"900\"]"},
        })
        lago.aplicar(CURSOS, [refeito], self.lake)
        self.assertEqual(self._nomes(), {1: "ATUAL"})

    def test_fim_do_snapshot_marca_as_chaves_ausentes(self):
        lago.aplicar(CURSOS, [_evento("c", _curso(i, f"C{i}"), 100, 100 + i) for i in (1, 2, 3, 5)], self.lake)
        lago.aplicar(CURSOS, [_evento("d", {"id_curso": 5}, 200, 201)], self.lake)
        # Snapshot refeito depois de o curso 2 ser excluído com o fluxo interrompido.
        resumo = lago.aplicar(CURSOS, [
            _snapshot(_curso(1, "C1"), 900, "first_in_data_collection"),
            _snapshot(_curso(3, "C3"), 900, "last_in_data_collection"),
            _evento("c", _curso(4, "C4"), 950, 951),
        ], self.lake)
        self.assertEqual(resumo["reconciliadas"], 1)  # o curso 2; o 5 já estava marcado
        self.assertEqual(self._nomes(), {1: "C1", 3: "C3", 4: "C4"})
        # Reprocessar o snapshot não marca o que veio depois dele.
        lago.aplicar(CURSOS, [_snapshot(_curso(3, "C3"), 900, "last")], self.lake)
        self.assertEqual(self._nomes(), {1: "C1", 3: "C3", 4: "C4"})

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


class _Mensagem:
    def __init__(self, topico, valor=None, erro=None):
        self._topico, self._valor, self._erro = topico, valor, erro

    def topic(self):
        return self._topico

    def value(self):
        return None if self._valor is None else json.dumps(self._valor).encode()

    def error(self):
        return self._erro


class TestConsumidor(unittest.TestCase):
    """Consumidor com o Kafka e o catálogo do banco simulados."""

    TOPICO = "observatorio.silver.cursos"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.lake = Path(self._tmp.name)
        self.kafka = mock.MagicMock()
        for alvo, valor in (("carregar_tabelas", lambda: {self.TOPICO: CURSOS}),
                            ("Consumer", lambda config: self.kafka)):
            patch = mock.patch.object(consumidor, alvo, side_effect=valor)
            patch.start()
            self.addCleanup(patch.stop)

    def tearDown(self):
        self._tmp.cleanup()

    def _consumidor(self, **kwargs):
        return consumidor.Consumidor(lake_dir=self.lake, **kwargs)

    def _lote(self, *mensagens):
        self.kafka.consume.return_value = list(mensagens)

    def test_confirma_o_offset_so_depois_de_gravar(self):
        c = self._consumidor()
        ordem = []
        self.kafka.commit.side_effect = lambda **_: ordem.append("commit")
        aplicar = lago.aplicar

        def aplicar_e_registrar(*args, **kwargs):
            resumo = aplicar(*args, **kwargs)
            ordem.append("gravou")
            return resumo

        self._lote(_Mensagem(self.TOPICO, _mensagem("c", _curso(1, "A"), 100, 101)))
        with mock.patch.object(lago, "aplicar", side_effect=aplicar_e_registrar):
            self.assertEqual(c.rodada(), 1)
        self.assertEqual(ordem, ["gravou", "commit"])
        self.assertEqual(lago.ler(CURSOS, self.lake).column("nome_curso_norm").to_pylist(), ["A"])

    def test_falha_na_gravacao_nao_confirma_o_offset(self):
        c = self._consumidor()
        self._lote(_Mensagem(self.TOPICO, _mensagem("c", _curso(1, "A"), 100, 101)))
        with mock.patch.object(lago, "aplicar", side_effect=OSError("disco cheio")):
            with self.assertRaises(OSError):
                c.rodada()
        self.kafka.commit.assert_not_called()

    def test_topico_inexistente_e_ignorado(self):
        c = self._consumidor()
        self._lote(_Mensagem(self.TOPICO, erro=KafkaError(KafkaError.UNKNOWN_TOPIC_OR_PART)))
        self.assertEqual(c.rodada(), 0)
        self.kafka.commit.assert_not_called()

    def test_do_inicio_so_na_primeira_atribuicao(self):
        self._consumidor(do_inicio=True)
        ao_receber = self.kafka.subscribe.call_args.kwargs["on_assign"]
        primeira = [TopicPartition(self.TOPICO, 0, 42)]
        ao_receber(self.kafka, primeira)
        self.assertEqual(primeira[0].offset, OFFSET_BEGINNING)
        rebalance = [TopicPartition(self.TOPICO, 0, 42)]
        ao_receber(self.kafka, rebalance)
        self.assertEqual(rebalance[0].offset, 42)

    def _com_wal_do_banco(self, lsn):
        conn = mock.MagicMock()
        conn.__enter__.return_value.execute.return_value.fetchone.return_value = (lsn,)
        return mock.patch.object(consumidor, "conectar", return_value=conn)

    def test_aborta_quando_o_banco_esta_atras_do_lago(self):
        lago.aplicar(CURSOS, [_evento("c", _curso(1, "A"), 5_000, 5_001)], self.lake)
        c = self._consumidor()
        self.assertEqual(c.maior_lsn, 5_001)
        # Banco recriado: o WAL recomeçou abaixo do lago.
        self._lote(_Mensagem(self.TOPICO, _mensagem("c", _curso(1, "B"), 100, 101)))
        with self._com_wal_do_banco(200), self.assertRaises(consumidor.WalRegrediu):
            c.rodada()
        self.kafka.commit.assert_not_called()

    def test_reprocessamento_legitimo_passa_pela_guarda(self):
        lago.aplicar(CURSOS, [_evento("c", _curso(1, "A"), 100, 101), _evento("u", _curso(1, "B"), 200, 201)],
                     self.lake)
        c = self._consumidor()
        self._lote(_Mensagem(self.TOPICO, _mensagem("c", _curso(1, "A"), 100, 101)))
        with self._com_wal_do_banco(10_000):
            self.assertEqual(c.rodada(), 1)
        self.kafka.commit.assert_called_once()
        self.assertEqual(lago.ler(CURSOS, self.lake).column("nome_curso_norm").to_pylist(), ["B"])


if __name__ == "__main__":
    unittest.main()
