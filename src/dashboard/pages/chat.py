"""
Página de chat do painel (Streamlit multipage): conversa com um LLM local (Ollama) que consulta a gold.

Precisa do banco e do Ollama no ar; na versão estática do GitHub Pages (stlite) esta página não é publicada.
"""

import sys
from pathlib import Path

import streamlit as st

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

st.set_page_config(page_title="Chat · Observatório UnB", page_icon="💬", layout="wide")
st.title("💬 Chat com os dados")
st.caption(
    "Um modelo local (Ollama) consulta só a gold agregada (k ≥ 5), em modo somente leitura. "
    "Confira os números no SQL executado antes de usá-los."
)

if "historico" not in st.session_state:
    st.session_state.historico = []  # mensagens no formato do Ollama, incluindo as de ferramenta
    st.session_state.exibicao = []  # (papel, texto, consultas) para desenhar a conversa

if st.sidebar.button("Nova conversa"):
    st.session_state.historico, st.session_state.exibicao = [], []

for papel, texto, consultas in st.session_state.exibicao:
    with st.chat_message(papel):
        st.markdown(texto)
        for sql in consultas:
            with st.expander("SQL executado"):
                st.code(sql, language="sql")

pergunta = st.chat_input("Pergunte sobre cursos, retenção, alunos ativos, IC...")
if pergunta:
    st.session_state.exibicao.append(("user", pergunta, []))
    with st.chat_message("user"):
        st.markdown(pergunta)
    with st.chat_message("assistant"), st.spinner("Consultando os dados..."):
        try:
            from src.chat.agente import conversar

            r = conversar(st.session_state.historico, pergunta)
            resposta, consultas = r["resposta"], r["consultas"]
        except Exception as e:  # noqa: BLE001
            resposta, consultas = f"Não consegui falar com o Ollama ou o banco: `{e}`", []
        st.markdown(resposta)
        for sql in consultas:
            with st.expander("SQL executado"):
                st.code(sql, language="sql")
    st.session_state.exibicao.append(("assistant", resposta, consultas))
