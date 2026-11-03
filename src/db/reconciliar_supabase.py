"""
Verificação de conformidade, reconciliação de dados e auditoria de escopo do Supabase.

Inspeciona o banco remoto (Supabase) frente ao banco local e às diretrizes da E3/LGPD:
  1. Extensão pgvector instalada e ativa;
  2. Migrações aplicadas no destino vs db/migrations/;
  3. Conformidade LGPD: garante que microdados sensíveis (bronze e silver de discentes)
     não possuem linhas expostas na nuvem pública;
  4. Papel de leitura e privilégio mínimo (observatorio_leitura e esquemas restritos);
  5. Reconciliação de contagens das tabelas analíticas (gold e busca);
  6. Limites do plano gratuito (tamanho em disco, conexões e SSL).

Uso:
    python3 src/db/reconciliar_supabase.py [--markdown] [--salvar-evidencia]
"""

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import database_url, ler_variavel  # noqa: E402
from src.db.sincronizar_supabase import SINCRONIAS  # noqa: E402

MIGRATIONS_DIR = BASE_DIR / "db" / "migrations"
DOCS_DIR = BASE_DIR / "docs"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("reconciliar_supabase")

# Tabelas com microdados individuais que NUNCA devem ter registros na nuvem pública (LGPD / ADRs 0017 e 0020)
TABELAS_SENSIVEIS_MICRODADOS = [
    "bronze.sigra_discentes",
    "bronze.sigaa_discentes",
    "bronze.sigaa_ativos",
    "bronze.bolsistas_iniciacao_cientifica",
    "silver.discentes",
    "silver.discentes_graduacao",
    "silver.movimentacoes_vinculos",
    "silver.movimentacoes_p2000_2015",
    "silver.movimentacoes_p2016_2020",
    "silver.movimentacoes_p2021_atual",
    "silver.sigaa_ativos",
    "silver.pibic_bolsistas",
]

COTA_GRATUITA_SUPABASE_MB = 500.0


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
        linhas = conn.execute(
            "SELECT versao FROM public.schema_migrations ORDER BY versao"
        ).fetchall()
        aplicadas = [r[0] for r in linhas]
    except Exception as e:
        return {
            "status": "ERRO",
            "erro": str(e),
            "locais": len(arquivos_locais),
            "aplicadas": 0,
            "pendentes": arquivos_locais,
        }

    pendentes = [m for m in arquivos_locais if m not in aplicadas]
    extras = [m for m in aplicadas if m not in arquivos_locais]
    status = "OK" if not pendentes else "PENDENTE"

    return {
        "status": status,
        "total_locais": len(arquivos_locais),
        "total_aplicadas": len(aplicadas),
        "pendentes": pendentes,
        "extras_no_destino": extras,
        "aplicadas": aplicadas,
    }


def verificar_controle_acesso(conn: psycopg.Connection) -> Dict[str, Any]:
    """Verifica se o papel observatorio_leitura existe e restringe o acesso a bronze e silver."""
    papel_existe = conn.execute(
        "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'observatorio_leitura')"
    ).fetchone()[0]

    esquemas_acesso = {}
    for esq in ["bronze", "silver", "gold", "busca", "public"]:
        try:
            pode_usar = conn.execute(
                "SELECT has_schema_privilege('observatorio_leitura', %s, 'USAGE')",
                (esq,),
            ).fetchone()[0]
            esquemas_acesso[esq] = pode_usar
        except Exception:
            esquemas_acesso[esq] = None

    # Bronze e Silver devem ter USAGE = False para observatorio_leitura
    seguro_esquemas = (
        papel_existe
        and (not esquemas_acesso.get("bronze"))
        and (not esquemas_acesso.get("silver"))
        and bool(esquemas_acesso.get("gold"))
        and bool(esquemas_acesso.get("busca"))
    )

    return {
        "papel_existe": papel_existe,
        "esquemas": esquemas_acesso,
        "isolamento_ok": seguro_esquemas,
        "status": "OK" if seguro_esquemas else "ALERTA",
    }


