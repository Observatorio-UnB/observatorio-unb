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


def _mostrar_resultado(r):
    meta = r["metadados"] or {}
    with st.container(border=True):
        planos = f" · {br(meta['planos'])} planos iguais" if r["tipo"] == "projeto_pibic" and meta.get("planos", 1) > 1 else ""
        st.markdown(
            f"**{r['titulo']}**  \n"
            f"<small>{NOMES_TIPO.get(r['tipo'], r['tipo'])} · similaridade {dec(r['similaridade'], 2)}{planos}</small>",
            unsafe_allow_html=True,
        )
        st.caption(_virgula_decimal(r["conteudo"], r["tipo"]))
        if r["tipo"] == "curso":
            evasao, formatura, irc = (meta.get(c) for c in ("taxa_evasao_pct", "taxa_formatura_pct", "indice_retencao_critica"))
            m1, m2, m3 = st.columns(3)
            m1.metric("Evasão", "—" if evasao is None else f"{dec(evasao, 1)}%")
            m2.metric("Formatura", "—" if formatura is None else f"{dec(formatura, 1)}%")
            m3.metric("Índice de retenção crítica", "—" if irc is None else f"{dec(irc, 1)}")
        if meta:
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
            "- A busca capta tema, não número: para filtrar cursos por turno ou taxa de evasão, use as outras telas.\n"
            "- A similaridade é o cosseno entre a consulta e o texto (0 a 1), e não uma % de acerto: de 0,45 a 0,70 "
            "é comum em bons resultados.\n"
            "- A lista segue a relevância (similaridade, termos e título juntos): um resultado com similaridade "
            "menor pode vir antes porque o título ou os termos casam. Compare dentro da mesma busca, não entre buscas."
        )

    col_consulta, col_tipo, col_k = st.columns([4, 2, 1])
    consulta = col_consulta.text_input("O que você procura?", key="busca_consulta", placeholder="ex.: inteligência artificial na saúde")
    tipo = ROTULOS[col_tipo.selectbox("Onde procurar", list(ROTULOS))]
    k = col_k.number_input("Resultados", min_value=1, max_value=30, value=8)

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
            resultados = buscar(consulta, int(k) * (1 if tipo else 3), tipo)
            if tipo is None:
                resultados = [r for r in resultados if r["tipo"] in TIPOS_PADRAO][: int(k)]
            latencia_ms = (time.perf_counter() - inicio) * 1000
    except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn) as erro:
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
            st.info("Nenhum resultado relevante para essa consulta. Tente outras palavras ou um tema mais amplo.")
        return
    st.caption(f"{len(resultados)} resultado(s) em {dec(latencia_ms, 0)} ms.")
    for r in resultados:
        _mostrar_resultado(r)
