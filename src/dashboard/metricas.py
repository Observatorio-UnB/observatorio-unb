"""
Leitura da camada semântica de métricas pelo painel, sem Streamlit.

As comparações entre grupos de cursos (turno, grau, campus) vêm de dbt_marts.metricas_por_recorte, em
que cada taxa de um grupo é a razão das somas dos cursos, pela mesma fórmula do curso
(transform/macros/metricas.sql). O app.py a usa em agregar_ponderado, e assim o painel não mantém
uma segunda implementação da fórmula.

Sem o mart no export (banco sem as camadas do dbt), o recorte é recalculado da gold pela mesma regra,
razão das somas, no mesmo universo (cursos terminais, sem os cursos-tronco). As métricas que precisam
das bases por vínculo (tempo médio, prazo ideal médio, % no prazo ideal) ficam vazias nesse caso, em
vez de saírem por outra conta.

O registro versionado das definições (dbt_marts.metricas_definicoes) vai junto, para o painel mostrar
o que cada número significa e em que versão está.

Fica num módulo próprio para ser testado sem subir o painel (tests/test_unit_metricas_painel.py) e
para rodar igual no GitHub Pages, onde o stlite carrega este arquivo junto com o app.py.
"""

from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

FONTE_SEMANTICA = "dbt_marts.metricas_por_recorte (camada semântica)"
FONTE_GOLD = "gold.retencao_cursos_unb, pela mesma definição (sem a camada semântica nestes dados)"

# Coluna da gold que corresponde a cada recorte da camada semântica.
COLUNA_GOLD = {
    "CAMPUS": "campus",
    "CATEGORIA_GRAU": "categoria_grau",
    "AREA_CONHECIMENTO": "area_conhecimento",
    "TURNO": "turno",
}

COLUNAS = [
    "valor", "cursos", "ingressantes", "formados", "evadidos",
    "taxa_formatura_pct", "taxa_evasao_pct", "formados_tempo_ideal_pct",
    "atraso_medio_semestres", "tempo_medio_formatura_semestres", "prazo_ideal_medio_semestres",
]


def _arredondar(serie: pd.Series) -> pd.Series:
    """Duas casas com empate para o par, como a macro arredondar do dbt (numpy.round)."""
    return serie.astype(float).round(2)


def metricas_por_recorte(tabelas: Dict[str, List[Dict]], df_gold: Optional[pd.DataFrame], recorte: str,
                         cursos_tronco: Iterable[str] = ()) -> Tuple[Optional[pd.DataFrame], str]:
    """Métricas de cada grupo do recorte (TURNO, CAMPUS, ...) e a tabela de onde vieram."""
    linhas = [r for r in (tabelas.get("metricas_por_recorte") or []) if r.get("recorte") == recorte]
    if linhas:
        return pd.DataFrame(linhas)[COLUNAS].reset_index(drop=True), FONTE_SEMANTICA

    if df_gold is None or df_gold.empty or recorte not in COLUNA_GOLD:
        return None, FONTE_GOLD
    terminais = df_gold[~df_gold["curso"].isin(set(cursos_tronco))]
    df = terminais.groupby(COLUNA_GOLD[recorte]).agg(
        cursos=("curso", "count"),
        ingressantes=("total_discentes_registrados", "sum"),
        formados=("total_formados", "sum"),
        evadidos=("total_evadidos_desligados", "sum"),
    ).reset_index().rename(columns={COLUNA_GOLD[recorte]: "valor"})
    df["taxa_formatura_pct"] = _arredondar(df["formados"] / df["ingressantes"] * 100)
    df["taxa_evasao_pct"] = _arredondar(df["evadidos"] / df["ingressantes"] * 100)
    for coluna in ("formados_tempo_ideal_pct", "atraso_medio_semestres",
                   "tempo_medio_formatura_semestres", "prazo_ideal_medio_semestres"):
        df[coluna] = float("nan")
    return df[COLUNAS], FONTE_GOLD


def metricas_da_unb(tabelas: Dict[str, List[Dict]]) -> Optional[Dict]:
    """A linha UNB da camada semântica: os números "da UnB inteira" que o painel mostra (KPIs da Visão
    Executiva, escopo global do simulador). Mesmo universo do ranking: cursos terminais, k >= 5."""
    for linha in tabelas.get("metricas_por_recorte") or []:
        if linha.get("recorte") == "UNB":
            return linha
    return None


def definicoes(tabelas: Dict[str, List[Dict]], metricas: Optional[Iterable[str]] = None) -> Optional[pd.DataFrame]:
    """Registro das métricas (rótulo, definição, fórmula, unidade, versão), na ordem do registro."""
    registro = tabelas.get("metricas_definicoes") or []
    if not registro:
        return None
    df = pd.DataFrame(registro)
    if metricas is not None:
        df = df[df["metrica"].isin(set(metricas))]
    return df[["rotulo", "definicao", "formula", "unidade", "versao", "vigente_desde", "adr"]].rename(columns={
        "rotulo": "Métrica", "definicao": "Definição", "formula": "Fórmula", "unidade": "Unidade",
        "versao": "Versão", "vigente_desde": "Desde", "adr": "ADR",
    }).reset_index(drop=True)
