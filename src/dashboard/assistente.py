"""
Assistente do Observatório (chat com os dados): botão flutuante no canto inferior direito, exibido pelo app.py.
A conversa mora em st.session_state ('historico'/'exibicao') e sobrevive à troca de aba do painel.

Precisa do banco e do Ollama; na versão estática (stlite, sys.platform == "emscripten") o assistente flutuante não aparece.
"""

import base64
import html
import logging
import re
import sys
import threading
from pathlib import Path

import requests
import streamlit as st

log = logging.getLogger(__name__)
ASSETS = Path(__file__).resolve().parent / "assets"
# Imagem e link do markdown: o navegador buscaria a URL (vazamento por injeção de prompt). Fica só o texto.
IMAGEM_MD = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
LINK_MD = re.compile(r"\[([^\]]*)\]\([^)]*\)")
# Imagem/link por referência: `![x][r]` mais a definição `[r]: url` em outra linha.
# Cobre também as formas curta `![x]` e colapsada `![x][]`.
IMAGEM_REF_MD = re.compile(r"!\[([^\]]*)\](?:\[[^\]]*\])?")
DEFINICAO_MD = re.compile(r"(?m)^[ ]{0,3}\[[^\]]+\]:[ \t]*(\S.*)$")
# Destino com esquema (qualquer um) ou `//`; o markdown aceita entidades HTML e escapes (`h&#116;tp://`), então decodifica antes.
DESTINO_URL = re.compile(r"<?(?:[a-z][a-z0-9+.-]*:|//)", re.I)
MSG_INDISPONIVEL = "O assistente está indisponível no momento. Tente novamente em instantes."
MSG_AQUECENDO = ("O assistente ainda está se preparando (a primeira pergunta depois de um tempo parado demora). "
                 "Tente de novo em alguns minutos.")

EXEMPLOS = (
    "Quais cursos têm a maior taxa de evasão?",
    "Quantos alunos ativos a UnB tem hoje?",
    "Como é calculado o índice de retenção crítica?",
)

# Botão fixado no canto inferior direito (cores UnB: verde #008940, azul #133E79, amarelo #F2B705).
CSS_ASSISTENTE = """
<style>
.st-key-assistente { position: fixed; bottom: 1.2rem; right: 1.2rem; z-index: 999990; width: auto; }
.st-key-assistente button[data-testid="stPopoverButton"],
.st-key-assistente button[data-testid="stPopoverButton"]:focus,
.st-key-assistente button[data-testid="stPopoverButton"]:active {
    width: 58px; height: 58px; border-radius: 50%; padding: 0; border: 2px solid #fff;
    background: #008940 url("__ICONE__") center / 56% no-repeat !important;
    box-shadow: 0 6px 18px rgba(19,62,121,.35); transition: transform .15s, background-color .15s;
}
.st-key-assistente button[data-testid="stPopoverButton"]:hover { background-color: #133E79 !important; transform: scale(106%); }
.st-key-assistente button[data-testid="stPopoverButton"]:focus-visible { outline: 3px solid #F2B705; outline-offset: 2px; }
/* O rótulo fica no DOM (leitores de tela) mas invisível: quem aparece é o ícone. */
.st-key-assistente button[data-testid="stPopoverButton"] > div { opacity: 0; }
@media (prefers-reduced-motion: reduce) { .st-key-assistente button[data-testid="stPopoverButton"] { transition: none; } }
div[data-testid="stPopoverBody"]:has(.assistente-marca) {
    width: 380px; max-width: calc(100vw - 2rem); max-height: 85vh; overflow-y: auto;
    border-top: 4px solid #133E79;
}
div[data-testid="stPopoverBody"]:has(.assistente-marca) pre, div[data-testid="stPopoverBody"]:has(.assistente-marca) code { white-space: pre-wrap !important; word-break: break-word; }
div[data-testid="stPopoverBody"]:has(.assistente-marca) [data-testid="stCodeBlock"] pre { padding-right: 3.2rem; }
div[data-testid="stPopoverBody"]:has(.assistente-marca) [data-testid="stCodeBlock"] [data-testid="stCodeCopyButton"] { background: var(--secondary-background-color, #f0f2f6); border-radius: .3rem; }
.assistente-titulo { color: #133E79; font-weight: 700; font-size: 1.05rem; }
</style>
"""


def mostrar_sql() -> bool:
    """O SQL executado é para depuração: só aparece com `?sql=1` na URL do painel."""
    return st.query_params.get("sql") == "1"


def sem_links(texto):
    """Remove imagens e links do markdown, inclusive por referência (mantém o texto/rótulo)."""
    texto = DEFINICAO_MD.sub(
        lambda m: "" if DESTINO_URL.match(html.unescape(m.group(1)).replace("\\", "")) else m.group(0), texto)
    return LINK_MD.sub(r"\1", IMAGEM_REF_MD.sub(r"\1", IMAGEM_MD.sub(r"\1", texto)))


def desenhar_mensagem(papel, texto, consultas=(), avisos=()):
    """Desenha uma mensagem: texto, avisos e, só no modo de depuração, o SQL executado."""
    with st.chat_message(papel):
        st.markdown(sem_links(texto))
        for aviso in avisos:
            st.warning(aviso)
        for sql in consultas if mostrar_sql() else ():
            with st.expander("SQL executado"):
                st.code(sql, language="sql")


