"""
Conexão com o PostgreSQL da plataforma.

A URL vem de DATABASE_URL (variável de ambiente ou arquivo .env na raiz do
repositório). Sem ela, usa o banco do docker-compose.yml na porta 5435.
SUPABASE_DATABASE_URL, lida do mesmo jeito, é o destino da sincronização da gold
(src/db/sincronizar_supabase.py).
"""

import os
from pathlib import Path
from typing import Optional

import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent.parent
URL_PADRAO = "postgresql://observatorio:observatorio@localhost:5435/observatorio"


def ler_variavel(nome: str) -> Optional[str]:
    """Valor de `nome` no ambiente ou, se ausente, no .env da raiz."""
    if os.environ.get(nome):
        return os.environ[nome]
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        for linha in env_file.read_text(encoding="utf-8").splitlines():
            chave, sep, valor = linha.partition("=")
            if sep and chave.strip() == nome and valor.strip():
                return valor.strip().strip('"').strip("'")
    return None


def database_url() -> str:
    """Resolve a URL do banco: ambiente, depois .env, depois o padrão do docker-compose."""
    return ler_variavel("DATABASE_URL") or URL_PADRAO


def conectar(url: Optional[str] = None, **kwargs) -> psycopg.Connection:
    """Abre uma conexão nova com o banco da plataforma, ou com `url` se informada."""
    # Sem banco no ar, o painel cai no export estático em segundos, e não trava esperando.
    kwargs.setdefault("connect_timeout", 5)
    return psycopg.connect(url or database_url(), **kwargs)
