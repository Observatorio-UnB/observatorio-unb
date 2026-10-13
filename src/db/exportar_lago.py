"""
Exporta a Silver 3NF e a gold dimensional do banco para tabelas Delta Lake em data/lake/lote/.

É a camada analítica em formato aberto: cada tabela é uma pasta de arquivos Parquet mais o log
de transações do Delta (_delta_log/), que qualquer leitor de Delta ou de Parquet abre sem o
PostgreSQL (DuckDB, Spark, Polars, pandas). A escolha do Delta e da compressão está no ADR 0024.

- Idempotente: cada exportação substitui o conteúdo da tabela (mode="overwrite") numa versão
  nova do log. Rodar duas vezes dá as mesmas linhas e o mesmo número de arquivos ativos.
- Reprocessamento de janela: com --quinquenio, só as partições pedidas de
  silver.movimentacoes_vinculos são regravadas (overwrite com predicado); as demais ficam
  intactas. Um quinquênio que ficou sem linhas no banco fica sem linhas no lago.
- Particionamento: só a tabela de vínculos, por quinquênio de ingresso, como as partições do
  PostgreSQL (migração 0019). As demais têm poucas centenas de linhas e ficam num arquivo só.
- Arquivos antigos (versões substituídas) saem pelo VACUUM depois de RETENCAO_HORAS, o que
  deixa a viagem no tempo dos últimos 7 dias para comparar uma reexecução com a anterior.

silver.discentes não entra: guarda data de nascimento, sexo e raça/cor por pessoa. Os vínculos
levam só o id sintético do discente. data/ não é versionado.

Uso:
    python3 src/db/exportar_lago.py                                  # todas as tabelas
    python3 src/db/exportar_lago.py --quinquenio 2020 --quinquenio 2025   # só essas janelas
"""

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pyarrow as pa
from deltalake import DeltaTable, WriterProperties, write_deltalake
from psycopg import sql

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.tabelas import _conectar_leitura, colunas_da_tabela  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("exportar_lago")

LAGO_DIR = BASE_DIR / "data" / "lake" / "lote"
RETENCAO_HORAS = 7 * 24
COLUNA_QUINQUENIO = "quinquenio_ingresso"

# Leitura do lago é varredura analítica (DuckDB lendo colunas inteiras), escrita uma vez por mês.
# ZSTD 3 comprime mais que o Snappy padrão com descompressão na mesma ordem de velocidade (ADR 0024).
PROPRIEDADES = WriterProperties(compression="ZSTD", compression_level=3)

TIPOS_ARROW = {
    "smallint": pa.int16(),
    "integer": pa.int32(),
    "bigint": pa.int64(),
    "numeric": pa.float64(),
    "double precision": pa.float64(),
    "real": pa.float32(),
    "boolean": pa.bool_(),
    "text": pa.string(),
    "character": pa.string(),
    "character varying": pa.string(),
    "date": pa.date32(),
    "timestamp with time zone": pa.timestamp("us", tz="UTC"),
    "timestamp without time zone": pa.timestamp("us"),
}


@dataclass(frozen=True)
class TabelaLago:
    origem: str
    particionada: bool = False

    @property
    def caminho(self) -> Path:
        esquema, nome = self.origem.split(".")
        return Path(esquema) / nome


TABELAS = (
    TabelaLago("silver.cursos"),
    TabelaLago("silver.estruturas_curriculares"),
    TabelaLago("silver.movimentacoes_vinculos", particionada=True),
    TabelaLago("gold.dim_curso"),
    TabelaLago("gold.dim_campus"),
    TabelaLago("gold.dim_tempo"),
    TabelaLago("gold.dim_perfil_social"),
    TabelaLago("gold.fato_retencao_curso"),
    TabelaLago("gold.fato_alunos_ativos"),
    TabelaLago("gold.fato_pibic_perfil"),
)


def quinquenio(ano: int) -> int:
    """Primeiro ano do quinquênio: 2023 -> 2020."""
    return ano - ano % 5


