"""
Aplica as migrações SQL de db/migrations/ em ordem, uma única vez cada.

Cada arquivo roda numa transação própria e fica registrado em
public.schema_migrations com o checksum. Editar uma migração já aplicada é erro:
a mudança de esquema entra como uma migração nova, com número maior.
"""

import hashlib
import logging
import sys
from pathlib import Path
from typing import List

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("migrar")

MIGRATIONS_DIR = BASE_DIR / "db" / "migrations"

# Chave arbitrária do advisory lock: impede duas execuções simultâneas (ex.: CI e
# docker compose apontando para o mesmo banco) de aplicarem a mesma migração.
ADVISORY_LOCK_ID = 70402026


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def aplicar_migracoes() -> List[str]:
    """Aplica as migrações pendentes e devolve os nomes das que foram aplicadas agora."""
    # autocommit: cada `conn.transaction()` abaixo é uma transação de verdade, e não um
    # savepoint dentro da transação implícita aberta pelo primeiro comando.
    conn = conectar(autocommit=True)
    aplicadas_agora = []
    try:
        conn.execute("SELECT pg_advisory_lock(%s)", (ADVISORY_LOCK_ID,))
        with conn.transaction():
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS public.schema_migrations (
                  versao      TEXT PRIMARY KEY,
                  checksum    TEXT NOT NULL,
                  aplicada_em TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        ja_aplicadas = dict(conn.execute("SELECT versao, checksum FROM public.schema_migrations").fetchall())

        for arquivo in sorted(MIGRATIONS_DIR.glob("*.sql")):
            checksum = _checksum(arquivo)
            if arquivo.name in ja_aplicadas:
                if ja_aplicadas[arquivo.name] != checksum:
                    raise RuntimeError(
                        f"A migração {arquivo.name} foi alterada depois de aplicada. "
                        "Reverta a edição e crie uma migração nova em db/migrations/."
                    )
                continue
            logger.info(f"Aplicando {arquivo.name}...")
            with conn.transaction():
                conn.execute(arquivo.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT INTO public.schema_migrations (versao, checksum) VALUES (%s, %s)",
                    (arquivo.name, checksum),
                )
            aplicadas_agora.append(arquivo.name)
    finally:
        conn.execute("SELECT pg_advisory_unlock(%s)", (ADVISORY_LOCK_ID,))
        conn.close()

    if aplicadas_agora:
        logger.info(f"{len(aplicadas_agora)} migração(ões) aplicada(s).")
    else:
        logger.info("Esquema já está na versão mais recente.")
    return aplicadas_agora


if __name__ == "__main__":
    aplicar_migracoes()