def responder(historico, pergunta):
    """Chama o agente; qualquer falha (Ollama ou banco fora do ar) vira mensagem amigável.
    Devolve (resposta, consultas, avisos)."""
    try:
        from src.chat.agente import conversar

        r = conversar(historico, pergunta)
        return r["resposta"], r["consultas"], r["avisos"]
    except requests.exceptions.Timeout:
        log.warning("Ollama não respondeu a tempo (modelo ainda carregando o prompt?)")
        return MSG_AQUECENDO, [], []
    except Exception:  # noqa: BLE001
        log.exception("Falha no chat")
        return MSG_INDISPONIVEL, [], []


def iniciar_estado():
    if "historico" not in st.session_state:
        st.session_state.historico = []  # mensagens no formato do Ollama, incluindo as de ferramenta
        st.session_state.exibicao = []  # (papel, texto, consultas, avisos) para desenhar a conversa


def nova_conversa():
    st.session_state.historico, st.session_state.exibicao = [], []


ROLAR_PARA_PERGUNTA = """<script>setTimeout(() => {
  const m = document.querySelectorAll('[data-testid="stPopoverBody"] [data-testid="stChatMessage"]');
  if (m.length > 1) m[m.length - 2].scrollIntoView({block: "start"});
}, 150);</script>"""


def conversa(pergunta=None, rolar=False):
    """Desenha o histórico e, se houver `pergunta`, envia ao agente e desenha a resposta.
    `rolar`: ao fim, mostra o começo da resposta (a área do assistente rola sozinha para o fim)."""
    iniciar_estado()
    # Pergunta interrompida por um rerun (troca de aba) é retomada aqui.
    pergunta = pergunta or st.session_state.get("pergunta_em_curso")
    for m in st.session_state.exibicao:
        desenhar_mensagem(*m)
    if pergunta:
        st.session_state.pergunta_em_curso = pergunta
        desenhar_mensagem("user", pergunta)
        # Trabalha numa cópia e grava o par pergunta/resposta só no fim: um rerun no meio da espera (clique em
        # outra aba) interrompe o script, e assim historico e exibicao nunca ficam dessincronizados.
        historico = list(st.session_state.historico)
        with st.spinner("Consultando os dados..."):
            resposta, consultas, avisos = responder(historico, pergunta)
        st.session_state.pergunta_em_curso = None  # um rerun no meio da espera não chega aqui: a pergunta é retomada
        desenhar_mensagem("assistant", resposta, consultas, avisos)
        st.session_state.historico = historico
        st.session_state.exibicao += [("user", pergunta, [], []), ("assistant", resposta, consultas, avisos)]
        if rolar:
            st.html(ROLAR_PARA_PERGUNTA, unsafe_allow_javascript=True)


@st.cache_resource
def _aquecer_modelo():
    """Uma vez por processo do painel: aquece o Ollama em segundo plano (falha só vai para o log)."""
    def tarefa():
        try:
            from src.chat.agente import aquecer

            aquecer()
        except Exception:  # noqa: BLE001
            log.warning("Não foi possível aquecer o modelo do assistente", exc_info=True)

    threading.Thread(target=tarefa, daemon=True).start()
    return True


def renderizar_assistente():
    """Botão flutuante que abre o assistente. Chamar no máximo uma vez por execução do script."""
    if sys.platform == "emscripten":  # stlite: sem banco nem Ollama
        return
    iniciar_estado()
    _aquecer_modelo()
    icone = "data:image/svg+xml;base64," + base64.b64encode((ASSETS / "assistente.svg").read_bytes()).decode("ascii")
    st.markdown(CSS_ASSISTENTE.replace("__ICONE__", icone), unsafe_allow_html=True)
    with st.container(key="assistente"), st.popover("Abrir o assistente"):
        st.markdown(
            '<span class="assistente-marca"></span><div class="assistente-titulo">Assistente do Observatório</div>',
            unsafe_allow_html=True,
        )
        area = st.container(height=360)  # a conversa rola dentro da área, acima da caixa de texto (criada depois)
        # O clique num exemplo vira a pergunta do próximo rerun (o botão é desenhado antes da conversa).
        pergunta = st.session_state.pop("assistente_pendente", None)
        pergunta = st.chat_input("Escreva sua pergunta...", key="assistente_entrada") or pergunta
        with area:
            if not st.session_state.exibicao and not (pergunta or st.session_state.get("pergunta_em_curso")):
                st.markdown("Olá! Sou o assistente do Observatório. Respondo perguntas sobre cursos, evasão, alunos ativos e iniciação científica da UnB. Por exemplo:")
                for i, exemplo in enumerate(EXEMPLOS):
                    st.button(exemplo, key=f"assistente_ex_{i}", use_container_width=True,
                              on_click=st.session_state.__setitem__, args=("assistente_pendente", exemplo))
            conversa(pergunta, rolar=True)
            if st.session_state.exibicao:
                st.button("Nova conversa", key="assistente_nova", on_click=nova_conversa)
