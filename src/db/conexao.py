"""
Conexão com o PostgreSQL da plataforma.

A URL vem de DATABASE_URL (variável de ambiente ou arquivo .env na raiz do
repositório). Sem ela, usa o banco do docker-compose.yml na porta 5435.
"""

import os
from pathlib import Path

import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent.parent
URL_PADRAO = "postgresql://observatorio:observatorio@localhost:5435/observatorio"


def database_url() -> str:
    """Resolve a URL do banco: ambiente, depois .env, depois o padrão do docker-compose."""
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        for linha in env_file.read_text(encoding="utf-8").splitlines():
            chave, sep, valor = linha.partition("=")
            if sep and chave.strip() == "DATABASE_URL" and valor.strip():
                return valor.strip().strip('"').strip("'")
    return URL_PADRAO


def conectar(**kwargs) -> psycopg.Connection:
    """Abre uma conexão nova com o banco da plataforma."""
    # Sem banco no ar, o painel cai no export estático em segundos, e não trava esperando.
    kwargs.setdefault("connect_timeout", 5)
    return psycopg.connect(database_url(), **kwargs)
