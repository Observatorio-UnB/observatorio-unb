"""
Leitura e gravação das camadas do medalhão no PostgreSQL.

Cada etapa do pipeline lê a camada anterior e grava a sua direto no banco, sem
arquivo intermediário:

    ingestão (src/ingestion)              -> bronze.*
    src/pipeline/transform_silver.py      bronze.* -> silver.*
    src/pipeline/build_gold.py            silver.* -> gold.*

O esquema é o contrato. `gravar` recusa DataFrame com coluna que a tabela não tem,
ou sem coluna obrigatória: a mudança precisa de uma migração nova em db/migrations/.
"""

import json
import logging
import math
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import psycopg
from psycopg import sql
from psycopg.types.numeric import FloatLoader

from src.db.conexao import conectar

logger = logging.getLogger("tabelas")

TIPOS_INTEIROS = {"smallint", "integer", "bigint"}
LINHAS_POR_LOTE = 50_000

# Colunas preenchidas pelo banco ou pela gravação, e não pelo pipeline.
COLUNAS_DE_CONTROLE = {"_ordem", "_carregado_em"}

# Textos que o pandas.read_csv trata como nulo por padrão. A bronze guarda o texto
# como veio da fonte (inclusive o literal "NULL"); ler_bronze devolve os mesmos nulos
# que o read_csv(dtype=str) devolvia quando a bronze era arquivo.
NULOS_DO_READ_CSV = {
    "", "#N/A", "#N/A N/A", "#NA", "-1.#IND", "-1.#QNAN", "-NaN", "-nan", "1.#IND", "1.#QNAN",
    "<NA>", "N/A", "NA", "NULL", "NaN", "None", "n/a", "nan", "null",
}


class ErroDeContrato(Exception):
    """O DataFrame não bate com o esquema da tabela de destino."""


@dataclass
class Coluna:
    nome: str
    tipo: str
    nulavel: bool
    tem_default: bool
    identidade: bool


def colunas_da_tabela(conn: psycopg.Connection, tabela: str) -> List[Coluna]:
    esquema, nome = tabela.split(".")
    linhas = conn.execute(
        """
        SELECT column_name, data_type, is_nullable = 'YES', column_default IS NOT NULL, is_identity = 'YES'
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
        """,
        (esquema, nome),
    ).fetchall()
    if not linhas:
        raise ErroDeContrato(f"Tabela {tabela} não existe. Rode as migrações (src/db/migrar.py).")
    return [Coluna(*linha) for linha in linhas]


def preparar(df: pd.DataFrame, colunas: List[Coluna], tabela: str) -> pd.DataFrame:
    """Confere o DataFrame contra o esquema e ajusta os tipos para o COPY."""
    carregaveis = [c for c in colunas if not c.identidade]
    nomes = {c.nome for c in colunas}

    extras = sorted(set(df.columns) - nomes)
    if extras:
        raise ErroDeContrato(
            f"{tabela}: colunas fora do esquema: {extras}. "
            "Crie uma migração em db/migrations/ que as acrescente."
        )

    ausentes = [c for c in carregaveis if c.nome not in df.columns and not c.tem_default]
    obrigatorias = [c.nome for c in ausentes if not c.nulavel]
    if obrigatorias:
        raise ErroDeContrato(f"{tabela}: colunas obrigatórias ausentes: {obrigatorias}.")
    if ausentes:
        logger.warning(f"{tabela}: colunas ausentes, gravadas como nulo: {[c.nome for c in ausentes]}")

    alvo = [c for c in carregaveis if c.nome in df.columns or not c.tem_default]
    saida = pd.DataFrame(index=df.index)
    for c in alvo:
        serie = df[c.nome] if c.nome in df.columns else pd.Series(None, index=df.index, dtype="object")
        if c.tipo in TIPOS_INTEIROS:
            # Int64 recusa 8.5 -> 8 silencioso; 8.0 vira 8, que o COPY aceita como inteiro.
            serie = pd.to_numeric(serie, errors="raise").astype("Int64")
        elif c.tipo == "boolean" and serie.dtype == bool:
            serie = serie.map({True: "t", False: "f"})
        saida[c.nome] = serie
    return saida


def copiar(conn: psycopg.Connection, tabela: str, df: pd.DataFrame) -> int:
    esquema, nome = tabela.split(".")
    comando = sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT csv)").format(
        sql.Identifier(esquema, nome), sql.SQL(", ").join(map(sql.Identifier, df.columns))
    )
    with conn.cursor() as cur:
        with cur.copy(comando) as copy:
            for inicio in range(0, len(df), LINHAS_POR_LOTE):
                lote = df.iloc[inicio:inicio + LINHAS_POR_LOTE]
                copy.write(lote.to_csv(index=False, header=False))
        return cur.rowcount


