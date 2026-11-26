"""
Ferramentas que o LLM do chat pode chamar. Todas leem o banco com o usuário observatorio_chat
(migração 0033): o que protege bronze e silver é o papel do banco (somente leitura, sem acesso a essas camadas).
A validação do SQL aqui é a segunda camada e usa o parser do próprio PostgreSQL (pglast/libpg_query): confere a
árvore, não o texto, então comentário, literal, aspas e escapes são lidos como o servidor os lê. Ver ADR 0034.
"""

import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlsplit

from pglast import ast, parse_sql
from pglast.parser import ParseError
from pglast.visitors import Visitor

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conexao_do_pool, ler_variavel  # noqa: E402

ESQUEMAS = ("gold", "dbt_marts", "busca")
LIMITE_LINHAS = 200
URL_PADRAO_CHAT = "postgresql://observatorio_chat:observatorio_chat@localhost:5435/observatorio"
# Só estas funções (sem esquema ou em pg_catalog) podem ser chamadas: agregados, janelas, texto, número, data e
# busca textual. Lista de permissão, e não de bloqueio: toda função que lê arquivo, abre conexão ou executa SQL
# em texto (pg_read_file, dblink, query_to_xml, ts_stat, xpath...) fica de fora sem precisar ser citada.
# Funções dos esquemas gold, dbt_marts e busca (ex.: busca.sem_acento, gold.arredondar) são aceitas pelo esquema.
FUNCOES_PERMITIDAS = frozenset("""
count sum avg min max stddev stddev_pop stddev_samp variance var_pop var_samp corr covar_pop covar_samp
percentile_cont percentile_disc mode string_agg array_agg bool_and bool_or every
row_number rank dense_rank percent_rank cume_dist ntile lag lead first_value last_value nth_value
abs ceil ceiling floor round trunc sqrt power exp ln log log10 mod sign div greatest least random_normal
lower upper initcap length char_length character_length substr substring trim ltrim rtrim btrim replace
concat concat_ws left right split_part position strpos reverse translate starts_with overlay
regexp_replace regexp_match regexp_matches regexp_split_to_table string_to_array array_position to_char to_number to_date to_timestamp unaccent
now date_trunc date_part extract age timezone make_date make_interval isfinite
array_length cardinality array_to_string unnest generate_series
to_tsvector to_tsquery plainto_tsquery websearch_to_tsquery phraseto_tsquery ts_rank ts_rank_cd
""".split())
# repeat, lpad e rpad ficam de fora de propósito: alocam até 1 GB numa chamada, dentro do tempo limite.
# Colunas de identificação pessoal: a gold não as tem (é agregada), então pedir uma é tentativa de reidentificar.
# O sublinhado conta como separador (cpf_responsavel casa), letra e dígito não (qt_matriculas_unb não casa).
PESSOAIS = re.compile(r"(?<![a-z0-9])(matricula|nome_discente|nome_aluno|cpf|email|e_mail|telefone|data_nascimento)(?![a-z0-9])", re.I)
# Nós que não existem numa consulta de leitura (escrita dentro de WITH, SELECT INTO, FOR UPDATE).
_ESCRITA = ("InsertStmt", "UpdateStmt", "DeleteStmt", "MergeStmt", "IntoClause", "LockingClause", "CallStmt", "DoStmt")


class SqlRecusado(ValueError):
    pass


def url_chat() -> str:
    """URL do usuário do chat. Recusa o Supabase (o chat é local, ADR 0034): host da SUPABASE_DATABASE_URL ou *.supabase.*."""
    url = ler_variavel("CHAT_DATABASE_URL") or URL_PADRAO_CHAT
    host = (urlsplit(url).hostname or "").lower()
    sup = ler_variavel("SUPABASE_DATABASE_URL")
    if "supabase" in host or (sup and host == (urlsplit(sup).hostname or "").lower()):
        raise SqlRecusado("CHAT_DATABASE_URL não pode apontar para o Supabase: o chat só lê o banco local.")
    return url


