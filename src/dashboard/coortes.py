"""
Lógica analítica de coortes, incerteza estatística (Wilson / Funil) e narrativa executiva, sem Streamlit.

Projetado para rodar igualmente no PostgreSQL local e no GitHub Pages (stlite/Pyodide), usando
apenas pandas e numpy (sem scipy), e para ser testado em unittest sem subir o painel.
"""

from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

Z_95 = 1.959963984540054
Z_998 = 3.090232306167813

ATRIBUTOS_ESTATICOS_CURSO = [
    "departamento",
    "campus",
    "turno",
    "area_conhecimento",
    "grau_academico",
    "categoria_grau",
    "semestre_minimo_previsto",
    "semestre_ideal_previsto",
    "semestre_maximo_previsto",
    "carga_horaria_minima",
    "pibic_total_projetos",
    "pibic_bolsas_remuneradas",
    "pibic_bolsas_voluntarias",
    "pibic_cotistas",
    "pibic_investimento_total",
    "pibic_projetos_por_100_alunos",
]

COLUNAS_FAIXAS_PCT = [
    "formados_tempo_minimo_pct",
    "formados_tempo_ideal_pct",
    "formados_acima_ideal_pct",
    "formados_limite_maximo_pct",
    "faixa_minimo_pct",
    "faixa_ideal_pct",
    "faixa_acima_pct",
    "faixa_limite_pct",
]


def intervalo_oficial(meta: Optional[dict]) -> Tuple[int, int]:
    """Extrai (ano_ini, ano_fim) de global_meta['coortes_ingresso_analisadas']."""
    texto = str((meta or {}).get("coortes_ingresso_analisadas", "2010-2016"))
    try:
        a, b = texto.split("-")
        return int(a.strip()), int(b.strip())
    except (ValueError, AttributeError):
        return 2010, 2016


def anos_disponiveis(df_coortes: Optional[pd.DataFrame]) -> Tuple[List[int], Optional[int]]:
    """Lista ordenada de anos de ingresso e o último ano de coorte madura."""
    if df_coortes is None or df_coortes.empty or "ano_ingresso" not in df_coortes.columns:
        return [], None
    anos = sorted(int(a) for a in df_coortes["ano_ingresso"].dropna().unique())
    maduras = df_coortes[df_coortes["coorte_madura"].astype(bool)]["ano_ingresso"] if "coorte_madura" in df_coortes.columns else pd.Series(dtype=int)
    ultimo_maduro = int(maduras.max()) if not maduras.empty else None
    return anos, ultimo_maduro


def _norm_p5_p95(serie: pd.Series) -> pd.Series:
    """Normalização min-max saturada nos percentis 5 e 95 (ADR 0006)."""
    s = serie.astype(float)
    validos = s.dropna()
    if validos.empty:
        return pd.Series(0.0, index=s.index)
    p05 = float(validos.quantile(0.05))
    p95 = float(validos.quantile(0.95))
    if p95 <= p05:
        return pd.Series(0.0, index=s.index)
    return ((s.clip(lower=p05, upper=p95) - p05) / (p95 - p05)).fillna(0.0)


