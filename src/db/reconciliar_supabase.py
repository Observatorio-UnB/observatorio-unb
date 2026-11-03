"""
Verificação de conformidade, reconciliação de dados e auditoria de escopo do Supabase.

Inspeciona o banco remoto (Supabase) frente ao banco local e às diretrizes da E3/LGPD:
  1. Extensão pgvector instalada e ativa;
  2. Migrações aplicadas no destino vs db/migrations/;
  3. Minimização por escopo: nenhuma tabela de bronze e silver tem linhas na nuvem;
  4. Tamanho mínimo de célula (k >= 5) nas tabelas agregadas da gold;
  5. Privilégio mínimo: nem observatorio_leitura nem os papéis públicos do Supabase (anon,
     authenticated, PUBLIC) alcançam bronze e silver;
  6. Reconciliação de contagens das tabelas sincronizadas (gold e busca) com o banco local;
  7. Conexão por SSL e ocupação frente à cota do plano gratuito.

A auditoria falha fechada: verificação que não consegue ler o dado sai como INCONCLUSIVO ou
NAO_VERIFICADO, e qualquer veredito diferente de APROVADO dá código de saída 1.

Uso:
    python3 src/db/reconciliar_supabase.py [--markdown] [--salvar-evidencia]
"""

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import database_url, ler_variavel  # noqa: E402
from src.db.sincronizar_supabase import SINCRONIAS  # noqa: E402

MIGRATIONS_DIR = BASE_DIR / "db" / "migrations"
EVIDENCIA = BASE_DIR / "docs" / "disponibilizacao_online_supabase_evidencias.md"

logger = logging.getLogger("reconciliar_supabase")

ESQUEMAS_RESTRITOS = ["bronze", "silver"]

# Mínimo esperado em bronze e silver (LGPD / ADRs 0017 e 0020). A auditoria soma a estas as tabelas
# que o catálogo do destino listar nos dois esquemas, para que uma tabela nova não escape. Partições
# entram pela tabela-mãe: o count(*) dela já inclui todas, inclusive as criadas depois (0019).
TABELAS_SENSIVEIS_MINIMAS = [
    "bronze.sigra_discentes",
    "bronze.sigaa_discentes",
    "bronze.sigaa_ativos",
    "bronze.bolsistas_iniciacao_cientifica",
    "silver.discentes",
    "silver.discentes_graduacao",
    "silver.movimentacoes_vinculos",
    "silver.sigaa_ativos",
    "silver.pibic_bolsistas",
]

# Papéis que não podem alcançar bronze e silver. anon e authenticated são os da API do Supabase;
# só são conferidos onde existem. "public" é o pseudo-papel PUBLIC, aceito por has_*_privilege.
PAPEIS_PUBLICOS = ["observatorio_leitura", "anon", "authenticated", "public"]

# Coluna de contagem de cada tabela agregada publicada; nenhuma linha pode ter menos que CELULA_MINIMA
# (ADR 0005). As CHECK do esquema cobrem parte delas; esta verificação cobre também as que não têm.
CELULA_MINIMA = 5
COLUNAS_DE_CONTAGEM = {
    "gold.retencao_cursos_unb": "total_discentes_registrados",
    "gold.ativos_hoje_cursos_unb": "total_ativos_hoje",
    "gold.pibic_social_unb": "total_projetos",
    "gold.fato_retencao_curso": "total_ingressantes",
    "gold.fato_alunos_ativos": "total_ativos",
    "gold.fato_pibic_perfil": "total_projetos",
}

# A sincronização insere e atualiza, mas não apaga: o Supabase pode ter mais linhas que o local.
RECONCILIACAO_OK = {"RECONCILIADO", "RECONCILIADO_COM_EXTRAS"}

COTA_GRATUITA_SUPABASE_MB = 500.0


def _citar(tabela: str) -> str:
    esquema, nome = tabela.split(".")
    return f'"{esquema}"."{nome}"'


def verificar_extensao_vector(conn: psycopg.Connection) -> Dict[str, Any]:
    """Verifica se a extensão pgvector está ativa e retorna sua versão."""
    row = conn.execute(
        "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
    ).fetchone()
    if row:
        return {"instalada": True, "versao": row[0], "status": "OK"}
    return {"instalada": False, "versao": None, "status": "FALHA"}