def gravar_varias(tabelas: Dict[str, pd.DataFrame]) -> Dict[str, int]:
    """Substitui o conteúdo das tabelas numa transação só (TRUNCATE + COPY).

    Quem lê o banco nunca vê a camada pela metade, e regravar dá o mesmo resultado.
    A ordem do dicionário é a ordem da carga: tabela referenciada por chave
    estrangeira vem antes de quem a referencia. DataFrame sem colunas (etapa opcional
    que não rodou, ex.: PIBIC sem dado na bronze) só esvazia a tabela.
    """
    contagens = {}
    with conectar(autocommit=True) as conn:
        with conn.transaction():
            # Datas das fontes chegam como dd/mm/aaaa.
            conn.execute("SET LOCAL datestyle = 'ISO, DMY'")
            conn.execute(f"TRUNCATE {', '.join(tabelas)} RESTART IDENTITY")
            for tabela, df in tabelas.items():
                if len(df.columns) == 0:
                    contagens[tabela] = 0
                    continue
                colunas = colunas_da_tabela(conn, tabela)
                df = df.reset_index(drop=True)
                if "_ordem" in {c.nome for c in colunas} and "_ordem" not in df.columns:
                    df = df.assign(_ordem=np.arange(1, len(df) + 1))
                contagens[tabela] = copiar(conn, tabela, preparar(df, colunas, tabela))
        for tabela in tabelas:
            conn.execute(f"ANALYZE {tabela}")
    for tabela, total in contagens.items():
        logger.info(f"{tabela}: {total:,} linhas gravadas.")
    return contagens


def gravar(df: pd.DataFrame, tabela: str) -> int:
    """Substitui o conteúdo de uma tabela pelo DataFrame."""
    return gravar_varias({tabela: df})[tabela]


def _conectar_leitura() -> psycopg.Connection:
    conn = conectar()
    # NUMERIC chega como float, e não Decimal: o pipeline faz conta com pandas e numpy.
    conn.adapters.register_loader("numeric", FloatLoader)
    return conn


def consultar(consulta: str, params=None) -> pd.DataFrame:
    """Resultado de uma consulta SQL como DataFrame."""
    with _conectar_leitura() as conn:
        cur = conn.execute(consulta, params)
        return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])


def ler(tabela: str, colunas_de_controle: bool = False) -> pd.DataFrame:
    """Lê uma tabela inteira, na ordem em que foi gravada."""
    with _conectar_leitura() as conn:
        colunas = colunas_da_tabela(conn, tabela)
        nomes = [c.nome for c in colunas]
        ordem = next((c for c in ("_ordem", "id") if c in nomes), None)
        esquema, nome = tabela.split(".")
        consulta = sql.SQL("SELECT * FROM {}").format(sql.Identifier(esquema, nome))
        if ordem:
            consulta += sql.SQL(" ORDER BY {}").format(sql.Identifier(ordem))
        cur = conn.execute(consulta)
        df = pd.DataFrame(cur.fetchall(), columns=nomes)
    if not colunas_de_controle:
        df = df.drop(columns=[c.nome for c in colunas if c.nome in COLUNAS_DE_CONTROLE or c.identidade])
    return df


def ler_bronze(tabela: str) -> pd.DataFrame:
    """Lê uma tabela bronze como texto, com os nulos que o read_csv(dtype=str) produziria."""
    df = ler(tabela)
    return df.mask(df.isin(NULOS_DO_READ_CSV)).astype("str")


def tem_linhas(tabela: str) -> bool:
    with conectar() as conn:
        esquema, nome = tabela.split(".")
        consulta = sql.SQL("SELECT EXISTS (SELECT 1 FROM {})").format(sql.Identifier(esquema, nome))
        return conn.execute(consulta).fetchone()[0]


def _sem_nan(valor):
    """JSON do pipeline pode ter NaN, que o jsonb do PostgreSQL rejeita."""
    if isinstance(valor, float) and math.isnan(valor):
        return None
    if isinstance(valor, dict):
        return {k: _sem_nan(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_sem_nan(v) for v in valor]
    if isinstance(valor, np.generic):
        return _sem_nan(valor.item())
    return valor


def gravar_relatorio(nome: str, conteudo: Dict) -> None:
    """Grava (ou substitui) um relatório JSON em gold.relatorios."""
    texto = json.dumps(_sem_nan(conteudo), ensure_ascii=False, allow_nan=False)
    with conectar() as conn:
        conn.execute(
            """
            INSERT INTO gold.relatorios (nome, conteudo) VALUES (%s, %s)
            ON CONFLICT (nome) DO UPDATE SET conteudo = EXCLUDED.conteudo, _carregado_em = now()
            """,
            (nome, texto),
        )
    logger.info(f"gold.relatorios: relatório '{nome}' gravado.")


def ler_relatorio(nome: str) -> Optional[Dict]:
    with conectar() as conn:
        linha = conn.execute("SELECT conteudo FROM gold.relatorios WHERE nome = %s", (nome,)).fetchone()
    return linha[0] if linha else None
