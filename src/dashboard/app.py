"""
Dashboard Interativo de Apoio à Decisão - Retenção e Formatura na UnB
Desenvolvido para o Decanato de Ensino de Graduação (DEG/UnB)
Challenge de Dados Abertos da UnB - Metodologia CBL
"""

import base64
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Paleta institucional da UnB (verde e azul da marca, extraídas do símbolo oficial) aplicada como padrão dos gráficos
UNB_GREEN = "#008940"
UNB_NAVY = "#133E79"
UNB_PALETTE = [UNB_GREEN, UNB_NAVY, "#F2B705", "#8AC24A", "#6B7280"]


try:
    import psycopg
    from psycopg_pool import PoolTimeout

    _ERROS_DO_BANCO = (psycopg.Error, PoolTimeout)
except ImportError:  # versão estática (stlite): sem driver, só o export
    _ERROS_DO_BANCO = ()
# O que pode faltar na fonte principal (banco): driver ausente, rede, banco fora do ar. Qualquer outro
# erro é bug e deve aparecer, e não cair no export em silêncio.
ERROS_DE_FONTE = (ImportError, OSError, *_ERROS_DO_BANCO)


sys.path.insert(0, str(Path(__file__).resolve().parent))
from formatacao import br, dec, grafico, mostrar_tabela, reducao  # noqa: E402,F401
from abas import alunos_ativos, auditoria, benchmark_inep, detalhe_curso, limites_do_dado, pibic, simulador, turnos, visao_executiva  # noqa: E402

px.defaults.color_discrete_sequence = UNB_PALETTE

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
UNB_ICON_PATH = ASSETS_DIR / "unb_icon.png"
if UNB_ICON_PATH.exists():
    try:
        UNB_ICON_B64 = base64.b64encode(
            UNB_ICON_PATH.read_bytes()).decode("ascii")
        UNB_HEADER_IMG = f'<img src="data:image/png;base64,{UNB_ICON_B64}" style="height:2.1rem;vertical-align:-0.3rem;margin-right:0.6rem;">'
    except OSError:
        UNB_ICON_B64 = None
        UNB_HEADER_IMG = "🎓 "
else:
    UNB_ICON_B64 = None
    UNB_HEADER_IMG = "🎓 "

# Rótulos legíveis para colunas técnicas que aparecem em eixos/legendas dos gráficos
LABELS_PT = {
    "turno": "Turno",
    "categoria_grau": "Grau Acadêmico",
    "campus": "Campus",
    "total_discentes_registrados": "Alunos que ingressaram",
    "taxa_evasao_pct": "Taxa de Evasão (%)",
    "taxa_formatura_pct": "Taxa de Formatura (%)",
    "tempo_medio_real_semestres": "Tempo Médio Real (semestres)",
    "semestre_ideal_previsto": "Tempo Ideal Previsto (semestres)",
    "desvio_medio_semestres": "Desvio Médio (semestres)",
    "value": "Semestres",
    "variable": "Métrica",
}