def verificar_migracoes(conn: psycopg.Connection) -> Dict[str, Any]:
    """Compara migrações aplicadas no Supabase com os arquivos em db/migrations/."""
    arquivos_locais = sorted(f.name for f in MIGRATIONS_DIR.glob("*.sql"))
    try:
        aplicadas = [r[0] for r in conn.execute(
            "SELECT versao FROM public.schema_migrations ORDER BY versao"
        ).fetchall()]
    except Exception as e:
        return {
            "status": "ERRO",
            "erro": str(e),
            "total_locais": len(arquivos_locais),
            "total_aplicadas": 0,
            "pendentes": arquivos_locais,
            "extras_no_destino": [],
        }

    pendentes = [m for m in arquivos_locais if m not in aplicadas]
    return {
        "status": "OK" if not pendentes else "PENDENTE",
        "erro": None,
        "total_locais": len(arquivos_locais),
        "total_aplicadas": len(aplicadas),
        "pendentes": pendentes,
        "extras_no_destino": [m for m in aplicadas if m not in arquivos_locais],
    }


def tabelas_restritas(conn: psycopg.Connection) -> List[str]:
    """Tabelas de bronze e silver no destino (sem as partições), somadas ao mínimo esperado."""
    no_catalogo = [r[0] for r in conn.execute(
        """
        SELECT n.nspname || '.' || c.relname
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = ANY(%s) AND c.relkind IN ('r', 'p') AND NOT c.relispartition
        """,
        (ESQUEMAS_RESTRITOS,),
    ).fetchall()]
    return sorted(set(TABELAS_SENSIVEIS_MINIMAS) | set(no_catalogo))


def verificar_privacidade_lgpd(conn: psycopg.Connection, tabelas: List[str]) -> Dict[str, Any]:
    """Confere que nenhuma tabela de bronze e silver tem linhas no destino.

    Uma contagem que falha não prova nada: a tabela sai INCONCLUSIVO, e o veredito também."""
    achados = {}
    linhas_indevidas = 0
    inconclusivas = 0

    for tabela in tabelas:
        if conn.execute("SELECT to_regclass(%s) IS NOT NULL", (tabela,)).fetchone()[0] is not True:
            achados[tabela] = {"existe": False, "linhas": 0, "status": "OK (tabela não existe)"}
            continue
        try:
            qtd = conn.execute(f"SELECT count(*) FROM {_citar(tabela)}").fetchone()[0]
        except Exception as e:
            achados[tabela] = {"existe": True, "linhas": None, "status": f"INCONCLUSIVO: {e}"}
            inconclusivas += 1
            continue
        achados[tabela] = {"existe": True, "linhas": qtd, "status": "OK" if qtd == 0 else "VIOLAÇÃO LGPD"}
        linhas_indevidas += qtd

    if linhas_indevidas:
        status = "FALHA_CRITICA"
    elif inconclusivas:
        status = "INCONCLUSIVO"
    else:
        status = "OK"
    return {
        "status": status,
        "linhas_vazadas": linhas_indevidas,
        "tabelas_inconclusivas": inconclusivas,
        "tabelas_auditadas": achados,
    }


def verificar_celula_minima(conn: psycopg.Connection) -> Dict[str, Any]:
    """Conta, em cada tabela agregada da gold, as linhas com menos de CELULA_MINIMA pessoas ou planos."""
    achados = {}
    for tabela, coluna in COLUNAS_DE_CONTAGEM.items():
        try:
            abaixo = conn.execute(
                f'SELECT count(*) FILTER (WHERE "{coluna}" < %s) FROM {_citar(tabela)}', (CELULA_MINIMA,)
            ).fetchone()[0]
            achados[tabela] = {"coluna": coluna, "abaixo_do_minimo": abaixo, "status": "OK" if abaixo == 0 else "VIOLAÇÃO"}
        except Exception as e:
            achados[tabela] = {"coluna": coluna, "abaixo_do_minimo": None, "status": f"INCONCLUSIVO: {e}"}

    situacoes = [a["status"] for a in achados.values()]
    if "VIOLAÇÃO" in situacoes:
        status = "FALHA_CRITICA"
    elif any(s.startswith("INCONCLUSIVO") for s in situacoes):
        status = "INCONCLUSIVO"
    else:
        status = "OK"
    return {"status": status, "minimo": CELULA_MINIMA, "tabelas": achados}


