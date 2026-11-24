"""
Catálogo e linhagem da plataforma, da fonte pública ao consumo.

O dbt desenha a linhagem da Silver 3NF em diante (manifest.json, publicado no dbt docs). O trecho
antes dele, portal -> bronze -> silver -> Silver 3NF e gold, é feito por scripts Python e por funções
SQL que o dbt não enxerga. Este módulo junta os dois:

  - ETAPAS declara, para cada tabela gravada fora do dbt, de onde ela lê e qual script a grava;
  - as fontes do portal saem de src/ingestion/ckan_client.py (DATASETS_CONFIG), as mesmas que a
    ingestão baixa;
  - o resto (staging, intermediate, marts, seeds, snapshot e os consumidores, as exposures) sai do
    manifest do dbt;
  - TRILHAS segue colunas do painel, uma a uma, até a coluna do arquivo do portal.

O resultado é docs/catalogo/linhagem.md: o grafo (Mermaid), o catálogo de ativos (camada, quem grava,
se tem dado pessoal, quem pode ler) e as trilhas de coluna.

--verificar não confia na declaração: confere que cada script de ETAPAS cita as tabelas que a declaração
diz que ele lê e grava, que toda fonte do dbt tem uma etapa que a grava (a linhagem não para no meio),
que todo consumidor do dbt chega a uma fonte pública, e que o documento gerado está em dia. Com o banco
no ar, confere também que toda coluna das trilhas existe. Roda no CI (medalhao.yml) e nos testes.

Uso:
    python3 src/governanca/linhagem.py              # regrava docs/catalogo/linhagem.md
    python3 src/governanca/linhagem.py --verificar  # falha se a declaração ou o documento divergirem
"""

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.ingestion.ckan_client import DATASETS_CONFIG  # noqa: E402

MANIFEST = BASE_DIR / "transform" / "target" / "manifest.json"
SAIDA = BASE_DIR / "docs" / "catalogo" / "linhagem.md"
PORTAL_UNB = "https://dados.unb.br/dataset/"


# --- Fontes públicas ------------------------------------------------------------------------------

@dataclass(frozen=True)
class Fonte:
    chave: str          # nó do grafo: "portal:<chave>"
    nome: str
    url: str
    grava_em: str       # tabela bronze (ou arquivo) que recebe o recurso
    script: str


def fontes_publicas() -> List[Fonte]:
    """As fontes do portal da UnB vêm da própria configuração da ingestão, mais INEP e CNPq."""
    fontes = [
        Fonte(f"portal:{chave}", f"dados.unb.br: {cfg['package_id']} ({cfg['resource_pattern']})",
              PORTAL_UNB + cfg["package_id"], cfg["tabela"], "src/ingestion/ckan_client.py")
        for chave, cfg in DATASETS_CONFIG.items()
    ]
    fontes.append(Fonte("portal:inep_censo_2019", "INEP: microdados do Censo da Educação Superior 2019",
                        "https://download.inep.gov.br/microdados/microdados_censo_da_educacao_superior_2019.zip",
                        "bronze.inep_censo_superior_federais", "src/ingestion/inep_censo_superior.py"))
    fontes.append(Fonte("portal:cnpq_bolsas", "CNPq: tabela de valores de bolsas no país",
                        "https://www.gov.br/cnpq/pt-br/acesso-a-informacao/acoes-e-programas/bolsas/valores-de-bolsas",
                        "data/bronze/cnpq_valor_bolsa_ic.json", "src/ingestion/cnpq_valor_bolsa.py"))
    return fontes


# --- Etapas fora do dbt ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Etapa:
    destino: str
    origens: Tuple[str, ...]
    script: str
    # Arquivos onde a lógica está escrita, além do script (funções SQL das migrações).
    logica: Tuple[str, ...] = ()
    nota: str = ""


