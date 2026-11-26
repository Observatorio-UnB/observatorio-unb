"""Tela: 🔎 Busca Semântica.

Consulta busca.documentos no PostgreSQL, então só existe com o banco no ar: o app.py não a oferece na
versão estática do GitHub Pages (stlite). Os imports de banco e de modelo são feitos dentro das funções.
"""

import re
import time

import streamlit as st
from formatacao import br, dec

ROTULOS = {
    "Cursos e projetos de IC": None,
    "Cursos": "curso",
    "Projetos de iniciação científica": "projeto_pibic",
    "Documentação do projeto": "documentacao",
}
# Sem escolha explícita, a documentação técnica fica de fora: ela cita números de cargas antigas.
TIPOS_PADRAO = ("curso", "projeto_pibic")
NOMES_TIPO = {"curso": "Curso", "projeto_pibic": "Projeto de IC", "documentacao": "Documentação"}

CAMPI = ["Todos", "DARCY RIBEIRO", "GAMA (FGA/FCTE)", "CEILÂNDIA (FCE/FCTS)", "PLANALTINA (FUP)", "MULTICAMPUS"]
TURNOS = ["Todos", "DIURNO", "NOTURNO", "DIURNO E NOTURNO"]
RETENCAO = ["Todas", "RETENÇÃO CRÍTICA", "RETENÇÃO ALTA", "RETENÇÃO MÉDIA", "RETENÇÃO BAIXA"]


def _virgula_decimal(texto, tipo):
    """Os textos indexados trazem ponto decimal ("23.5"); a tela mostra vírgula, como o resto do painel.
    Na documentação só mexe em percentual e semestres, para não alterar versão e código."""
    padrao = r"(?<=\d)\.(?=\d{1,2}(?!\d))" if tipo != "documentacao" else r"(?<=\d)\.(?=\d{1,2}(?:%| semestres))"
    return re.sub(padrao, ",", texto)


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


MINUSCULAS = {"de", "da", "do", "das", "dos", "e", "em", "na", "no"}


def _nome(texto):
    """CURSO EM MAIÚSCULAS -> Curso em Maiúsculas (as fontes vêm sem acento)."""
    palavras = texto.lower().split()
    return " ".join(p if (i and p in MINUSCULAS) else p.capitalize() for i, p in enumerate(palavras))


def _campus(texto):
    """'FCE - CEILANDIA' -> 'FCE · Ceilandia': a sigla antes do hífen fica como está."""
    sigla, _, resto = texto.partition(" - ")
    return f"{sigla} · {_nome(resto)}" if resto else _nome(texto)


def _selos(r, meta):
    """Selos coloridos do cartão: tipo do resultado e, para IC, ano, curso, campus e linha de pesquisa."""
    selos = [f":{'green' if r['tipo'] == 'projeto_pibic' else 'blue' if r['tipo'] == 'curso' else 'gray'}-badge[{NOMES_TIPO.get(r['tipo'], r['tipo'])}]"]
    if r["tipo"] == "projeto_pibic":
        if meta.get("ano"):
            selos.append(f":orange-badge[{meta['ano']}]")
        if meta.get("curso"):
            selos.append(f":gray-badge[{_nome(meta['curso'])}]")
        if meta.get("campus"):
            selos.append(f":gray-badge[{_campus(meta['campus'])}]")
        if meta.get("linha_pesquisa"):
            selos.append(f":gray-badge[{meta['linha_pesquisa'].lower().capitalize()}]")
        if meta.get("planos", 1) > 1:
            selos.append(f":violet-badge[{br(meta['planos'])} planos iguais]")
    return " ".join(selos)


def _abrir_curso(nome):
    st.session_state["curso_selecionado"] = nome
    st.session_state["nav_aba"] = "🔍 Detalhe por Curso"


def _filtros(tipo):
    """Filtros de campus, turno, retenção, evasão e ano; só entram os que o usuário mexeu."""
    filtros = {}
    if tipo == "documentacao":
        return filtros
    with st.expander("🎛️ Filtros (campus, turno, retenção, evasão, ano)"):
        c1, c2, c3 = st.columns(3)
        if (campus := c1.selectbox("Campus", CAMPI)) != "Todos":
            filtros["campus"] = campus
        if tipo in (None, "curso"):
            if (turno := c2.selectbox("Turno (cursos)", TURNOS)) != "Todos":
                filtros["turno"] = turno
            if (ret := c3.selectbox("Retenção (cursos)", RETENCAO)) != "Todas":
                filtros["classificacao_retencao"] = ret
            lo, hi = st.slider("Taxa de evasão (%), só cursos", 0, 100, (0, 100))
            if lo > 0:
                filtros["evasao_min"] = lo
            if hi < 100:
                filtros["evasao_max"] = hi
        if tipo in (None, "projeto_pibic"):
            lo, hi = st.slider("Ano do plano de IC", 2018, 2025, (2018, 2025))
            if lo > 2018:
                filtros["ano_min"] = lo
            if hi < 2025:
                filtros["ano_max"] = hi
    return filtros