class _Auditor(Visitor):
    """Percorre a árvore do SELECT e recusa o que o chat não pode tocar."""

    def visit_RangeVar(self, ancestors, node):
        esquema = (node.schemaname or "").lower()
        if node.catalogname or (esquema and esquema not in ESQUEMAS):
            raise SqlRecusado("Só gold, dbt_marts e busca podem ser consultados.")
        if not esquema and node.relname.lower() not in _ctes_visiveis(ancestors):
            raise SqlRecusado("Só gold, dbt_marts e busca podem ser consultados (use esquema.tabela).")

    def visit_FuncCall(self, ancestors, node):
        nomes = [n.sval.lower() for n in node.funcname]
        if len(nomes) == 1 or nomes[0] == "pg_catalog":
            ok = nomes[-1] in FUNCOES_PERMITIDAS
        else:
            ok = len(nomes) == 2 and nomes[0] in ESQUEMAS
        if not ok:
            raise SqlRecusado(f"Função não permitida: {'.'.join(nomes)}.")

    def visit_ColumnRef(self, ancestors, node):
        ultimo = node.fields[-1]
        if isinstance(ultimo, ast.String) and PESSOAIS.search(ultimo.sval):
            raise SqlRecusado("Dado pessoal não é consultável: o chat só responde com dados agregados.")


def _ctes_visiveis(ancestors) -> set:
    """Nomes de CTE que o ponto da árvore enxerga: no corpo, todos os do WITH; dentro de uma CTE, só as anteriores
    (e ela mesma, se RECURSIVE). Nome sem esquema fora disso cairia no search_path do banco."""
    entradas = []
    a = ancestors
    while a is not None:
        entradas.append((a.node, a.member))
        a = a.parent
    visiveis = set()
    for k, (no, membro) in enumerate(entradas):
        if not (isinstance(no, ast.SelectStmt) and no.withClause):
            continue
        ctes = no.withClause.ctes
        if membro == "withClause":  # estamos dentro da CTE de índice entradas[k-2][1]
            i = entradas[k - 2][1]
            visiveis |= {c.ctename.lower() for c in ctes[:i]}
            if no.withClause.recursive:
                visiveis.add(ctes[i].ctename.lower())
        else:
            visiveis |= {c.ctename.lower() for c in ctes}
    return visiveis


def _recusar_escrita(self, ancestors, node):
    raise SqlRecusado("Só consulta de leitura (SELECT/WITH).")


for _tipo in _ESCRITA:
    setattr(_Auditor, f"visit_{_tipo}", _recusar_escrita)


def _auditar(sql: str) -> None:
    """Levanta SqlRecusado se `sql` não for um único SELECT/WITH só sobre gold, dbt_marts e busca."""
    try:
        comandos = parse_sql(sql)
    except ParseError as e:
        raise SqlRecusado(f"SQL inválido: {e}") from e
    if len(comandos) != 1 or not isinstance(comandos[0].stmt, ast.SelectStmt):
        raise SqlRecusado("Só um SELECT ou WITH, em um único comando.")
    _Auditor()(comandos[0])


def validar_sql(sql: str) -> str:
    """Devolve o SQL sem `;` final, ou levanta SqlRecusado: só um SELECT/WITH, sem camadas pessoais."""
    s = sql.strip().rstrip(";").strip()
    # No PostgreSQL, NULL vem primeiro em DESC: "o maior gap" devolvia um curso sem dado. Sempre NULLS LAST.
    # Literais, identificadores entre aspas e comentários passam intactos (o grupo 1 casa primeiro).
    s = re.sub(
        r"""('(?:[^']|'')*'|"(?:[^"]|"")*"|--[^\r\n]*|/\*.*?\*/)|\bDESC\b(?!\s+NULLS)""",
        lambda m: m.group(1) or "DESC NULLS LAST", s, flags=re.I | re.S)
    _auditar(s)  # audita o texto final, que é o que vai ao banco
    return s


def _json(v):
    return v if v is None or isinstance(v, (int, float, str, bool)) else str(v)


def consultar_sql(sql: str, url: Optional[str] = None) -> Dict[str, Any]:
    """Executa um SELECT somente leitura e devolve colunas e até LIMITE_LINHAS linhas."""
    s = validar_sql(sql)
    with conexao_do_pool(url or url_chat()) as conn:
        conn.read_only = True  # além do papel do banco: a transação já nasce somente leitura
        # Cursor nomeado (do lado do servidor): o resultado vem em lotes, e uma consulta com milhões de linhas
        # não é carregada inteira na memória do painel antes do corte em LIMITE_LINHAS.
        with conn.cursor(name="chat") as cur:
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
    with conexao_do_pool(url or url_chat()) as conn:
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
