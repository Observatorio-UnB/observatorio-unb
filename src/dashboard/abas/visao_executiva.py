"""Tela: 📊 Visão Executiva (DEG)."""

import plotly.express as px
import streamlit as st
from formatacao import br, dec, grafico, mostrar_tabela
from resposta_e1 import COLUNAS as COLUNAS_E1
from resposta_e1 import PERGUNTA_E1, SLA_DIAS, frescor, ranking_cursos_criticos


def renderizar(g):
    """g: namespace com o que o app.py carregou (dados, metadados e helpers)."""
    EXCLUDED_GENERIC_COURSES = g.EXCLUDED_GENERIC_COURSES
    N_MIN_RANKING = g.N_MIN_RANKING
    _COORTES = g._COORTES
    _media_ponderada = g._media_ponderada
    carregado_em = g.carregado_em
    df_gold = g.df_gold
    mostrar_escopo = g.mostrar_escopo
    painel_e1 = g.painel_e1

    mostrar_escopo("exec")
    ranking_e1, fonte_e1 = ranking_cursos_criticos(
        {"painel_cursos_criticos": painel_e1}, df_gold, EXCLUDED_GENERIC_COURSES)
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

    st.markdown("---")

    # KPIs Globais: o recorte UNB da camada semântica (dbt_marts.metricas_por_recorte), mesma fórmula e
    # mesmo universo do ranking e das comparações. Sem o mart, a mesma conta sobre a gold.
    unb = g.unb_semantica
    if unb:
        kpi_ingressantes = float(unb["ingressantes"])
        kpi_tempo = float(unb["tempo_medio_formatura_semestres"])
        kpi_prazo = float(unb["formados_tempo_ideal_pct"])
        kpi_formados, kpi_evadidos, kpi_ativos = (float(unb[c]) for c in ("formados", "evadidos", "ativos"))
    else:
        kpi_ingressantes = float(df_gold["total_discentes_registrados"].sum())
        kpi_tempo = _media_ponderada(df_gold, "tempo_medio_real_semestres")
        kpi_prazo = _media_ponderada(df_gold, "formados_tempo_ideal_pct")
        kpi_formados = float(df_gold["total_formados"].sum())
        kpi_evadidos = float(df_gold["total_evadidos_desligados"].sum())
        kpi_ativos = float(df_gold["total_ainda_ativos"].sum())
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(
            label="Alunos que ingressaram (turmas analisadas)",
            value=f"{br(int(kpi_ingressantes))}",
            help=(f"Ingressantes de {_COORTES} nos cursos com 5+ alunos, sem cursos-tronco. É uma parte dos "
                  "vínculos de graduação auditados (aba Auditoria), que somam todas as turmas."),
        )
    with c2:
        st.metric(
            label="Tempo Médio Real de Formatura",
            value=f"{dec(kpi_tempo, 2)} sem.",
            help="Média em semestres entre o ingresso e a formatura, entre os formados com permanência calculável.",
        )
    with c3:
        st.metric(
            label="Formados até o prazo ideal",
            value=f"{dec(kpi_prazo, 1)}%",
            help=("% dos formados que concluíram até o tempo ideal da matriz, **incluindo** quem fechou no tempo "
                  "mínimo (acumulado). Na aba Detalhe, as faixas são exclusivas: 'Do mínimo ao ideal' é só uma "
                  "parte deste número."),
        )
    with c4:
        n_criticos = (df_gold["classificacao_retencao"]
                      == "RETENÇÃO CRÍTICA").sum()
        st.metric(
            label="Cursos em Retenção Crítica",
            value=f"{n_criticos} cursos",
            delta="25% com maior IRC",
            delta_color="inverse",
            help="Cursos no quartil mais alto do IRC (nota relativa entre os cursos, 0,7 evasão + 0,3 atraso). O quartil é relativo: sempre há cerca de 25% de cursos nesta faixa.",
        )

    # Desfecho global do mesmo universo dos KPIs: o número central da retenção.
    _tot = kpi_ingressantes
    g1, g2, g3, g4 = st.columns(4)
    g1.metric("Formatura (turmas analisadas)",
              f"{dec(kpi_formados / _tot * 100, 1)}%".replace(".", ","),
              help="Formados ÷ alunos que ingressaram em " + str(_COORTES) + ".")
    g2.metric("Evasão (turmas analisadas)",
              f"{dec(kpi_evadidos / _tot * 100, 1)}%".replace(
                  ".", ","),
              help="Evadidos ou desligados ÷ alunos que ingressaram. Inclui mudança de curso.")
    g3.metric("Ainda ativos (turmas analisadas)",
              f"{dec(kpi_ativos / _tot * 100, 1)}%".replace(".", ","),
              help="Alunos dessas turmas que seguem com vínculo ativo. Não é a lista de ativos de hoje (aba Alunos Ativos).")
    _outros = _tot - kpi_formados - kpi_evadidos - kpi_ativos
    g4.metric("Outros desfechos",
              f"{dec(_outros / _tot * 100, 1)}%",
              help="O que não é formatura, evasão nem vínculo ativo (por exemplo, transferências e falecimentos). Fecha os 100% com os três números ao lado.")

    st.markdown("---")

    # Gráfico Scatter: Atraso vs Evasão
    st.subheader(
        "🎯 Matriz de Retenção Crítica: Atraso de Formatura vs. Taxa de Evasão")
    st.markdown(
        "Cursos no quadrante superior direito formam **depois do tempo ideal da matriz** (à direita da linha "
        "vertical, onde o atraso é zero) e têm **evasão acima da mediana dos cursos** (acima da linha "
        "horizontal): são os candidatos a intervenção pedagógica prioritária."
    )

    fig_scatter = px.scatter(
        df_gold,
        x="desvio_medio_semestres",
        y="taxa_evasao_pct",
        size="total_discentes_registrados",
        color="classificacao_retencao",
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
        color_discrete_map={
            "RETENÇÃO CRÍTICA": "#DC2626",
            "RETENÇÃO ALTA": "#F59E0B",
            "RETENÇÃO MÉDIA": "#3B82F6",
            "RETENÇÃO BAIXA": "#10B981",
        },
        height=500,
    )
    fig_scatter.add_vline(x=0, line_dash="dash", line_color="#9CA3AF")
    fig_scatter.add_hline(y=df_gold["taxa_evasao_pct"].median(
    ), line_dash="dash", line_color="#9CA3AF")
    # Rótulo nos 8 cursos críticos com mais alunos: sem nome no gráfico, o leitor só descobre passando o mouse.
    for _, c in df_gold[df_gold["classificacao_retencao"] == "RETENÇÃO CRÍTICA"].nlargest(
            8, "total_discentes_registrados").iterrows():
        fig_scatter.add_annotation(x=c["desvio_medio_semestres"], y=c["taxa_evasao_pct"], text=str(c["curso"]).title(),
                                   showarrow=False, yshift=14, font={"size": 10, "color": "#374151"})
    grafico(fig_scatter, width="stretch")
    _mediana_ev = float(df_gold["taxa_evasao_pct"].median())
    _quadrante = (df_gold["desvio_medio_semestres"] > 0) & (
        df_gold["taxa_evasao_pct"] > _mediana_ev)
    _critico = df_gold["classificacao_retencao"] == "RETENÇÃO CRÍTICA"
    st.caption(
        f"A linha horizontal é a mediana de evasão dos cursos ({dec(_mediana_ev, 1)}%). O quadrante superior direito "
        f"reúne {int(_quadrante.sum())} cursos; o IRC crítico (quartil mais alto) marca {int(_critico.sum())}, e "
        f"{int((_quadrante & _critico).sum())} estão nos dois grupos. Os critérios são diferentes: o quadrante "
        "usa só atraso e evasão acima da mediana; o IRC pesa evasão (0,7) e atraso (0,3) e ordena os cursos.")
        
    st.markdown("---")

    # Rankings: à esquerda os 25 piores, à direita os 25 melhores, na mesma ordem de tema.
    # Colunas: (coluna do df, nome na tabela). A primeira é a que ordena.
    RANKINGS = [
        (("🚨 Top 25 Maiores Atrasos na Formatura", "desvio_medio_semestres", False,
          [("desvio_medio_semestres", "Atraso (sem.)"), ("tempo_medio_real_semestres", "Tempo Real (sem.)"),
           ("semestre_ideal_previsto", "Tempo Ideal (sem.)")]),
         ("⭐ Top 25 Menores Atrasos na Formatura", "desvio_medio_semestres", True,
          [("desvio_medio_semestres", "Atraso (sem.)"), ("tempo_medio_real_semestres", "Tempo Real (sem.)"),
           ("semestre_ideal_previsto", "Tempo Ideal (sem.)")])),
        (("🚨 Top 25 Maiores Evasões", "taxa_evasao_pct", False,
          [("taxa_evasao_pct", "Evasão (%)"), ("taxa_formatura_pct", "Formatura (%)"),
           ("total_discentes_registrados", "Alunos")]),
         ("⭐ Top 25 Menores Evasões", "taxa_evasao_pct", True,
          [("taxa_evasao_pct", "Evasão (%)"), ("taxa_formatura_pct", "Formatura (%)"),
           ("total_discentes_registrados", "Alunos")])),
        (("🚨 Top 25 Maiores Retenções Críticas (IRC)", "indice_retencao_critica", False,
          [("indice_retencao_critica", "IRC"), ("desvio_medio_semestres", "Atraso (sem.)"),
           ("taxa_evasao_pct", "Evasão (%)"), ("total_discentes_registrados", "Alunos")]),
         ("⭐ Top 25 Menores Retenções Críticas (IRC)", "indice_retencao_critica", True,
          [("indice_retencao_critica", "IRC"), ("desvio_medio_semestres", "Atraso (sem.)"),
           ("taxa_evasao_pct", "Evasão (%)"), ("total_discentes_registrados", "Alunos")])),
        (("🚨 Top 25 Menores Formados até o Prazo Ideal", "formados_tempo_ideal_pct", True,
          [("formados_tempo_ideal_pct", "Formados até o prazo ideal (%)"), ("taxa_formatura_pct", "Formatura (%)"),
           ("total_discentes_registrados", "Alunos")]),
         ("⭐ Top 25 Maiores Formados até o Prazo Ideal", "formados_tempo_ideal_pct", False,
          [("formados_tempo_ideal_pct", "Formados até o prazo ideal (%)"), ("taxa_formatura_pct", "Formatura (%)"),
           ("total_discentes_registrados", "Alunos")])),
    ]
    st.caption(f"Rankings sobre as turmas com 8+ anos de acompanhamento, só cursos com {N_MIN_RANKING}+ alunos (os KPIs acima usam 5+; cursos pequenos dominam os extremos dos rankings). "
               "À esquerda, os 25 cursos mais problemáticos; à direita, os 25 com melhor desempenho, "
               "sempre pela mesma métrica. Evasão inclui mudança de curso.")
    for linha in RANKINGS:
        col_ruim, col_bom = st.columns(2)
        for coluna, (titulo, ordena_por, crescente, colunas) in zip((col_ruim, col_bom), linha):
            with coluna:
                st.subheader(titulo)
                ranking = (df_gold[df_gold["total_discentes_registrados"] >= N_MIN_RANKING]
                           .dropna(subset=[ordena_por])
                           .sort_values(ordena_por, ascending=crescente, kind="stable").head(25))
                tabela = ranking[["curso"] + [c for c, _ in colunas]].rename(
                    columns={"curso": "Curso", **dict(colunas)})
                mostrar_tabela(tabela, width="stretch", hide_index=True)