def verificar_controle_acesso(conn: psycopg.Connection, tabelas: List[str]) -> Dict[str, Any]:
    """Confere que nenhum papel público alcança bronze e silver, nem pelo esquema nem tabela a tabela,
    e que observatorio_leitura lê gold e busca."""
    existentes = {r[0] for r in conn.execute(
        "SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)", (PAPEIS_PUBLICOS,)
    ).fetchall()}
    papeis = [p for p in PAPEIS_PUBLICOS if p in existentes or p == "public"]
    papel_existe = "observatorio_leitura" in existentes

    tabelas_no_destino = [
        t for t in tabelas if conn.execute("SELECT to_regclass(%s) IS NOT NULL", (t,)).fetchone()[0] is True
    ]
    exposicoes = []
    for papel in papeis:
        for esquema in ESQUEMAS_RESTRITOS:
            if conn.execute("SELECT has_schema_privilege(%s, %s, 'USAGE')", (papel, esquema)).fetchone()[0]:
                exposicoes.append(f"{papel}: USAGE em {esquema}")
        for tabela in tabelas_no_destino:
            if conn.execute("SELECT has_table_privilege(%s, %s, 'SELECT')", (papel, tabela)).fetchone()[0]:
                exposicoes.append(f"{papel}: SELECT em {tabela}")

    leitura = {}
    if papel_existe:
        for esquema in ["gold", "busca"]:
            leitura[esquema] = conn.execute(
                "SELECT has_schema_privilege('observatorio_leitura', %s, 'USAGE')", (esquema,)
            ).fetchone()[0]
    leitura_ok = papel_existe and all(leitura.values())

    return {
        "papel_existe": papel_existe,
        "papeis_conferidos": papeis,
        "exposicoes": exposicoes,
        "leitura_gold_busca": leitura,
        "isolamento_ok": not exposicoes,
        "status": "OK" if not exposicoes and leitura_ok else "ALERTA",
    }


def reconciliar_contagens(
    conn_remoto: psycopg.Connection, conn_local: Optional[psycopg.Connection] = None
) -> List[Dict[str, Any]]:
    """Compara as contagens das tabelas sincronizadas entre local e remoto.

    Sem banco local, nada é reconciliado: o status é NAO_VERIFICADO. Como a sincronização não apaga,
    o Supabase pode ter mais linhas que o local (RECONCILIADO_COM_EXTRAS); menos é DIVERGENTE."""
    tabelas_para_checar = [s.tabela for s in SINCRONIAS]
    if "gold.mv_dashboard_executivo" not in tabelas_para_checar:
        tabelas_para_checar.append("gold.mv_dashboard_executivo")

    relatorio_tabelas = []
    for tabela in tabelas_para_checar:
        qtd_remota = qtd_local = erro_remoto = erro_local = None
        try:
            qtd_remota = conn_remoto.execute(f"SELECT count(*) FROM {_citar(tabela)}").fetchone()[0]
        except Exception as e:
            erro_remoto = str(e)
        if conn_local is not None:
            try:
                qtd_local = conn_local.execute(f"SELECT count(*) FROM {_citar(tabela)}").fetchone()[0]
            except Exception as e:
                erro_local = str(e)

        if erro_remoto or erro_local:
            status = "ERRO"
        elif conn_local is None:
            status = "NAO_VERIFICADO"
        elif qtd_remota == qtd_local:
            status = "RECONCILIADO"
        elif qtd_remota > qtd_local:
            status = "RECONCILIADO_COM_EXTRAS"
        else:
            status = "DIVERGENTE"

        relatorio_tabelas.append({
            "tabela": tabela,
            "qtd_remota": qtd_remota,
            "qtd_local": qtd_local,
            "erro_remoto": erro_remoto,
            "erro_local": erro_local,
            "status": status,
        })
    return relatorio_tabelas


