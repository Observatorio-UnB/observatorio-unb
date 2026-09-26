"""
Página de busca semântica do painel (Streamlit multipage).

Consulta busca.documentos no PostgreSQL. Só funciona com o banco no ar: na
versão estática do GitHub Pages (stlite) esta página não é publicada.
"""

import sys
from pathlib import Path

import streamlit as st

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

st.set_page_config(page_title="Busca semântica · Observatório UnB", page_icon="🔎", layout="wide")

ROTULOS = {
    "Tudo": None,
    "Cursos": "curso",
    "Projetos de iniciação científica": "projeto_pibic",
    "Documentação do projeto": "documentacao",
}
NOMES_TIPO = {"curso": "Curso", "projeto_pibic": "Projeto de IC", "documentacao": "Documentação"}

st.title("🔎 Busca semântica")
st.markdown(
    "Pesquise por **significado**, não por palavra exata: planos de iniciação científica pelo "
    "tema, a documentação do projeto pela dúvida e cursos pela descrição. "
    "A consulta é vetorizada e comparada com os documentos em `busca.documentos` (pgvector)."
)
st.caption(
    "A busca semântica capta tema, não número: para filtrar cursos por turno ou taxa de evasão, "
    "use as outras telas do painel."
)

col_consulta, col_tipo, col_k = st.columns([4, 2, 1])
consulta = col_consulta.text_input(
    "O que você procura?", placeholder="ex.: inteligência artificial na saúde"
)
tipo = ROTULOS[col_tipo.selectbox("Onde procurar", list(ROTULOS))]
k = col_k.number_input("Resultados", min_value=1, max_value=30, value=8)

if consulta.strip():
    try:
        from src.busca.buscar import buscar

        with st.spinner("Buscando..."):
            resultados = buscar(consulta, int(k), tipo)
    except Exception as erro:  # banco fora do ar, tabela vazia, modelo não baixado
        st.error(
            "Não foi possível consultar o banco. Suba com `docker compose up -d db` e rode "
            f"`scripts/rodar_pipeline.sh`.\n\nDetalhe: `{erro}`"
        )
        st.stop()

    if not resultados:
        st.info("Nenhum documento vetorizado. Rode `python3 src/busca/vetorizar.py`.")
    for r in resultados:
        with st.container(border=True):
            st.markdown(
                f"**{r['titulo']}**  \n"
                f"<small>{NOMES_TIPO.get(r['tipo'], r['tipo'])} · similaridade {r['similaridade']:.2f}</small>",
                unsafe_allow_html=True,
            )
            st.caption(r["conteudo"])
            if r["metadados"]:
                with st.expander("Metadados"):
                    st.json(r["metadados"])