def montar_tabela_arrow(colunas: List[tuple], linhas: List[tuple], particionada: bool) -> pa.Table:
    """Monta a tabela Arrow com tipos fixos, para o esquema do Delta não variar entre execuções.

    `colunas` é uma lista de (nome, tipo do PostgreSQL). Inferir o tipo pelo dado faria uma
    coluna toda nula numa execução virar outro tipo, e o overwrite seguinte seria recusado.
    """
    nomes = [nome for nome, _ in colunas]
    campos = [pa.field(nome, TIPOS_ARROW[tipo]) for nome, tipo in colunas]
    valores = list(zip(*linhas)) if linhas else [[] for _ in nomes]
    arrays = [pa.array(list(v), type=campo.type) for v, campo in zip(valores, campos)]
    tabela = pa.Table.from_arrays(arrays, schema=pa.schema(campos))
    if particionada:
        anos = tabela.column("ano_ingresso").to_pylist()
        tabela = tabela.append_column(
            pa.field(COLUNA_QUINQUENIO, pa.int16(), nullable=False),
            pa.array([quinquenio(a) for a in anos], type=pa.int16()),
        )
    return tabela


def ler_do_banco(tabela: str, quinquenios: Optional[Iterable[int]] = None) -> tuple:
    """Colunas (nome, tipo) e linhas da tabela, opcionalmente só dos quinquênios pedidos."""
    with _conectar_leitura() as conn:
        colunas = [(c.nome, c.tipo) for c in colunas_da_tabela(conn, tabela)]
        esquema, nome = tabela.split(".")
        consulta = sql.SQL("SELECT {} FROM {}").format(
            sql.SQL(", ").join(sql.Identifier(n) for n, _ in colunas), sql.Identifier(esquema, nome)
        )
        params = None
        if quinquenios is not None:
            consulta += sql.SQL(" WHERE ano_ingresso - ano_ingresso %% 5 = ANY(%s)")
            params = (list(quinquenios),)
        linhas = conn.execute(consulta, params).fetchall()
    return colunas, linhas


def gravar_no_lago(
    tabela: pa.Table,
    destino: Path,
    particionada: bool = False,
    quinquenios: Optional[Iterable[int]] = None,
) -> DeltaTable:
    """Substitui o conteúdo da tabela Delta (ou só das partições em `quinquenios`)."""
    predicado = None
    if quinquenios is not None:
        if not particionada:
            raise ValueError(f"{destino}: reprocessamento por quinquênio só vale para tabela particionada.")
        predicado = f"{COLUNA_QUINQUENIO} IN ({', '.join(str(int(q)) for q in sorted(set(quinquenios)))})"
    destino.mkdir(parents=True, exist_ok=True)
    write_deltalake(
        str(destino),
        tabela,
        mode="overwrite",
        partition_by=[COLUNA_QUINQUENIO] if particionada else None,
        predicate=predicado,
        writer_properties=PROPRIEDADES,
    )
    delta = DeltaTable(str(destino))
    delta.vacuum(retention_hours=RETENCAO_HORAS, dry_run=False)
    return delta


def exportar(
    lago_dir: Path = LAGO_DIR,
    tabelas: Iterable[TabelaLago] = TABELAS,
    quinquenios: Optional[List[int]] = None,
) -> Dict[str, int]:
    """Exporta as tabelas do banco para o lago e devolve as linhas gravadas por tabela."""
    if quinquenios is not None:
        tabelas = [t for t in tabelas if t.particionada]
    contagens = {}
    for t in tabelas:
        colunas, linhas = ler_do_banco(t.origem, quinquenios)
        delta = gravar_no_lago(
            montar_tabela_arrow(colunas, linhas, t.particionada),
            lago_dir / t.caminho,
            particionada=t.particionada,
            quinquenios=quinquenios,
        )
        contagens[t.origem] = len(linhas)
        logger.info(
            f"{t.origem}: {len(linhas):,} linhas -> {t.caminho} "
            f"(versão {delta.version()}, {len(delta.file_uris())} arquivo(s) ativos)"
        )
    return contagens


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--quinquenio", type=int, action="append",
        help="Regrava só esse quinquênio de ingresso dos vínculos (ex.: 2020). Pode repetir.",
    )
    args = parser.parse_args()
    exportar(quinquenios=[quinquenio(q) for q in args.quinquenio] if args.quinquenio else None)
