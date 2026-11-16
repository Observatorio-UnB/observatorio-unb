"""
Conexão com o PostgreSQL da plataforma.

A URL vem de DATABASE_URL (variável de ambiente ou arquivo .env na raiz do
repositório). Sem ela, usa o banco do docker-compose.yml na porta 5435.
SUPABASE_DATABASE_URL, lida do mesmo jeito, é o destino da sincronização da gold
(src/db/sincronizar_supabase.py).

Leituras curtas e repetidas (painel, busca semântica, consultar/ler de src/db/tabelas.py) usam
`conexao_do_pool()`: um pool por URL, criado na primeira leitura e fechado na saída do processo.
O tamanho e os tempos vêm das variáveis POOL_* (ver ConfigPool). Scripts que gravam ou fazem
DDL continuam com `conectar()`, uma conexão própria.
"""

import atexit
import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, Optional
from urllib.parse import parse_qs, unquote, urlsplit

import psycopg
from psycopg_pool import ConnectionPool, PoolTimeout

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


def variaveis_dbt(url: Optional[str] = None) -> Dict[str, str]:
    """As variáveis que transform/profiles.yml lê, a partir da URL do banco (padrão: DATABASE_URL)."""
    u = urlsplit(url or database_url())
    return {
        "DBT_HOST": u.hostname or "localhost",
        "DBT_PORT": str(u.port or 5432),
        "DBT_USER": unquote(u.username or ""),
        "DBT_PASSWORD": unquote(u.password or ""),
        "DBT_DBNAME": u.path.lstrip("/"),
        "DBT_SSLMODE": parse_qs(u.query).get("sslmode", ["prefer"])[0],
    }


def conectar(url: Optional[str] = None, **kwargs) -> psycopg.Connection:
    """Abre uma conexão nova com o banco da plataforma, ou com `url` se informada."""
    # Sem banco no ar, o painel cai no export estático em segundos, e não trava esperando.
    kwargs.setdefault("connect_timeout", 5)
    return psycopg.connect(url or database_url(), **kwargs)


@dataclass(frozen=True)
class ConfigPool:
    """Limites do pool. O plano gratuito do Supabase aceita poucas dezenas de clientes no pooler;
    o máximo padrão deixa folga para o pipeline e o keep-alive."""
    minimo: int = 1               # conexões mantidas abertas mesmo ociosas
    maximo: int = 10              # teto de conexões simultâneas com o banco
    espera: float = 10.0          # segundos esperando uma conexão livre antes de PoolTimeout
    ociosa: float = 300.0         # conexão ociosa além do mínimo é fechada depois disso
    vida_maxima: float = 1800.0   # toda conexão é renovada depois disso (failover, rotação de senha)

    @classmethod
    def do_ambiente(cls) -> "ConfigPool":
        padrao = cls()
        return cls(
            minimo=int(ler_variavel("POOL_MINIMO") or padrao.minimo),
            maximo=int(ler_variavel("POOL_MAXIMO") or padrao.maximo),
            espera=float(ler_variavel("POOL_ESPERA_S") or padrao.espera),
            ociosa=float(ler_variavel("POOL_OCIOSA_S") or padrao.ociosa),
            vida_maxima=float(ler_variavel("POOL_VIDA_MAXIMA_S") or padrao.vida_maxima),
        )


NOME_DO_POOL = "observatorio_pool"
_pools: Dict[str, ConnectionPool] = {}
_trava_pools = threading.Lock()


def pool(url: Optional[str] = None, config: Optional[ConfigPool] = None) -> ConnectionPool:
    """O pool de `url` (padrão: database_url()), criado na primeira chamada e reaproveitado depois.

    Seguro entre threads: o Streamlit atende cada sessão numa thread, e duas sessões que chegam
    juntas recebem o mesmo pool."""
    url = url or database_url()
    with _trava_pools:
        if url not in _pools:
            config = config or ConfigPool.do_ambiente()
            # Sem banco no ar, falha já, como uma conexão avulsa: o pool tentaria de novo em segundo
            # plano e cada leitura esperaria `espera` segundos, e o painel demoraria a cair no
            # export estático.
            conectar(url).close()
            _pools[url] = ConnectionPool(
                url,
                min_size=config.minimo,
                max_size=config.maximo,
                timeout=config.espera,
                max_idle=config.ociosa,
                max_lifetime=config.vida_maxima,
                # Conexão que o banco derrubou (reinício, failover) é descartada na retirada, e não
                # entregue quebrada.
                check=ConnectionPool.check_connection,
                # prepare_threshold=None: o pooler transacional do Supabase (porta 6543) não aceita
                # prepared statements entre transações.
                # application_name identifica as conexões do pool em pg_stat_activity.
                kwargs={"connect_timeout": 5, "prepare_threshold": None, "application_name": NOME_DO_POOL},
                name=f"observatorio-{len(_pools) + 1}",
                open=False,
            )
            _pools[url].open(wait=False)
        return _pools[url]


def _descartar_pool_se_o_banco_caiu(url: str) -> None:
    """Depois de um PoolTimeout: se o banco não aceita conexão, descarta o pool, e a próxima leitura
    falha já na conexão de teste de pool(). Se aceita, o pool só estava cheio, e fica."""
    try:
        conectar(url).close()
        return
    except psycopg.OperationalError:
        pass
    with _trava_pools:
        p = _pools.pop(url, None)
    if p is not None:
        p.close(timeout=1)


@contextmanager
def conexao_do_pool(url: Optional[str] = None) -> Iterator[psycopg.Connection]:
    """Empresta uma conexão do pool. Na saída, a transação é confirmada (ou desfeita, se houve
    erro) e a conexão volta ao pool. Sem conexão livre em `espera` segundos, levanta PoolTimeout."""
    url = url or database_url()
    try:
        with pool(url).connection() as conn:
            yield conn
    except PoolTimeout:
        _descartar_pool_se_o_banco_caiu(url)
        raise


def fechar_pools() -> None:
    """Fecha todos os pools, esperando as conexões emprestadas voltarem (até 5 s)."""
    with _trava_pools:
        for p in _pools.values():
            p.close(timeout=5)
        _pools.clear()


atexit.register(fechar_pools)
