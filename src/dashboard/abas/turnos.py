"""Tela: ⚖️ Noturno vs. Diurno & Turnos."""

import plotly.express as px
import streamlit as st
from formatacao import botao_csv, br, dec, grafico


def renderizar(g):
    """g: namespace com o que o app.py carregou (dados, metadados e helpers)."""
    LABELS_PT = g.LABELS_PT
    agregar_ponderado = g.agregar_ponderado
    df_gold = g.df_gold
    mostrar_escopo = g.mostrar_escopo

    st.subheader("⚖️ Comparativo de Evasão e Tempo de Formatura por Turno")
    mostrar_escopo("turnos")

    st.markdown(
        "Análise do impacto do turno na permanência estudantil. *Nota: Cursos noturnos já têm prazos ideais maiores em suas matrizes.*"
    )

    df_turno = agregar_ponderado(df_gold, "turno")
    _mistos = df_gold[~df_gold["turno"].str.upper().isin(
        ["DIURNO", "NOTURNO"])]
    if not _mistos.empty:
        st.caption(
            f"Categorias que não são só diurno ou só noturno ({', '.join(sorted(_mistos['turno'].unique()))}) reúnem "
            f"cursos com turmas nos dois turnos: {len(_mistos)} cursos, "
            f"{br(int(_mistos['total_discentes_registrados'].sum()))} alunos "
            f"({dec(_mistos['total_discentes_registrados'].sum() / df_gold['total_discentes_registrados'].sum() * 100, 0)}% do total).")

    c1, c2 = st.columns(2)
    with c1:
        fig_turno_evas = px.bar(
            df_turno,
            x="turno",
            y="taxa_evasao_pct",
            title="Taxa de Evasão por Turno (%)",
            color="turno",
            labels=LABELS_PT,
            text_auto=".1f",
            height=380,
        )
        grafico(fig_turno_evas, width="stretch")

    with c2:
        df_turno_tempo = df_turno.rename(columns={
            "semestre_ideal_previsto": "Tempo Ideal",
            "tempo_medio_real_semestres": "Tempo Real",
        })
        fig_turno_tempo = px.bar(
            df_turno_tempo,
            x="turno",
            y=["Tempo Ideal", "Tempo Real"],
            barmode="group",
            title="Tempo Ideal Previsto vs. Tempo Médio Real (Semestres)",
            labels=LABELS_PT,
            height=380,
        )
        fig_turno_tempo.update_layout(legend_title_text="")
        fig_turno_tempo.update_traces(
            hovertemplate="<b>%{fullData.name}</b>: %{y:.1f} sem.<extra></extra>")
        grafico(fig_turno_tempo, width="stretch")

    st.markdown("---")
    st.subheader(
        "🎓 Comparativo de Evasão e Tempo de Formatura por Grau Acadêmico")
    st.markdown(
        "Separação dos cursos por titulação: **Bacharelado** (inclui habilitações profissionais como Engenheiro, Médico, Arquiteto etc.) vs. **Licenciatura**."
    )

    # "MISTO" (cursos com Bacharelado e Licenciatura sob o mesmo nome, sem forma confiável
    # de separar os discentes) não é uma categoria de grau real — fora desta comparação.
    df_misto = df_gold[df_gold["categoria_grau"] == "MISTO"]
    df_grau = agregar_ponderado(
        df_gold[df_gold["categoria_grau"] != "MISTO"], "categoria_grau")
    st.caption(
        f"Ficam de fora desta comparação {len(df_misto)} cursos com grau MISTO "
        f"({br(int(df_misto['total_discentes_registrados'].sum()))} alunos, "
        f"{dec(df_misto['total_discentes_registrados'].sum() / df_gold['total_discentes_registrados'].sum() * 100, 0)}% do total)."
    )

    c3, c4 = st.columns(2)
    with c3:
        fig_grau_evas = px.bar(
            df_grau,
            x="categoria_grau",
            y="taxa_evasao_pct",
            title="Taxa de Evasão por Grau Acadêmico (%)",
            color="categoria_grau",
            labels=LABELS_PT,
            text_auto=".1f",
            height=380,
        )
        grafico(fig_grau_evas, width="stretch")

    with c4:
        df_grau_tempo = df_grau.rename(columns={
            "semestre_ideal_previsto": "Tempo Ideal",
            "tempo_medio_real_semestres": "Tempo Real",
        })
        fig_grau_tempo = px.bar(
            df_grau_tempo,
            x="categoria_grau",
            y=["Tempo Ideal", "Tempo Real"],
            barmode="group",
            title="Tempo Ideal Previsto vs. Tempo Médio Real (Semestres)",
            labels=LABELS_PT,
            height=380,
        )
        fig_grau_tempo.update_layout(legend_title_text="")
        fig_grau_tempo.update_traces(
            hovertemplate="<b>%{fullData.name}</b>: %{y:.1f} sem.<extra></extra>")
        grafico(fig_grau_tempo, width="stretch")

    st.markdown("---")
    st.subheader("🏫 Comparativo de Evasão e Tamanho por Campus")
    st.markdown(
        "Taxa de evasão ponderada pelo total de alunos que ingressaram em cada campus (soma de evadidos/desligados dividida pela soma dos ingressantes). Turno e grau usam a mesma regra."
    )

    df_campus = agregar_ponderado(df_gold, "campus").sort_values(
        "taxa_evasao_pct", ascending=False)
    df_multi = df_gold[df_gold["campus"].str.upper() == "MULTICAMPUS"]
    if not df_multi.empty:
        st.caption("MULTICAMPUS reúne cursos de mais de um campus: " +
                   ", ".join(sorted(df_multi["curso"])) + ".")

    c5, c6 = st.columns(2)
    with c5:
        fig_campus_evas = px.bar(
            df_campus,
            x="campus",
            y="taxa_evasao_pct",
            title="Taxa de Evasão por Campus (%)",
            color="campus",
            labels=LABELS_PT,
            text_auto=".1f",
            height=420,
        )
        fig_campus_evas.update_layout(showlegend=False)
        grafico(fig_campus_evas, width="stretch")

    with c6:
        fig_campus_alunos = px.bar(
            df_campus,
            x="campus",
            y="total_discentes_registrados",
            title="Alunos que Ingressaram por Campus",
            color="campus",
            labels=LABELS_PT,
            text_auto=",.0f",
            height=420,
        )
        fig_campus_alunos.update_layout(showlegend=False)
        grafico(fig_campus_alunos, width="stretch")
    st.caption("Cursos por campus: " + " · ".join(
        f"{c} ({int(n)})" for c, n in zip(df_campus["campus"], df_campus["cursos"])) + ".")
    c_dl1, c_dl2, c_dl3 = st.columns(3)
    with c_dl1:
        botao_csv(df_turno, "comparativo_turnos_unb.csv", "📥 Baixar Turnos (CSV)", key="csv_turnos")
    with c_dl2:
        botao_csv(df_grau, "comparativo_graus_unb.csv", "📥 Baixar Graus (CSV)", key="csv_graus")
    with c_dl3:
        botao_csv(df_campus, "comparativo_campi_unb.csv", "📥 Baixar Campi (CSV)", key="csv_campi")
    g.mostrar_definicoes(["ingressantes", "taxa_evasao_pct", "taxa_formatura_pct", "atraso_medio_semestres",
                          "tempo_medio_formatura_semestres", "prazo_ideal_medio_semestres"])
