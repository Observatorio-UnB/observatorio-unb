"""Tela: 🇧🇷 Benchmark Nacional (INEP)."""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from formatacao import br, dec, grafico, mostrar_tabela


def renderizar(g):
    """g: namespace com o que o app.py carregou (dados, metadados e helpers)."""
    UNB_GREEN = g.UNB_GREEN
    UNB_NAVY = g.UNB_NAVY
    df_inep = g.df_inep
    mostrar_escopo = g.mostrar_escopo

    st.subheader("🇧🇷 A UnB Perde Mais Alunos que as Outras Federais?")
    mostrar_escopo("inep")
    st.markdown(
        "Cada curso da UnB comparado com **o mesmo curso nas demais universidades federais**, "
        "usando os microdados do Censo da Educação Superior de 2019 (INEP/MEC). A referência "
        "é a **mediana** das outras federais — ou seja, o padrão nacional daquele curso."
    )

    if df_inep is not None and not df_inep.empty:
        st.info(
            "ℹ️ **Estas taxas são do Censo, e medem outra coisa que a aba de evasão.** O Censo "
            "fotografa a situação das matrículas dentro de um ano (quantas estavam trancadas ou "
            "foram desvinculadas em 2019). A taxa de evasão do resto do painel acompanha a turma "
            "de ingresso ao longo de todo o curso. Os dois números são corretos e não devem ser "
            "somados nem comparados entre si.\n\n"
            "A comparação também é feita **pelo nome do curso**: mesmo nome não garante mesmo "
            "currículo, perfil de ingresso ou mercado regional. Use como indicação de onde "
            "investigar, não como veredito sobre o curso."
        )

        df_bench = df_inep[df_inep["n_ies_comparadas"] >= 10].copy()

        metrica_label = st.selectbox(
            "Indicador para comparar:",
            ["Desvinculação (aluno deixou o curso)",
             "Trancamento de matrícula"],
        )
        if metrica_label.startswith("Desvinculação"):
            col_gap, col_unb, col_med = "gap_desvinculacao_pp", "taxa_desvinculacao_unb_pct", "mediana_desvinculacao_federais_pct"
            col_razao = "razao_desvinculacao"
            _verbo = "desvincula"
        else:
            col_gap, col_unb, col_med = "gap_trancamento_pp", "taxa_trancamento_unb_pct", "mediana_trancamento_federais_pct"
            col_razao = "razao_trancamento"
            _verbo = "tranca"
        _acima = int((df_bench[col_gap] > 0).sum())
        st.markdown(
            f"**Resposta curta:** em **{_acima} de {len(df_bench)} cursos** comparáveis (com pelo menos 10 "
            f"federais no mesmo curso), a UnB {_verbo} proporcionalmente mais alunos que a mediana nacional.")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Cursos da UnB comparados", f"{len(df_bench)}",
                  help="Cursos com pelo menos 10 federais comparáveis. É a base dos três primeiros indicadores e do gráfico de barras.")
        k2.metric(
            "Acima da mediana nacional",
            f"{int((df_bench[col_gap] > 0).sum())} cursos",
            help="Cursos em que a UnB desvincula proporcionalmente mais alunos que a mediana das demais federais.",
            delta="pior que o padrão",
            delta_color="inverse",
        )
        k3.metric(
            "Abaixo da mediana nacional",
            f"{int((df_bench[col_gap] < 0).sum())} cursos",
            delta="melhor que o padrão",
        )
        k4.metric(
            "Matrículas trancadas na UnB",
            f"{br(int(df_bench['qt_trancadas_unb'].sum()))}".replace(
                ",", "."),
            help=(
                "Matrículas trancadas no Censo 2019 nos cursos comparados ao lado — as bases de discentes do "
                "portal não trazem o histórico de trancamentos."
            ),
        )

        st.markdown("---")

        df_plot = df_bench.dropna(subset=[col_gap]).copy()
        destaques = pd.concat(
            [df_plot.nlargest(10, col_gap), df_plot.nsmallest(10, col_gap)])
        destaques = destaques.sort_values(col_gap)
        destaques["situacao"] = destaques[col_gap].apply(
            lambda v: "Acima do padrão nacional" if v > 0 else "Abaixo do padrão nacional"
        )

        fig_gap = px.bar(
            destaques,
            x=col_gap,
            y="curso_inep",
            orientation="h",
            color="situacao",
            color_discrete_map={
                "Acima do padrão nacional": "#DC2626",
                "Abaixo do padrão nacional": UNB_GREEN,
            },
            labels={
                col_gap: "Diferença para a mediana nacional (pontos percentuais)",
                "curso_inep": "",
                col_unb: "Taxa na UnB (%)",
                col_med: "Mediana das federais (%)",
                col_razao: "Quantas vezes o padrão nacional",
                "n_ies_comparadas": "Federais comparadas",
                "qt_matriculas_unb": "Matrículas na UnB",
            },
            title=f"Onde a UnB mais se distancia do padrão nacional — {metrica_label.split(' (')[0]}",
            hover_data={
                col_unb: ":.1f",
                col_med: ":.1f",
                col_razao: ":.2f",
                "qt_matriculas_unb": ":,.0f",
                "n_ies_comparadas": True,
            },
            height=620,
        )
        fig_gap.add_vline(x=0, line_color="#374151", line_width=2)
        fig_gap.update_layout(legend_title_text="")
        grafico(fig_gap, width="stretch")
        st.caption(
            "Passe o mouse sobre a barra para ver **quantas vezes o padrão nacional** aquele curso "
            "representa. A barra mede a diferença em pontos percentuais, que não distingue gravidade "
            "relativa: +6 pp num curso que perde 24% em todo o país pesa menos que +7 pp num que "
            "perde 8%."
        )

        st.markdown("---")
        st.markdown(
            "##### 🎯 Cursos mais disputados no vestibular perdem menos alunos?")

        df_sc = df_bench.dropna(
            subset=["concorrencia_vestibular_unb", col_unb]).copy()

        # A concorrência vai de 0,6 a 69 candidatos por vaga, mas 75% dos cursos ficam
        # abaixo de 6: em escala linear quase todos os pontos se amontoam num canto. O eixo
        # logarítmico distribui os cursos de forma legível, e a correlação é medida no mesmo
        # espaço em que a tendência é desenhada.
        x_log = np.log10(
            df_sc["concorrencia_vestibular_unb"].values.astype(float))
        y_v = df_sc[col_unb].values.astype(float)
        r_sc = float(np.corrcoef(x_log, y_v)[0, 1])

        # Teste t da correlação de Pearson (H0: r = 0). Com dezenas de cursos a distribuição t
        # já é próxima da normal, então |t| > 1,96 corresponde a p < 0,05 bilateral.
        n_sc = len(df_sc)
        t_sc = r_sc * np.sqrt((n_sc - 2) /
                              max(1 - r_sc**2, 1e-12)) if n_sc > 2 else 0.0
        if abs(t_sc) > 1.96:
            sentido = "menor" if r_sc < 0 else "maior"
            leitura = (
                "com esse número de cursos, a relação é estatisticamente significativa (p < 0,05): "
                f"quanto mais disputado o ingresso, {sentido} o indicador."
            )
        else:
            leitura = (
                "com esse número de cursos, a relação não é estatisticamente significativa (p ≥ 0,05)."
            )

        st.markdown(
            f"Relação entre a concorrência de entrada (inscritos por vaga) e o indicador selecionado, "
            f"nos **{n_sc} cursos** da UnB. **Correlação: {dec(r_sc)}** — {leitura}"
        )

        fig_conc = px.scatter(
            df_sc,
            x="concorrencia_vestibular_unb",
            y=col_unb,
            size="qt_matriculas_unb",
            hover_name="curso_inep",
            log_x=True,
            labels={
                "concorrencia_vestibular_unb": "Concorrência no vestibular (inscritos por vaga, escala log)",
                col_unb: metrica_label.split(" (")[0] + " (%)",
                "qt_matriculas_unb": "Matrículas na UnB",
            },
            color_discrete_sequence=[UNB_NAVY],
            height=460,
        )
        slope, intercept = np.polyfit(x_log, y_v, 1)
        x_line_log = np.linspace(x_log.min(), x_log.max(), 50)
        fig_conc.add_trace(
            go.Scatter(
                x=10 ** x_line_log,
                y=slope * x_line_log + intercept,
                mode="lines",
                name=f"Tendência (r = {dec(r_sc)})",
                line=dict(color="#DC2626", dash="dash", width=2),
            )
        )
        grafico(fig_conc, width="stretch")

        with st.expander("📄 Ver todos os cursos comparados"):
            mostrar_tabela(
                df_bench[[
                    "curso_inep", "qt_matriculas_unb", "taxa_desvinculacao_unb_pct",
                    "mediana_desvinculacao_federais_pct", "taxa_trancamento_unb_pct",
                    "mediana_trancamento_federais_pct", "n_ies_comparadas",
                ]].rename(columns={
                    "curso_inep": "Curso",
                    "qt_matriculas_unb": "Matrículas (UnB)",
                    "taxa_desvinculacao_unb_pct": "Desvinculação UnB (%)",
                    "mediana_desvinculacao_federais_pct": "Desvinculação Federais (%)",
                    "taxa_trancamento_unb_pct": "Trancamento UnB (%)",
                    "mediana_trancamento_federais_pct": "Trancamento Federais (%)",
                    "n_ies_comparadas": "Federais comparadas",
                }),
                width="stretch",
                hide_index=True,
                height=400,
            )
    else:
        st.warning(
            "Benchmark do INEP não encontrado na camada Gold. Execute "
            "`python src/ingestion/inep_censo_superior.py`, depois `transform_silver.py` e `build_gold.py`."
        )
