"""Tela: 🔍 Detalhe por Curso."""

import pandas as pd
import plotly.express as px
import streamlit as st
from formatacao import br, dec, grafico


def renderizar(g):
    """g: namespace com o que o app.py carregou (dados, metadados e helpers)."""
    _graficos_do_curso = g._graficos_do_curso
    _versao_dos_dados = g._versao_dos_dados
    df_gold = g.df_gold
    global_meta = g.global_meta
    load_coortes = g.load_coortes
    mostrar_escopo = g.mostrar_escopo

    st.subheader("🔍 Raio-X Acadêmico por Curso")
    mostrar_escopo("detalhe")

    course_list = sorted(df_gold["curso"].unique())
    selected_course = st.selectbox(
        "Selecione o Curso para detalhamento:", course_list)
    st.caption(
        "ℹ️ Cursos com menos de 5 discentes registrados não aparecem nesta lista — "
        "supressão ética (k-anonimato) para proteger a identidade de alunos em turmas pequenas."
    )

    row_course = df_gold[df_gold["curso"] == selected_course].iloc[0]
    coortes = (global_meta or {}).get("coortes_ingresso_analisadas", "n/d")
    st.markdown(
        f"**{br(int(row_course['total_discentes_registrados']))} alunos** ingressaram em "
        f"**{selected_course}** nas turmas de **{coortes}** (ano de ingresso): "
        f"{br(int(row_course['total_formados']))} se formaram, "
        f"{br(int(row_course['total_evadidos_desligados']))} evadiram ou foram desligados e "
        f"{br(int(row_course['total_ainda_ativos']))} ainda estão ativos. "
        "Só entram turmas com 8+ anos de acompanhamento."
    )

    # Metadados do curso
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric("Tempo Médio Real",
                  f"{dec(row_course['tempo_medio_real_semestres'], 1)} sem.",
                  help="Média de semestres do ingresso à formatura, só entre quem se formou.")
    with m2:
        st.metric("Tempo Ideal da Matriz",
                  f"{dec(row_course['semestre_ideal_previsto'], 0)} sem.",
                  help="Duração prevista na estrutura curricular do curso (publicada em 10/2020), aplicada a todos os ingressantes analisados.")
    with m3:
        st.metric("Atraso Médio",
                  f"{'+' if row_course['desvio_medio_semestres'] >= 0 else '-'}{dec(abs(row_course['desvio_medio_semestres']), 1)} sem.",
                  help="Tempo médio real menos o tempo ideal da matriz. Positivo = formam depois do ideal; negativo = antes.")
    with m4:
        st.metric("Taxa de Formatura",
                  f"{dec(row_course['taxa_formatura_pct'], 1)}%",
                  help="Alunos formados ÷ alunos que ingressaram nas turmas analisadas.")
    with m5:
        st.metric("Taxa de Evasão",
                  f"{dec(row_course['taxa_evasao_pct'], 1)}%",
                  help="Evadidos ou desligados ÷ alunos que ingressaram. Inclui mudança de curso.")
    _irc = row_course["indice_retencao_critica"]
    if pd.notna(_irc):
        _pos = int((df_gold["indice_retencao_critica"] > _irc).sum()) + 1
        _ev_unb = df_gold["total_evadidos_desligados"].sum() / df_gold["total_discentes_registrados"].sum() * 100
        _fo_unb = df_gold["total_formados"].sum() / df_gold["total_discentes_registrados"].sum() * 100
        st.caption(
            f"Contexto: IRC {dec(_irc, 1)} ({_pos}º de {len(df_gold)} cursos; 100 = pior). "
            f"Média da UnB: evasão {dec(_ev_unb, 1)}% e formatura {dec(_fo_unb, 1)}%.")

    st.markdown("---")

    _graficos_do_curso(row_course, "curso")

    st.markdown("---")
    st.subheader("🎓 Por turma de ingresso")
    todas_coortes = pd.DataFrame(load_coortes(_versao_dos_dados()))
    df_coortes = todas_coortes[todas_coortes["curso"] ==
                             selected_course] if not todas_coortes.empty else todas_coortes
    if todas_coortes.empty:
        st.warning(
            "Os dados por turma não vieram na carga que o painel está lendo (tabela "
            "`gold.retencao_cursos_coorte` vazia ou ausente). Rode as migrações e o pipeline, ou "
            "gere o export novo (`python3 src/db/exportar_gold.py`)."
        )
    elif df_coortes.empty:
        st.info(f"Sem turmas com 5 ou mais alunos em {selected_course}.")
    else:
        df_coortes = df_coortes.sort_values("ano_ingresso")
        anos = [int(a) for a in df_coortes["ano_ingresso"]]
        maduras = [i for i, m in enumerate(df_coortes["coorte_madura"]) if m]
        # Abre na última coorte madura: a mais recente ainda não tem desfecho e confunde o primeiro número visto.
        ano_sel = st.selectbox("Turma (ano de ingresso):", anos,
                               index=maduras[-1] if maduras else len(anos) - 1, key="coorte_sel")
        row_coorte = df_coortes[df_coortes["ano_ingresso"] == ano_sel].iloc[0]
        if not row_coorte["coorte_madura"]:
            st.warning(
                f"A turma de {ano_sel} ainda não tem 8 anos de acompanhamento: muitos alunos seguem "
                "ativos, a evasão é registrada com atraso e o tempo de formatura só conta quem já "
                "se formou (parece menor do que será). Não entra nos números do topo da página."
            )
        _pct_ativos = row_coorte["total_ainda_ativos"] / \
            row_coorte["total_discentes_registrados"] * 100
        if row_coorte["coorte_madura"] and _pct_ativos >= 5:
            st.info(f"A turma de {ano_sel} já passou de 8 anos, mas ainda tem {dec(_pct_ativos, 0)}% de alunos ativos: "
                    "formatura e evasão ainda podem mudar um pouco.")
        st.markdown(
            f"**{br(int(row_coorte['total_discentes_registrados']))} alunos** ingressaram em {ano_sel}: "
            f"{br(int(row_coorte['total_formados']))} formados "
            f"({dec(row_coorte['taxa_formatura_pct'], 1)}%), "
            f"{br(int(row_coorte['total_evadidos_desligados']))} evadidos ou desligados "
            f"({dec(row_coorte['taxa_evasao_pct'], 1)}%) e "
            f"{br(int(row_coorte['total_ainda_ativos']))} ainda ativos."
        )
        _graficos_do_curso(row_coorte, f"coorte{ano_sel}")

        st.caption("Turmas com menos de 5 alunos não aparecem, por isso a soma das turmas pode ficar um pouco "
                   "abaixo do total do curso.")
        st.markdown("##### 📈 Todas as turmas")
        st.caption("Turmas recentes (sem 8 anos de acompanhamento) têm formatura baixa e evasão "
                   "subestimada só porque o tempo ainda não passou. Marcadas com ⚠️.")
        df_evol = df_coortes.assign(
            coorte=[f"{int(a)}" + ("" if m else " ⚠️") for a, m in
                   zip(df_coortes["ano_ingresso"], df_coortes["coorte_madura"])]
        ).melt(id_vars="coorte", value_vars=["taxa_formatura_pct", "taxa_evasao_pct"],
               var_name="Indicador", value_name="Percentual")
        df_evol["Indicador"] = df_evol["Indicador"].map(
            {"taxa_formatura_pct": "Formatura", "taxa_evasao_pct": "Evasão / Desligamento"})
        fig_evol = px.line(df_evol, x="coorte", y="Percentual", color="Indicador", markers=True,
                           color_discrete_map={
                               "Formatura": "#10B981", "Evasão / Desligamento": "#DC2626"},
                           height=320)
        fig_evol.update_traces(
            hovertemplate="Turma %{x}<br>%{y:.1f}% dos alunos<extra></extra>")
        fig_evol.update_xaxes(type="category", title="Ano de ingresso")
        grafico(fig_evol, width="stretch", key="coorte_evolucao")