def verificar_limites_recursos(conn: psycopg.Connection) -> Dict[str, Any]:
    """Avalia o tamanho do banco frente à cota do Supabase Free Tier e se a conexão usa SSL."""
    tamanho_bytes = conn.execute("SELECT pg_database_size(current_database())").fetchone()[0]
    tamanho_mb = tamanho_bytes / (1024 * 1024)
    tamanho_legivel = conn.execute("SELECT pg_size_pretty(pg_database_size(current_database()))").fetchone()[0]
    # Sessões do banco, e não clientes do pooler: atrás do pooler, cada sessão é uma conexão dele.
    sessoes_no_banco = conn.execute(
        "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
    ).fetchone()[0]
    # SSL do lado do cliente (desta conexão até o Supabase ou o pooler).
    ssl = bool(conn.pgconn.ssl_in_use)

    return {
        "tamanho_bytes": tamanho_bytes,
        "tamanho_mb": round(tamanho_mb, 2),
        "tamanho_legivel": tamanho_legivel,
        "cota_mb": COTA_GRATUITA_SUPABASE_MB,
        "pct_uso": round(tamanho_mb / COTA_GRATUITA_SUPABASE_MB * 100, 2),
        "sessoes_no_banco": sessoes_no_banco,
        "ssl": ssl,
        "status": "OK" if ssl and tamanho_mb < COTA_GRATUITA_SUPABASE_MB * 0.9 else "ALERTA",
    }


def veredito(auditoria: Dict[str, Any]) -> str:
    """APROVADO só se todas as verificações e todas as tabelas reconciliadas passarem."""
    if "FALHA_CRITICA" in (auditoria["privacidade_lgpd"]["status"], auditoria["celula_minima"]["status"]):
        return "FALHA_CRITICA"
    verificacoes = ["extensao_vector", "migracoes", "controle_acesso", "privacidade_lgpd", "celula_minima", "limites"]
    if any(auditoria[v]["status"] != "OK" for v in verificacoes):
        return "REQUER_ATENCAO"
    if any(r["status"] not in RECONCILIACAO_OK for r in auditoria["reconciliacao"]):
        return "REQUER_ATENCAO"
    return "APROVADO"


def executar_auditoria_completa(url_supabase: str, url_local: Optional[str] = None) -> Dict[str, Any]:
    """Executa a bateria completa de auditoria e reconciliação."""
    data_execucao = datetime.now(timezone.utc).isoformat()
    logger.info("Iniciando auditoria de conformidade no Supabase...")
    if url_local == url_supabase:
        logger.warning("DATABASE_URL aponta para o Supabase: a reconciliação com o banco local fica de fora.")
        url_local = None

    # autocommit: a auditoria só lê, e um erro numa consulta não aborta as seguintes.
    # prepare_threshold=None: a auditoria repete a mesma consulta dezenas de vezes (uma por tabela), e
    # o psycopg passaria a usar prepared statement na quinta. O pooler transacional do Supabase troca
    # a conexão do servidor a cada transação, e o prepared statement some ou já existe
    # (DuplicatePreparedStatement, reproduzido com PgBouncer em modo transação).
    with psycopg.connect(url_supabase, connect_timeout=15, autocommit=True, prepare_threshold=None) as conn_supa:
        conn_loc = None
        if url_local:
            try:
                conn_loc = psycopg.connect(url_local, connect_timeout=5, autocommit=True, prepare_threshold=None)
            except Exception as e:
                logger.warning(f"Banco local inacessível: a reconciliação sai NAO_VERIFICADO ({e}).")

        try:
            tabelas = tabelas_restritas(conn_supa)
            auditoria = {
                "data_execucao": data_execucao,
                "extensao_vector": verificar_extensao_vector(conn_supa),
                "migracoes": verificar_migracoes(conn_supa),
                "controle_acesso": verificar_controle_acesso(conn_supa, tabelas),
                "privacidade_lgpd": verificar_privacidade_lgpd(conn_supa, tabelas),
                "celula_minima": verificar_celula_minima(conn_supa),
                "reconciliacao": reconciliar_contagens(conn_supa, conn_loc),
                "limites": verificar_limites_recursos(conn_supa),
            }
        finally:
            if conn_loc:
                conn_loc.close()

    auditoria["status_geral"] = veredito(auditoria)
    return auditoria


