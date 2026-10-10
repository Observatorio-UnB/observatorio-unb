"""
Consome os tópicos do Debezium e aplica as mudanças da Silver 3NF no lago CDC (src/cdc/lago.py).

Fluxo: PostgreSQL (WAL, publicação observatorio_cdc) -> Debezium -> Kafka (um tópico por
tabela) -> este consumidor -> Delta Lake em data/lake/cdc/.

Semântica de entrega: o offset só é confirmado no Kafka depois que o lote foi gravado no lago.
Se o consumidor cair entre a gravação e a confirmação, o lote volta: entrega no mínimo uma vez.
Como o MERGE do lago é idempotente pela posição no WAL, o lote repetido não muda nada, e o
efeito no lago é o de uma entrega só.

Colunas e chave primária de cada tabela vêm do catálogo do PostgreSQL, como no lago em lote.

Uso:
    python3 src/cdc/consumidor.py                    # consome continuamente (Ctrl+C para parar)
    python3 src/cdc/consumidor.py --ate-esvaziar     # para depois de 5 s sem mensagem nova
    python3 src/cdc/consumidor.py --do-inicio --ate-esvaziar   # reprocessa os tópicos inteiros
"""

import argparse
import json
import logging
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from confluent_kafka import OFFSET_BEGINNING, Consumer, KafkaError, KafkaException

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.cdc import lago  # noqa: E402
from src.db.conexao import conectar, ler_variavel  # noqa: E402
from src.db.tabelas import colunas_da_tabela  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("consumidor_cdc")

PREFIXO_TOPICOS = "observatorio"
GRUPO = "observatorio-lago"
MENSAGENS_POR_LOTE = 5_000
# Cada MERGE grava arquivos novos: a cada tantos lotes, a manutenção junta os pequenos.
MANTER_A_CADA_LOTES = 50

# Tabela de origem -> particionada no lago (mesmo critério do lago em lote).
TABELAS_CDC = {
    "silver.cursos": False,
    "silver.estruturas_curriculares": False,
    "silver.movimentacoes_vinculos": True,
}


def bootstrap_servers() -> str:
    return ler_variavel("KAFKA_BOOTSTRAP_SERVERS") or "localhost:9092"


def carregar_tabelas() -> Dict[str, lago.Tabela]:
    """Tabelas do lago CDC por tópico, com colunas e chave primária lidas do banco."""
    tabelas = {}
    with conectar() as conn:
        for nome, particionada in TABELAS_CDC.items():
            colunas = tuple((c.nome, c.tipo) for c in colunas_da_tabela(conn, nome))
            chave = tuple(r[0] for r in conn.execute(
                """
                SELECT a.attname
                FROM pg_index i
                JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY (i.indkey)
                WHERE i.indrelid = %s::regclass AND i.indisprimary
                ORDER BY array_position(i.indkey::int2[], a.attnum)
                """,
                (nome,),
            ).fetchall())
            tabelas[f"{PREFIXO_TOPICOS}.{nome}"] = lago.Tabela(nome, colunas, chave, particionada)
    return tabelas


class Consumidor:
    """Lê lotes dos tópicos, aplica no lago e só então confirma os offsets."""

    def __init__(self, lake_dir: Path = lago.LAKE_DIR, grupo: str = GRUPO, do_inicio: bool = False):
        self.lake_dir = lake_dir
        self.tabelas = carregar_tabelas()
        self.lotes = 0
        self.consumer = Consumer({
            "bootstrap.servers": bootstrap_servers(),
            "group.id": grupo,
            "enable.auto.commit": False,
            "auto.offset.reset": "earliest",
        })

        def ao_receber_particoes(consumer, particoes):
            if do_inicio:
                for p in particoes:
                    p.offset = OFFSET_BEGINNING
            consumer.assign(particoes)

        self.consumer.subscribe(list(self.tabelas), on_assign=ao_receber_particoes)

    def rodada(self, timeout: float = 1.0) -> int:
        """Processa um lote e devolve o número de mensagens lidas (0 se nada chegou)."""
        mensagens = self.consumer.consume(MENSAGENS_POR_LOTE, timeout=timeout)
        eventos = defaultdict(list)
        for m in mensagens:
            if m.error():
                # Tópico ainda não criado: o conector não publicou nada daquela tabela.
                if m.error().code() in (KafkaError._PARTITION_EOF, KafkaError.UNKNOWN_TOPIC_OR_PART):
                    continue
                raise KafkaException(m.error())
            if m.value() is None:
                continue
            eventos[m.topic()].append(lago.decodificar(json.loads(m.value())))
        if not eventos:
            return 0

        agora = datetime.now(timezone.utc)
        for topico, lista in eventos.items():
            tabela = self.tabelas[topico]
            resumo = lago.aplicar(tabela, lista, self.lake_dir)
            atraso = max((agora - e.origem_em).total_seconds() for e in lista)
            truncates = f", {resumo['truncates']} truncate(s)" if resumo["truncates"] else ""
            logger.info(
                f"{tabela.nome}: {len(lista):,} eventos -> {resumo['linhas']:,} linhas{truncates}"
                f" (maior atraso desde o commit na origem: {atraso:.1f} s)"
            )
        # Depois de gravar: se cair antes daqui, o lote volta e o MERGE o absorve.
        self.consumer.commit(asynchronous=False)
        self.lotes += 1
        if self.lotes % MANTER_A_CADA_LOTES == 0:
            self.manter()
        return len(mensagens)

    def manter(self) -> None:
        for tabela in self.tabelas.values():
            if lago.DeltaTable.is_deltatable(str(tabela.caminho(self.lake_dir))):
                lago.manter(tabela, self.lake_dir)

    def esvaziar(self, ociosidade_s: float = 5.0) -> int:
        """Consome até passar `ociosidade_s` sem mensagem nova; devolve o total de mensagens."""
        total, ocioso_desde = 0, time.monotonic()
        while time.monotonic() - ocioso_desde < ociosidade_s:
            lidas = self.rodada()
            if lidas:
                total += lidas
                ocioso_desde = time.monotonic()
        return total

    def fechar(self) -> None:
        self.consumer.close()


def consumir(ate_esvaziar: bool = False, do_inicio: bool = False, grupo: Optional[str] = None) -> None:
    consumidor = Consumidor(grupo=grupo or GRUPO, do_inicio=do_inicio)
    logger.info(f"Consumindo {', '.join(consumidor.tabelas)} de {bootstrap_servers()}...")
    try:
        if ate_esvaziar:
            total = consumidor.esvaziar()
            consumidor.manter()
            logger.info(f"{total:,} mensagens aplicadas; nada novo nos tópicos.")
        else:
            while True:
                consumidor.rodada()
    except KeyboardInterrupt:
        pass
    finally:
        consumidor.fechar()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ate-esvaziar", action="store_true", help="Para quando os tópicos ficam sem mensagem nova.")
    parser.add_argument("--do-inicio", action="store_true", help="Relê os tópicos desde o primeiro offset.")
    parser.add_argument("--grupo", help=f"Grupo de consumidores no Kafka (padrão: {GRUPO}).")
    args = parser.parse_args()
    consumir(ate_esvaziar=args.ate_esvaziar, do_inicio=args.do_inicio, grupo=args.grupo)
