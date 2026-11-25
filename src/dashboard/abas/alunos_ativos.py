"""Tela: 🎒 Alunos Ativos."""

import plotly.express as px
import streamlit as st
from formatacao import botao_csv, br, dec, grafico, mostrar_tabela


def renderizar(g):
    """g: namespace com o que o app.py carregou (dados, metadados e helpers)."""
    EXCLUDED_GENERIC_COURSES = g.EXCLUDED_GENERIC_COURSES
    EH_COORTE_OFICIAL = getattr(g, "EH_COORTE_OFICIAL", True)
    df_ativos = g.df_ativos
    global_meta = g.global_meta
    mostrar_escopo = g.mostrar_escopo

    ref = global_meta.get("ativos_hoje_referencia", "")
    st.subheader(f"🎒 Quem Está no Curso Agora ({ref})")
    mostrar_escopo("ativos")
    if not EH_COORTE_OFICIAL:
        st.caption(
            f"ℹ️ Esta tela retrata a fotografia atual de ativos no SIGAA ({ref}) e **não é filtrada** "
            "pelo seletor de intervalo de coortes da barra lateral."
        )
    st.markdown(
        "Discentes de graduação na **lista de ativos mais recente do SIGAA**, de todas "
        "as turmas de ingresso. As outras abas olham só turmas antigas, que já tiveram tempo de "
        "se formar; esta mostra **onde a retenção está se acumulando hoje**."
    )
    if df_ativos is None or df_ativos.empty:
        st.warning(
            "Tabela de ativos não encontrada. Execute o pipeline (build_gold.py).")
    else:
        df_at = df_ativos.copy()
        df_at = df_at[~df_at["curso"].isin(EXCLUDED_GENERIC_COURSES)]
        total_at = int(df_at['total_ativos_hoje'].sum())
        k1, k2, k3 = st.columns(3)
        k1.metric(
            "Discentes ativos", f"{br(int(df_at['total_ativos_hoje'].sum()))}".replace(",", "."))
        k2.metric(
            "Já passaram do prazo ideal",
            f"{br(int(df_at['ativos_acima_prazo_ideal'].sum()))}".replace(
                ",", "."),
            delta=f"{dec(df_at['ativos_acima_prazo_ideal'].sum() / total_at * 100, 1)}% dos ativos" if total_at else None,
            delta_color="off",
            help="Semestres cursados do ingresso até o semestre de referência (contando os dois) acima do prazo ideal da matriz.",
        )
        k3.metric(
            "Já passaram do prazo máximo",
            f"{br(int(df_at['ativos_acima_prazo_maximo'].sum()))}".replace(
                ",", "."),
            delta=f"{dec(df_at['ativos_acima_prazo_maximo'].sum() / total_at * 100, 1)}% dos ativos" if total_at else None,
            delta_color="off",
            help="Risco de desligamento por decurso de prazo. É um subconjunto de 'Já passaram do prazo ideal': não some os dois.",
        )
        st.caption(
            "A lista de ativos não separa formandos nem trancados. Cursos-tronco (Engenharia, "
            "Educação Física - Ciclo Básico) ficam de fora: não têm prazo próprio de conclusão."
        )

        min_ativos = st.slider(
            "Mínimo de ativos no curso:", 5, 200, 50, step=5)
        df_plot = df_at[df_at["total_ativos_hoje"] >=
                        min_ativos].nlargest(20, "pct_acima_prazo_ideal")
        fig_at = px.bar(
            df_plot.sort_values("pct_acima_prazo_ideal"),
            x="pct_acima_prazo_ideal",
            y="curso",
            orientation="h",
            color_discrete_sequence=["#3B82F6"],
            labels={
                "pct_acima_prazo_ideal": "% dos ativos já acima do prazo ideal",
                "curso": "",
                "total_ativos_hoje": "Ativos",
                "ativos_acima_prazo_maximo": "Acima do prazo máximo",
            },
            hover_data={"total_ativos_hoje": True,
                        "ativos_acima_prazo_maximo": True},
            title="Cursos com maior parcela de ativos atrasados",
        )
        fig_at.update_layout(height=600)
        grafico(fig_at, width="stretch")
        _tabela_at = df_at[df_at["total_ativos_hoje"] >= min_ativos].sort_values(
            "pct_acima_prazo_ideal", ascending=False)
        st.caption(f"Tabela: {len(_tabela_at)} de {len(df_at)} cursos com {min_ativos}+ ativos (mesmo filtro do gráfico, "
                   "que mostra os 20 primeiros).")
        _tabela_exib = _tabela_at.rename(columns={
            "curso": "Curso",
            "periodo_referencia": "Semestre de referência",
            "semestre_ideal_previsto": "Prazo ideal (semestres)",
            "semestre_maximo_previsto": "Prazo máximo (semestres)",
            "total_ativos_hoje": "Ativos",
            "ativos_acima_prazo_ideal": "Acima do prazo ideal",
            "ativos_acima_prazo_maximo": "Acima do prazo máximo",
            "pct_acima_prazo_ideal": "% acima do prazo ideal",
        })
        mostrar_tabela(_tabela_exib, width="stretch", hide_index=True)
        botao_csv(
            _tabela_exib,
            f"ativos_unb_{str(ref).replace('/', '_')}.csv",
            label="📥 Baixar tabela de ativos filtrada (CSV, Gold k ≥ 5)",
            key="csv_ativos",
        )
