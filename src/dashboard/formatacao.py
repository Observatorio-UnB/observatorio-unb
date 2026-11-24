"""Formatação de números (padrão brasileiro), paleta acessível, exportação CSV e gráficos do painel."""

import pandas as pd
import streamlit as st

# Paleta colorblind-safe (Okabe-Ito / WCAG AA) combinada com formas distintas para codificação redundante
CORES_IRC = {
    "RETENÇÃO CRÍTICA": "#C23B22",  # vermelhão alto contraste
    "RETENÇÃO ALTA": "#D97706",     # âmbar escuro
    "RETENÇÃO MÉDIA": "#0072B2",    # azul Okabe-Ito
    "RETENÇÃO BAIXA": "#008940",    # verde institucional UnB
}

SIMBOLOS_IRC = {
    "RETENÇÃO CRÍTICA": "triangle-up",
    "RETENÇÃO ALTA": "diamond",
    "RETENÇÃO MÉDIA": "square",
    "RETENÇÃO BAIXA": "circle",
}

CORES_DESFECHO = {
    "Formatura": "#008940",
    "Evasão / Desligamento": "#C23B22",
    "Ainda ativo": "#0072B2",
    "Outros": "#64748B",
}


def br(valor, casas=0):
    """Número no padrão brasileiro: milhar com ponto, decimal com vírgula."""
    texto = f"{float(valor):,.{casas}f}"
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def dec(valor, casas=2):
    return f"{float(valor):.{casas}f}".replace(".", ",")


def delta_pp(atual, referencia, casas=1, unidade="p.p.", sufixo=""):
    """Formata diferença assinada no padrão brasileiro ('+2,3 p.p. vs. UnB')."""
    if pd.isna(atual) or pd.isna(referencia):
        return None
    diff = float(atual) - float(referencia)
    if round(abs(diff), casas) == 0:
        return f"0,{ '0' * casas if casas else '' } {unidade}{sufixo}".replace(", ", " ")
    sinal = "+" if diff > 0 else "-"
    return f"{sinal}{dec(abs(diff), casas)} {unidade}{sufixo}"


def botao_csv(df: pd.DataFrame, nome_arquivo: str, label: str = "📥 Baixar CSV (Gold, k ≥ 5)", key: str = None):
    """Exporta DataFrame já agregado da Gold (k >= 5) em CSV compatível com Excel PT-BR."""
    if df is None or df.empty:
        return
    csv_bytes = df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
    st.download_button(
        label=label,
        data=csv_bytes,
        file_name=nome_arquivo,
        mime="text/csv",
        key=key,
    )


def mostrar_tabela(df, casas=1, **kwargs):
    """st.dataframe com número no padrão brasileiro (vírgula decimal, ponto de milhar). Usa Styler: o
    texto mostrado muda, mas a coluna continua numérica e ordena como número. Colunas de ano ficam sem milhar."""
    formatos = {}
    for coluna in df.columns:
        serie = df[coluna]
        if pd.api.types.is_float_dtype(serie):
            formatos[coluna] = lambda v: "—" if pd.isna(v) else br(v, casas)
        elif pd.api.types.is_integer_dtype(serie) and not (serie.min() >= 1900 and serie.max() <= 2100):
            formatos[coluna] = br
    return st.dataframe(df.style.format(formatos), **kwargs)


def grafico(fig, **kwargs):
    """st.plotly_chart com vírgula decimal e ponto de milhar também nos eixos e no hover."""
    fig.update_layout(separators=",.")
    return st.plotly_chart(fig, **kwargs)


def reducao(valor, casas, unidade):
    """Texto de redução ("-1,5 p.p."), sem "-0" quando o valor arredonda para zero."""
    return f"-{dec(valor, casas)} {unidade}" if round(float(valor), casas) > 0 else f"0 {unidade}"