def calcular_irc(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula IRC (0-100) e classificação por quartis conforme ADR 0006."""
    out = df.copy()
    if out.empty:
        out["indice_retencao_critica"] = pd.Series(dtype=float)
        out["classificacao_retencao"] = pd.Series(dtype=str)
        return out

    atraso_pos = out["desvio_medio_semestres"].astype(float).clip(lower=0.0).fillna(0.0)
    evasao = out["taxa_evasao_pct"].astype(float).fillna(0.0)
    irc = ((0.3 * _norm_p5_p95(atraso_pos) + 0.7 * _norm_p5_p95(evasao)) * 100.0).round(1)
    out["indice_retencao_critica"] = irc

    q25, q50, q75 = irc.quantile([0.25, 0.50, 0.75]).tolist()

    def _classificar(v: float) -> str:
        if pd.isna(v):
            return "RETENÇÃO BAIXA"
        if v >= q75:
            return "RETENÇÃO CRÍTICA"
        if v >= q50:
            return "RETENÇÃO ALTA"
        if v >= q25:
            return "RETENÇÃO MÉDIA"
        return "RETENÇÃO BAIXA"

    out["classificacao_retencao"] = irc.apply(_classificar)
    return out


def _media_ponderada_grupo(g: pd.DataFrame, col: str, peso_col: str = "total_formados") -> float:
    if col not in g.columns:
        return float("nan")
    d = g.dropna(subset=[col])
    if d.empty:
        return float("nan")
    w = d[peso_col].astype(float)
    soma_w = float(w.sum())
    if soma_w <= 0:
        return float("nan")
    return float((d[col].astype(float) * w).sum() / soma_w)


def reagregar_por_coortes(
    df_coortes: pd.DataFrame,
    df_gold_base: pd.DataFrame,
    ano_ini: int,
    ano_fim: int,
    cursos_tronco: Iterable[str] = (),
) -> pd.DataFrame:
    """Reagrega gold.retencao_cursos_coorte num intervalo [ano_ini, ano_fim] em Pandas.

    Enriquece com atributos estáticos de df_gold_base (campus, turno, grau, PIBIC) e recalcula
    atraso e IRC seguindo a ADR 0006. Exclui cursos-tronco (ADR 0022).
    """
    if df_coortes is None or df_coortes.empty:
        return pd.DataFrame()

    troncos = set(cursos_tronco)
    recorte = df_coortes[
        (df_coortes["ano_ingresso"] >= ano_ini)
        & (df_coortes["ano_ingresso"] <= ano_fim)
        & (~df_coortes["curso"].isin(troncos))
    ]
    if recorte.empty:
        return pd.DataFrame()

    linhas = []
    for curso, g in recorte.groupby("curso", sort=True):
        reg = int(g["total_discentes_registrados"].sum())
        form = int(g["total_formados"].sum())
        evad = int(g["total_evadidos_desligados"].sum())
        ativos = int(g["total_ainda_ativos"].sum())
        sem_ideal = float(g["semestre_ideal_previsto"].iloc[0]) if "semestre_ideal_previsto" in g.columns else float("nan")
        tempo_real = _media_ponderada_grupo(g, "tempo_medio_real_semestres", "total_formados")
        desvio = (tempo_real - sem_ideal) if (pd.notna(tempo_real) and pd.notna(sem_ideal)) else float("nan")

        linha = {
            "curso": curso,
            "semestre_ideal_previsto": sem_ideal,
            "total_discentes_registrados": reg,
            "total_formados": form,
            "total_evadidos_desligados": evad,
            "total_ainda_ativos": ativos,
            "taxa_formatura_pct": (form / reg * 100.0) if reg else float("nan"),
            "taxa_evasao_pct": (evad / reg * 100.0) if reg else float("nan"),
            "tempo_medio_real_semestres": tempo_real,
            "desvio_medio_semestres": desvio,
        }
        for col_pct in COLUNAS_FAIXAS_PCT:
            if col_pct in g.columns:
                linha[col_pct] = _media_ponderada_grupo(g, col_pct, "total_formados")
        linhas.append(linha)

    df_agg = pd.DataFrame(linhas)

    if df_gold_base is not None and not df_gold_base.empty:
        cols_disp = [c for c in ATRIBUTOS_ESTATICOS_CURSO if c in df_gold_base.columns and c != "semestre_ideal_previsto"]
        estaticos = df_gold_base[["curso"] + cols_disp].drop_duplicates(subset=["curso"])
        df_agg = df_agg.merge(estaticos, on="curso", how="left")
        if "semestre_ideal_previsto" in df_gold_base.columns:
            ideais = df_gold_base.set_index("curso")["semestre_ideal_previsto"]
            df_agg["semestre_ideal_previsto"] = df_agg["semestre_ideal_previsto"].fillna(df_agg["curso"].map(ideais))

    for col_txt in ("campus", "turno", "categoria_grau", "area_conhecimento", "departamento"):
        if col_txt not in df_agg.columns:
            df_agg[col_txt] = "NÃO INFORMADO"
        else:
            df_agg[col_txt] = df_agg[col_txt].fillna("NÃO INFORMADO")

    if "pibic_total_projetos" in df_agg.columns:
        df_agg["pibic_total_projetos"] = df_agg["pibic_total_projetos"].fillna(0).astype(int)

    return calcular_irc(df_agg)


def ic_wilson_pct(sucessos: float, n: float, z: float = Z_95) -> Tuple[float, float, float]:
    """Intervalo de confiança de Wilson em percentual: (inferior_pct, superior_pct, meia_largura_pct)."""
    if n is None or n <= 0 or pd.isna(n) or pd.isna(sucessos):
        return float("nan"), float("nan"), float("nan")
    p = min(1.0, max(0.0, float(sucessos) / float(n)))
    z2 = z * z
    denom = 1.0 + z2 / n
    centro = (p + z2 / (2.0 * n)) / denom
    margem = (z * np.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n)) / denom
    inf = max(0.0, (centro - margem) * 100.0)
    sup = min(100.0, (centro + margem) * 100.0)
    return float(inf), float(sup), float((sup - inf) / 2.0)


def limites_funil(p_global_pct: float, n_vals: Sequence[float], z: float = Z_95) -> Tuple[np.ndarray, np.ndarray]:
    """Limites inferior e superior (%) de um Funnel Plot em torno da taxa institucional."""
    n_arr = np.asarray(n_vals, dtype=float)
    p = min(1.0, max(0.0, float(p_global_pct) / 100.0))
    se = np.sqrt(p * (1.0 - p) / np.maximum(n_arr, 1.0))
    inf = np.clip((p - z * se) * 100.0, 0.0, 100.0)
    sup = np.clip((p + z * se) * 100.0, 0.0, 100.0)
    return inf, sup


def comparar_periodos(
    df_coortes: pd.DataFrame,
    periodo_a: Tuple[int, int],
    periodo_b: Tuple[int, int],
    cursos_tronco: Iterable[str] = (),
    min_alunos: int = 15,
) -> pd.DataFrame:
    """Compara evasão e formatura de cada curso entre dois intervalos de coortes."""
    if df_coortes is None or df_coortes.empty:
        return pd.DataFrame()
    troncos = set(cursos_tronco)
    base = df_coortes[~df_coortes["curso"].isin(troncos)]

    def _agg(ini: int, fim: int) -> pd.DataFrame:
        rec = base[(base["ano_ingresso"] >= ini) & (base["ano_ingresso"] <= fim)]
        if rec.empty:
            return pd.DataFrame(columns=["curso", "n", "evasao", "formatura"])
        g = rec.groupby("curso", as_index=False).agg(
            n=("total_discentes_registrados", "sum"),
            evad=("total_evadidos_desligados", "sum"),
            form=("total_formados", "sum"),
        )
        g["evasao"] = g["evad"] / g["n"] * 100.0
        g["formatura"] = g["form"] / g["n"] * 100.0
        return g[g["n"] >= min_alunos][["curso", "n", "evasao", "formatura"]]

    a = _agg(*periodo_a)
    b = _agg(*periodo_b)
    if a.empty or b.empty:
        return pd.DataFrame()
    m = a.merge(b, on="curso", suffixes=("_a", "_b"))
    m["delta_evasao_pp"] = m["evasao_b"] - m["evasao_a"]
    m["delta_formatura_pp"] = m["formatura_b"] - m["formatura_a"]
    return m.sort_values("delta_evasao_pp", ascending=False).reset_index(drop=True)


def matriz_heatmap_coortes(
    df_coortes: pd.DataFrame,
    metrica: str = "taxa_evasao_pct",
    cursos_tronco: Iterable[str] = (),
    top_n: int = 25,
    cursos_selecionados: Optional[Sequence[str]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, List[int]]:
    """Prepara matrizes (cursos x ano_ingresso) de valores e de n para o heatmap.

    Células ausentes permanecem NaN para receber rótulo neutro de privacidade (ADR 0005).
    """
    if df_coortes is None or df_coortes.empty:
        return pd.DataFrame(), pd.DataFrame(), []
    troncos = set(cursos_tronco)
    base = df_coortes[~df_coortes["curso"].isin(troncos)].copy()
    if base.empty:
        return pd.DataFrame(), pd.DataFrame(), []

    if cursos_selecionados:
        base = base[base["curso"].isin(cursos_selecionados)]
    else:
        # Ordena pelos maiores cursos (em ingressantes) para máxima representatividade no heatmap
        maiores = (
            base.groupby("curso")["total_discentes_registrados"]
            .sum()
            .nlargest(top_n)
            .index.tolist()
        )
        base = base[base["curso"].isin(maiores)]

    if base.empty:
        return pd.DataFrame(), pd.DataFrame(), []

    # Ordenação vertical: cursos com maior média na métrica escolhida no topo (usando coortes maduras se houver)
    mad = base[base["coorte_madura"].astype(bool)] if "coorte_madura" in base.columns else base
    ordem_ref = mad if not mad.empty else base
    ordem_cursos = (
        ordem_ref.groupby("curso")[metrica]
        .mean()
        .sort_values(ascending=False)
        .index.tolist()
    )
    # Garante que cursos presentes só em coortes recentes também entrem na ordem
    for c in sorted(base["curso"].unique()):
        if c not in ordem_cursos:
            ordem_cursos.append(c)

    anos = sorted(int(a) for a in base["ano_ingresso"].unique())
    piv_val = base.pivot(index="curso", columns="ano_ingresso", values=metrica).reindex(index=ordem_cursos, columns=anos)
    piv_n = base.pivot(index="curso", columns="ano_ingresso", values="total_discentes_registrados").reindex(index=ordem_cursos, columns=anos)
    return piv_val, piv_n, anos


def _fmt_br(valor: float, casas: int = 1) -> str:
    texto = f"{float(valor):,.{casas}f}"
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def narrativa_executiva(
    df_view: pd.DataFrame,
    df_baseline: Optional[pd.DataFrame],
    recorte_txt: str,
    eh_oficial: bool = True,
    min_ranking: int = 30,
) -> List[str]:
    """Gera até 3 bullets factuais (sem alegação causal) resumindo o recorte visível."""
    if df_view is None or df_view.empty:
        return []

    bullets: List[str] = []
    tot_n = int(df_view["total_discentes_registrados"].sum())
    tot_ev = int(df_view["total_evadidos_desligados"].sum())
    tot_fo = int(df_view["total_formados"].sum())
    ev_pct = (tot_ev / tot_n * 100.0) if tot_n else 0.0
    fo_pct = (tot_fo / tot_n * 100.0) if tot_n else 0.0

    # 1. Síntese geral do recorte
    if not eh_oficial and df_baseline is not None and not df_baseline.empty:
        base_n = float(df_baseline["total_discentes_registrados"].sum())
        base_ev = (float(df_baseline["total_evadidos_desligados"].sum()) / base_n * 100.0) if base_n else 0.0
        diff = ev_pct - base_ev
        sinal = "+" if diff >= 0 else "-"
        bullets.append(
            f"**Panorama ({recorte_txt}):** {_fmt_br(tot_n, 0)} ingressantes em {len(df_view)} cursos, "
            f"com evasão agregada de **{_fmt_br(ev_pct, 1)}%** ({sinal}{_fmt_br(abs(diff), 1)} p.p. vs. "
            f"baseline oficial) e formatura de **{_fmt_br(fo_pct, 1)}%**."
        )
    else:
        bullets.append(
            f"**Panorama ({recorte_txt}):** {_fmt_br(tot_n, 0)} ingressantes em {len(df_view)} cursos terminais, "
            f"com **{_fmt_br(fo_pct, 1)}%** de formatura e **{_fmt_br(ev_pct, 1)}%** de evasão/desligamento."
        )

    # 2. Concentração da evasão no Top 5 cursos por volume de evadidos
    if tot_ev > 0 and len(df_view) >= 5:
        top5 = df_view.nlargest(5, "total_evadidos_desligados")
        share_top5 = float(top5["total_evadidos_desligados"].sum()) / tot_ev * 100.0
        lider = str(top5.iloc[0]["curso"]).title()
        bullets.append(
            f"**Concentração de volume:** os 5 cursos com mais saídas sem diploma concentram "
            f"**{_fmt_br(share_top5, 1)}%** de todas as evasões do recorte (liderado por **{lider}**, "
            f"com {_fmt_br(int(top5.iloc[0]['total_evadidos_desligados']), 0)} discentes)."
        )

    # 3. Contraste de turno (quando ambos Diurno e Noturno estão presentes) ou extremo do recorte
    if "turno" in df_view.columns:
        diu = df_view[df_view["turno"].astype(str).str.upper() == "DIURNO"]
        notu = df_view[df_view["turno"].astype(str).str.upper() == "NOTURNO"]
        if not diu.empty and not notu.empty:
            ev_diu = diu["total_evadidos_desligados"].sum() / max(1, diu["total_discentes_registrados"].sum()) * 100.0
            ev_not = notu["total_evadidos_desligados"].sum() / max(1, notu["total_discentes_registrados"].sum()) * 100.0
            diff_t = ev_not - ev_diu
            dir_txt = "maior" if diff_t >= 0 else "menor"
            bullets.append(
                f"**Recorte por turno:** cursos noturnos registram evasão agregada de **{_fmt_br(ev_not, 1)}%**, "
                f"**{_fmt_br(abs(diff_t), 1)} p.p. {dir_txt}** que os cursos diurnos ({_fmt_br(ev_diu, 1)}%) — "
                "associação descritiva, sem controle de perfil socioeconômico."
            )
            return bullets

    grandes = df_view[df_view["total_discentes_registrados"] >= min_ranking]
    if not grandes.empty:
        pior = grandes.sort_values("taxa_evasao_pct", ascending=False).iloc[0]
        melhor = grandes.sort_values("taxa_evasao_pct", ascending=True).iloc[0]
        bullets.append(
            f"**Extremos ({min_ranking}+ alunos):** maior taxa de evasão em **{str(pior['curso']).title()}** "
            f"({_fmt_br(pior['taxa_evasao_pct'], 1)}%) e menor em **{str(melhor['curso']).title()}** "
            f"({_fmt_br(melhor['taxa_evasao_pct'], 1)}%)."
        )
    return bullets
