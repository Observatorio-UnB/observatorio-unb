"""
Ferramentas que o LLM do chat pode chamar. Todas leem o banco com o usuário observatorio_chat
(migração 0032): o que protege bronze e silver é o papel do banco; a validação do SQL aqui é só a
segunda camada, e é contornável (ex.: identificadores Unicode escapados, que recusamos abaixo, mas outros
truques podem existir). A defesa real é o papel do banco; ver ADR 0033.
"""

import re
import sys
from urllib.parse import urlsplit
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar, ler_variavel  # noqa: E402

ESQUEMAS = ("gold", "dbt_marts", "busca")
LIMITE_LINHAS = 200
URL_PADRAO_CHAT = "postgresql://observatorio_chat:observatorio_chat@localhost:5435/observatorio"
# Esquemas com dado pessoal ou fora do papel de leitura: recusados antes de ir ao banco.
PROIBIDOS = re.compile(
    r"\b(bronze|silver|dbt_staging|dbt_intermediate|dbt_snapshots|information_schema)\b|\bpg_\w+", re.I
)


# Funções que leem arquivo, abrem outra conexão ou mexem na sessão/servidor: o papel do banco já barra a
# maioria, mas o modelo nem precisa tentar.
FUNCOES_PROIBIDAS = re.compile(
    r"\b(pg_read_\w+|pg_ls_\w+|pg_stat_file|lo_\w+|dblink\w*|set_config|pg_sleep\w*|pg_terminate_backend|"
    r"pg_cancel_backend|current_setting|pg_reload_conf)\b", re.I)
# Colunas de identificação pessoal: a gold não as tem (é agregada), então pedir uma é tentativa de reidentificar.
# Identificador/literal Unicode escapado (U&"pg\\005fclass") esconde nomes da denylist; o chat não precisa dele.
UNICODE_ESCAPADO = re.compile(r"\bU&", re.I)
PESSOAIS = re.compile(r"\b(matricula|nome_discente|nome_aluno|cpf|email|e_mail|telefone|data_nascimento)\b", re.I)


class SqlRecusado(ValueError):
    pass


def url_chat() -> str:
    """URL do usuário do chat. Recusa o Supabase (o chat é local, ADR 0033): host da SUPABASE_DATABASE_URL ou *.supabase.*."""
    url = ler_variavel("CHAT_DATABASE_URL") or URL_PADRAO_CHAT
    host = (urlsplit(url).hostname or "").lower()
    hosts_supabase = {(urlsplit(u).hostname or "").lower() for u in [ler_variavel("SUPABASE_DATABASE_URL")] if u}
    if "supabase" in host or host in hosts_supabase:
        raise SqlRecusado("CHAT_DATABASE_URL não pode apontar para o Supabase: o chat só lê o banco local.")
    return url


def validar_sql(sql: str) -> str:
    """Devolve o SQL sem `;` final, ou levanta SqlRecusado: só um SELECT/WITH, sem camadas pessoais."""
    s = sql.strip().rstrip(";").strip()
    # ponytail: heurística de texto (';' dentro de literal também é recusado); o papel do banco é a defesa real.
    if ";" in s:
        raise SqlRecusado("Só um comando por consulta.")
    if not re.match(r"(?is)^(select|with)\b", s):
        raise SqlRecusado("Só SELECT ou WITH.")
    if UNICODE_ESCAPADO.search(s):
        raise SqlRecusado("Identificador Unicode escapado (U&) não é permitido.")
    if PROIBIDOS.search(s):
        raise SqlRecusado("Só gold, dbt_marts e busca podem ser consultados.")
    if FUNCOES_PROIBIDAS.search(s):
        raise SqlRecusado("Função não permitida.")
    if PESSOAIS.search(s):
        raise SqlRecusado("Dado pessoal não é consultável: o chat só responde com dados agregados.")
    # No PostgreSQL, NULL vem primeiro em DESC: "o maior gap" devolvia um curso sem dado. Sempre NULLS LAST.
    # Literais, identificadores entre aspas e comentários passam intactos (o grupo 1 casa primeiro).
    return re.sub(
        r"""('(?:[^']|'')*'|"(?:[^"]|"")*"|--[^\n]*|/\*.*?\*/)|\bDESC\b(?!\s+NULLS)""",
        lambda m: m.group(1) or "DESC NULLS LAST", s, flags=re.I | re.S)


def _json(v):
    return v if v is None or isinstance(v, (int, float, str, bool)) else str(v)


def consultar_sql(sql: str, url: Optional[str] = None) -> Dict[str, Any]:
    """Executa um SELECT somente leitura e devolve colunas e até LIMITE_LINHAS linhas."""
    s = validar_sql(sql)
    with conectar(url or url_chat(), options="-c default_transaction_read_only=on") as conn:
        with conn.cursor() as cur:
            cur.execute(s)
            colunas = [d.name for d in cur.description]
            if any(PESSOAIS.search(c) for c in colunas):  # alias ou SELECT * que traga coluna pessoal
                raise SqlRecusado("Dado pessoal não é consultável: o chat só responde com dados agregados.")
            linhas = cur.fetchmany(LIMITE_LINHAS + 1)
    return {
        "colunas": colunas,
        "linhas": [[_json(v) for v in linha] for linha in linhas[:LIMITE_LINHAS]],
        "truncado": len(linhas) > LIMITE_LINHAS,
    }


def descrever_esquema(url: Optional[str] = None, tabelas: Optional[Iterable[str]] = None,
                      limite_comentario: int = 50) -> str:
    """Tabelas e colunas de gold, dbt_marts e busca, com os COMMENT ON do catálogo.
    `tabelas` ("esquema.tabela") restringe a saída; `limite_comentario` é o tamanho do comentário de coluna."""
    so = set(tabelas) if tabelas else None
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
        if col.startswith("_") or (so and f"{esq}.{tab}" not in so):
            continue
        if (esq, tab) != atual:
            atual = (esq, tab)
            saida.append(f"\n{esq}.{tab}" + (f" -- {_curto(comt, 90)}" if comt else ""))
        extra = f" [valores: {valores[(esq, tab, col)]}]" if tipo == "text" and (esq, tab, col) in valores else ""
        saida.append(f"  {col} {tipo.split('(')[0]}" + (f" -- {_curto(ccomt, limite_comentario)}" if ccomt else "") + extra)
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
        for d in buscar(consulta, k=min(max(int(k), 1), 10), url=url_chat())
    ]
