"""
Orquestração do pipeline em Dagster (ADR 0030, issue #40).

Cada etapa de scripts/rodar_pipeline.sh vira um asset que roda o mesmo script: a lógica continua
em src/, e aqui fica só o grafo de dependências, o retry de cada etapa e as partições do backfill.
Este grafo é a fonte da verdade da ordem das etapas: é ele que roda no agendamento mensal e no CI.
O rodar_pipeline.sh fica para o Docker e para quem roda sem o Dagster, e um teste
(tests/test_unit_orquestracao.py) acusa se os dois deixarem de chamar os mesmos scripts.
Os modelos do dbt (transform/) entram no grafo um a um, pelo dagster-dbt, e os testes do dbt viram
checagens dos assets.

  pipeline_mensal  todas as etapas, do portal ao Supabase. Agendado no dia 1 de cada mês; no CI, o
                   atualiza-dados.yml dispara o mesmo job (`dagster job execute`).
  backfill_lago    reprocessa janelas (quinquênios de ingresso) dos vínculos no lago Delta, uma
                   partição por quinquênio (ADR 0024 e 0026).

Uso:
    dagster dev -m orquestracao                               # UI em http://localhost:3000
    dagster job execute -m orquestracao -j pipeline_mensal
    dagster asset materialize -m orquestracao --select lago_vinculos_por_quinquenio \
        --partition-range "$(python -c 'from orquestracao.definicoes import INTERVALO_BACKFILL as i; print(i)')"

Retry, falha forçada e backfill demonstrados em docs/orquestracao.md.
"""

import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from dagster import (
    AssetExecutionContext,
    AssetKey,
    AssetSpec,
    Backoff,
    BackfillPolicy,
    DefaultScheduleStatus,
    Definitions,
    Failure,
    RetryPolicy,
    ScheduleDefinition,
    StaticPartitionsDefinition,
    asset,
    define_asset_job,
    in_process_executor,
    MaterializeResult,
    multi_asset,
)
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, dbt_assets

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import variaveis_dbt  # noqa: E402

# O dbt lê a conexão destas variáveis (transform/profiles.yml), as mesmas de scripts/dbt.sh.
for _nome, _valor in variaveis_dbt().items():
    os.environ.setdefault(_nome, _valor)

DBT_DIR = BASE_DIR / "transform"
MANIFEST = DBT_DIR / "target" / "manifest.json"

# Banco e rede caem por instantes: três novas tentativas. A espera é exponencial e conta entre uma
# tentativa e a seguinte (não é acumulada): 10, 30 e 70 s depois de cada falha (docs/orquestracao.md).
# O portal CKAN, mais instável, espera mais: 30, 90 e 210 s.
RETRY_BANCO = RetryPolicy(max_retries=3, delay=10, backoff=Backoff.EXPONENTIAL)
RETRY_PORTAL = RetryPolicy(max_retries=3, delay=30, backoff=Backoff.EXPONENTIAL)

# Uma etapa travada (rede pendurada, lock no banco) vira falha depois de 1 h, e o retry assume.
TEMPO_MAXIMO_ETAPA = 3600

# Quinquênios de ingresso dos vínculos, a partição do lago (ADR 0024): de 2000 ao atual. O intervalo
# completo, para o backfill de todas as janelas, cresce sozinho com o ano (usado no medalhao.yml).
QUINQUENIOS = StaticPartitionsDefinition([str(q) for q in range(2000, date.today().year + 1, 5)])
INTERVALO_BACKFILL = f"{QUINQUENIOS.get_partition_keys()[0]}...{QUINQUENIOS.get_partition_keys()[-1]}"


def rodar(context: AssetExecutionContext, script: str, *argumentos: str, tolerar_falha: bool = False) -> None:
    """Roda um script do pipeline com o mesmo Python do Dagster e leva a saída para o log do asset.

    Saída diferente de zero, ou mais de TEMPO_MAXIMO_ETAPA rodando, levanta Failure, e o Dagster
    aplica o retry do asset. Com tolerar_falha, a falha vira aviso: é o `|| echo AVISO` do
    rodar_pipeline.sh, para fontes que caem com frequência.
    """
    comando = [sys.executable, script, *argumentos]
    context.log.info(f"Rodando {' '.join(comando[1:])} (tentativa {context.retry_number + 1})")
    try:
        resultado = subprocess.run(comando, cwd=BASE_DIR, capture_output=True, text=True, timeout=TEMPO_MAXIMO_ETAPA)
    except subprocess.TimeoutExpired:
        if tolerar_falha:
            context.log.warning(f"{script} passou de {TEMPO_MAXIMO_ETAPA} s; seguindo sem atualizar esta fonte.")
            return
        raise Failure(f"{script} passou de {TEMPO_MAXIMO_ETAPA} s e foi interrompido")
    saida = (resultado.stdout + resultado.stderr).strip()
    if saida:
        context.log.info(saida[-4000:])
    if resultado.returncode != 0:
        if tolerar_falha:
            context.log.warning(f"{script} falhou (código {resultado.returncode}); seguindo sem atualizar esta fonte.")
            return
        raise Failure(f"{script} terminou com código {resultado.returncode}", metadata={"saida": saida[-2000:]})