def _mostrar_resultado(r, idx):
    meta = r["metadados"] or {}
    com_texto = r["tipo"] != "projeto_pibic"  # o texto do plano de IC só repete o título e os selos
    with st.container(border=True):
        titulo = r["titulo"] if r["tipo"] != "curso" else _nome(r["titulo"])
        st.markdown(f"**{titulo}**")
        st.markdown(_selos(r, meta))
        if com_texto:
            texto = _virgula_decimal(r["conteudo"], r["tipo"])
            st.caption(texto[:420] + ("…" if len(texto) > 420 else ""))
        if r["tipo"] == "curso":
            st.button("🔍 Ver no Detalhe por Curso", key=f"abrir_{idx}", on_click=_abrir_curso, args=(r["titulo"],))
            evasao, formatura, irc = (meta.get(c) for c in ("taxa_evasao_pct", "taxa_formatura_pct", "indice_retencao_critica"))
            m1, m2, m3 = st.columns(3)
            m1.metric("Evasão", "—" if evasao is None else f"{dec(evasao, 1)}%")
            m2.metric("Formatura", "—" if formatura is None else f"{dec(formatura, 1)}%")
            m3.metric("Índice de retenção crítica", "—" if irc is None else f"{dec(irc, 1)}")
        st.caption(f"Similaridade {dec(r['similaridade'], 2)}")
        if meta and st.query_params.get("sql") == "1":  # metadados brutos: só no modo de depuração (?sql=1)
            with st.expander("Metadados"):
                st.json(meta)


def renderizar(g):
    """g: namespace do app.py (não usado: esta tela só lê do banco)."""
    st.subheader("🔎 Busca Semântica")
    st.markdown(
        "Pesquise por **significado**, não por palavra exata: planos de iniciação científica pelo tema, "
        "a documentação pela dúvida e cursos pela descrição. Siglas e nomes exatos também funcionam "
        "(ex.: `ADR 0028`, em *Documentação do projeto*)."
    )
    with st.expander("Como ler os resultados"):
        st.markdown(
            "- A busca capta tema, não número; use os filtros para restringir por campus, turno, retenção, evasão ou ano.\n"
            "- A similaridade é o cosseno entre a consulta e o texto (0 a 1), e não uma % de acerto: de 0,45 a 0,70 "
            "é comum em bons resultados.\n"
            "- A lista segue a relevância (similaridade, termos e título juntos): um resultado com similaridade "
            "menor pode vir antes porque o título ou os termos casam. Compare dentro da mesma busca, não entre buscas."
        )

    col_consulta, col_tipo, col_k = st.columns([4, 2, 1])
    consulta = col_consulta.text_input("O que você procura?", key="busca_consulta", placeholder="ex.: inteligência artificial na saúde")
    tipo = ROTULOS[col_tipo.selectbox("Onde procurar", list(ROTULOS))]
    k = col_k.number_input("Resultados", min_value=1, max_value=30, value=8)
    filtros = _filtros(tipo)

    try:
        temas, planos = _contagem_projetos_ic()
        if planos:
            st.caption(
                f"Projetos de IC: {br(temas)} documentos de busca representam {br(planos)} planos cadastrados "
                "(planos com mesmo título, ano, curso, campus e linha de pesquisa viram um só resultado)."
            )
    except Exception:  # banco fora do ar: a busca abaixo mostra o erro com o detalhe
        pass

    if not consulta.strip():
        return

    # O modelo vem antes e à parte: a primeira busca não fica parada sem aviso enquanto ele baixa, e
    # uma falha nele não aparece como banco fora do ar.
    try:
        _carregar_modelo()
    except Exception as erro:
        st.error(
            "Não foi possível carregar o modelo de embedding. Na primeira vez ele é baixado (~220 MB) "
            f"para `FASTEMBED_CACHE_PATH`; confira a conexão com a internet.\n\nDetalhe: `{erro}`"
        )
        return

    import psycopg
    from psycopg_pool import PoolTimeout

    from src.busca.buscar import buscar

    try:
        with st.spinner("Buscando..."):
            inicio = time.perf_counter()
            # Sem tipo escolhido, filtro só de curso ou só de IC restringe o tipo; senão vale o padrão.
            tipos = TIPOS_PADRAO if tipo is None else None
            if tipo is None and filtros.keys() & {"turno", "classificacao_retencao", "evasao_min", "evasao_max"}:
                tipos = ("curso",)
            elif tipo is None and filtros.keys() & {"ano_min", "ano_max"}:
                tipos = ("projeto_pibic",)
            resultados = buscar(consulta, k=int(k), tipo=tipo, tipos=tipos, filtros=filtros or None)
            latencia_ms = (time.perf_counter() - inicio) * 1000
    except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn, psycopg.errors.UndefinedFunction) as erro:
        st.error(
            "O banco não tem a busca semântica atualizada. Aplique as migrações e vetorize: "
            f"`python3 src/db/migrar.py && python3 src/busca/vetorizar.py`.\n\nDetalhe: `{erro}`"
        )
        return
    except (psycopg.OperationalError, PoolTimeout) as erro:
        st.error(
            "Não foi possível consultar o banco. Suba com `docker compose up -d db` e rode "
            f"`scripts/rodar_pipeline.sh`.\n\nDetalhe: `{erro}`"
        )
        return

    if not resultados:
        if _documentos_vetorizados() == 0:
            st.info("Nenhum documento vetorizado. Rode `python3 src/busca/vetorizar.py`.")
        else:
            st.info("Nenhum resultado relevante para essa consulta"
                    + (" e esses filtros. Tente limpar os filtros." if filtros else ". Tente outras palavras ou um tema mais amplo."))
        return
    st.caption(f"{len(resultados)} resultado(s) em {dec(latencia_ms, 0)} ms.")
    if expansoes := resultados[0].get("expansoes"):
        st.caption("💡 Siglas entendidas: " + " · ".join(f"`{a}` → _{b}_" for a, b in expansoes))
    for idx, r in enumerate(resultados):
        _mostrar_resultado(r, idx)
