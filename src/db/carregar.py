"""
Carga das camadas bronze, silver e gold no PostgreSQL.

Os arquivos gerados pelo pipeline (data/bronze, data/silver, data/gold) entram
nas tabelas definidas em db/migrations/. A carga é idempotente: numa transação
só, as tabelas das camadas escolhidas são esvaziadas e recarregadas por COPY, e
quem lê o banco nunca vê uma camada pela metade.

O esquema é o contrato. Coluna no arquivo que não existe na tabela, ou coluna
obrigatória ausente no arquivo, interrompe a carga: a mudança precisa de uma
migração nova antes de chegar ao banco.

Uso:
    python3 src/db/carregar.py                   # bronze, silver e gold
    python3 src/db/carregar.py --camadas gold    # só a gold (ex.: banco remoto)
"""

import argparse
import json
import logging
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

import pandas as pd
import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar  # noqa: E402
from src.db.migrar import aplicar_migracoes  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("carregar")

BRONZE_DIR = BASE_DIR / "data" / "bronze"
SILVER_DIR = BASE_DIR / "data" / "silver"
GOLD_DIR = BASE_DIR / "data" / "gold"

CAMADAS = ("bronze", "silver", "gold")
TIPOS_INTEIROS = {"smallint", "integer", "bigint"}
LINHAS_POR_LOTE = 50_000


class ErroDeContrato(Exception):
    """O arquivo não bate com o esquema da tabela de destino."""


@dataclass
class Fonte:
    tabela: str
    ler: Callable[[], pd.DataFrame]
    arquivo: Path
    # Opcional: a etapa que gera o arquivo pode não ter rodado (ex.: PIBIC). Sem o
    # arquivo, a tabela fica vazia em vez de interromper a carga.
    opcional: bool = False


@dataclass
class Coluna:
    nome: str
    tipo: str
    nulavel: bool
    tem_default: bool
    identidade: bool


def _ler_bronze(arquivo: Path, **opcoes) -> Callable[[], pd.DataFrame]:
    # Bronze guarda o texto como veio: sem inferência de tipo e sem converter "NULL" em nulo.
    return lambda: pd.read_csv(arquivo, dtype=str, keep_default_na=False, on_bad_lines="skip", **opcoes)


def _ler_csv(arquivo: Path) -> Callable[[], pd.DataFrame]:
    return lambda: pd.read_csv(arquivo)


