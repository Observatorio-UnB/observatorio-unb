"""
Ferramentas que o LLM do chat pode chamar. Todas leem o banco com o usuário observatorio_chat
(migração 0027): o que protege bronze e silver é o papel do banco; a validação do SQL aqui é só a
segunda camada.
"""

import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar, ler_variavel  # noqa: E402

ESQUEMAS = ("gold", "dbt_marts", "busca")
LIMITE_LINHAS = 200
URL_PADRAO_CHAT = "postgresql://observatorio_chat:observatorio_chat@localhost:5435/observatorio"
# Esquemas com dado pessoal ou fora do papel de leitura: recusados antes de ir ao banco.
PROIBIDOS = re.compile(
    r"\b(bronze|silver|dbt_staging|dbt_intermediate|dbt_snapshots|pg_catalog|information_schema)\b", re.I
)


class SqlRecusado(ValueError):
    pass


def url_chat() -> str:
    return ler_variavel("CHAT_DATABASE_URL") or URL_PADRAO_CHAT


def validar_sql(sql: str) -> str:
    """Devolve o SQL sem `;` final, ou levanta SqlRecusado: só um SELECT/WITH, sem camadas pessoais."""
    s = sql.strip().rstrip(";").strip()
    # ponytail: heurística de texto (';' dentro de literal também é recusado); o papel do banco é a defesa real.
    if ";" in s:
        raise SqlRecusado("Só um comando por consulta.")
    if not re.match(r"(?is)^(select|with)\b", s):
        raise SqlRecusado("Só SELECT ou WITH.")
    if PROIBIDOS.search(s):
        raise SqlRecusado("Só gold, dbt_marts e busca podem ser consultados.")
    return s


def _json(v):
    return v if v is None or isinstance(v, (int, float, str, bool)) else str(v)


def consultar_sql(sql: str, url: Optional[str] = None) -> Dict[str, Any]:
    """Executa um SELECT somente leitura e devolve colunas e até LIMITE_LINHAS linhas."""
    s = validar_sql(sql)
    with conectar(url or url_chat(), options="-c default_transaction_read_only=on") as conn:
        with conn.cursor() as cur:
            cur.execute(s)
            colunas = [d.name for d in cur.description]
            linhas = cur.fetchmany(LIMITE_LINHAS + 1)
    return {
        "colunas": colunas,
        "linhas": [[_json(v) for v in linha] for linha in linhas[:LIMITE_LINHAS]],
        "truncado": len(linhas) > LIMITE_LINHAS,
    }


def descrever_esquema(url: Optional[str] = None) -> str:
    """Tabelas e colunas de gold, dbt_marts e busca, com os COMMENT ON do catálogo."""
    q = """
    SELECT n.nspname, c.relname, obj_description(c.oid, 'pg_class'),
           a.attname, format_type(a.atttypid, a.atttypmod), col_description(c.oid, a.attnum)
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
    WHERE n.nspname = ANY(%s) AND c.relkind IN ('r','v','m','p') AND has_table_privilege(c.oid, 'SELECT')
      AND format_type(a.atttypid, a.atttypmod) NOT LIKE 'vector%%'
    ORDER BY 1, 2, a.attnum"""
    # Valores das colunas de texto com poucas categorias (pg_stats): sem eles o modelo escreve
    # `= 'CRÍTICA'` quando o dado é 'RETENÇÃO CRÍTICA', ou `campus = 'FCTE'`, e conclui que não há dado.
    q_valores = """
    SELECT schemaname, tablename, attname,
           array_to_string(most_common_vals::text::text[], ' | ')
    FROM pg_stats
    WHERE schemaname = ANY(%s) AND n_distinct BETWEEN 1 AND 12 AND most_common_vals IS NOT NULL"""
    with conectar(url or url_chat()) as conn:
        linhas = conn.execute(q, (list(ESQUEMAS),)).fetchall()
        valores = {(e, t, c): v for e, t, c, v in conn.execute(q_valores, (list(ESQUEMAS),)).fetchall()}
    # Compacto de propósito: o esquema inteiro, com os comentários completos, passava de 8 mil tokens e
    # estourava o contexto do modelo local (o início era descartado e ele inventava tabelas).
    saida: List[str] = []
    atual = None
    for esq, tab, comt, col, tipo, ccomt in linhas:
        if col.startswith("_"):
            continue
        if (esq, tab) != atual:
            atual = (esq, tab)
            saida.append(f"\n{esq}.{tab}" + (f" -- {_curto(comt, 90)}" if comt else ""))
        extra = f" [valores: {valores[(esq, tab, col)]}]" if tipo == "text" and (esq, tab, col) in valores else ""
        saida.append(f"  {col} {tipo.split('(')[0]}" + (f" -- {_curto(ccomt, 50)}" if ccomt else "") + extra)
    return "\n".join(saida)


def _curto(texto: str, n: int) -> str:
    """Primeira frase do comentário, cortada em n caracteres."""
    primeira = texto.split(". ")[0].strip()
    return primeira if len(primeira) <= n else primeira[: n - 1] + "…"


def buscar_documentos(consulta: str, k: int = 5) -> List[Dict[str, Any]]:
    """Busca semântica em busca.documentos (cursos, planos de IC, documentação)."""
    from src.busca.buscar import buscar

    return [
        {"tipo": d["tipo"], "titulo": d["titulo"], "conteudo": d["conteudo"][:800]}
        for d in buscar(consulta, k=min(max(int(k), 1), 10))
    ]