# --- Ingestão --------------------------------------------------------------------------------

@asset(group_name="ingestao", retry_policy=RETRY_BANCO, description="Migrações do esquema (db/migrations).")
def migracoes(context: AssetExecutionContext) -> None:
    rodar(context, "src/db/migrar.py")


@asset(group_name="ingestao", deps=[migracoes], retry_policy=RETRY_PORTAL,
       description="Bronze: arquivos do portal dados.unb.br pela API CKAN.")
def bronze_ckan(context: AssetExecutionContext) -> None:
    rodar(context, "src/ingestion/ckan_client.py")


@asset(group_name="ingestao", deps=[migracoes], retry_policy=RETRY_PORTAL,
       description="Bronze: Censo da Educação Superior (INEP). O servidor cai com frequência; sem ele, segue o benchmark anterior.")
def bronze_inep(context: AssetExecutionContext) -> None:
    rodar(context, "src/ingestion/inep_censo_superior.py", tolerar_falha=True)


@asset(group_name="ingestao", deps=[migracoes], retry_policy=RETRY_PORTAL,
       description="Bronze: valor da bolsa IC no CNPq. Sem ele, valem as vigências versionadas.")
def bronze_cnpq(context: AssetExecutionContext) -> None:
    rodar(context, "src/ingestion/cnpq_valor_bolsa.py", tolerar_falha=True)


# --- Silver e gold ---------------------------------------------------------------------------

@asset(group_name="silver", deps=[bronze_ckan, bronze_inep, bronze_cnpq], retry_policy=RETRY_BANCO,
       description="Silver: limpeza, tipagem e normalização.")
def silver(context: AssetExecutionContext) -> None:
    rodar(context, "src/pipeline/transform_silver.py")


@asset(group_name="gold", deps=[silver], retry_policy=RETRY_BANCO, description="Gold tabular e joins heterogêneos.")
def gold_tabular(context: AssetExecutionContext) -> None:
    rodar(context, "src/pipeline/build_gold.py")


@asset(group_name="qualidade", deps=[silver], retry_policy=RETRY_BANCO, description="Auditoria de qualidade.")
def auditoria_qualidade(context: AssetExecutionContext) -> None:
    rodar(context, "src/audit/quality_auditor.py")


@asset(group_name="qualidade", deps=[silver], retry_policy=RETRY_BANCO, description="Privacidade: k-anonimato.")
def privacidade(context: AssetExecutionContext) -> None:
    rodar(context, "src/privacy/lgpd_check.py")


# O que src/db/povoar_dimensional.py grava, numa transação só: a Silver 3NF e o star schema da gold.
# As chaves batem com as fontes do dbt (transform/models/staging/_fontes.yml), e é assim que os
# modelos do dbt ficam ligados a esta etapa no grafo.
TABELAS_STAR_SCHEMA = [
    AssetKey(["silver", "cursos"]), AssetKey(["silver", "estruturas_curriculares"]),
    AssetKey(["silver", "movimentacoes_vinculos"]),
    AssetKey(["gold", "dim_campus"]), AssetKey(["gold", "dim_curso"]), AssetKey(["gold", "dim_tempo"]),
    AssetKey(["gold", "dim_perfil_social"]), AssetKey(["gold", "fato_retencao_curso"]),
    AssetKey(["gold", "fato_alunos_ativos"]), AssetKey(["gold", "fato_pibic_perfil"]),
]


@multi_asset(
    name="star_schema", group_name="gold", retry_policy=RETRY_BANCO,
    specs=[AssetSpec(chave, deps=[gold_tabular, auditoria_qualidade, privacidade]) for chave in TABELAS_STAR_SCHEMA],
    description="Silver 3NF e star schema da gold (SCD tipo 2 na dim_curso).",
)
def star_schema(context: AssetExecutionContext):
    rodar(context, "src/db/povoar_dimensional.py")
    for chave in TABELAS_STAR_SCHEMA:
        yield MaterializeResult(asset_key=chave)


@asset(group_name="consumo", deps=TABELAS_STAR_SCHEMA, retry_policy=RETRY_BANCO,
       description="REFRESH CONCURRENTLY da gold.mv_dashboard_executivo.")
def view_painel(context: AssetExecutionContext) -> None:
    rodar(context, "src/db/atualizar_view_painel.py")


# --- dbt -------------------------------------------------------------------------------------

class TradutorDbt(DagsterDbtTranslator):
    """Os modelos do dbt num grupo próprio. As fontes ficam com a chave padrão (esquema, tabela), que
    é a das tabelas gravadas pelo star_schema."""

    def get_group_name(self, dbt_resource_props):
        return "transformacao_dbt"


