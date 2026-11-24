"""Tela: 📊 Visão Executiva (DEG)."""

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from coortes import narrativa_executiva
from formatacao import (
    CORES_IRC,
    SIMBOLOS_IRC,
    botao_csv,
    br,
    dec,
    delta_pp,
    grafico,
    mostrar_tabela,
)
from resposta_e1 import COLUNAS as COLUNAS_E1
from resposta_e1 import PERGUNTA_E1, SLA_DIAS, frescor, ranking_cursos_criticos

from abas.graficos_coorte import render_funil, render_heatmap_e_comparador


def _abrir_curso_atalho():
    curso = st.session_state.get("exec_atalho_curso")
    if curso and curso != "(selecione)":
        st.session_state["curso_selecionado"] = curso
        st.session_state["_ir_para_aba"] = "🔍 Detalhe por Curso"
        st.session_state["exec_atalho_curso"] = "(selecione)"


def renderizar(g):
    """g: namespace com o que o app.py carregou (dados, metadados e helpers)."""
    EXCLUDED_GENERIC_COURSES = g.EXCLUDED_GENERIC_COURSES
    N_MIN_RANKING = g.N_MIN_RANKING
    _COORTES = g._COORTES
    COORTE_SELECIONADA = getattr(g, "COORTE_SELECIONADA", str(_COORTES))
    EH_COORTE_OFICIAL = getattr(g, "EH_COORTE_OFICIAL", True)
    INCLUI_IMATURAS = getattr(g, "INCLUI_IMATURAS", False)
    ULTIMO_ANO_MADURO = getattr(g, "ULTIMO_ANO_MADURO", None)
    _media_ponderada = g._media_ponderada
    carregado_em = g.carregado_em
    df_gold = g.df_gold
    df_gold_oficial = getattr(g, "df_gold_oficial", df_gold)
    df_coortes_all = getattr(g, "df_coortes_all", pd.DataFrame())
    mostrar_escopo = g.mostrar_escopo
    painel_e1 = g.painel_e1

    mostrar_escopo("exec")
    ranking_e1, fonte_e1 = ranking_cursos_criticos(
        {"painel_cursos_criticos": painel_e1}, df_gold_oficial, EXCLUDED_GENERIC_COURSES)
    st.subheader(
        "❓ Pergunta da E1: em quais cursos intervir primeiro?")
    st.markdown(f"> *{PERGUNTA_E1}*")
    if ranking_e1 is not None:
        n_criticos_e1 = (
            ranking_e1["classificacao_retencao"] == "RETENÇÃO CRÍTICA").sum()
        _grandes = ranking_e1[ranking_e1["total_ingressantes"] >= N_MIN_RANKING]
        primeiros = ", ".join(f"**{c}**" for c in _grandes["nome_curso"].head(3))
        _pos_primeiro_grande = ranking_e1.index.get_loc(_grandes.index[0]) if len(_grandes) else len(ranking_e1)
        _pequenos_antes = ranking_e1.iloc[:_pos_primeiro_grande]
        if len(_pequenos_antes):
            st.info(
                f"{len(_pequenos_antes)} curso(s) com IRC maior que o primeiro abaixo têm menos de {N_MIN_RANKING} "
                f"ingressantes (ex.: {_pequenos_antes.iloc[0]['nome_curso']}, {int(_pequenos_antes.iloc[0]['total_ingressantes'])}): "
                "amostra pequena oscila muito, por isso a resposta considera só cursos com "
                f"{N_MIN_RANKING}+ ingressantes. A tabela mostra todos.")
        st.markdown(
            f"**Resposta:** {n_criticos_e1} cursos estão em retenção crítica, o quartil mais alto do "
            f"Índice de Retenção Crítica (IRC). Os primeiros da fila de intervenção, entre os cursos com {N_MIN_RANKING}+ ingressantes, são {primeiros}. "
            "O IRC combina a evasão (peso 0,7) e o atraso na formatura (peso 0,3), medidos nas "
            "turmas que já tiveram 8 anos para se formar."
        )
        QUARTIL_IRC = {"RETENÇÃO CRÍTICA": "4º quartil (crítica)", "RETENÇÃO ALTA": "3º quartil (alta)",
                       "RETENÇÃO MÉDIA": "2º quartil (média)", "RETENÇÃO BAIXA": "1º quartil (baixa)"}
        tabela_e1 = ranking_e1.head(15).assign(
            classificacao_retencao=lambda d: d["classificacao_retencao"].map(
                QUARTIL_IRC).fillna(d["classificacao_retencao"])
        ).rename(columns=COLUNAS_E1).rename(columns={"Classificação": "Quartil do IRC"})
        _todos_no_mesmo_quartil = tabela_e1["Quartil do IRC"].nunique() == 1
        if _todos_no_mesmo_quartil:  # coluna repetida em todas as linhas não informa nada
            tabela_e1 = tabela_e1.drop(columns="Quartil do IRC")
        mostrar_tabela(tabela_e1, width="stretch", hide_index=True)
        _legenda_q = ("O quartil é relativo entre os cursos (quartil mais alto = maior IRC), e não um nível absoluto: "
                      "a coluna Evasão (%) mostra a taxa real de cada curso.")
        if _todos_no_mesmo_quartil:
            _legenda_q = "Todos os cursos da tabela estão no quartil mais alto do IRC. " + _legenda_q
        st.caption(_legenda_q)
        legenda = (f"Ranking completo: {len(ranking_e1)} cursos. Fonte: `{fonte_e1}`. "
                   "Dados abertos do portal dados.unb.br (datas das fontes na barra lateral).")
        dados_frescor = frescor(carregado_em)
        if dados_frescor:
            data_carga, idade_dias, dentro_do_sla = dados_frescor
            legenda += f" Dados da carga de {data_carga:%d/%m/%Y} (há {idade_dias} dia(s); SLA de frescor: {SLA_DIAS} dias)."
            if not dentro_do_sla:
                st.warning(f"A carga tem {idade_dias} dias, acima do SLA de {SLA_DIAS} dias: "
                           "o ranking pode não refletir a publicação mais recente do portal.")
        st.caption(legenda)

        c_dl1, c_dl2 = st.columns([2, 3])
        with c_dl1:
            botao_csv(
                ranking_e1.rename(columns=COLUNAS_E1),
                f"ranking_cursos_criticos_unb_{_COORTES}.csv",
                label="📥 Baixar ranking completo E1 (CSV, Gold k ≥ 5)",
                key="csv_ranking_e1",
            )
        with c_dl2:
            if not EH_COORTE_OFICIAL:
                st.caption(
                    f"ℹ️ O ranking oficial da E1 acima permanece ancorado em **{_COORTES}** (ADR 0014). "
                    f"Os gráficos e KPIs abaixo refletem o recorte exploratório **{COORTE_SELECIONADA}**."
                )

    st.markdown("---")

    # Aviso persistente de censura à direita quando o usuário inclui coortes imaturas
    if INCLUI_IMATURAS:
        st.warning(
            f"**Atenção — Censura à direita (ADR 0014):** o intervalo **{COORTE_SELECIONADA}** inclui turmas "
            f"posteriores a {ULTIMO_ANO_MADURO} (menos de 8 anos de acompanhamento). Nessas turmas, muitos "
            "discentes seguem ativos, a taxa de formatura aparece artificialmente baixa e o tempo médio de "
            "formatura considera apenas quem concluiu mais rápido. Use este recorte apenas em caráter exploratório."
        )

    # Filtros rápidos transversais (Campus, Turno, Grau) + Drill-down para Detalhe por Curso
    f1, f2, f3, f4 = st.columns([2, 2, 2, 2])
    with f1:
        campi_disp = sorted(df_gold["campus"].dropna().unique())
        campi_sel = st.multiselect("Filtrar Campus:", campi_disp, default=[], key="exec_campus")
    with f2:
        turnos_disp = sorted(df_gold["turno"].dropna().unique())
        turnos_sel = st.multiselect("Filtrar Turno:", turnos_disp, default=[], key="exec_turno")
    with f3:
        graus_disp = sorted(df_gold["categoria_grau"].dropna().unique())
        graus_sel = st.multiselect("Filtrar Grau:", graus_disp, default=[], key="exec_grau")

    df_view = df_gold.copy()
    if campi_sel:
        df_view = df_view[df_view["campus"].isin(campi_sel)]
    if turnos_sel:
        df_view = df_view[df_view["turno"].isin(turnos_sel)]
    if graus_sel:
        df_view = df_view[df_view["categoria_grau"].isin(graus_sel)]

    with f4:
        cursos_para_ir = sorted(df_view["curso"].unique()) if not df_view.empty else []
        st.selectbox(
            "Abrir Raio-X do curso:",
            options=["(selecione)"] + cursos_para_ir,
            key="exec_atalho_curso",
            on_change=_abrir_curso_atalho,
        )

    if df_view.empty:
        st.warning("Nenhum curso corresponde à combinação de filtros selecionada.")
        return

    filtro_ativo = bool(campi_sel or turnos_sel or graus_sel or not EH_COORTE_OFICIAL)

    # Narrativa executiva automática (3 bullets descritivos, sem causalidade)
    bullets = narrativa_executiva(
        df_view,
        df_gold_oficial,
        recorte_txt=COORTE_SELECIONADA,
        eh_oficial=not filtro_ativo,
        min_ranking=N_MIN_RANKING,
    )
    if bullets:
        with st.container(border=True):
            st.markdown("##### 📝 Síntese Executiva do Recorte")
            st.markdown("\n".join(f"- {b}" for b in bullets))

    # Baselines oficiais para deltas comparativos nos KPIs
    _tot_base = float(df_gold_oficial["total_discentes_registrados"].sum()) if df_gold_oficial is not None else 0.0
    _fo_base = float(df_gold_oficial["total_formados"].sum()) / _tot_base * 100.0 if _tot_base else np.nan
    _ev_base = float(df_gold_oficial["total_evadidos_desligados"].sum()) / _tot_base * 100.0 if _tot_base else np.nan
    _at_base = float(df_gold_oficial["total_ainda_ativos"].sum()) / _tot_base * 100.0 if _tot_base else np.nan
    _tm_base = _media_ponderada(df_gold_oficial, "tempo_medio_real_semestres") if df_gold_oficial is not None else np.nan
    _id_base = _media_ponderada(df_gold_oficial, "formados_tempo_ideal_pct") if df_gold_oficial is not None else np.nan

    _tm_atual = _media_ponderada(df_view, "tempo_medio_real_semestres")
    _id_atual = _media_ponderada(df_view, "formados_tempo_ideal_pct")

    # KPIs Globais (com deltas comparativos contra o baseline oficial quando filtrado/alterado)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _share_txt = (
            f"{dec(df_view['total_discentes_registrados'].sum() / _tot_base * 100, 1)}% do baseline"
            if (filtro_ativo and _tot_base) else f"{len(df_view)} cursos terminais"
        )
        st.metric(
            label="Alunos que ingressaram (turmas analisadas)",
            value=f"{br(int(df_view['total_discentes_registrados'].sum()))}",
            delta=_share_txt,
            delta_color="off",
            help=(f"Ingressantes de {COORTE_SELECIONADA} nos cursos com 5+ alunos, sem cursos-tronco. É uma parte dos "
                  "vínculos de graduação auditados (aba Auditoria), que somam todas as turmas."),
        )
    with c2:
        st.metric(
            label="Tempo Médio Real de Formatura",
            value=f"{dec(_tm_atual, 2)} sem." if pd.notna(_tm_atual) else "—",
            delta=delta_pp(_tm_atual, _tm_base, 2, "sem.", " vs. oficial") if filtro_ativo else None,
            delta_color="inverse",
            help="Média em semestres entre o ingresso e a formatura, só entre quem se formou (ponderada pelo nº de formados de cada curso).",
        )
    with c3:
        st.metric(
            label="Formados até o prazo ideal",
            value=f"{dec(_id_atual, 1)}%" if pd.notna(_id_atual) else "—",
            delta=delta_pp(_id_atual, _id_base, 1, "p.p.", " vs. oficial") if filtro_ativo else None,
            delta_color="normal",
            help=("% dos formados que concluíram até o tempo ideal da matriz, **incluindo** quem fechou no tempo "
                  "mínimo (acumulado). Na aba Detalhe, as faixas são exclusivas: 'Do mínimo ao ideal' é só uma "
                  "parte deste número."),
        )
    with c4:
        n_criticos = int((df_view["classificacao_retencao"] == "RETENÇÃO CRÍTICA").sum())
        st.metric(
            label="Cursos em Retenção Crítica",
            value=f"{n_criticos} cursos",
            delta="25% com maior IRC" if not filtro_ativo else f"{dec(n_criticos / len(df_view) * 100, 0)}% do recorte",
            delta_color="inverse",
            help="Cursos no quartil mais alto do IRC (nota relativa entre os cursos, 0,7 evasão + 0,3 atraso). O quartil é relativo: sempre há cerca de 25% de cursos nesta faixa.",
        )

    # Desfecho global do mesmo universo dos KPIs: o número central da retenção.
    _tot = float(df_view["total_discentes_registrados"].sum())
    _fo_atual = df_view["total_formados"].sum() / _tot * 100.0 if _tot else 0.0
    _ev_atual = df_view["total_evadidos_desligados"].sum() / _tot * 100.0 if _tot else 0.0
    _at_atual = df_view["total_ainda_ativos"].sum() / _tot * 100.0 if _tot else 0.0
    _outros = _tot - df_view["total_formados"].sum() - df_view["total_evadidos_desligados"].sum() - df_view["total_ainda_ativos"].sum()

    g1, g2, g3, g4 = st.columns(4)
    g1.metric(
        "Formatura (turmas analisadas)",
        f"{dec(_fo_atual, 1)}%",
        delta=delta_pp(_fo_atual, _fo_base, 1, "p.p.", " vs. oficial") if filtro_ativo else None,
        delta_color="normal",
        help=f"Formados ÷ alunos que ingressaram em {COORTE_SELECIONADA}.",
    )
    g2.metric(
        "Evasão (turmas analisadas)",
        f"{dec(_ev_atual, 1)}%",
        delta=delta_pp(_ev_atual, _ev_base, 1, "p.p.", " vs. oficial") if filtro_ativo else None,
        delta_color="inverse",
        help="Evadidos ou desligados ÷ alunos que ingressaram. Inclui mudança de curso.",
    )
    g3.metric(
        "Ainda ativos (turmas analisadas)",
        f"{dec(_at_atual, 1)}%",
        delta=delta_pp(_at_atual, _at_base, 1, "p.p.", " vs. oficial") if filtro_ativo else None,
        delta_color="off",
        help="Alunos dessas turmas que seguem com vínculo ativo. Não é a lista de ativos de hoje (aba Alunos Ativos).",
    )
    g4.metric(
        "Outros desfechos",
        f"{dec(_outros / _tot * 100, 1)}%" if _tot else "0,0%",
        help="O que não é formatura, evasão nem vínculo ativo (por exemplo, transferências e falecimentos). Fecha os 100% com os três números ao lado.",
    )

    st.markdown("---")

    # Matriz de Retenção Crítica + Gráfico Funil (IC 95% / 99,8% para cursos pequenos)
    st.subheader("🎯 Matriz de Retenção Crítica & Incerteza Amostral")
    tab_scatter, tab_funil = st.tabs([
        "🎯 Matriz Atraso × Evasão",
        "📐 Gráfico Funil (IC 95% / Cursos Pequenos)",
    ])

    with tab_scatter:
        st.markdown(
            "Cursos no quadrante superior direito formam **depois do tempo ideal da matriz** (à direita da linha "
            "vertical, onde o atraso é zero) e têm **evasão acima da mediana dos cursos** (acima da linha "
            "horizontal): são os candidatos a intervenção pedagógica prioritária. "
            "Cada quartil combina **cor acessível e forma distinta** (codificação redundante para daltonismo)."
        )

        df_plot_sc = df_view.dropna(subset=["desvio_medio_semestres", "taxa_evasao_pct"])
        if df_plot_sc.empty:
            st.info("Sem cursos com tempo médio calculável neste recorte para plotar a matriz.")
        else:
            fig_scatter = px.scatter(
                df_plot_sc,
                x="desvio_medio_semestres",
                y="taxa_evasao_pct",
                size="total_discentes_registrados",
                color="classificacao_retencao",
                symbol="classificacao_retencao",
                symbol_map=SIMBOLOS_IRC,
                hover_name="curso",
                hover_data={
                    "tempo_medio_real_semestres": ":.1f",
                    "semestre_ideal_previsto": ":.0f",
                    "taxa_formatura_pct": ":.1f",
                    "campus": True,
                },
                labels={
                    "desvio_medio_semestres": "Atraso Médio na Formatura (Semestres além do Ideal)",
                    "taxa_evasao_pct": "Taxa de Evasão / Desligamento (%)",
                    "classificacao_retencao": "Grau de Retenção",
                    "tempo_medio_real_semestres": "Tempo médio (sem.)",
                    "semestre_ideal_previsto": "Prazo ideal (sem.)",
                    "taxa_formatura_pct": "Formatura (%)",
                    "campus": "Campus",
                    "total_discentes_registrados": "Ingressantes",
                },
                color_discrete_map=CORES_IRC,
                height=500,
            )
            fig_scatter.add_vline(x=0, line_dash="dash", line_color="#64748B")
            _mediana_ev = float(df_plot_sc["taxa_evasao_pct"].median())
            fig_scatter.add_hline(y=_mediana_ev, line_dash="dash", line_color="#64748B")
            for _, c in df_plot_sc[df_plot_sc["classificacao_retencao"] == "RETENÇÃO CRÍTICA"].nlargest(
                    8, "total_discentes_registrados").iterrows():
                fig_scatter.add_annotation(
                    x=c["desvio_medio_semestres"], y=c["taxa_evasao_pct"],
                    text=str(c["curso"]).title(),
                    showarrow=False, yshift=14, font={"size": 10, "color": "#1E293B"},
                )
            grafico(fig_scatter, width="stretch", key="scatter_retencao")
            _quadrante = (df_plot_sc["desvio_medio_semestres"] > 0) & (
                df_plot_sc["taxa_evasao_pct"] > _mediana_ev)
            _critico = df_plot_sc["classificacao_retencao"] == "RETENÇÃO CRÍTICA"
            st.caption(
                f"A linha horizontal é a mediana de evasão dos cursos ({dec(_mediana_ev, 1)}%). O quadrante superior direito "
                f"reúne {int(_quadrante.sum())} cursos; o IRC crítico (quartil mais alto) marca {int(_critico.sum())}, e "
                f"{int((_quadrante & _critico).sum())} estão nos dois grupos. Os critérios são diferentes: o quadrante "
                "usa só atraso e evasão acima da mediana; o IRC pesa evasão (0,7) e atraso (0,3) e ordena os cursos."
            )

    with tab_funil:
        render_funil(df_view, _ev_atual, N_MIN_RANKING)

    # Seção Longitudinal: Heatmap de Coortes + Comparador de Períodos Maduros
    if df_coortes_all is not None and not df_coortes_all.empty:
        render_heatmap_e_comparador(g, df_coortes_all)

    st.markdown("---")

    # Rankings organizados em abas (reduz scroll vertical mantendo todos os Top 25)
    st.subheader("🏆 Rankings Comparativos (Top 25 Piores vs. Melhores)")
    RANKINGS = [
        ("⏱️ Atraso na Formatura",
         ("🚨 Top 25 Maiores Atrasos na Formatura", "desvio_medio_semestres", False,
          [("desvio_medio_semestres", "Atraso (sem.)"), ("tempo_medio_real_semestres", "Tempo Real (sem.)"),
           ("semestre_ideal_previsto", "Tempo Ideal (sem.)")]),
         ("⭐ Top 25 Menores Atrasos na Formatura", "desvio_medio_semestres", True,
          [("desvio_medio_semestres", "Atraso (sem.)"), ("tempo_medio_real_semestres", "Tempo Real (sem.)"),
           ("semestre_ideal_previsto", "Tempo Ideal (sem.)")])),
        ("🚪 Evasão",
         ("🚨 Top 25 Maiores Evasões", "taxa_evasao_pct", False,
          [("taxa_evasao_pct", "Evasão (%)"), ("taxa_formatura_pct", "Formatura (%)"),
           ("total_discentes_registrados", "Alunos")]),
         ("⭐ Top 25 Menores Evasões", "taxa_evasao_pct", True,
          [("taxa_evasao_pct", "Evasão (%)"), ("taxa_formatura_pct", "Formatura (%)"),
           ("total_discentes_registrados", "Alunos")])),
        ("🔥 Retenção Crítica (IRC)",
         ("🚨 Top 25 Maiores Retenções Críticas (IRC)", "indice_retencao_critica", False,
          [("indice_retencao_critica", "IRC"), ("desvio_medio_semestres", "Atraso (sem.)"),
           ("taxa_evasao_pct", "Evasão (%)"), ("total_discentes_registrados", "Alunos")]),
         ("⭐ Top 25 Menores Retenções Críticas (IRC)", "indice_retencao_critica", True,
          [("indice_retencao_critica", "IRC"), ("desvio_medio_semestres", "Atraso (sem.)"),
           ("taxa_evasao_pct", "Evasão (%)"), ("total_discentes_registrados", "Alunos")])),
        ("🎯 Formados no Prazo Ideal",
         ("🚨 Top 25 Menores Formados até o Prazo Ideal", "formados_tempo_ideal_pct", True,
          [("formados_tempo_ideal_pct", "Formados até o prazo ideal (%)"), ("taxa_formatura_pct", "Formatura (%)"),
           ("total_discentes_registrados", "Alunos")]),
         ("⭐ Top 25 Maiores Formados até o Prazo Ideal", "formados_tempo_ideal_pct", False,
          [("formados_tempo_ideal_pct", "Formados até o prazo ideal (%)"), ("taxa_formatura_pct", "Formatura (%)"),
           ("total_discentes_registrados", "Alunos")])),
    ]
    st.caption(
        f"Rankings sobre o recorte **{COORTE_SELECIONADA}**, só cursos com {N_MIN_RANKING}+ alunos "
        "(os KPIs acima usam 5+; cursos pequenos dominam os extremos dos rankings). "
        "À esquerda, os 25 cursos mais problemáticos; à direita, os 25 com melhor desempenho, "
        "sempre pela mesma métrica. Evasão inclui mudança de curso."
    )
    abas_rank = st.tabs([r[0] for r in RANKINGS])
    for aba_tab, (_, pior_cfg, melhor_cfg) in zip(abas_rank, RANKINGS):
        with aba_tab:
            col_ruim, col_bom = st.columns(2)
            for coluna, (titulo, ordena_por, crescente, colunas) in zip((col_ruim, col_bom), (pior_cfg, melhor_cfg)):
                with coluna:
                    st.markdown(f"##### {titulo}")
                    if ordena_por not in df_view.columns:
                        st.info("Coluna indisponível neste recorte.")
                        continue
                    ranking = (df_view[df_view["total_discentes_registrados"] >= N_MIN_RANKING]
                               .dropna(subset=[ordena_por])
                               .sort_values(ordena_por, ascending=crescente, kind="stable").head(25))
                    tabela = ranking[["curso"] + [c for c, _ in colunas if c in ranking.columns]].rename(
                        columns={"curso": "Curso", **dict(colunas)})
                    mostrar_tabela(tabela, width="stretch", hide_index=True)

    botao_csv(
        df_view,
        f"retencao_cursos_unb_{COORTE_SELECIONADA.replace('–', '_')}.csv",
        label="📥 Baixar tabela completa do recorte atual (CSV, Gold k ≥ 5)",
        key="csv_exec_recorte",
    )
