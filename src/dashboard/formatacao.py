"""Formatação de números (padrão brasileiro) e de tabelas e gráficos do painel."""

import pandas as pd
import streamlit as st


def br(valor, casas=0):
    """Número no padrão brasileiro: milhar com ponto, decimal com vírgula."""
    texto = f"{float(valor):,.{casas}f}"
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def dec(valor, casas=2):
    return f"{float(valor):.{casas}f}".replace(".", ",")


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