def formatar_relatorio_markdown(auditoria: Dict[str, Any]) -> str:
    """Gera um relatório estruturado em Markdown com as evidências da auditoria."""
    ext = auditoria["extensao_vector"]
    mig = auditoria["migracoes"]
    acesso = auditoria["controle_acesso"]
    priv = auditoria["privacidade_lgpd"]
    celula = auditoria["celula_minima"]
    lim = auditoria["limites"]

    linhas = [
        "# Relatório de Auditoria e Reconciliação do Banco Online (Supabase)",
        "",
        f"- **Data da Execução:** `{auditoria['data_execucao']}`",
        f"- **Veredito Geral:** **{auditoria['status_geral']}**",
        "",
        "---",
        "",
        "## 1. Extensões e Capacidades Analíticas",
        f"- **pgvector:** {'✅ Instalada' if ext['instalada'] else '❌ Ausente'} (Versão: `{ext['versao']}`)",
        "",
        "## 2. Integridade de Esquema e Migrações",
        f"- **Total de migrações locais:** `{mig['total_locais']}`",
        f"- **Total aplicadas no Supabase:** `{mig['total_aplicadas']}`",
        f"- **Migrações pendentes:** `{len(mig['pendentes'])}`",
    ]
    if mig.get("erro"):
        linhas.append(f"- ❌ Não foi possível ler `public.schema_migrations`: `{mig['erro']}`")
    elif mig["pendentes"]:
        linhas.extend(f"  - ⚠️ Pendente: `{p}`" for p in mig["pendentes"])
    else:
        linhas.append("- ✅ Todas as migrações aplicadas.")

    veredito_privacidade = {
        "OK": "✅ Nenhuma linha em bronze e silver",
        "INCONCLUSIVO": f"⚠️ Inconclusivo ({priv['tabelas_inconclusivas']} tabela(s) não puderam ser lidas)",
    }.get(priv["status"], "❌ VIOLAÇÃO IDENTIFICADA")
    linhas.extend([
        "",
        "## 3. Minimização por Escopo (LGPD)",
        "Bronze e silver não são sincronizadas; as tabelas existem no destino porque as migrações são as mesmas.",
        "",
        f"- **Linhas em bronze e silver no Supabase:** `{priv['linhas_vazadas']}`",
        f"- **Veredito:** {veredito_privacidade}",
        "",
        "| Tabela (bronze e silver) | Existe no Destino? | Registros no Supabase | Situação |",
        "| :--- | :---: | :---: | :--- |",
    ])
    for tab, info in priv["tabelas_auditadas"].items():
        linhas.append(f"| `{tab}` | {'Sim' if info['existe'] else 'Não'} | `{info['linhas']}` | {info['status']} |")

    linhas.extend([
        "",
        f"## 4. Tamanho Mínimo de Célula na Gold (k ≥ {celula['minimo']})",
        "",
        "| Tabela agregada | Coluna de contagem | Linhas abaixo do mínimo | Situação |",
        "| :--- | :--- | :---: | :--- |",
    ])
    for tab, info in celula["tabelas"].items():
        linhas.append(f"| `{tab}` | `{info['coluna']}` | `{info['abaixo_do_minimo']}` | {info['status']} |")

    linhas.extend([
        "",
        "## 5. Controle de Acesso e Privilégio Mínimo",
        f"- **Papel `observatorio_leitura`:** {'✅ Criado' if acesso['papel_existe'] else '❌ Inexistente'}",
        f"- **Leitura de `gold` e `busca` por `observatorio_leitura`:** `{acesso['leitura_gold_busca']}`",
        f"- **Papéis conferidos em bronze e silver (USAGE no esquema e SELECT em cada tabela):** "
        f"{', '.join(f'`{p}`' for p in acesso['papeis_conferidos'])}",
    ])
    if acesso["exposicoes"]:
        linhas.append("- ❌ **Acessos indevidos:**")
        linhas.extend(f"  - `{e}`" for e in acesso["exposicoes"])
    else:
        linhas.append("- ✅ Nenhum desses papéis alcança bronze ou silver.")

    linhas.extend([
        "",
        "## 6. Reconciliação de Contagens das Tabelas Sincronizadas",
        "A sincronização não apaga linhas no Supabase: `RECONCILIADO_COM_EXTRAS` é o Supabase com mais linhas que o "
        "local. Sem banco local, a tabela fica `NAO_VERIFICADO`.",
        "",
        "| Tabela | Supabase (Remoto) | Banco Local | Status de Reconciliação |",
        "| :--- | :---: | :---: | :---: |",
    ])
    for r in auditoria["reconciliacao"]:
        loc_str = str(r["qtd_local"]) if r["qtd_local"] is not None else "N/A"
        linhas.append(f"| `{r['tabela']}` | `{r['qtd_remota']}` | `{loc_str}` | {r['status']} |")

    linhas.extend([
        "",
        "## 7. Conexão e Limites da Infraestrutura",
        f"- **Conexão por SSL:** {'✅ Sim' if lim['ssl'] else '❌ Não'}",
        f"- **Espaço ocupado em disco:** `{lim['tamanho_legivel']}` ({lim['tamanho_mb']} MB)",
        f"- **Cota do Free Tier:** `{lim['cota_mb']} MB` ({lim['pct_uso']}% utilizado)",
        f"- **Sessões abertas no banco (`pg_stat_activity`):** `{lim['sessoes_no_banco']}`",
        "",
        "---",
        "*Evidência gerada automaticamente por `src/db/reconciliar_supabase.py`*",
    ])
    return "\n".join(linhas)


