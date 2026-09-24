"""
Gera docs/dicionario_dados_banco.md a partir do catálogo do PostgreSQL.

As descrições vêm dos COMMENT ON das migrações, então o dicionário não
desatualiza em relação ao esquema: para mudar um texto, mude o comentário numa
migração nova e rode este script de novo.
"""

import logging
import sys
from pathlib import Path

import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("gerar_dicionario")

SAIDA = BASE_DIR / "docs" / "dicionario_dados_banco.md"
ESQUEMAS = ("bronze", "silver", "gold", "busca")
PAPEL_LEITURA = "observatorio_leitura"
TIPOS_RESTRICAO = {"p": "Chave primária", "f": "Chave estrangeira", "u": "Única", "c": "Verificação"}


def _celula(texto) -> str:
    return "" if texto is None else str(texto).replace("|", "\\|").replace("\n", " ")


def gerar_markdown(conn: psycopg.Connection) -> str:
    linhas = [
        "# Dicionário de Dados do Banco (PostgreSQL)",
        "",
        "> Gerado por `src/db/gerar_dicionario.py` a partir do catálogo do banco. **Não edite à mão**: "
        "as descrições são os `COMMENT ON` de `db/migrations/`.",
        "",
        "O banco guarda o medalhão inteiro, um esquema por camada. Bronze e silver têm registro "
        f"individual de discente; o papel `{PAPEL_LEITURA}` (privilégio mínimo) só lê gold e busca.",
        "",
        "| Esquema | Descrição | Leitura por `" + PAPEL_LEITURA + "` |",
        "| :--- | :--- | :--- |",
    ]
    papel_existe = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (PAPEL_LEITURA,)).fetchone()
    for esquema in ESQUEMAS:
        descricao = conn.execute(
            "SELECT obj_description(oid, 'pg_namespace') FROM pg_namespace WHERE nspname = %s", (esquema,)
        ).fetchone()[0]
        pode_ler = papel_existe and conn.execute(
            "SELECT has_schema_privilege(%s, %s, 'USAGE')", (PAPEL_LEITURA, esquema)
        ).fetchone()[0]
        linhas.append(f"| `{esquema}` | {_celula(descricao)} | {'sim' if pode_ler else 'não'} |")

    for esquema in ESQUEMAS:
        linhas += ["", f"## Esquema `{esquema}`"]
        tabelas = conn.execute(
            """
            SELECT c.oid, c.relname, obj_description(c.oid, 'pg_class')
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = %s AND c.relkind = 'r'
            ORDER BY c.relname
            """,
            (esquema,),
        ).fetchall()
        for oid, tabela, descricao in tabelas:
            total = conn.execute(f'SELECT count(*) FROM "{esquema}"."{tabela}"').fetchone()[0]
            linhas += [
                "",
                f"### `{esquema}.{tabela}`",
                "",
                _celula(descricao) or "_Sem descrição._",
                "",
                f"**Linhas na última carga:** {total:,}".replace(",", "."),
                "",
                "| Coluna | Tipo | Nulo | Descrição |",
                "| :--- | :--- | :---: | :--- |",
            ]
            colunas = conn.execute(
                """
                SELECT a.attname, format_type(a.atttypid, a.atttypmod), NOT a.attnotnull,
                       col_description(a.attrelid, a.attnum), a.attidentity <> ''
                FROM pg_attribute a
                WHERE a.attrelid = %s AND a.attnum > 0 AND NOT a.attisdropped
                ORDER BY a.attnum
                """,
                (oid,),
            ).fetchall()
            for nome, tipo, nulavel, comentario, identidade in colunas:
                if identidade:
                    tipo = f"{tipo} (identity)"
                linhas.append(f"| `{nome}` | `{tipo}` | {'sim' if nulavel else 'não'} | {_celula(comentario)} |")

            restricoes = conn.execute(
                """
                SELECT contype, pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conrelid = %s AND contype IN ('p', 'f', 'u', 'c')
                ORDER BY array_position(ARRAY['p', 'u', 'f', 'c']::"char"[], contype), conname
                """,
                (oid,),
            ).fetchall()
            if restricoes:
                linhas += ["", "**Restrições:**", ""]
                linhas += [f"- {TIPOS_RESTRICAO[tipo]}: `{definicao}`" for tipo, definicao in restricoes]
    return "\n".join(linhas) + "\n"


def gerar_dicionario() -> Path:
    with conectar() as conn:
        SAIDA.write_text(gerar_markdown(conn), encoding="utf-8")
    logger.info(f"Dicionário do banco salvo em {SAIDA.relative_to(BASE_DIR)}")
    return SAIDA


if __name__ == "__main__":
    gerar_dicionario()