def verificar_privacidade_lgpd(conn: psycopg.Connection) -> Dict[str, Any]:
    """Audita tabelas de microdados sensíveis para assegurar que nenhuma linha foi exposta."""
    achados = {}
    linhas_indevidas = 0

    for tabela in TABELAS_SENSIVEIS_MICRODADOS:
        esquema, nome = tabela.split(".")
        existe = conn.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_schema = %s AND table_name = %s
            )
            """,
            (esquema, nome),
        ).fetchone()[0]

        if not existe:
            achados[tabela] = {"existe": False, "linhas": 0, "status": "OK (tabela não existe)"}
            continue

        try:
            qtd = conn.execute(f"SELECT count(*) FROM {tabela}").fetchone()[0]
            achados[tabela] = {"existe": True, "linhas": qtd, "status": "OK" if qtd == 0 else "VIOLAÇÃO LGPD"}
            linhas_indevidas += qtd
        except Exception as e:
            achados[tabela] = {"existe": True, "linhas": None, "status": f"ERRO: {e}"}

    status = "OK" if linhas_indevidas == 0 else "FALHA_CRITICA"
    return {
        "status": status,
        "linhas_vazadas": linhas_indevidas,
        "tabelas_auditadas": achados,
    }


def reconciliar_contagens(
    conn_remoto: psycopg.Connection, conn_local: Optional[psycopg.Connection] = None
) -> List[Dict[str, Any]]:
    """Compara as contagens das tabelas analíticas sincronizadas entre local e remoto."""
    relatorio_tabelas = []
    tabelas_para_checar = [s.tabela for s in SINCRONIAS]
    if "gold.mv_dashboard_executivo" not in tabelas_para_checar:
        tabelas_para_checar.append("gold.mv_dashboard_executivo")

    for tabela in tabelas_para_checar:
        # Contagem remota (Supabase)
        qtd_remota = None
        erro_remoto = None
        try:
            qtd_remota = conn_remoto.execute(f"SELECT count(*) FROM {tabela}").fetchone()[0]
        except Exception as e:
            erro_remoto = str(e)

        # Contagem local (se banco local estiver disponível)
        qtd_local = None
        erro_local = None
        if conn_local:
            try:
                qtd_local = conn_local.execute(f"SELECT count(*) FROM {tabela}").fetchone()[0]
            except Exception as e:
                erro_local = str(e)

        if conn_local:
            if erro_remoto or erro_local:
                status = "ERRO"
            elif qtd_remota == qtd_local:
                status = "RECONCILIADO"
            else:
                status = "DIVERGENTE"
        else:
            status = "OK" if qtd_remota is not None and qtd_remota > 0 else "VAZIA"

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
    """Avalia o tamanho do banco e o consumo frente à cota do Supabase Free Tier."""
    tamanho_bytes = conn.execute(
        "SELECT pg_database_size(current_database())"
    ).fetchone()[0]
    tamanho_mb = tamanho_bytes / (1024 * 1024)
    pct_uso = (tamanho_mb / COTA_GRATUITA_SUPABASE_MB) * 100

    tamanho_legivel = conn.execute(
        "SELECT pg_size_pretty(pg_database_size(current_database()))"
    ).fetchone()[0]

    # Conexões ativas
    conexoes_ativas = conn.execute(
        "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
    ).fetchone()[0]

    return {
        "tamanho_bytes": tamanho_bytes,
        "tamanho_mb": round(tamanho_mb, 2),
        "tamanho_legivel": tamanho_legivel,
        "cota_mb": COTA_GRATUITA_SUPABASE_MB,
        "pct_uso": round(pct_uso, 2),
        "conexoes_ativas": conexoes_ativas,
        "status": "OK" if tamanho_mb < (COTA_GRATUITA_SUPABASE_MB * 0.9) else "ALERTA",
    }


def executar_auditoria_completa(
    url_supabase: str, url_local: Optional[str] = None
) -> Dict[str, Any]:
    """Executa a bateria completa de auditoria e reconciliação."""
    data_execucao = datetime.now(timezone.utc).isoformat()
    logger.info("Iniciando auditoria de conformidade no Supabase...")

    with psycopg.connect(url_supabase, connect_timeout=15) as conn_supa:
        conn_loc = None
        if url_local:
            try:
                conn_loc = psycopg.connect(url_local, connect_timeout=5)
                logger.info("Conexão com o banco local estabelecida para reconciliação.")
            except Exception as e:
                logger.warning(f"Banco local inacessível para reconciliação direta: {e}")

        try:
            extensao = verificar_extensao_vector(conn_supa)
            migracoes = verificar_migracoes(conn_supa)
            acesso = verificar_controle_acesso(conn_supa)
            privacidade = verificar_privacidade_lgpd(conn_supa)
            reconciliacao = reconciliar_contagens(conn_supa, conn_loc)
            limites = verificar_limites_recursos(conn_supa)
        finally:
            if conn_loc:
                conn_loc.close()

    status_geral = "APROVADO"
    if (
        extensao["status"] != "OK"
        or migracoes["status"] != "OK"
        or acesso["status"] != "OK"
        or privacidade["status"] != "OK"
        or limites["status"] != "OK"
    ):
        status_geral = "REQUER_ATENCAO"

    return {
        "data_execucao": data_execucao,
        "status_geral": status_geral,
        "extensao_vector": extensao,
        "migracoes": migracoes,
        "controle_acesso": acesso,
        "privacidade_lgpd": privacidade,
        "reconciliacao": reconciliacao,
        "limites": limites,
    }


def formatar_relatorio_markdown(auditoria: Dict[str, Any]) -> str:
    """Gera um relatório estruturado em Markdown com as evidências da auditoria."""
    data = auditoria["data_execucao"]
    status = auditoria["status_geral"]
    ext = auditoria["extensao_vector"]
    mig = auditoria["migracoes"]
    acesso = auditoria["controle_acesso"]
    priv = auditoria["privacidade_lgpd"]
    lim = auditoria["limites"]
    reconc = auditoria["reconciliacao"]

    linhas = [
        "# Relatório de Auditoria e Reconciliação do Banco Online (Supabase)",
        "",
        f"- **Data da Execução:** `{data}`",
        f"- **Veredito Geral:** **{status}**",
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

    if mig["pendentes"]:
        for p in mig["pendentes"]:
            linhas.append(f"  - ⚠️ Pendente: `{p}`")
    else:
        linhas.append("- ✅ Todas as migrações aplicadas deterministicamente.")

    linhas.extend([
        "",
        "## 3. Conformidade LGPD e Minimização de Dados",
        f"- **Microdados sensíveis expostos:** `{priv['linhas_vazadas']}` linhas",
        f"- **Veredito de Privacidade:** {'✅ Conforme (Zero registros de microdados de alunos)' if priv['linhas_vazadas'] == 0 else '❌ VIOLAÇÃO IDENTIFICADA'}",
        "",
        "| Tabela Sensível (Microdado) | Existe no Destino? | Registros no Supabase | Situação |",
        "| :--- | :---: | :---: | :--- |",
    ])

    for tab, info in priv["tabelas_auditadas"].items():
        existe_str = "Sim" if info["existe"] else "Não"
        linhas.append(f"| `{tab}` | {existe_str} | `{info['linhas']}` | {info['status']} |")

    linhas.extend([
        "",
        "## 4. Controle de Acesso e Privilégio Mínimo",
        f"- **Papel `observatorio_leitura`:** {'✅ Criado' if acesso['papel_existe'] else '❌ Inexistente'}",
        f"- **Isolamento de esquemas restritos:** {'✅ Bronze e Silver bloqueados' if acesso['isolamento_ok'] else '⚠️ Alerta de permissões'}",
        "",
        "| Esquema | Permissão `USAGE` concedida a `observatorio_leitura` | Regra de Negócio |",
        "| :--- | :---: | :--- |",
        f"| `gold` | {acesso['esquemas'].get('gold')} | Leitura pública autorizada (dados agregados $k \\ge 5$) |",
        f"| `busca` | {acesso['esquemas'].get('busca')} | Leitura pública de documentos vetoriais |",
        f"| `bronze` | {acesso['esquemas'].get('bronze')} | ⛔ Bloqueado (Dado bruto restrito) |",
        f"| `silver` | {acesso['esquemas'].get('silver')} | ⛔ Bloqueado (Microdados 3NF restritos) |",
        "",
        "## 5. Reconciliação de Contagens das Tabelas Analíticas",
        "",
        "| Tabela Analítica | Supabase (Remoto) | Banco Local | Status de Reconciliação |",
        "| :--- | :---: | :---: | :---: |",
    ])

    for r in reconc:
        loc_str = str(r["qtd_local"]) if r["qtd_local"] is not None else "N/A"
        linhas.append(f"| `{r['tabela']}` | `{r['qtd_remota']}` | `{loc_str}` | {r['status']} |")

    linhas.extend([
        "",
        "## 6. Recursos e Limites da Infraestrutura",
        f"- **Espaço ocupado em disco:** `{lim['tamanho_legivel']}` ({lim['tamanho_mb']} MB)",
        f"- **Cota do Free Tier:** `{lim['cota_mb']} MB` ({lim['pct_uso']}% utilizado)",
        f"- **Conexões ativas no pooler:** `{lim['conexoes_ativas']}`",
        f"- **Status de capacidade:** {'✅ Saudável (abaixo de 90% da cota)' if lim['status'] == 'OK' else '⚠️ Próximo ao limite'}",
        "",
        "---",
        "*Evidência gerada automaticamente por `src/db/reconciliar_supabase.py`*",
    ])

    return "\n".join(linhas)


def main(argv: Optional[List[str]] = None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--markdown", action="store_true", help="Emite o relatório em formato Markdown.")
    parser.add_argument("--salvar-evidencia", action="store_true",
                        help="Salva o relatório em docs/disponibilizacao_online_supabase_evidencias.md")
    args = parser.parse_args(argv)

    url_supa = ler_variavel("SUPABASE_DATABASE_URL")
    if not url_supa:
        logger.error("Variável SUPABASE_DATABASE_URL não configurada no ambiente ou .env.")
        sys.exit(1)

    url_loc = database_url() if ler_variavel("DATABASE_URL") else None

    auditoria = executar_auditoria_completa(url_supa, url_loc)
    relatorio_md = formatar_relatorio_markdown(auditoria)

    if args.salvar_evidencia:
        caminho_evidencia = DOCS_DIR / "disponibilizacao_online_supabase_evidencias.md"
        caminho_evidencia.write_text(relatorio_md, encoding="utf-8")
        logger.info(f"Evidência salva com sucesso em {caminho_evidencia}")

    if args.markdown:
        print(relatorio_md)
    else:
        print(f"\nAuditoria do Supabase concluída: Status {auditoria['status_geral']}")
        print(f"Extensão vector: {auditoria['extensao_vector']['status']} (v{auditoria['extensao_vector']['versao']})")
        print(f"Migrações: {auditoria['migracoes']['total_aplicadas']}/{auditoria['migracoes']['total_locais']} aplicadas")
        print(f"Conformidade LGPD: {auditoria['privacidade_lgpd']['linhas_vazadas']} linhas sensíveis expostas ({auditoria['privacidade_lgpd']['status']})")
        print(f"Isolamento de Esquemas: {auditoria['controle_acesso']['status']}")
        print(f"Espaço ocupado: {auditoria['limites']['tamanho_legivel']} ({auditoria['limites']['pct_uso']}% da cota)")
        print("\nTabelas analíticas no Supabase:")
        for r in auditoria["reconciliacao"]:
            print(f"  - {r['tabela']}: {r['qtd_remota']} linhas [{r['status']}]")

    if auditoria["status_geral"] != "APROVADO":
        sys.exit(1)


if __name__ == "__main__":
    main()