ETAPAS: Tuple[Etapa, ...] = (
    # Bronze -> silver tabular (src/pipeline/transform_silver.py)
    Etapa("silver.discentes_graduacao", ("bronze.sigra_discentes", "bronze.sigaa_discentes"),
          "src/pipeline/transform_silver.py",
          nota="SIGRA e SIGAA unidos; desfecho e permanência derivados (ADR 0012, 0013, 0015)"),
    Etapa("silver.sigaa_ativos", ("bronze.sigaa_ativos",), "src/pipeline/transform_silver.py"),
    Etapa("silver.estrutura_curricular", ("bronze.estrutura_curricular",), "src/pipeline/transform_silver.py",
          nota="uma matriz por curso: mediana das versões"),
    Etapa("silver.cursos_graduacao", ("bronze.cursos_graduacao",), "src/pipeline/transform_silver.py",
          nota="todas as versões do catálogo, a mais recente valendo (ADR 0021)"),
    Etapa("silver.pibic_bolsistas", ("bronze.bolsistas_iniciacao_cientifica", "data/bronze/cnpq_valor_bolsa_ic.json"),
          "src/pipeline/transform_silver.py", nota="valor da bolsa pela vigência do CNPq (ADR 0023)"),
    Etapa("silver.inep_censo_superior", ("bronze.inep_censo_superior_federais",), "src/pipeline/transform_silver.py"),

    # Gold tabular (src/pipeline/build_gold.py -> gold.atualizar_gold, migração 0022)
    Etapa("gold.regras_harmonizacao_canonicas", (), "src/pipeline/build_gold.py",
          nota="regras de negócio no código (CANONICAL_RULES_METADATA, ADR 0003)"),
    Etapa("gold.retencao_cursos_unb",
          ("silver.discentes_graduacao", "silver.estrutura_curricular", "silver.cursos_graduacao",
           "silver.pibic_bolsistas", "gold.regras_harmonizacao_canonicas"),
          "src/pipeline/build_gold.py", ("db/migrations/0022_gold_agregacoes_sql.sql",)),
    Etapa("gold.ativos_hoje_cursos_unb",
          ("silver.sigaa_ativos", "silver.estrutura_curricular", "gold.regras_harmonizacao_canonicas"),
          "src/pipeline/build_gold.py", ("db/migrations/0022_gold_agregacoes_sql.sql",)),
    Etapa("gold.pibic_social_unb",
          ("silver.pibic_bolsistas", "silver.cursos_graduacao", "gold.regras_harmonizacao_canonicas"),
          "src/pipeline/build_gold.py", ("db/migrations/0022_gold_agregacoes_sql.sql",)),
    Etapa("gold.inep_benchmark_cursos_unb", ("silver.inep_censo_superior",),
          "src/pipeline/build_gold.py", ("db/migrations/0022_gold_agregacoes_sql.sql",)),

    # Silver 3NF (o OLTP modelado na E1), src/db/povoar_silver_3nf.py
    Etapa("silver.cursos", ("silver.cursos_graduacao",), "src/db/povoar_silver_3nf.py"),
    Etapa("silver.estruturas_curriculares", ("silver.estrutura_curricular",), "src/db/povoar_silver_3nf.py"),
    Etapa("silver.discentes", ("silver.discentes_graduacao",), "src/db/povoar_silver_3nf.py",
          nota="nascimento, sexo e raça/cor por pseudônimo; não sai da silver"),
    Etapa("silver.movimentacoes_vinculos",
          ("silver.discentes_graduacao", "silver.discentes", "silver.estruturas_curriculares",
           "gold.regras_harmonizacao_canonicas"),
          "src/db/povoar_silver_3nf.py", nota="curso do vínculo pela harmonização canônica"),

    # Star schema da gold (src/db/povoar_dimensional.py), lido pelo lago Delta
    Etapa("gold.dim_curso", ("silver.cursos", "silver.estruturas_curriculares"), "src/db/povoar_dimensional.py",
          nota="SCD tipo 2 (ADR 0028)"),
    Etapa("gold.dim_campus", ("silver.cursos",), "src/db/povoar_dimensional.py"),
    Etapa("gold.fato_retencao_curso", ("silver.movimentacoes_vinculos", "silver.estruturas_curriculares",
                                       "gold.dim_curso", "gold.dim_campus"), "src/db/povoar_dimensional.py"),

    # ETL reverso: o analítico volta ao operacional
    Etapa("operacional.fila_intervencao", ("dbt_marts.painel_cursos_criticos", "dbt_marts.metricas_definicoes"),
          "src/etl_reverso/fila_intervencao.py", ("db/migrations/0027_fila_intervencao.sql",),
          nota="fila que a coordenação opera; o andamento é dela, as métricas são do ETL reverso"),
)


