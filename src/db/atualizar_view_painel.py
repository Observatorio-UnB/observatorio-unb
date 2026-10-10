"""
Atualiza a gold.mv_dashboard_executivo depois da carga, sem bloquear as leituras do painel.

Roda depois de src/db/povoar_dimensional.py e chama a procedure
gold.atualizar_mv_dashboard_executivo() (REFRESH MATERIALIZED VIEW CONCURRENTLY, migração 0018).
Se a carga da Silver falhou (silver.discentes_graduacao ou a Silver 3NF vazias), o refresh é
cancelado com erro e a view continua com a última versão boa.

Uso:
    python3 src/db/atualizar_view_painel.py
"""

import logging
import sys
from pathlib import Path

import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar  # noqa: E402
from src.db.povoar_silver_3nf import silver_carregada  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("atualizar_view_painel")


class SilverNaoCarregada(RuntimeError):
    pass


def atualizar_view_painel(conn: psycopg.Connection) -> int:
    """Confere a carga da Silver, dispara o refresh e devolve o número de linhas da view."""
    if not silver_carregada(conn):
        raise SilverNaoCarregada("silver.discentes_graduacao vazia: refresh da view cancelado.")
    if not conn.execute("SELECT EXISTS (SELECT 1 FROM silver.movimentacoes_vinculos)").fetchone()[0]:
        raise SilverNaoCarregada("Silver 3NF vazia (silver.movimentacoes_vinculos): refresh da view cancelado.")
    conn.execute("CALL gold.atualizar_mv_dashboard_executivo()")
    return conn.execute("SELECT count(*) FROM gold.mv_dashboard_executivo").fetchone()[0]


if __name__ == "__main__":
    with conectar(autocommit=True) as conn:
        linhas = atualizar_view_painel(conn)
    logger.info(f"gold.mv_dashboard_executivo: {linhas:,} linhas.")