def _sem_nan(valor):
    """JSON do pipeline pode ter NaN, que o jsonb do PostgreSQL rejeita."""
    if isinstance(valor, float) and math.isnan(valor):
        return None
    if isinstance(valor, dict):
        return {k: _sem_nan(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_sem_nan(v) for v in valor]
    return valor


def _ler_regras() -> pd.DataFrame:
    with open(GOLD_DIR / "regras_harmonizacao_canonicas.json", encoding="utf-8") as f:
        return pd.DataFrame(json.load(f)["regras"])


def _ler_relatorios() -> pd.DataFrame:
    linhas = []
    for nome in ("metricas_gerais_unb", "pibic_metricas_gerais", "relatorio_casamento_joins"):
        caminho = GOLD_DIR / f"{nome}.json"
        if caminho.exists():
            with open(caminho, encoding="utf-8") as f:
                conteudo = _sem_nan(json.load(f))
            linhas.append({"nome": nome, "conteudo": json.dumps(conteudo, ensure_ascii=False, allow_nan=False)})
    return pd.DataFrame(linhas, columns=["nome", "conteudo"])


# Ordem importa dentro de cada camada: silver.cursos_graduacao antes de
# silver.estrutura_curricular, que tem chave estrangeira para ela.
FONTES: Dict[str, List[Fonte]] = {
    "bronze": [
        Fonte("bronze.sigra_discentes",
              _ler_bronze(BRONZE_DIR / "sigra_discentes.csv", sep=";", encoding="utf-8"),
              BRONZE_DIR / "sigra_discentes.csv"),
        Fonte("bronze.estrutura_curricular",
              _ler_bronze(BRONZE_DIR / "estrutura_curricular.csv", sep=";", encoding="latin-1"),
              BRONZE_DIR / "estrutura_curricular.csv"),
        Fonte("bronze.cursos_graduacao",
              _ler_bronze(BRONZE_DIR / "cursos_graduacao.csv", sep=",", encoding="utf-8"),
              BRONZE_DIR / "cursos_graduacao.csv"),
        Fonte("bronze.bolsistas_iniciacao_cientifica",
              _ler_bronze(BRONZE_DIR / "bolsistas_iniciacao_cientifica.csv", sep=",", encoding="latin-1"),
              BRONZE_DIR / "bolsistas_iniciacao_cientifica.csv", opcional=True),
    ],
    "silver": [
        Fonte("silver.cursos_graduacao", _ler_csv(SILVER_DIR / "cursos_graduacao_silver.csv"),
              SILVER_DIR / "cursos_graduacao_silver.csv"),
        Fonte("silver.estrutura_curricular", _ler_csv(SILVER_DIR / "estrutura_curricular_silver.csv"),
              SILVER_DIR / "estrutura_curricular_silver.csv"),
        Fonte("silver.sigra_graduacao", _ler_csv(SILVER_DIR / "sigra_graduacao_silver.csv"),
              SILVER_DIR / "sigra_graduacao_silver.csv"),
        Fonte("silver.pibic_bolsistas", _ler_csv(SILVER_DIR / "pibic_bolsistas_silver.csv"),
              SILVER_DIR / "pibic_bolsistas_silver.csv", opcional=True),
    ],
    "gold": [
        Fonte("gold.retencao_cursos_unb", _ler_csv(GOLD_DIR / "retencao_cursos_unb.csv"),
              GOLD_DIR / "retencao_cursos_unb.csv"),
        Fonte("gold.pibic_social_unb", _ler_csv(GOLD_DIR / "pibic_social_unb.csv"),
              GOLD_DIR / "pibic_social_unb.csv", opcional=True),
        Fonte("gold.regras_harmonizacao_canonicas", _ler_regras,
              GOLD_DIR / "regras_harmonizacao_canonicas.json"),
        Fonte("gold.relatorios", _ler_relatorios, GOLD_DIR / "metricas_gerais_unb.json"),
    ],
}


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
    """Confere o arquivo contra o esquema e ajusta os tipos para o COPY."""
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
        raise ErroDeContrato(f"{tabela}: colunas obrigatórias ausentes no arquivo: {obrigatorias}.")
    if ausentes:
        logger.warning(f"{tabela}: colunas ausentes no arquivo, carregadas como nulo: {[c.nome for c in ausentes]}")

    alvo = [c for c in carregaveis if c.nome in df.columns or not c.tem_default]
    saida = pd.DataFrame(index=df.index)
    for c in alvo:
        serie = df[c.nome] if c.nome in df.columns else pd.Series(None, index=df.index, dtype="object")
        if c.tipo in TIPOS_INTEIROS:
            # Int64 recusa 8.5 -> 8 silencioso; "8.0" vira 8, que o COPY aceita como inteiro.
            serie = pd.to_numeric(serie, errors="raise").astype("Int64")
        elif c.tipo == "boolean" and serie.dtype == bool:
            serie = serie.map({True: "t", False: "f"})
        saida[c.nome] = serie
    return saida


def copiar(conn: psycopg.Connection, tabela: str, df: pd.DataFrame) -> int:
    colunas = ", ".join(df.columns)
    with conn.cursor() as cur:
        with cur.copy(f"COPY {tabela} ({colunas}) FROM STDIN WITH (FORMAT csv)") as copy:
            for inicio in range(0, len(df), LINHAS_POR_LOTE):
                lote = df.iloc[inicio:inicio + LINHAS_POR_LOTE]
                copy.write(lote.to_csv(index=False, header=False))
        return cur.rowcount


def carregar(camadas: tuple = CAMADAS) -> Dict[str, int]:
    """Recarrega as camadas pedidas e devolve o número de linhas por tabela."""
    desconhecidas = set(camadas) - set(CAMADAS)
    if desconhecidas:
        raise ValueError(f"Camadas desconhecidas: {sorted(desconhecidas)}. Use {CAMADAS}.")

    aplicar_migracoes()
    fontes = [f for camada in CAMADAS if camada in camadas for f in FONTES[camada]]

    contagens = {}
    with conectar(autocommit=True) as conn:
        with conn.transaction():
            # Datas da fonte vêm como dd/mm/aaaa.
            conn.execute("SET LOCAL datestyle = 'ISO, DMY'")
            conn.execute(f"TRUNCATE {', '.join(f.tabela for f in fontes)} RESTART IDENTITY")
            for fonte in fontes:
                if not fonte.arquivo.exists():
                    if fonte.opcional:
                        logger.warning(f"{fonte.arquivo.name} não encontrado; {fonte.tabela} fica vazia.")
                        contagens[fonte.tabela] = 0
                        continue
                    raise FileNotFoundError(
                        f"{fonte.arquivo} não existe. Rode o pipeline antes da carga (scripts/rodar_pipeline.sh)."
                    )
                df = preparar(fonte.ler(), colunas_da_tabela(conn, fonte.tabela), fonte.tabela)
                contagens[fonte.tabela] = copiar(conn, fonte.tabela, df)
                logger.info(f"{fonte.tabela}: {contagens[fonte.tabela]:,} linhas.")
        for fonte in fontes:
            conn.execute(f"ANALYZE {fonte.tabela}")

    logger.info(f"=== Carga concluída: {len(contagens)} tabelas, camadas {', '.join(camadas)} ===")
    return contagens


def main(argv: Optional[List[str]] = None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--camadas",
        default=",".join(CAMADAS),
        help="Camadas a carregar, separadas por vírgula (padrão: bronze,silver,gold).",
    )
    args = parser.parse_args(argv)
    carregar(tuple(c.strip() for c in args.camadas.split(",") if c.strip()))


if __name__ == "__main__":
    main()
