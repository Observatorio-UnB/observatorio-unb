"""
Página de busca semântica do painel (Streamlit multipage).

Consulta busca.documentos no PostgreSQL com busca híbrida (pgvector + FTS sem acento +
trigramas no título), expansão de siglas da UnB, filtros facetados, explicabilidade
dos sinais de ranqueamento e atalho direto para a aba Detalhe por Curso.
"""

import html
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote_plus

import streamlit as st

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

st.set_page_config(page_title="Busca semântica · Observatório UnB", page_icon="🔎", layout="wide")

st.markdown(
    """
    <style>
    .busca-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 600;
        margin-right: 6px;
        margin-bottom: 4px;
    }
    .badge-tipo { background: #EBF3FF; color: #133E79; }
    .badge-exato { background: #DCFCE7; color: #166534; }
    .badge-texto { background: #FEF3C7; color: #92400E; }
    .badge-vetor { background: #F3E8FF; color: #6B21A8; }
    .badge-meta  { background: #F1F5F9; color: #334155; }
    .busca-snippet {
        font-size: 0.92rem;
        color: #334155;
        line-height: 1.5;
        margin: 0.35rem 0 0.5rem 0;
    }
    .busca-snippet mark {
        background-color: #FEF08A;
        color: #1E293B;
        padding: 0 3px;
        border-radius: 3px;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

ROTULOS = {
    "Cursos e projetos de IC": None,
    "Cursos": "curso",
    "Projetos de iniciação científica": "projeto_pibic",
    "Documentação do projeto": "documentacao",
}
# Sem escolha explícita, a documentação técnica fica de fora: ela cita números de cargas antigas.
TIPOS_PADRAO = ("curso", "projeto_pibic")
NOMES_TIPO = {"curso": "Curso", "projeto_pibic": "Projeto de IC", "documentacao": "Documentação"}

EXEMPLOS = [
    ("Engenharias noturnas com alta evasão", "Cursos"),
    ("Inteligência artificial na saúde", "Projetos de iniciação científica"),
    ("Projetos de PIBIC no Gama", "Projetos de iniciação científica"),
    ("Cursos com retenção crítica na FCTS", "Cursos"),
    ("Janela de maturação de 8 anos", "Documentação do projeto"),
    ("LGPD e k-anonimato", "Documentação do projeto"),
]

CAMPI_OPCOES = [
    "Todos",
    "DARCY RIBEIRO",
    "GAMA (FGA/FCTE)",
    "CEILÂNDIA (FCE/FCTS)",
    "PLANALTINA (FUP)",
    "MULTICAMPUS",
]
TURNOS_OPCOES = ["Todos", "DIURNO", "NOTURNO", "DIURNO E NOTURNO"]
RETENCAO_OPCOES = [
    "Todas",
    "RETENÇÃO CRÍTICA",
    "RETENÇÃO ALTA",
    "RETENÇÃO MÉDIA",
    "RETENÇÃO BAIXA",
]


def br(valor):
    return f"{int(valor):,}".replace(",", ".")


def dec(valor, casas=2):
    """Número com vírgula decimal (padrão do restante do painel)."""
    return f"{float(valor):.{casas}f}".replace(".", ",")


def _virgula_decimal(texto: str, tipo: str) -> str:
    """Os textos indexados trazem ponto decimal ("23.5"); a tela mostra vírgula, como o resto do painel.
    Na documentação só mexe em percentual e semestres, para não alterar versão e código."""
    padrao = r"(?<=\d)\.(?=\d{1,2}(?!\d))" if tipo != "documentacao" else r"(?<=\d)\.(?=\d{1,2}(?:%| semestres))"
    return re.sub(padrao, ",", texto)


def _sanitizar_highlight(trecho: str, tipo: str) -> str:
    """Escapa HTML do texto preservando apenas as tags <mark>...</mark> geradas pelo ts_headline."""
    texto = _virgula_decimal(trecho or "", tipo)
    escapado = html.escape(texto)
    return escapado.replace("&lt;mark&gt;", "<mark>").replace("&lt;/mark&gt;", "</mark>")


def _badges_explicabilidade(fontes: List[str]) -> str:
    mapa = {
        "titulo_exato": ("🎯 Título exato", "badge-exato"),
        "titulo": ("🏷️ Título parecido", "badge-exato"),
        "texto": ("🔤 Termos encontrados", "badge-texto"),
        "vetorial": ("🧠 Significado semelhante", "badge-vetor"),
    }
    return "".join(
        f'<span class="busca-badge {css}">{rotulo}</span>'
        for f in fontes
        if f in mapa
        for rotulo, css in [mapa[f]]
    )


def _abrir_no_detalhe(nome_curso: str):
    st.session_state["_ir_para_aba"] = "🔍 Detalhe por Curso"
    st.session_state["curso_selecionado"] = nome_curso
    st.switch_page("app.py")


def _abrir_aba_pibic():
    st.session_state["_ir_para_aba"] = "🔬 PIBIC & Inclusão Social na Ciência"
    st.switch_page("app.py")


def _score_rrf_pct(relevancia: float) -> int:
    """Converte o score RRF bruto (escala 0..4/61) em percentual relativo ao máximo teórico (0–100%)."""
    from src.busca.buscar import RRF_K

    rrf_max = 4.0 / (RRF_K + 1)
    return min(100, max(1, round((float(relevancia) / rrf_max) * 100)))


@st.cache_data(ttl=600)
def _cursos_da_gold() -> set:
    """Conjunto de cursos disponíveis na aba Detalhe por Curso (para habilitar o atalho no card PIBIC)."""
    try:
        from src.db.conexao import conexao_do_pool

        with conexao_do_pool() as conn:
            return {c for (c,) in conn.execute("SELECT curso FROM gold.retencao_cursos_unb").fetchall()}
    except Exception:
        return set()


# Estado inicial dos controles
if "busca_consulta" not in st.session_state:
    st.session_state["busca_consulta"] = ""
if "busca_onde" not in st.session_state:
    st.session_state["busca_onde"] = "Cursos e projetos de IC"

st.title("🔎 Busca semântica")
st.markdown(
    "Pesquise por **significado, siglas da UnB ou termos exatos** combinados com filtros estruturados: "
    "cursos da Gold, planos de iniciação científica (PIBIC) e documentação técnica do projeto."
)

# Chips de consultas sugeridas para facilitar a exploração pelo DEG e pela banca
st.caption("Sugestões rápidas:")
cols_ex = st.columns(len(EXEMPLOS))
for idx, (texto_ex, onde_ex) in enumerate(EXEMPLOS):
    if cols_ex[idx].button(texto_ex, key=f"ex_{idx}", use_container_width=True):
        st.session_state["busca_consulta"] = texto_ex
        st.session_state["busca_onde"] = onde_ex
        st.rerun()

col_consulta, col_tipo, col_k = st.columns([4, 2, 1])
consulta = col_consulta.text_input(
    "O que você procura?",
    key="busca_consulta",
    placeholder="ex.: engenharias noturnas no Gama com alta evasão",
)
onde_rotulo = col_tipo.selectbox("Onde procurar", list(ROTULOS), key="busca_onde")
tipo = ROTULOS[onde_rotulo]
k = col_k.number_input("Resultados", min_value=1, max_value=30, value=8)

# Filtros facetados (combinados com SQL + pgvector HNSW iterative_scan)
filtros: Dict[str, Any] = {}
if tipo != "documentacao":
    with st.expander("🎛️ Filtros estruturados (campus, turno, retenção, evasão, ano)", expanded=False):
        f1, f2, f3 = st.columns(3)
        campus_sel = f1.selectbox("Campus", CAMPI_OPCOES, key="filtro_campus")
        if campus_sel != "Todos":
            filtros["campus"] = campus_sel

        if tipo in (None, "curso"):
            turno_sel = f2.selectbox("Turno (cursos)", TURNOS_OPCOES, key="filtro_turno")
            if turno_sel != "Todos":
                filtros["turno"] = turno_sel
            ret_sel = f3.selectbox("Classificação de retenção (cursos)", RETENCAO_OPCOES, key="filtro_retencao")
            if ret_sel != "Todas":
                filtros["classificacao_retencao"] = ret_sel
            ev_min, ev_max = st.slider(
                "Faixa de taxa de evasão (%) — aplica-se a cursos",
                min_value=0,
                max_value=100,
                value=(0, 100),
                key="filtro_evasao",
            )
            if ev_min > 0:
                filtros["evasao_min"] = ev_min
            if ev_max < 100:
                filtros["evasao_max"] = ev_max

        if tipo in (None, "projeto_pibic"):
            ano_min, ano_max = st.slider(
                "Ano do plano de IC (PIBIC)",
                min_value=2018,
                max_value=2025,
                value=(2018, 2025),
                key="filtro_ano_pibic",
            )
            if ano_min > 2018:
                filtros["ano_min"] = ano_min
            if ano_max < 2025:
                filtros["ano_max"] = ano_max


@st.cache_resource(show_spinner="Carregando o modelo de linguagem (só na primeira busca; ~220 MB)...")
def _carregar_modelo():
    from src.busca.buscar import modelo

    return modelo()


def _contagem_projetos_ic():
    """(temas distintos indexados, planos de IC que eles representam)."""
    from src.db.conexao import conexao_do_pool

    with conexao_do_pool() as conn:
        return conn.execute(
            "SELECT count(*), coalesce(sum((metadados->>'planos')::int), 0) "
            "FROM busca.documentos WHERE tipo = 'projeto_pibic'"
        ).fetchone()


def _documentos_vetorizados() -> int:
    from src.db.conexao import conexao_do_pool

    with conexao_do_pool() as conn:
        return conn.execute("SELECT count(*) FROM busca.documentos").fetchone()[0]


try:
    _temas, _planos = _contagem_projetos_ic()
    if _planos:
        st.caption(
            f"Base indexada: cursos da Gold, documentação do projeto e {br(_temas)} temas distintos de IC "
            f"({br(_planos)} planos cadastrados, sem dados pessoais)."
        )
except Exception:  # banco fora do ar: a busca abaixo mostra o erro com o detalhe
    pass

if consulta.strip():
    try:
        _carregar_modelo()
    except Exception as erro:
        st.error(
            "Não foi possível carregar o modelo de embedding. Na primeira vez ele é baixado (~220 MB) "
            f"para `FASTEMBED_CACHE_PATH`; confira a conexão com a internet.\n\nDetalhe: `{erro}`"
        )
        st.stop()

    import psycopg
    from psycopg_pool import PoolTimeout

    from src.busca.buscar import buscar

    # Se filtros exclusivos de curso ou PIBIC foram acionados no modo combinado, restringe o tipo automaticamente.
    tipos_consulta = TIPOS_PADRAO if tipo is None else None
    if tipo is None and any(k_f in filtros for k_f in ("turno", "classificacao_retencao", "evasao_min", "evasao_max")):
        tipos_consulta = ("curso",)
    elif tipo is None and any(k_f in filtros for k_f in ("ano_min", "ano_max")):
        tipos_consulta = ("projeto_pibic",)

    try:
        with st.spinner("Buscando..."):
            inicio = time.perf_counter()
            resultados = buscar(
                consulta,
                k=int(k),
                tipo=tipo,
                tipos=tipos_consulta,
                filtros=filtros or None,
            )
            latencia_ms = (time.perf_counter() - inicio) * 1000
    except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn, psycopg.errors.UndefinedFunction) as erro:
        st.error(
            "O banco não tem a busca semântica atualizada. Aplique as migrações e vetorize: "
            f"`python3 src/db/migrar.py && python3 src/busca/vetorizar.py`.\n\nDetalhe: `{erro}`"
        )
        st.stop()
    except (psycopg.OperationalError, PoolTimeout) as erro:
        st.error(
            "Não foi possível consultar o banco. Suba com `docker compose up -d db` e rode "
            f"`scripts/rodar_pipeline.sh`.\n\nDetalhe: `{erro}`"
        )
        st.stop()

    if not resultados:
        if _documentos_vetorizados() == 0:
            st.info("Nenhum documento vetorizado. Rode `python3 src/busca/vetorizar.py`.")
        else:
            st.info(
                "Nenhum resultado com evidência suficiente para essa combinação de termos"
                + (" e filtros." if filtros else ".")
            )
            c_rec1, c_rec2 = st.columns(2)
            if filtros and c_rec1.button("🧹 Limpar filtros e tentar novamente"):
                for k_f in ("filtro_campus", "filtro_turno", "filtro_retencao", "filtro_evasao", "filtro_ano_pibic"):
                    st.session_state.pop(k_f, None)
                st.rerun()
            if tipo != "documentacao" and c_rec2.button("📄 Procurar também na documentação"):
                st.session_state["busca_onde"] = "Documentação do projeto"
                st.rerun()
    else:
        expansoes = resultados[0].get("expansoes") or []
        barra_info = f"**{len(resultados)} resultado(s)** em {dec(latencia_ms, 0)} ms"
        if filtros:
            resumo_f = ", ".join(f"{chave}={val}" for chave, val in filtros.items())
            barra_info += f" · filtros ativos: `{resumo_f}`"
        st.caption(barra_info)
        if expansoes:
            txt_exp = " · ".join(f"`{orig}` → _{exp}_" for orig, exp in expansoes)
            st.caption(f"💡 Siglas/termos expandidos automaticamente: {txt_exp}")

    cursos_gold = _cursos_da_gold()
    for idx, r in enumerate(resultados):
        meta = r["metadados"] or {}
        rrf_pct = _score_rrf_pct(r["relevancia"])
        with st.container(border=True):
            topo_esq, topo_dir = st.columns([5, 2])
            tipo_nome = NOMES_TIPO.get(r["tipo"], r["tipo"])
            badges_html = (
                f'<span class="busca-badge badge-tipo">{html.escape(tipo_nome)}</span>'
                f'<span class="busca-badge badge-meta">⭐ Relevância {rrf_pct}%</span>'
                + _badges_explicabilidade(r.get("fontes") or [])
            )
            if r["tipo"] == "curso" and meta.get("campus_norm"):
                badges_html += f'<span class="busca-badge badge-meta">📍 {html.escape(str(meta["campus_norm"]))}</span>'
            if r["tipo"] == "curso" and meta.get("turno"):
                badges_html += f'<span class="busca-badge badge-meta">🕒 {html.escape(str(meta["turno"]))}</span>'
            if r["tipo"] == "projeto_pibic":
                if meta.get("ano"):
                    badges_html += f'<span class="busca-badge badge-meta">📅 {meta["ano"]}</span>'
                if meta.get("campus_norm") or meta.get("campus"):
                    badges_html += f'<span class="busca-badge badge-meta">📍 {html.escape(str(meta.get("campus_norm") or meta.get("campus")))}</span>'
                if meta.get("planos", 1) > 1:
                    badges_html += f'<span class="busca-badge badge-meta">{br(meta["planos"])} planos iguais</span>'

            topo_esq.markdown(f"#### {r['titulo']}")
            topo_esq.markdown(badges_html, unsafe_allow_html=True)

            if r["tipo"] == "curso":
                with topo_dir:
                    if st.button(
                        "🔍 Ver no Detalhe por Curso",
                        key=f"abrir_curso_{idx}_{r['titulo']}",
                        use_container_width=True,
                    ):
                        _abrir_no_detalhe(r["titulo"])
            elif r["tipo"] == "projeto_pibic":
                with topo_dir:
                    curso_ic = meta.get("curso")
                    if curso_ic and curso_ic in cursos_gold:
                        if st.button(
                            "🔍 Ver curso no Detalhe",
                            key=f"abrir_curso_ic_{idx}_{r['chave']}",
                            use_container_width=True,
                        ):
                            _abrir_no_detalhe(curso_ic)
                    if st.button(
                        "🔬 Abrir aba PIBIC",
                        key=f"abrir_pibic_{idx}_{r['chave']}",
                        use_container_width=True,
                    ):
                        _abrir_aba_pibic()

            snippet_html = _sanitizar_highlight(r.get("trecho_destacado") or r["conteudo"], r["tipo"])
            st.markdown(f'<div class="busca-snippet">{snippet_html}</div>', unsafe_allow_html=True)

            if r["tipo"] == "curso":
                evasao = meta.get("taxa_evasao_pct")
                formatura = meta.get("taxa_formatura_pct")
                irc = meta.get("indice_retencao_critica")
                ativos = meta.get("total_ativos_hoje")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Evasão", "—" if evasao is None else f"{dec(evasao, 1)}%")
                m2.metric("Formatura", "—" if formatura is None else f"{dec(formatura, 1)}%")
                m3.metric("IRC (0–100)", "—" if irc is None else f"{dec(irc, 1)}")
                m4.metric("Ativos hoje", "—" if ativos is None else br(ativos))
            elif r["tipo"] == "projeto_pibic":
                partes_ic = []
                if meta.get("curso"):
                    partes_ic.append(f"**Curso:** {meta['curso']}")
                if meta.get("linha_pesquisa"):
                    partes_ic.append(f"**Linha de pesquisa:** {meta['linha_pesquisa']}")
                if partes_ic:
                    st.caption(" · ".join(partes_ic))

                q_titulo = quote_plus(f'"{r["titulo"]}"')
                q_scholar = quote_plus(f'"{r["titulo"]}" UnB')
                url_riunb = f"https://repositorio.unb.br/simple-search?query={q_titulo}"
                url_scholar = f"https://scholar.google.com/scholar?q={q_scholar}"
                st.markdown(
                    f"[📚 Buscar trabalho no RIUnB]({url_riunb}) · "
                    f"[🎓 Buscar no Google Acadêmico]({url_scholar}) "
                    "<small style='color:#64748B;'>(os dados abertos da UnB não trazem URL direta do PDF)</small>",
                    unsafe_allow_html=True,
                )

                chave_sim = f"sim_pibic_{r['chave']}"
                if st.button("🧭 Ver projetos de IC com tema parecido", key=f"btn_{chave_sim}_{idx}"):
                    from src.busca.buscar import projetos_semelhantes

                    st.session_state[chave_sim] = projetos_semelhantes(r["chave"], k=4)
                if chave_sim in st.session_state:
                    viz = st.session_state[chave_sim]
                    if viz:
                        for v_ic in viz:
                            vm = v_ic["metadados"] or {}
                            st.caption(
                                f"• **{v_ic['titulo']}** "
                                f"({vm.get('ano', '—')} · {vm.get('curso') or 'Curso n/d'} · "
                                f"{vm.get('campus_norm') or vm.get('campus', '—')})"
                            )
                    else:
                        st.caption("Nenhum projeto semelhante encontrado.")
            elif r["tipo"] == "documentacao":
                if meta.get("arquivo"):
                    st.caption(f"📄 `{meta['arquivo']}`")
                with st.expander("📖 Ler trecho completo"):
                    st.markdown(_virgula_decimal(r["conteudo"], r["tipo"]))

            with st.expander("Detalhes técnicos do ranqueamento"):
                st.caption(
                    f"Relevância combinada (RRF): **{rrf_pct}%** (bruto `{dec(r['relevancia'], 5)}` de `0,06557`) · "
                    f"Similaridade de cosseno: **{dec(r['similaridade'], 3)}** · "
                    f"Sinais: `{', '.join(r.get('fontes') or [])}`"
                )
                if meta:
                    st.json(meta)
