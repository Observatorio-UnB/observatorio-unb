"""Componentes visuais longitudinais e de incerteza: Heatmap de Coortes, Comparador de Períodos e Funil."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from coortes import (
    Z_95,
    Z_998,
    comparar_periodos,
    limites_funil,
    matriz_heatmap_coortes,
)
from formatacao import CORES_IRC, SIMBOLOS_IRC, botao_csv, br, dec, grafico


def render_funil(df_view: pd.DataFrame, ev_atual: float, n_min_ranking: int):
    """Gráfico Funil (Funnel Plot) com limites de 95% e 99,8% para evidenciar variância em cursos pequenos."""
    st.markdown(
        f"O **Gráfico Funil (Funnel Plot)** ilustra por que a ADR 0006 adota o corte de **{n_min_ranking} ingressantes** "
        "na fila de intervenção: quanto menor a turma (esquerda), maior a dispersão aleatória esperada em torno da "
        f"média institucional ({dec(ev_atual, 1)}%). Cursos fora das curvas de **99,8%** exibem desvio estatisticamente "
        "incomum mesmo considerando o tamanho da amostra."
    )
    n_max = int(df_view["total_discentes_registrados"].max())
    n_grid = np.linspace(5, max(50, n_max), 200)
    inf95, sup95 = limites_funil(ev_atual, n_grid, z=Z_95)
    inf998, sup998 = limites_funil(ev_atual, n_grid, z=Z_998)

    fig_funil = go.Figure()
    fig_funil.add_trace(go.Scatter(
        x=n_grid, y=sup998, mode="lines", name="Limite 99,8% (3σ)",
        line={"color": "#C23B22", "dash": "dot", "width": 1.5},
    ))
    fig_funil.add_trace(go.Scatter(
        x=n_grid, y=inf998, mode="lines", showlegend=False,
        line={"color": "#C23B22", "dash": "dot", "width": 1.5},
    ))
    fig_funil.add_trace(go.Scatter(
        x=n_grid, y=sup95, mode="lines", name="Limite 95% (2σ)",
        line={"color": "#0072B2", "dash": "dash", "width": 1.5},
    ))
    fig_funil.add_trace(go.Scatter(
        x=n_grid, y=inf95, mode="lines", showlegend=False,
        line={"color": "#0072B2", "dash": "dash", "width": 1.5},
    ))
    fig_funil.add_hline(
        y=ev_atual, line_color="#1E293B", line_width=1.5,
        annotation_text=f"Média do recorte ({dec(ev_atual, 1)}%)",
    )
    fig_funil.add_vline(
        x=n_min_ranking, line_dash="dash", line_color="#64748B",
        annotation_text=f"Corte ADR 0006 (n={n_min_ranking})",
    )

    for classe, cor in CORES_IRC.items():
        sub = df_view[df_view["classificacao_retencao"] == classe]
        if sub.empty:
            continue
        fig_funil.add_trace(go.Scatter(
            x=sub["total_discentes_registrados"],
            y=sub["taxa_evasao_pct"],
            mode="markers",
            name=classe,
            text=sub["curso"],
            marker={"color": cor, "symbol": SIMBOLOS_IRC[classe], "size": 9},
            hovertemplate="<b>%{text}</b><br>Ingressantes: %{x:,}<br>Evasão: %{y:.1f}%<extra></extra>",
        ))
    fig_funil.update_layout(
        xaxis_title="Total de Ingressantes (Tamanho da Amostra)",
        yaxis_title="Taxa de Evasão (%)",
        height=480,
        legend={"orientation": "h", "y": -0.18},
    )
    grafico(fig_funil, width="stretch", key="funnel_evasao")


def render_heatmap_e_comparador(g, df_coortes_all: pd.DataFrame):
    """Seção longitudinal: Heatmap de Coortes (com fronteira madura/imatura) + Comparador de Períodos."""
    EXCLUDED_GENERIC_COURSES = g.EXCLUDED_GENERIC_COURSES
    ULTIMO_ANO_MADURO = g.ULTIMO_ANO_MADURO
    ANOS_COORTE = g.ANOS_COORTE

    st.markdown("---")
    st.subheader("🗓️ Evolução Longitudinal por Coorte (Ano de Ingresso)")
    st.caption(
        "Células sem número indicam ausência de dado publicado (turma com menos de 5 alunos — "
        "supressão por k-anonimato, ADR 0005 — ou curso sem ingresso naquele ano). "
        "A escala de cor é calibrada apenas nas coortes maduras (8+ anos) para evitar distorção visual por censura à direita."
    )

    tab_hm, tab_comp = st.tabs([
        "🔥 Heatmap de Coortes (Curso × Ano)",
        "🔀 Comparador de Períodos Maduros",
    ])

    with tab_hm:
        hc1, hc2, hc3 = st.columns([2, 1, 2])
        with hc1:
            metrica_label = st.radio(
                "Indicador no heatmap:",
                ["Taxa de Evasão (%)", "Taxa de Formatura (%)"],
                horizontal=True,
                key="hm_metrica",
            )
            metrica_col = "taxa_evasao_pct" if "Evasão" in metrica_label else "taxa_formatura_pct"
        with hc2:
            top_n_hm = st.slider("Top cursos (por volume):", 10, 40, 20, step=5, key="hm_top_n")
        with hc3:
            cursos_hm = st.multiselect(
                "Ou selecione cursos específicos:",
                options=sorted(df_coortes_all["curso"].unique()),
                default=[],
                key="hm_cursos",
            )

        piv_val, piv_n, anos_hm = matriz_heatmap_coortes(
            df_coortes_all,
            metrica=metrica_col,
            cursos_tronco=EXCLUDED_GENERIC_COURSES,
            top_n=top_n_hm,
            cursos_selecionados=cursos_hm if cursos_hm else None,
        )

        if piv_val.empty:
            st.info("Sem dados suficientes para montar o heatmap com o filtro atual.")
        else:
            anos_rotulo = [
                f"{a}" if (ULTIMO_ANO_MADURO is None or a <= ULTIMO_ANO_MADURO) else f"{a} ⚠️"
                for a in anos_hm
            ]
            anos_maduros_hm = [a for a in anos_hm if ULTIMO_ANO_MADURO is None or a <= ULTIMO_ANO_MADURO]
            vals_ref = piv_val[anos_maduros_hm].values.flatten() if anos_maduros_hm else piv_val.values.flatten()
            vals_ref = vals_ref[~np.isnan(vals_ref)]
            zmin = float(np.percentile(vals_ref, 5)) if len(vals_ref) else 0.0
            zmax = float(np.percentile(vals_ref, 95)) if len(vals_ref) else 100.0
            if zmax <= zmin:
                zmin, zmax = 0.0, 100.0

            hover_text = []
            text_cell = []
            for curso in piv_val.index:
                linha_hover = []
                linha_txt = []
                for ano in anos_hm:
                    val = piv_val.loc[curso, ano]
                    n_val = piv_n.loc[curso, ano]
                    imatura = ULTIMO_ANO_MADURO is not None and ano > ULTIMO_ANO_MADURO
                    if pd.isna(val):
                        linha_hover.append(
                            f"<b>{curso}</b> · Turma {ano}<br>"
                            "Sem dado publicado (n &lt; 5 ou sem ingresso)"
                        )
                        linha_txt.append("—")
                    else:
                        status_txt = " ⚠️ Coorte imatura (&lt; 8 anos)" if imatura else " (coorte madura)"
                        linha_hover.append(
                            f"<b>{curso}</b> · Turma {ano}{status_txt}<br>"
                            f"{metrica_label}: <b>{dec(val, 1)}%</b><br>"
                            f"Ingressantes: <b>{br(int(n_val))}</b>"
                        )
                        linha_txt.append(f"{dec(val, 0)}%")
                hover_text.append(linha_hover)
                text_cell.append(linha_txt)

            escala = "YlOrRd" if "Evasão" in metrica_label else "YlGnBu"
            fig_hm = go.Figure(
                data=go.Heatmap(
                    z=piv_val.values,
                    x=anos_rotulo,
                    y=list(piv_val.index),
                    colorscale=escala,
                    zmin=zmin,
                    zmax=zmax,
                    text=text_cell,
                    texttemplate="%{text}",
                    textfont={"size": 10},
                    hovertext=hover_text,
                    hoverinfo="text",
                    xgap=2,
                    ygap=2,
                    colorbar={"title": "%"},
                )
            )

            if ULTIMO_ANO_MADURO is not None and any(a > ULTIMO_ANO_MADURO for a in anos_hm):
                idx_maduros = [i for i, a in enumerate(anos_hm) if a <= ULTIMO_ANO_MADURO]
                if idx_maduros:
                    x_fronteira = idx_maduros[-1] + 0.5
                    fig_hm.add_vline(
                        x=x_fronteira,
                        line_width=2,
                        line_dash="dash",
                        line_color="#1E293B",
                    )
                    fig_hm.add_vrect(
                        x0=x_fronteira,
                        x1=len(anos_hm) - 0.5,
                        fillcolor="#94A3B8",
                        opacity=0.14,
                        line_width=0,
                    )
                    fig_hm.add_annotation(
                        x=x_fronteira,
                        y=1.06,
                        yref="paper",
                        text="← Maduras (8+ anos) | Imaturas (censura à direita) →",
                        showarrow=False,
                        font={"size": 11, "color": "#1E293B"},
                    )

            fig_hm.update_layout(
                height=max(420, 26 * len(piv_val.index) + 120),
                xaxis_title="Ano de Ingresso (Coorte)",
                yaxis_title="",
                yaxis={"autorange": "reversed"},
                margin={"t": 55, "l": 10, "r": 10, "b": 40},
            )
            grafico(fig_hm, width="stretch", key="heatmap_coortes")

            df_hm_export = piv_val.reset_index().rename(columns={"curso": "Curso"})
            botao_csv(
                df_hm_export,
                f"heatmap_coortes_{metrica_col}.csv",
                label="📥 Baixar matriz do Heatmap (CSV, Gold k ≥ 5)",
                key="csv_heatmap_coortes",
            )

    with tab_comp:
        anos_mad = [a for a in ANOS_COORTE if ULTIMO_ANO_MADURO is None or a <= ULTIMO_ANO_MADURO]
        if len(anos_mad) < 2:
            st.info("São necessárias ao menos 2 coortes maduras para comparar períodos.")
        else:
            idx_meio = len(anos_mad) // 2
            cc1, cc2, cc3 = st.columns([2, 2, 1])
            with cc1:
                per_a = st.select_slider(
                    "Período A (referência):",
                    options=anos_mad,
                    value=(anos_mad[0], anos_mad[max(0, idx_meio - 1)]),
                    key="comp_per_a",
                )
            with cc2:
                per_b = st.select_slider(
                    "Período B (comparação):",
                    options=anos_mad,
                    value=(anos_mad[idx_meio], anos_mad[-1]),
                    key="comp_per_b",
                )
            with cc3:
                min_n_comp = st.number_input("Mín. alunos/período:", 5, 100, 20, step=5, key="comp_min_n")

            df_comp = comparar_periodos(
                df_coortes_all,
                periodo_a=per_a,
                periodo_b=per_b,
                cursos_tronco=EXCLUDED_GENERIC_COURSES,
                min_alunos=int(min_n_comp),
            )
            if df_comp.empty:
                st.info("Nenhum curso atingiu o mínimo de ingressantes nos dois períodos escolhidos.")
            else:
                st.caption(
                    f"Comparação de evasão entre **{per_a[0]}–{per_a[1]}** e **{per_b[0]}–{per_b[1]}** "
                    f"({len(df_comp)} cursos com {int(min_n_comp)}+ alunos em cada período). "
                    "Apenas coortes maduras entram aqui, garantindo comparabilidade justa."
                )
                piores = df_comp.head(8)
                melhores = df_comp.tail(8)
                df_ext = pd.concat([piores, melhores]).drop_duplicates(subset=["curso"]).sort_values("delta_evasao_pp")

                fig_dumb = go.Figure()
                for _, r in df_ext.iterrows():
                    cor_linha = "#C23B22" if r["delta_evasao_pp"] > 0 else "#008940"
                    fig_dumb.add_trace(
                        go.Scatter(
                            x=[r["evasao_a"], r["evasao_b"]],
                            y=[r["curso"], r["curso"]],
                            mode="lines",
                            line={"color": cor_linha, "width": 2.5},
                            showlegend=False,
                            hoverinfo="skip",
                        )
                    )
                fig_dumb.add_trace(
                    go.Scatter(
                        x=df_ext["evasao_a"],
                        y=df_ext["curso"],
                        mode="markers",
                        name=f"{per_a[0]}–{per_a[1]}",
                        marker={"color": "#64748B", "size": 9, "symbol": "circle"},
                        hovertemplate="<b>%{y}</b><br>" + f"{per_a[0]}–{per_a[1]}: " + "%{x:.1f}%<extra></extra>",
                    )
                )
                fig_dumb.add_trace(
                    go.Scatter(
                        x=df_ext["evasao_b"],
                        y=df_ext["curso"],
                        mode="markers",
                        name=f"{per_b[0]}–{per_b[1]}",
                        marker={"color": "#0072B2", "size": 10, "symbol": "diamond"},
                        hovertemplate="<b>%{y}</b><br>" + f"{per_b[0]}–{per_b[1]}: " + "%{x:.1f}%<extra></extra>",
                    )
                )
                fig_dumb.update_layout(
                    title="Maiores altas (vermelho) e quedas (verde) na taxa de evasão (%)",
                    xaxis_title="Taxa de Evasão (%)",
                    yaxis_title="",
                    height=max(420, 28 * len(df_ext) + 100),
                    legend={"orientation": "h", "y": 1.06},
                )
                grafico(fig_dumb, width="stretch", key="dumbbell_periodos")

                tabela_comp = df_comp.rename(columns={
                    "curso": "Curso",
                    "n_a": f"Alunos ({per_a[0]}–{per_a[1]})",
                    "evasao_a": f"Evasão % ({per_a[0]}–{per_a[1]})",
                    "n_b": f"Alunos ({per_b[0]}–{per_b[1]})",
                    "evasao_b": f"Evasão % ({per_b[0]}–{per_b[1]})",
                    "delta_evasao_pp": "Variação evasão (p.p.)",
                    "delta_formatura_pp": "Variação formatura (p.p.)",
                })[
                    [
                        "Curso",
                        f"Alunos ({per_a[0]}–{per_a[1]})",
                        f"Evasão % ({per_a[0]}–{per_a[1]})",
                        f"Alunos ({per_b[0]}–{per_b[1]})",
                        f"Evasão % ({per_b[0]}–{per_b[1]})",
                        "Variação evasão (p.p.)",
                        "Variação formatura (p.p.)",
                    ]
                ]
                botao_csv(
                    tabela_comp,
                    f"comparativo_periodos_{per_a[0]}_{per_a[1]}_vs_{per_b[0]}_{per_b[1]}.csv",
                    label="📥 Baixar comparativo de períodos (CSV, Gold k ≥ 5)",
                    key="csv_comp_periodos",
                )