# --- Catálogo: dado pessoal e acesso por esquema ---------------------------------------------------

# Quem lê cada esquema (migração 0006, transform/dbt_project.yml, migração 0027).
ACESSO_POR_ESQUEMA = {
    "bronze": "só o dono do banco",
    "silver": "só o dono do banco",
    "dbt_staging": "só o dono do banco",
    "dbt_intermediate": "só o dono do banco",
    "dbt_snapshots": "só o dono do banco",
    "gold": "observatorio_leitura (painel, Supabase)",
    "dbt_marts": "observatorio_leitura (painel, Supabase)",
    "operacional": "coordenacao_academica (lê; grava só o andamento)",
}

# Tabelas com registro de pessoa (mesmo pseudonimizado). As demais são catálogo ou agregado (k >= 5).
DADO_PESSOAL = {
    "bronze.sigra_discentes": "pseudônimo, nascimento, sexo, raça/cor, curso e saída",
    "bronze.sigaa_discentes": "pseudônimo, nascimento, sexo, raça/cor, curso e situação",
    "bronze.sigaa_ativos": "um registro por aluno ativo (só grau, curso e ingresso)",
    "bronze.bolsistas_iniciacao_cientifica": "um registro por plano de IC (sem nome nem matrícula)",
    "silver.discentes_graduacao": "pseudônimo, nascimento, sexo, raça/cor e vínculo",
    "silver.sigaa_ativos": "um registro por aluno ativo",
    "silver.pibic_bolsistas": "um registro por plano de IC, com cota e faixa de renda",
    "silver.discentes": "nascimento, sexo e raça/cor por pseudônimo",
    "silver.movimentacoes_vinculos": "um vínculo por linha, com id_discente",
    "dbt_staging.stg_vinculos": "um vínculo por linha, sem id_discente",
    "dbt_intermediate.int_coortes_maduras": "um vínculo por linha, sem id_discente",
}


# --- Trilhas de coluna: do painel à fonte pública -------------------------------------------------

@dataclass(frozen=True)
class Passo:
    ativo: str           # "esquema.tabela" ou "portal:<chave>"
    coluna: Optional[str]
    como: str


@dataclass(frozen=True)
class Trilha:
    rotulo: str          # como aparece no painel
    passos: Tuple[Passo, ...] = field(default_factory=tuple)


_VINCULO_ATE_A_FONTE = (
    Passo("silver.movimentacoes_vinculos", "tipo_saida_grupo", "cópia (src/db/povoar_silver_3nf.py)"),
    Passo("silver.discentes_graduacao", "tipo_saida_grupo",
          "SIGRA: categorize_forma_saida(forma_saida); SIGAA: STATUS_SIGAA_GRUPO[status_aluno] "
          "(src/pipeline/transform_silver.py, ADR 0013)"),
    Passo("bronze.sigra_discentes", "forma_saida", "texto como veio do portal"),
    Passo("bronze.sigaa_discentes", "status_aluno", "texto como veio do portal"),
    Passo("portal:sigra", None, "sigra.csv"),
    Passo("portal:sigaa", None, "sigaa.csv"),
)