# Configuração da página
st.set_page_config(
    page_title="Painel de Retenção e Formatura UnB",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Estilização CSS customizada (cores institucionais UnB: verde #008940 / azul #133E79)
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #008940;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #4B5563;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
    }
    .metric-val {
        font-size: 1.8rem;
        font-weight: 700;
        color: #133E79;
    }
    .metric-label {
        font-size: 0.9rem;
        color: #64748B;
    }
    .badge-critica {
        background-color: #FEE2E2;
        color: #991B1B;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DOCS_DIR = BASE_DIR / "docs"
# Export estático da gold, gerado pelo CI a partir do banco (src/db/exportar_gold.py). É o
# que a versão do GitHub Pages lê: o stlite roda no navegador, sem acesso ao PostgreSQL.
EXPORT_PATH = BASE_DIR / "export" / "gold.json"


def _versao_dos_dados() -> str:
    """Assinatura de versão da gold, para invalidar o cache quando o pipeline a regrava
    (st.cache_data por si só não detecta mudança no banco nem no arquivo)."""
    try:
        from src.db.tabelas import consultar

        return str(consultar("SELECT max(_carregado_em) AS versao FROM gold.relatorios").iloc[0]["versao"])
    except ERROS_DE_FONTE:
        return str(EXPORT_PATH.stat().st_mtime) if EXPORT_PATH.exists() else ""


def _ler_dados_da_gold():
    """Gold do PostgreSQL quando o banco responde; senão, o export estático (GitHub Pages)."""
    try:
        from src.db.exportar_gold import montar_snapshot

        dados = montar_snapshot()
        if dados["tabelas"].get("retencao_cursos_unb"):
            return dados
    except ERROS_DE_FONTE:
        pass  # sem psycopg (stlite) ou banco fora do ar
    if EXPORT_PATH.exists():
        return json.loads(EXPORT_PATH.read_text(encoding="utf-8"))
    return None


@st.cache_data
def _snapshot_em_cache(versao: str):
    """Um snapshot da gold por versão, compartilhado pelas leituras abaixo."""
    dados = _ler_dados_da_gold()
    if dados is None:
        # Exceção não entra no cache: um "sem dados" transitório (banco ainda carregando) não fica preso.
        raise LookupError("gold indisponível")
    return dados


def _snapshot(versao: str):
    try:
        return _snapshot_em_cache(versao)
    except LookupError:
        return None


@st.cache_data
def load_gold_data(versao: str):
    # `versao` só existe para entrar na chave do cache (sem "_" na frente: o Streamlit
    # ignora parâmetros com "_" ao montar a chave).
    dados = _snapshot(versao)
    if dados is None:
        # não entra no cache; o aviso é mostrado fora dele
        raise LookupError("gold indisponível")

    tabelas, relatorios = dados["tabelas"], dados["relatorios"]
    df = pd.DataFrame(tabelas["retencao_cursos_unb"]) if tabelas.get(
        "retencao_cursos_unb") else None
    meta = relatorios.get("metricas_gerais_unb")
    join_meta = relatorios.get("relatorio_casamento_joins")

    df_pibic = pd.DataFrame(tabelas["pibic_social_unb"]) if tabelas.get(
        "pibic_social_unb") else None
    pibic_meta = relatorios.get("pibic_metricas_gerais")

    regras_meta = None
    if tabelas.get("regras_harmonizacao_canonicas"):
        regras_meta = {
            **relatorios.get("regras_harmonizacao_canonicas", {}),
            "regras": tabelas["regras_harmonizacao_canonicas"],
        }

    df_inep = pd.DataFrame(tabelas["inep_benchmark_cursos_unb"]) if tabelas.get(
        "inep_benchmark_cursos_unb") else None
    df_ativos = pd.DataFrame(tabelas["ativos_hoje_cursos_unb"]) if tabelas.get(
        "ativos_hoje_cursos_unb") else None

    return df, meta, join_meta, df_pibic, pibic_meta, regras_meta, df_inep, df_ativos


try:
    df_gold, global_meta, join_meta, df_pibic, pibic_meta, regras_meta, df_inep, df_ativos = load_gold_data(
        _versao_dos_dados())
except LookupError:
    st.error(
        "Sem dados da gold. Suba o banco (`docker compose up -d db`) e rode o pipeline "
        "(`bash scripts/rodar_pipeline.sh`)."
    )
    df_gold = global_meta = join_meta = df_pibic = pibic_meta = regras_meta = df_inep = df_ativos = None
# Resposta à pergunta da E1 (src/dashboard/resposta_e1.py), lida à parte do cache da gold: o mart do
# dbt e a data da carga entram no snapshot, mas não nas tabelas que o resto do painel usa.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from faixas import FAIXAS, faixas_exclusivas  # noqa: E402
from resposta_e1 import COLUNAS as COLUNAS_E1, PERGUNTA_E1, SLA_DIAS, frescor, ranking_cursos_criticos  # noqa: E402
from metricas import definicoes as definicoes_metricas, metricas_por_recorte  # noqa: E402


def _graficos_do_curso(row, chave: str):
    """Faixas de tempo dos formados e desfecho dos alunos de uma linha (curso inteiro ou uma coorte)."""
    c_chart1, c_chart2 = st.columns(2)
    with c_chart1:
        st.markdown("##### ⏱️ Distribuição de Tempo dos Formados")
        st.caption(f"% dos {br(int(row['total_formados']))} alunos formados com tempo de conclusão calculável, por faixa "
                   "(as faixas não se sobrepõem e somam 100%). Prazos mínimo, ideal e máximo vêm da matriz do curso.")
        df_dist = pd.DataFrame(
            {"Faixa de Conclusão": FAIXAS, "Percentual": faixas_exclusivas(row)})
        fig_bar = px.bar(
            df_dist, x="Faixa de Conclusão", y="Percentual", color="Faixa de Conclusão",
            color_discrete_sequence=["#10B981",
                                     "#3B82F6", "#F59E0B", "#DC2626"],
            text_auto=".1f", height=350,
        )
        fig_bar.update_traces(
            hovertemplate="%{x}<br>%{y:.1f}% dos alunos formados<extra></extra>")
        grafico(fig_bar, width="stretch", key=f"barras_{chave}")

    with c_chart2:
        st.markdown("##### 🚪 Desfecho das Movimentações Acadêmicas")
        st.caption("Situação de cada aluno que ingressou (1 fatia = nº de alunos). 'Outros' reúne registros anulados, falecimentos e alunos não cadastrados. "
                   "Evasão inclui mudança de curso.")
        n_form = row["total_formados"]
        n_evad = row["total_evadidos_desligados"]
        n_ativos = row["total_ainda_ativos"]
        n_outros = max(
            0, row["total_discentes_registrados"] - n_form - n_evad - n_ativos)
        df_pie = pd.DataFrame({
            "Desfecho": ["Formatura", "Evasão / Desligamento", "Ainda ativo", "Outros"],
            "Quantidade": [n_form, n_evad, n_ativos, n_outros],
        })
        fig_pie = px.pie(
            df_pie, names="Desfecho", values="Quantidade", color="Desfecho",
            color_discrete_map={
                "Formatura": "#10B981", "Evasão / Desligamento": "#DC2626",
                "Ainda ativo": "#3B82F6", "Outros": "#6B7280",
            },
            height=350,
        )
        fig_pie.update_traces(
            texttemplate="%{percent:.1%}",
            hovertemplate="%{label}<br>%{value:,} alunos (%{percent:.1%})<extra></extra>")
        grafico(fig_pie, width="stretch", key=f"pizza_{chave}")


@st.cache_data
def load_coortes(versao: str):
    return (_snapshot(versao) or {}).get("tabelas", {}).get("retencao_cursos_coorte") or []


@st.cache_data
def load_resposta_e1(versao: str):
    dados = _snapshot(versao) or {}
    return dados.get("tabelas", {}).get("painel_cursos_criticos") or [], dados.get("carregado_em")


painel_e1, carregado_em = load_resposta_e1(_versao_dos_dados())


def correlacao_pibic_evasao(df):
    """(cursos, r de Pearson) entre projetos de IC por 100 alunos e taxa de evasão, nos cursos com
    algum projeto de IC. É o recorte do gráfico da aba PIBIC: os textos citam o número calculado
    sobre os dados carregados, e não um valor fixo que envelhece com a carga."""
    if df is None or df.empty:
        return 0, None
    d = df[df["pibic_total_projetos"] > 0].dropna(
        subset=["pibic_projetos_por_100_alunos", "taxa_evasao_pct"])
    if len(d) < 3:
        return len(d), None
    r = float(np.corrcoef(d["pibic_projetos_por_100_alunos"].astype(float),
                          d["taxa_evasao_pct"].astype(float))[0, 1])
    return len(d), r


n_pibic_evasao, r_pibic_evasao = correlacao_pibic_evasao(df_gold)
r_pibic_evasao_txt = "indisponível" if r_pibic_evasao is None else f"{dec(r_pibic_evasao, 2)}".replace(
    ".", ",")


@st.cache_data(ttl=3600)
def load_frescor_da_view():
    """Atualização da view do painel e SLA (docs/frescor_sla.md), fora do cache da gold: uma
    sincronização sem dado novo atualiza a view, mas não muda a versão da gold."""
    try:
        from src.db.conexao import conexao_do_pool
        from src.db.frescor import resumo_para_o_painel

        with conexao_do_pool() as conn:
            resumo = resumo_para_o_painel(conn)
        if resumo:
            return resumo
    except ERROS_DE_FONTE:
        pass  # sem psycopg (stlite) ou banco fora do ar
    if EXPORT_PATH.exists():
        return json.loads(EXPORT_PATH.read_text(encoding="utf-8")).get("frescor")
    return None


frescor_da_view = load_frescor_da_view()
# Cursos-tronco (Engenharia, ABI de Educação Física): definidos em build_gold.py e publicados na Gold.
EXCLUDED_GENERIC_COURSES = set((global_meta or {}).get("cursos_tronco", []))
# Um só filtro para todas as abas: os cursos-tronco não são cursos terminais e distorciam totais,
# turnos e campi (ex.: FCTE com ENGENHARIA 55% de evasão, sem ela 36%).
if df_gold is not None:
    df_gold = df_gold[~df_gold["curso"].isin(EXCLUDED_GENERIC_COURSES)]
    n_pibic_evasao, r_pibic_evasao = correlacao_pibic_evasao(df_gold)
    r_pibic_evasao_txt = "indisponível" if r_pibic_evasao is None else f"{dec(r_pibic_evasao, 2)}".replace(
        ".", ",")

_COORTES = (global_meta or {}).get("coortes_ingresso_analisadas", "n/d")
_REF_ATIVOS = (global_meta or {}).get("ativos_hoje_referencia", "n/d")
# Recorte e fonte de cada aba, mostrados no topo dela: o mesmo nome ("alunos", "evasão") muda de
# universo entre as abas, e o usuário precisa saber qual está lendo.
ESCOPO = {
    "exec": f"ingressantes de {_COORTES} (turmas de ingresso com 8+ anos de acompanhamento), cursos com 5+ alunos, sem os "
    "cursos-tronco. Fontes: SIGRA (até 2020/1) e SIGAA (situação em 07/2024), do portal dados.unb.br.",
    "detalhe": f"ingressantes de {_COORTES} no curso escolhido; a seção por turma de ingresso mostra também as turmas de ingresso "
    "recentes, ainda sem desfecho. Fontes: SIGRA e SIGAA (dados.unb.br).",
    "ativos": f"alunos ativos na lista do SIGAA de {_REF_ATIVOS}, de todas as turmas de ingresso, sem os "
    "cursos-tronco. Não é o mesmo universo das outras abas (turmas de ingresso antigas).",
    "turnos": f"ingressantes de {_COORTES}, sem os cursos-tronco; taxas ponderadas pelo número de alunos "
    "de cada curso. Fontes: SIGRA e SIGAA (dados.unb.br).",
    "pibic": "projetos de IC de 2018 a 2023 (dados.unb.br), cruzados com os cursos pelo nome. Os alunos "
             f"das taxas de evasão ingressaram em {_COORTES}: são populações de períodos diferentes.",
    "inep": "Censo da Educação Superior 2019 (INEP/MEC), por nome de curso, comparando a UnB com as demais "
            "federais. Não é a mesma medida de evasão das outras abas.",
    "simulador": f"o cenário parte dos números de {_COORTES} e usa hipóteses fixas do simulador. É um exercício "
    "de cenário, não uma previsão.",
}


# Datas dos dados de origem (docs/): o painel "atualizado hoje" mede o pipeline, e não estas datas.
FONTES_DATAS = ("SIGRA até 2020/1 · SIGAA com situação em 07/2024 · lista de ativos 2025/1 · "
                "estrutura curricular 10/2020 · Censo INEP 2019 · iniciação científica 2018-2023")
# cursos muito pequenos dominam os extremos (ex.: 11 alunos com 9% de evasão)
N_MIN_RANKING = 30


def mostrar_escopo(aba: str):
    st.caption(f"🔎 **Recorte desta tela:** {ESCOPO[aba]}")


def _media_ponderada(df, coluna, pesos="total_formados"):
    d = df.dropna(subset=[coluna])
    w = d[pesos].astype(float)
    return float((d[coluna].astype(float) * w).sum() / w.sum()) if w.sum() else float("nan")


# Camada semântica (src/dashboard/metricas.py): recortes acima do curso e o registro das definições.
@st.cache_data
def load_camada_semantica(versao: str):
    tabelas = (_snapshot(versao) or {}).get("tabelas", {})
    return {nome: tabelas.get(nome) or [] for nome in ("metricas_por_recorte", "metricas_definicoes")}


camada_semantica = load_camada_semantica(_versao_dos_dados())

# Coluna da gold -> recorte da camada semântica (dbt_marts.metricas_por_recorte).
RECORTE_DA_COLUNA = {"turno": "TURNO", "categoria_grau": "CATEGORIA_GRAU", "campus": "CAMPUS"}


def mostrar_definicoes(metricas) -> None:
    """Rodapé de uma comparação: de onde vieram os números e a definição versionada das métricas."""
    if not camada_semantica["metricas_por_recorte"]:
        return
    st.caption("Fonte: dbt_marts.metricas_por_recorte (camada semântica). Taxa de um grupo = soma dos "
               "eventos / soma dos ingressantes dos cursos do grupo.")
    registro = definicoes_metricas(camada_semantica, metricas)
    if registro is not None:
        with st.expander("📐 Definição das métricas (camada semântica, versionada)"):
            st.dataframe(registro, width="stretch", hide_index=True)


def agregar_ponderado(df, chave):
    """Evasão, formatura e tempos por grupo de cursos. Com a camada semântica no snapshot, vêm de
    dbt_marts.metricas_por_recorte: a fórmula é a das macros do dbt, a mesma do ranking e da fila, no
    universo do ranking (cursos terminais). Os grupos seguem o filtro de `df` (ex.: sem MISTO). Sem o
    mart, a mesma regra calculada aqui: razão das somas para evasão e formatura, tempos ponderados
    pelos formados."""
    recorte = RECORTE_DA_COLUNA.get(chave)
    if recorte and camada_semantica["metricas_por_recorte"]:
        sem, _ = metricas_por_recorte(camada_semantica, None, recorte)
        sem = sem[sem["valor"].isin(set(df[chave].unique()))].rename(columns={
            "valor": chave, "ingressantes": "total_discentes_registrados", "formados": "total_formados",
            "evadidos": "total_evadidos_desligados", "atraso_medio_semestres": "desvio_medio_semestres",
            "tempo_medio_formatura_semestres": "tempo_medio_real_semestres",
            "prazo_ideal_medio_semestres": "semestre_ideal_previsto",
        })
        return sem.reset_index(drop=True)
    linhas = []
    for valor, g in df.groupby(chave):
        reg = g["total_discentes_registrados"].sum()
        linhas.append({
            chave: valor,
            "cursos": len(g),
            "total_discentes_registrados": reg,
            "total_formados": g["total_formados"].sum(),
            "total_evadidos_desligados": g["total_evadidos_desligados"].sum(),
            "taxa_evasao_pct": g["total_evadidos_desligados"].sum() / reg * 100 if reg else np.nan,
            "taxa_formatura_pct": g["total_formados"].sum() / reg * 100 if reg else np.nan,
            "tempo_medio_real_semestres": _media_ponderada(g, "tempo_medio_real_semestres"),
            "semestre_ideal_previsto": _media_ponderada(g, "semestre_ideal_previsto"),
            "desvio_medio_semestres": _media_ponderada(g, "desvio_medio_semestres"),
        })
    return pd.DataFrame(linhas)


def _anos_do_intervalo(texto: str) -> int:
    """'2010-2016' -> 7 anos de coortes."""
    try:
        a, b = str(texto).split("-")
        return int(b) - int(a) + 1
    except ValueError:
        return 1


GLOSSARIO = """
**IRC (Índice de Retenção Crítica):** nota de 0 a 100 *relativa* entre os cursos (0,7 evasão + 0,3 atraso).
Não é uma taxa: sempre cerca de 25% dos cursos caem na faixa "crítica", mesmo que o pior curso seja bom.
IRC 100 = o pior grupo depois de limitar os extremos (percentis 5 e 95); IRC 0 = curso sem atraso e com evasão
baixa, ou com atraso negativo: não significa "sem problema". Cursos pequenos oscilam mais.

**Evasão:** aluno da turma de ingresso que saiu sem se formar (desligado, cancelado ou mudou de curso). Os dados não
dizem o motivo.

**DEG:** Decanato de Ensino de Graduação. **E1:** primeira entrega do projeto, que fixou a pergunta de gestão
do topo da Visão Executiva. **NDE:** Núcleo Docente Estruturante do curso. **ABI:** Área Básica de Ingresso
(ingresso comum a vários cursos, como Engenharia).

**Evasão / evadidos / desligados:** o mesmo conceito nas telas de turma de ingresso e de curso. **Desvinculação**, do Censo
do INEP, é uma medida de outro tipo (ver aba INEP).

**Outros (pizza do curso):** registros anulados, falecimentos e alunos não cadastrados: quem não é formado,
evadido nem ativo.

**Diurno e Noturno:** cursos com turmas nos dois turnos.

**Atraso (sem.):** tempo real de formatura menos o tempo ideal da matriz. Negativo = formou antes do ideal.

**Tempo mínimo / ideal / máximo:** prazos da matriz do curso. "Até o prazo ideal" inclui quem fechou no mínimo.

**Turma de ingresso (madura):** alunos que ingressaram no mesmo ano. Madura = já passaram 8 anos desde o ingresso.

**Ativo:** na lista do SIGAA de hoje (aba Alunos Ativos). "Ainda ativo" nas turmas de ingresso antigas é outra contagem.

**Curso-tronco:** ingresso comum (ex.: Engenharia); não é curso terminal e fica de fora.

**k-anonimato:** cursos ou turmas de ingresso com menos de 5 alunos não aparecem.

**Desvinculação (INEP):** medida do Censo 2019 num ano; não é a evasão da turma de ingresso.

**SIGRA / SIGAA:** sistemas acadêmicos antigo e atual da UnB. **PIBIC / PIVIC:** iniciação científica com
bolsa / voluntária. **PPI:** pretos, pardos e indígenas.
"""

# Barra Lateral (Sidebar)
if UNB_ICON_PATH.exists():
    st.sidebar.image(str(UNB_ICON_PATH), width=180)
else:
    st.sidebar.image(
        "https://dados.unb.br/uploads/group/2019-11-01-175835.512234iconensino.png", width=180)
st.sidebar.title("Painel UnB")
st.sidebar.markdown("**Projeto**: Retenção e Formatura nos Cursos da UnB")
_carga = frescor(carregado_em)
st.sidebar.caption(
    "Fontes: dados abertos da UnB (dados.unb.br), Censo INEP e valor da bolsa do CNPq. "
    f"**Datas dos dados:** {FONTES_DATAS}.")
with st.sidebar.expander("📖 Como ler este painel"):
    st.markdown(GLOSSARIO)

tab_choice = st.sidebar.radio(
    "Navegação:",
    [
        "📊 Visão Executiva (DEG)",
        "🔍 Detalhe por Curso",
        "🎒 Alunos Ativos",
        "⚖️ Noturno vs. Diurno & Turnos",
        "🔬 PIBIC & Inclusão Social na Ciência",
        "🇧🇷 Benchmark Nacional (INEP)",
        "💡 Simulador What-If & Custo da Retenção",
        "🛠️ Auditoria & Qualidade de Dados",
        "⚠️ O Que Este Dado NÃO Responde",
    ],
)

st.sidebar.markdown("---")

# Frescor da view do painel contra o SLA (docs/frescor_sla.md). A idade é calculada aqui, fora do
# cache, para a versão estática do GitHub Pages também mostrar quando o export envelheceu.
if frescor_da_view:
    atualizada_em = datetime.fromisoformat(frescor_da_view["atualizada_em"])
    idade = datetime.now(timezone.utc) - atualizada_em
    idade_dias = idade.days
    # Mede a rotina de carga, e não a data dos dados (acima): por isso sem selo verde de "dados atuais".
    texto_frescor = f"Pipeline executado em {atualizada_em:%d/%m/%Y}."
    if idade <= timedelta(days=frescor_da_view["sla_dias"]):
        st.sidebar.caption(f"⚙️ {texto_frescor}")
    else:
        st.sidebar.warning(
            f"Carga fora do SLA de frescor: {texto_frescor} Já faz {idade_dias} dias, "
            f"e o limite é {frescor_da_view['sla_dias']}.")

if df_gold is not None:
    # Header Principal
    st.markdown(
        f'<div class="main-header">{UNB_HEADER_IMG}'
        f'Observatório de Retenção e Formatura da UnB</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="sub-header">Mapeamento do tempo real de integralização curricular, retenção crítica e evasão baseado nos Dados Abertos da UnB.</div>', unsafe_allow_html=True)

    ABAS = {
        "📊 Visão Executiva (DEG)": visao_executiva.renderizar,
        "🔍 Detalhe por Curso": detalhe_curso.renderizar,
        "🎒 Alunos Ativos": alunos_ativos.renderizar,
        "⚖️ Noturno vs. Diurno & Turnos": turnos.renderizar,
        "🔬 PIBIC & Inclusão Social na Ciência": pibic.renderizar,
        "🇧🇷 Benchmark Nacional (INEP)": benchmark_inep.renderizar,
        "💡 Simulador What-If & Custo da Retenção": simulador.renderizar,
        "🛠️ Auditoria & Qualidade de Dados": auditoria.renderizar,
        "⚠️ O Que Este Dado NÃO Responde": limites_do_dado.renderizar,
    }
    ABAS[tab_choice](SimpleNamespace(**globals()))