def manifest_desatualizado() -> bool:
    """Sem manifest, ou com algum arquivo do projeto dbt mais novo que ele (modelo, teste ou macro
    editado depois do último parse): os assets montados a partir dele não bateriam com o dbt."""
    if not MANIFEST.exists():
        return True
    fontes = [DBT_DIR / "dbt_project.yml",
              *(p for pasta in ("models", "tests", "macros") for p in (DBT_DIR / pasta).rglob("*") if p.is_file())]
    return any(p.stat().st_mtime > MANIFEST.stat().st_mtime for p in fontes)


def preparar_manifest() -> Path:
    """O dagster-dbt monta os assets a partir do manifest; desatualizado ou ausente, roda `dbt parse`."""
    if manifest_desatualizado():
        subprocess.run(["bash", "scripts/dbt.sh", "parse", "--quiet"], cwd=BASE_DIR, check=True,
                       capture_output=True, text=True)
    return MANIFEST


@dbt_assets(manifest=preparar_manifest(), dagster_dbt_translator=TradutorDbt(), retry_policy=RETRY_BANCO)
def camadas_dbt(context: AssetExecutionContext, dbt: DbtCliResource):
    yield from dbt.cli(["build", "--full-refresh"], context=context).stream()


# --- Publicação ------------------------------------------------------------------------------

@asset(group_name="publicacao", deps=TABELAS_STAR_SCHEMA, retry_policy=RETRY_BANCO,
       description="Lago Delta: só as tabelas e as janelas que mudaram desde a última exportação.")
def lago(context: AssetExecutionContext) -> None:
    rodar(context, "src/db/exportar_lago.py", "--janelas-alteradas")


@asset(group_name="publicacao", deps=TABELAS_STAR_SCHEMA, retry_policy=RETRY_BANCO, partitions_def=QUINQUENIOS,
       backfill_policy=BackfillPolicy.single_run(),
       description="Janelas (quinquênios de ingresso) dos vínculos no lago Delta, cada uma regravada inteira. "
                   "É o reprocessamento de janela do ADR 0026, e o alvo do backfill: um intervalo de "
                   "partições vira uma execução só, com um overwrite por janela.")
def lago_vinculos_por_quinquenio(context: AssetExecutionContext) -> None:
    janelas = [arg for q in context.partition_keys for arg in ("--quinquenio", q)]
    rodar(context, "src/db/exportar_lago.py", *janelas)


@asset(group_name="publicacao", deps=[gold_tabular], retry_policy=RETRY_BANCO, description="Busca semântica.")
def vetorizacao(context: AssetExecutionContext) -> None:
    rodar(context, "src/busca/vetorizar.py")


@asset(group_name="publicacao", deps=[camadas_dbt, view_painel], retry_policy=RETRY_BANCO,
       description="Dicionário de dados gerado do catálogo do banco.")
def dicionario(context: AssetExecutionContext) -> None:
    rodar(context, "src/db/gerar_dicionario.py")


@asset(group_name="publicacao", deps=[view_painel, vetorizacao, dicionario, lago], retry_policy=RETRY_PORTAL,
       description="Sincronização incremental da gold com o Supabase. Pulada sem SUPABASE_DATABASE_URL.")
def supabase(context: AssetExecutionContext) -> None:
    rodar(context, "src/db/sincronizar_supabase.py")


# --- Jobs, agenda e definições ---------------------------------------------------------------

pipeline_mensal = define_asset_job(
    "pipeline_mensal",
    selection=[migracoes, bronze_ckan, bronze_inep, bronze_cnpq, silver, gold_tabular, auditoria_qualidade,
               privacidade, star_schema, view_painel, camadas_dbt, lago, vetorizacao, dicionario, supabase],
    description="Pipeline completo, do portal ao Supabase, na ordem do grafo.",
)

backfill_lago = define_asset_job(
    "backfill_lago", selection=[lago_vinculos_por_quinquenio], partitions_def=QUINQUENIOS,
    description="Reprocessa janelas de vínculos no lago, uma partição por quinquênio.",
)

# Mesmo horário do atualiza-dados.yml. Ligada só quando o daemon do Dagster está no ar (dagster dev);
# no GitHub Actions, o cron do workflow dispara o job.
agenda_mensal = ScheduleDefinition(
    job=pipeline_mensal, cron_schedule="0 6 1 * *", execution_timezone="UTC",
    default_status=DefaultScheduleStatus.RUNNING,
)

defs = Definitions(
    assets=[migracoes, bronze_ckan, bronze_inep, bronze_cnpq, silver, gold_tabular, auditoria_qualidade,
            privacidade, star_schema, view_painel, camadas_dbt, lago, lago_vinculos_por_quinquenio,
            vetorizacao, dicionario, supabase],
    jobs=[pipeline_mensal, backfill_lago],
    schedules=[agenda_mensal],
    resources={"dbt": DbtCliResource(project_dir=str(DBT_DIR), profiles_dir=str(DBT_DIR))},
    # Uma etapa por vez, no mesmo processo: o pipeline divide um banco só, e as etapas pesadas
    # (silver, vetorização) disputariam memória no runner do CI.
    executor=in_process_executor,
)