TRILHAS: Tuple[Trilha, ...] = (
    Trilha("Evasão (%)", (
        Passo("operacional.fila_intervencao", "taxa_evasao_pct", "copiada pelo ETL reverso; lida pela coordenação"),
        Passo("dbt_marts.painel_cursos_criticos", "taxa_evasao_pct", "lida pelo painel (Visão Executiva) e pelo ETL reverso"),
        Passo("dbt_marts.fct_retencao_curso", "taxa_evasao_pct", "cópia"),
        Passo("dbt_intermediate.int_metricas_curso", "taxa_evasao_pct",
              "metrica_taxa_evasao_pct(evadidos, ingressantes), transform/macros/metricas.sql"),
        Passo("dbt_intermediate.int_bases_curso", "evadidos",
              "count(*) where tipo_saida_grupo = 'EVASAO', coortes maduras (ADR 0014), k >= 5"),
        Passo("dbt_staging.stg_vinculos", "tipo_saida_grupo", "renomeia e tipa"),
        *_VINCULO_ATE_A_FONTE,
    )),
    Trilha("Atraso médio (sem.)", (
        Passo("dbt_marts.painel_cursos_criticos", "atraso_medio_semestres", "lida pelo painel e pela fila"),
        Passo("dbt_intermediate.int_metricas_curso", "atraso_medio_semestres",
              "metrica_atraso_medio_semestres(soma_atraso, formados_com_atraso)"),
        Passo("dbt_intermediate.int_bases_curso", "soma_atraso",
              "sum(semestres_permanencia_valida - semestre_ideal) dos formados"),
        Passo("dbt_staging.stg_vinculos", "semestres_permanencia_valida", "renomeia e tipa"),
        Passo("silver.movimentacoes_vinculos", "semestres_permanencia_valida", "cópia"),
        Passo("silver.discentes_graduacao", "semestres_permanencia_valida",
              "2 x (ano_saida - ano_ingresso) + semestre_saida, só entre 1 e 30 (transform_silver._permanencia)"),
        Passo("bronze.sigra_discentes", "periodo_saida", "SIGRA: período de saída, ex. 20141"),
        Passo("bronze.sigaa_discentes", "data_registro_diploma", "SIGAA: semestre estimado pela data do diploma (ADR 0015)"),
        Passo("dbt_staging.stg_estruturas_curriculares", "semestre_ideal", "prazo ideal da matriz"),
        Passo("silver.estruturas_curriculares", "semestre_ideal", "cópia (povoar_silver_3nf.py)"),
        Passo("silver.estrutura_curricular", "semestre_conclusao_ideal", "mediana entre as versões da matriz"),
        Passo("bronze.estrutura_curricular", "semestre_conclusao_ideal", "como veio do portal"),
        Passo("portal:sigra", None, "sigra.csv"),
        Passo("portal:sigaa", None, "sigaa.csv"),
        Passo("portal:estrutura_curricular", None, "estrutura-curricular.csv"),
    )),
    Trilha("IRC e Classificação", (
        Passo("dbt_marts.painel_cursos_criticos", "indice_retencao_critica", "lida pelo painel e pela fila"),
        Passo("dbt_intermediate.int_irc_curso", "indice_retencao_critica",
              "(0,3 x atraso + 0,7 x evasão) x 100, saturados em p5/p95 e normalizados (ADR 0006); "
              "classificação pelos quartis"),
        Passo("dbt_intermediate.int_metricas_curso", "taxa_evasao_pct", "ver a trilha da Evasão"),
        Passo("dbt_intermediate.int_metricas_curso", "atraso_medio_semestres", "ver a trilha do Atraso"),
    )),
    Trilha("Ingressantes", (
        Passo("dbt_marts.painel_cursos_criticos", "total_ingressantes", "lida pelo painel e pela fila"),
        Passo("dbt_intermediate.int_bases_curso", "ingressantes", "count(*) dos vínculos das coortes maduras"),
        Passo("dbt_intermediate.int_coortes_maduras", "nome_curso",
              "vínculos com ano_ingresso <= último ano da base - 8 (ADR 0014)"),
        Passo("dbt_staging.stg_vinculos", "ano_ingresso", "renomeia e tipa"),
        Passo("silver.movimentacoes_vinculos", "ano_ingresso", "cópia"),
        Passo("silver.discentes_graduacao", "ano_ingresso", "numérico; SIGAA sem o separador de milhar"),
        Passo("bronze.sigra_discentes", "ano_ingresso", "como veio do portal"),
        Passo("bronze.sigaa_discentes", "ano_ingresso", "como veio do portal (\"2,010\")"),
        Passo("portal:sigra", None, "sigra.csv"),
        Passo("portal:sigaa", None, "sigaa.csv"),
    )),
    Trilha("Curso", (
        Passo("dbt_marts.painel_cursos_criticos", "nome_curso", "lida pelo painel e pela fila"),
        Passo("dbt_marts.dim_curso", "nome_curso", "versão atual do curso (SCD tipo 2)"),
        Passo("dbt_staging.stg_estruturas_curriculares", "nome_curso", "nome canônico da matriz"),
        Passo("silver.estruturas_curriculares", "nome_curso_canonico", "cópia"),
        Passo("silver.estrutura_curricular", "nome_curso_norm", "normalize_curso(nome_curso)"),
        Passo("bronze.estrutura_curricular", "nome_curso", "como veio do portal"),
        Passo("gold.regras_harmonizacao_canonicas", "destino_estrutura",
              "liga o curso do vínculo (SIGRA/SIGAA) ao nome canônico (ADR 0003)"),
        Passo("silver.discentes_graduacao", "curso_norm", "nome do curso no vínculo, normalizado"),
        Passo("portal:estrutura_curricular", None, "estrutura-curricular.csv"),
        Passo("portal:sigra", None, "sigra.csv (curso do vínculo)"),
    )),
    Trilha("Campus", (
        Passo("dbt_marts.painel_cursos_criticos", "campus", "lida pelo painel e pela fila"),
        Passo("dbt_marts.dim_campus", "campus", "com MULTICAMPUS"),
        Passo("dbt_intermediate.int_campus_do_curso", "campus", "MULTICAMPUS se o nome é oferecido em mais de um"),
        Passo("dbt_staging.stg_cursos", "campus", "renomeia"),
        Passo("silver.cursos", "campus", "campus_norm com GAMA -> FCTE, CEILANDIA -> FCTS, PLANALTINA -> FUP"),
        Passo("silver.cursos_graduacao", "campus_norm", "normalize_text(campus)"),
        Passo("bronze.cursos_graduacao", "campus", "como veio do portal"),
        Passo("portal:cursos_graduacao", None, "cursos-de-graduacao (todas as versões)"),
    )),
)