def formatar_resumo(auditoria: Dict[str, Any]) -> str:
    """Resumo curto para o terminal."""
    linhas = [
        f"Auditoria do Supabase concluída: {auditoria['status_geral']}",
        f"Extensão vector: {auditoria['extensao_vector']['status']} (v{auditoria['extensao_vector']['versao']})",
        f"Migrações: {auditoria['migracoes']['total_aplicadas']}/{auditoria['migracoes']['total_locais']} aplicadas "
        f"({auditoria['migracoes']['status']})",
        f"Bronze e silver: {auditoria['privacidade_lgpd']['linhas_vazadas']} linhas no Supabase "
        f"({auditoria['privacidade_lgpd']['status']})",
        f"Célula mínima na gold: {auditoria['celula_minima']['status']}",
        f"Controle de acesso: {auditoria['controle_acesso']['status']}",
        f"SSL e espaço: {auditoria['limites']['status']} ({auditoria['limites']['tamanho_legivel']}, "
        f"{auditoria['limites']['pct_uso']}% da cota)",
        "Tabelas sincronizadas:",
    ]
    linhas.extend(f"  - {r['tabela']}: {r['qtd_remota']} no Supabase, {r['qtd_local']} no local [{r['status']}]"
                  for r in auditoria["reconciliacao"])
    return "\n".join(linhas)


def verificar(url_supabase: str, url_local: Optional[str], markdown: bool = False,
              salvar_evidencia: bool = False) -> bool:
    """Roda a auditoria, imprime o relatório e diz se o veredito é APROVADO."""
    auditoria = executar_auditoria_completa(url_supabase, url_local)
    relatorio_md = formatar_relatorio_markdown(auditoria)
    if salvar_evidencia:
        EVIDENCIA.write_text(relatorio_md + "\n", encoding="utf-8")
        logger.info(f"Evidência salva em {EVIDENCIA}")
    print(relatorio_md if markdown else formatar_resumo(auditoria))
    if auditoria["status_geral"] != "APROVADO":
        logger.error(f"Auditoria do Supabase: {auditoria['status_geral']}.")
        return False
    return True


def main(argv: Optional[List[str]] = None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--markdown", action="store_true", help="Emite o relatório em formato Markdown.")
    parser.add_argument("--salvar-evidencia", action="store_true", help=f"Salva o relatório em {EVIDENCIA.relative_to(BASE_DIR)}")
    args = parser.parse_args(argv)

    url_supa = ler_variavel("SUPABASE_DATABASE_URL")
    if not url_supa:
        logger.error("Variável SUPABASE_DATABASE_URL não configurada no ambiente ou .env.")
        sys.exit(1)
    if not verificar(url_supa, database_url(), args.markdown, args.salvar_evidencia):
        sys.exit(1)


if __name__ == "__main__":
    main()
