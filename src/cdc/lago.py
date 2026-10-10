"""
Destino da captura de mudanças: tabelas Delta Lake (Parquet + log de transações) em data/lake/cdc/.

Recebe os eventos do Debezium (envelope JSON com before, after, op e source) e os aplica por
MERGE na chave primária da tabela de origem. A aplicação é idempotente: cada linha guarda a
posição no WAL da última mudança aplicada (_commit_lsn, _lsn), e um evento só altera a linha
se for mais novo que ela. Reprocessar o tópico do início, ou receber de novo um lote cujo
offset não chegou a ser confirmado no Kafka, não muda nada.

Exclusões viram marca (_deletado = true), e não DELETE: sem a marca, um INSERT antigo
reprocessado depois do DELETE ressuscitaria a linha. TRUNCATE (a recarga da Silver 3NF faz
um) marca todas as linhas anteriores a ele.

Sem Kafka nem PostgreSQL aqui: o consumidor (src/cdc/consumidor.py) entrega os eventos já
decodificados, e os testes (tests/test_unit_cdc.py) usam eventos sintéticos.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pyarrow as pa
import pyarrow.compute as pc
from deltalake import DeltaTable, write_deltalake

from src.db.exportar_lago import (
    COLUNA_QUINQUENIO,
    PROPRIEDADES,
    RETENCAO_HORAS,
    TIPOS_ARROW,
    quinquenio,
)

LAKE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "lake" / "cdc"

COLUNAS_CONTROLE = [
    pa.field("_deletado", pa.bool_()),
    pa.field("_commit_lsn", pa.int64()),
    pa.field("_lsn", pa.int64()),
    pa.field("_origem_em", pa.timestamp("us", tz="UTC")),
    pa.field("_gravado_em", pa.timestamp("us", tz="UTC")),
]

# Um evento só altera a linha do lago se vier depois, no WAL, da última mudança aplicada nela.
MAIS_NOVO = "(s._commit_lsn > t._commit_lsn OR (s._commit_lsn = t._commit_lsn AND s._lsn > t._lsn))"


@dataclass(frozen=True)
class Tabela:
    """Tabela de origem: nome no PostgreSQL, colunas (nome, tipo) e chave primária."""

    nome: str
    colunas: Tuple[Tuple[str, str], ...]
    chave: Tuple[str, ...]
    particionada: bool = False

    def esquema(self) -> pa.Schema:
        campos = [pa.field(nome, TIPOS_ARROW[tipo]) for nome, tipo in self.colunas]
        if self.particionada:
            campos.append(pa.field(COLUNA_QUINQUENIO, pa.int16()))
        return pa.schema(campos + COLUNAS_CONTROLE)

    def caminho(self, lake_dir: Path = LAKE_DIR) -> Path:
        esquema, nome = self.nome.split(".")
        return lake_dir / esquema / nome


@dataclass(frozen=True)
class Evento:
    """Mudança decodificada de uma mensagem do Debezium."""

    op: str  # c (insert), u (update), d (delete), r (leitura do snapshot), t (truncate)
    linha: Optional[Dict]  # after; no delete, before (só a chave, com REPLICA IDENTITY DEFAULT)
    commit_lsn: int
    lsn: int
    origem_em: datetime

    @property
    def posicao(self) -> Tuple[int, int]:
        return self.commit_lsn, self.lsn


def decodificar(valor: Dict) -> Evento:
    """Evento a partir do valor JSON do Debezium (JsonConverter sem schema).

    source.sequence é '["<lsn do commit da transação anterior>", "<lsn do evento>"]': o primeiro
    cresce de uma transação para a seguinte, na ordem de commit. Ele vem nulo no snapshot e na
    primeira transação depois de um slot novo; aí vale o lsn do próprio evento. O lsn do snapshot
    é o ponto consistente do slot, posterior a todo commit anterior a ele: um snapshot refeito
    (tópicos recriados) passa por cima do que o lago tinha, e não fica para trás.

    Limite: uma transação aberta antes do ponto do snapshot e confirmada depois pode ter lsn
    menor que o dele e perder para o valor do snapshot. O caso só existe durante o snapshot.
    """
    source = valor["source"]
    ultimo_commit, lsn = json.loads(source.get("sequence") or "[null, null]")
    lsn = int(lsn or source.get("lsn") or 0)
    op = valor["op"]
    return Evento(
        op=op,
        linha=valor.get("before") if op == "d" else valor.get("after"),
        commit_lsn=int(ultimo_commit) if ultimo_commit else lsn,
        lsn=lsn,
        origem_em=datetime.fromtimestamp(source["ts_ms"] / 1000, tz=timezone.utc),
    )


def _criar_se_nao_existe(tabela: Tabela, lake_dir: Path) -> DeltaTable:
    destino = tabela.caminho(lake_dir)
    if not DeltaTable.is_deltatable(str(destino)):
        destino.mkdir(parents=True, exist_ok=True)
        write_deltalake(
            str(destino),
            tabela.esquema().empty_table(),
            partition_by=[COLUNA_QUINQUENIO] if tabela.particionada else None,
            writer_properties=PROPRIEDADES,
        )
    return DeltaTable(str(destino))


def _linhas_do_lote(tabela: Tabela, eventos: List[Evento]) -> pa.Table:
    """Uma linha por chave, a da mudança mais nova do lote (o MERGE recusa chave repetida)."""
    ultima: Dict[Tuple, Evento] = {}
    for e in eventos:
        chave = tuple(e.linha[c] for c in tabela.chave)
        if chave not in ultima or e.posicao > ultima[chave].posicao:
            ultima[chave] = e
    agora = datetime.now(timezone.utc)
    registros = []
    for e in ultima.values():
        registro = {nome: e.linha.get(nome) for nome, _ in tabela.colunas}
        if tabela.particionada:
            registro[COLUNA_QUINQUENIO] = quinquenio(registro["ano_ingresso"])
        registro.update(
            _deletado=e.op == "d", _commit_lsn=e.commit_lsn, _lsn=e.lsn,
            _origem_em=e.origem_em, _gravado_em=agora,
        )
        registros.append(registro)
    return pa.Table.from_pylist(registros, schema=tabela.esquema())


def _merge(delta: DeltaTable, tabela: Tabela, eventos: List[Evento]) -> int:
    origem = _linhas_do_lote(tabela, eventos)
    casamento = " AND ".join(f"t.{c} = s.{c}" for c in tabela.chave)
    if tabela.particionada:
        # A partição é derivada da chave: entra no casamento para o MERGE só ler as partições do lote.
        casamento += f" AND t.{COLUNA_QUINQUENIO} = s.{COLUNA_QUINQUENIO}"
    marca = {c: f"s.{c}" for c in ("_deletado", "_commit_lsn", "_lsn", "_origem_em", "_gravado_em")}
    (
        delta.merge(origem, predicate=casamento, source_alias="s", target_alias="t",
                    writer_properties=PROPRIEDADES)
        # Exclusão só marca a linha: o resto das colunas fica com o último valor conhecido.
        .when_matched_update(updates=marca, predicate=f"s._deletado AND {MAIS_NOVO}")
        .when_matched_update_all(predicate=f"NOT s._deletado AND {MAIS_NOVO}")
        .when_not_matched_insert_all()
        .execute()
    )
    return len(origem)


def _truncar(delta: DeltaTable, evento: Evento) -> None:
    """Marca como excluída toda linha cuja última mudança veio antes do TRUNCATE."""
    c, l = evento.posicao
    delta.update(
        predicate=f"_commit_lsn < {c} OR (_commit_lsn = {c} AND _lsn < {l})",
        updates={
            "_deletado": "true",
            "_commit_lsn": str(c),
            "_lsn": str(l),
            "_origem_em": f"'{evento.origem_em.isoformat()}'",
            "_gravado_em": f"'{datetime.now(timezone.utc).isoformat()}'",
        },
        writer_properties=PROPRIEDADES,
    )


def aplicar(tabela: Tabela, eventos: Iterable[Evento], lake_dir: Path = LAKE_DIR) -> Dict[str, int]:
    """Aplica os eventos de uma tabela, na ordem do tópico, e devolve o que foi feito."""
    delta = _criar_se_nao_existe(tabela, lake_dir)
    resumo = {"linhas": 0, "truncates": 0}
    pendentes: List[Evento] = []
    for e in eventos:
        if e.op == "t":
            # O que veio antes do TRUNCATE entra antes dele; o que veio depois, depois.
            if pendentes:
                resumo["linhas"] += _merge(delta, tabela, pendentes)
                pendentes = []
            _truncar(delta, e)
            resumo["truncates"] += 1
        else:
            pendentes.append(e)
    if pendentes:
        resumo["linhas"] += _merge(delta, tabela, pendentes)
    return resumo


def manter(tabela: Tabela, lake_dir: Path = LAKE_DIR) -> Dict:
    """Junta os arquivos pequenos que cada MERGE deixa e apaga os substituídos há mais de 7 dias."""
    delta = DeltaTable(str(tabela.caminho(lake_dir)))
    metricas = delta.optimize.compact(writer_properties=PROPRIEDADES)
    delta.vacuum(retention_hours=RETENCAO_HORAS, dry_run=False)
    return metricas


def ler(tabela: Tabela, lake_dir: Path = LAKE_DIR, com_excluidas: bool = False) -> pa.Table:
    """Estado atual da tabela no lago, por padrão sem as linhas marcadas como excluídas."""
    dados = DeltaTable(str(tabela.caminho(lake_dir))).to_pyarrow_table()
    if com_excluidas:
        return dados
    return dados.filter(pc.invert(dados.column("_deletado")))