# --- Grafo -----------------------------------------------------------------------------------------

def carregar_manifest(parse_se_faltar: bool = True) -> Optional[Dict]:
    """O manifest do dbt; sem ele (ou desatualizado em relação aos YAML), roda `dbt parse`."""
    pasta = BASE_DIR / "transform"
    fontes = [p for d in ("models", "seeds", "snapshots", "macros", "tests") for p in (pasta / d).rglob("*") if p.is_file()]
    desatualizado = not MANIFEST.exists() or any(p.stat().st_mtime > MANIFEST.stat().st_mtime for p in fontes)
    if desatualizado and parse_se_faltar:
        try:
            subprocess.run(["bash", "scripts/dbt.sh", "parse", "--quiet"], cwd=BASE_DIR, check=True,
                           capture_output=True, text=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
    if not MANIFEST.exists():
        return None
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _relacao(no: Dict) -> str:
    """Nome no banco (esquema.tabela) de um nó do manifest."""
    if no["resource_type"] == "source":
        return f"{no['schema']}.{no['name']}"
    return f"{no['schema']}.{no.get('alias') or no['name']}"


@dataclass
class Grafo:
    arestas: Set[Tuple[str, str]] = field(default_factory=set)   # (origem, destino)
    camada: Dict[str, str] = field(default_factory=dict)
    descricao: Dict[str, str] = field(default_factory=dict)
    gravado_por: Dict[str, str] = field(default_factory=dict)
    fontes_dbt: Set[str] = field(default_factory=set)
    consumidores: Dict[str, Dict] = field(default_factory=dict)

    def origens(self, no: str) -> Set[str]:
        return {o for o, d in self.arestas if d == no}


def _camada(no: str) -> str:
    if no.startswith("portal:"):
        return "Fonte pública"
    if no.startswith("data/"):
        return "Bronze"
    esquema = no.split(".")[0]
    if no in {e.destino for e in ETAPAS if e.script == "src/db/povoar_silver_3nf.py"}:
        return "Silver 3NF (OLTP)"
    return {"bronze": "Bronze", "silver": "Silver", "gold": "Gold", "operacional": "Consumo"}.get(
        esquema, "dbt" if esquema.startswith("dbt_") else esquema)


def montar_grafo(manifest: Optional[Dict]) -> Grafo:
    g = Grafo()
    for f in fontes_publicas():
        g.arestas.add((f.chave, f.grava_em))
        g.descricao[f.chave] = f"{f.nome} — {f.url}"
        g.gravado_por[f.grava_em] = f.script
    for e in ETAPAS:
        for origem in e.origens:
            g.arestas.add((origem, e.destino))
        g.gravado_por[e.destino] = e.script
        if e.nota:
            g.descricao.setdefault(e.destino, e.nota)
    if manifest:
        nos = {**manifest["nodes"], **manifest["sources"]}
        for uid, no in manifest["sources"].items():
            rel = _relacao(no)
            g.fontes_dbt.add(rel)
            if no.get("description"):
                g.descricao.setdefault(rel, no["description"].split(". ")[0].strip())
        for uid, no in manifest["nodes"].items():
            if no["resource_type"] not in ("model", "seed", "snapshot"):
                continue
            rel = _relacao(no)
            g.gravado_por[rel] = f"dbt ({no['original_file_path']})"
            if no.get("description"):
                g.descricao[rel] = " ".join(no["description"].split()).split(". ")[0]
            for dep in no.get("depends_on", {}).get("nodes", []):
                if dep in nos:
                    g.arestas.add((_relacao(nos[dep]), rel))
        for uid, exp in manifest["exposures"].items():
            chave = f"consumo:{exp['name']}"
            g.consumidores[chave] = exp
            g.descricao[chave] = exp.get("label") or exp["name"]
            for dep in exp["depends_on"]["nodes"]:
                if dep in nos:
                    g.arestas.add((_relacao(nos[dep]), chave))
            # Tabela operacional lida pelo consumidor e gravada fora do dbt (ETL reverso).
            for tabela in (exp.get("meta") or {}).get("tabelas_fora_do_dbt", []):
                g.arestas.add((tabela, chave))
    for o, d in g.arestas:
        for no in (o, d):
            g.camada.setdefault(no, "Consumo" if no.startswith("consumo:") else _camada(no))
    return g


def ancestrais(g: Grafo, no: str) -> Set[str]:
    vistos, pilha = set(), [no]
    while pilha:
        for origem in g.origens(pilha.pop()):
            if origem not in vistos:
                vistos.add(origem)
                pilha.append(origem)
    return vistos


# --- Verificação -----------------------------------------------------------------------------------

def _texto(caminhos: Iterable[str]) -> str:
    return "\n".join((BASE_DIR / c).read_text(encoding="utf-8") for c in caminhos)


def verificar_declaracao(g: Grafo) -> List[str]:
    """Problemas da declaração contra o código e o manifest. Lista vazia: tudo confere."""
    problemas = []
    for e in ETAPAS:
        texto = _texto((e.script, *e.logica))
        for tabela in (e.destino, *e.origens):
            # Nome completo (esquema.tabela), e não só o da tabela: "discentes" aparece em todo lugar.
            nome = tabela.split("/")[-1] if tabela.startswith("data/") else tabela
            if not re.search(rf"(?<![\w.]){re.escape(nome)}(?!\w)", texto):
                problemas.append(f"{e.script} não cita {tabela} (etapa de {e.destino})")
    for f in fontes_publicas():
        if f.grava_em.split("/")[-1] not in _texto([f.script]):
            problemas.append(f"{f.script} não cita {f.grava_em}")
    # A linhagem não para no meio: toda fonte do dbt é gravada por alguma etapa declarada.
    for fonte in sorted(g.fontes_dbt):
        if fonte not in g.gravado_por:
            problemas.append(f"fonte do dbt {fonte} sem etapa que a grave (linhagem para no dbt)")
    # Todo consumidor chega a uma fonte pública.
    for consumidor in sorted(g.consumidores):
        if not any(a.startswith("portal:") for a in ancestrais(g, consumidor)):
            problemas.append(f"{consumidor} não chega a nenhuma fonte pública")
    # Toda tabela citada nas trilhas está no grafo.
    nos = {n for a in g.arestas for n in a}
    for t in TRILHAS:
        for p in t.passos:
            if p.ativo not in nos:
                problemas.append(f"trilha '{t.rotulo}': {p.ativo} fora do grafo")
    return problemas


def colunas_das_trilhas() -> Set[Tuple[str, str]]:
    return {(p.ativo, p.coluna) for t in TRILHAS for p in t.passos if p.coluna and not p.ativo.startswith("portal:")}


# --- Documento -------------------------------------------------------------------------------------

ORDEM_CAMADAS = ("Fonte pública", "Bronze", "Silver", "Silver 3NF (OLTP)", "Gold", "dbt", "Consumo")


def _id(no: str) -> str:
    """Id de nó do Mermaid: só ASCII (acento no id quebra a renderização)."""
    return re.sub(r"[^A-Za-z0-9_]", "_", no)


def _rotulo(no: str) -> str:
    if no.startswith("portal:"):
        return no.split(":", 1)[1]
    if no.startswith("consumo:"):
        return no.split(":", 1)[1]
    return no.split("/")[-1]


def mermaid(g: Grafo) -> str:
    """Grafo das tabelas, sem as que não levam a nenhum consumidor (ex.: relatórios internos)."""
    uteis = set()
    for c in g.consumidores:
        uteis |= ancestrais(g, c) | {c}
    linhas = ["flowchart LR"]
    for camada in ORDEM_CAMADAS:
        nos = sorted(n for n in uteis if g.camada.get(n) == camada)
        if not nos:
            continue
        linhas.append(f'  subgraph {_id(camada)}["{camada}"]')
        for n in nos:
            forma = ('(["', '"])') if n.startswith("portal:") else (('[/"', '"/]') if n.startswith("consumo:") else ('["', '"]'))
            linhas.append(f"    {_id(n)}{forma[0]}{_rotulo(n)}{forma[1]}")
        linhas.append("  end")
    for o, d in sorted(g.arestas):
        if o in uteis and d in uteis:
            linhas.append(f"  {_id(o)} --> {_id(d)}")
    return "\n".join(linhas)


def documento(g: Grafo) -> str:
    partes = [
        "# Catálogo e linhagem: da fonte pública ao consumo",
        "",
        "> Gerado por `python3 src/governanca/linhagem.py` a partir do código (configuração da ingestão, "
        "etapas declaradas e verificadas contra os scripts) e do manifest do dbt. Não edite à mão: o CI "
        "falha se este arquivo estiver desatualizado (`--verificar`).",
        "",
        "O grafo do dbt (Silver 3NF → marts → consumidores) também está no dbt docs publicado no GitHub Pages, "
        "em `/dbt/`. Este documento junta a ele o trecho que o dbt não enxerga: portal → bronze → silver → "
        "Silver 3NF e gold.",
        "",
        "## 1. Grafo",
        "",
        "```mermaid",
        mermaid(g),
        "```",
        "",
        "## 2. Consumidores",
        "",
        "| Consumidor | Tipo | Lê | Fontes públicas na origem | Quem usa |",
        "|---|---|---|---|---|",
    ]
    for chave, exp in sorted(g.consumidores.items()):
        le = sorted(o for o in g.origens(chave))
        publicas = sorted(_rotulo(a) for a in ancestrais(g, chave) if a.startswith("portal:"))
        quem = (exp.get("meta") or {}).get("consumidor", "")
        partes.append(f"| {exp.get('label') or exp['name']} | {exp['type']} | {', '.join(f'`{x}`' for x in le)} | "
                      f"{', '.join(publicas)} | {quem} |")
    partes += [
        "",
        "## 3. Trilhas de coluna: do painel ao arquivo do portal",
        "",
        "Cada trilha segue uma coluna do painel (e da fila de intervenção) para trás, tabela por tabela, até "
        "o arquivo publicado. As colunas citadas são conferidas contra o catálogo do banco "
        "(`tests/test_banco_linhagem.py`).",
    ]
    for t in TRILHAS:
        partes += ["", f"### {t.rotulo}", "", "| # | Tabela | Coluna | Como |", "|---|---|---|---|"]
        for i, p in enumerate(t.passos, 1):
            ativo = f"[{_rotulo(p.ativo)}]({_url_fonte(p.ativo)})" if p.ativo.startswith("portal:") else f"`{p.ativo}`"
            partes.append(f"| {i} | {ativo} | {f'`{p.coluna}`' if p.coluna else '—'} | {p.como} |")
    partes += [
        "",
        "## 4. Catálogo de ativos",
        "",
        "Toda tabela do grafo, com quem a grava, se guarda registro de pessoa e quem pode lê-la. Dicionário "
        "de colunas: [dicionario_dados_banco.md](../dicionario_dados_banco.md) (gerado do catálogo do banco) e o "
        "dbt docs.",
        "",
        "| Ativo | Camada | Gravado por | Registro de pessoa | Quem lê | Descrição |",
        "|---|---|---|---|---|---|",
    ]
    for camada in ORDEM_CAMADAS:
        for no in sorted(n for n, c in g.camada.items() if c == camada):
            if no.startswith("consumo:"):
                continue
            esquema = no.split(".")[0] if "." in no and ":" not in no else ""
            pessoal = DADO_PESSOAL.get(no, "não")
            acesso = "público" if no.startswith("portal:") else ACESSO_POR_ESQUEMA.get(esquema, "só o dono do banco")
            desc = g.descricao.get(no, "").replace("|", "/")
            partes.append(f"| `{_rotulo(no) if no.startswith('portal:') else no}` | {camada} | "
                          f"{g.gravado_por.get(no, 'portal' if no.startswith('portal:') else '')} | {pessoal} | "
                          f"{acesso} | {desc} |")
    partes += [
        "",
        "## 5. Como manter",
        "",
        "- **Tabela nova gravada fora do dbt:** declare a etapa em `ETAPAS` (`src/governanca/linhagem.py`). "
        "O `--verificar` falha se uma fonte do dbt não tiver etapa, ou se o script não citar as tabelas declaradas.",
        "- **Fonte nova do portal:** basta entrar em `DATASETS_CONFIG` (`src/ingestion/ckan_client.py`); "
        "o catálogo a lê de lá.",
        "- **Consumidor novo:** declare uma exposure em `transform/models/_exposures.yml`. O `--verificar` "
        "falha se ela não chegar a uma fonte pública.",
        "- **Regerar:** `python3 src/governanca/linhagem.py`. A procedência exata de cada download "
        "(URL do recurso, data, sha256, linhas) fica em `bronze.ingestoes`.",
        "",
    ]
    return "\n".join(partes)


def _url_fonte(chave: str) -> str:
    for f in fontes_publicas():
        if f.chave == chave:
            return f.url
    return ""


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--verificar", action="store_true",
                        help="Falha se a declaração divergir do código ou se o documento estiver desatualizado.")
    args = parser.parse_args(argv)

    manifest = carregar_manifest()
    if manifest is None:
        print("Manifest do dbt indisponível (pip install -r requirements-dbt.txt).", file=sys.stderr)
        return 1
    g = montar_grafo(manifest)
    texto = documento(g)

    if args.verificar:
        problemas = verificar_declaracao(g)
        atual = SAIDA.read_text(encoding="utf-8") if SAIDA.exists() else ""
        if atual != texto:
            problemas.append(f"{SAIDA.relative_to(BASE_DIR)} desatualizado: rode python3 src/governanca/linhagem.py")
        for p in problemas:
            print(f"ERRO: {p}", file=sys.stderr)
        if not problemas:
            print(f"Linhagem confere: {len(g.arestas)} arestas, {len(g.consumidores)} consumidores, "
                  f"{len(TRILHAS)} trilhas de coluna.")
        return 1 if problemas else 0

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(texto, encoding="utf-8")
    print(f"{SAIDA.relative_to(BASE_DIR)}: {len(g.arestas)} arestas, {len(g.consumidores)} consumidores.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
