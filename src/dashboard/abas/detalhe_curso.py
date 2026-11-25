"""Tela: 🔍 Detalhe por Curso."""

import pandas as pd
import plotly.express as px
import streamlit as st
from coortes import ic_wilson_pct
from formatacao import CORES_DESFECHO, botao_csv, br, dec, delta_pp, grafico


def renderizar(g):
    """g: namespace com o que o app.py carregou (dados, metadados e helpers)."""
    _graficos_do_curso = g._graficos_do_curso
    _versao_dos_dados = g._versao_dos_dados
    _media_ponderada = g._media_ponderada
    COORTE_SELECIONADA = getattr(g, "COORTE_SELECIONADA", str((g.global_meta or {}).get("coortes_ingresso_analisadas", "n/d")))
    INCLUI_IMATURAS = getattr(g, "INCLUI_IMATURAS", False)
    df_gold = g.df_gold
    load_coortes = g.load_coortes
    mostrar_escopo = g.mostrar_escopo

    st.subheader("🔍 Raio-X Acadêmico por Curso")
    mostrar_escopo("detalhe")

    if INCLUI_IMATURAS:
        st.warning(
            f"O recorte global ativo (**{COORTE_SELECIONADA}**) inclui coortes imaturas (< 8 anos): "
            "os números agregados do topo abaixo refletem esse intervalo exploratório."
        )

    course_list = sorted(df_gold["curso"].unique())
    idx_inicial = 0
    if "curso_selecionado" in st.session_state and st.session_state["curso_selecionado"] in course_list:
        idx_inicial = course_list.index(st.session_state["curso_selecionado"])

    selected_course = st.selectbox(
        "Selecione o Curso para detalhamento:",
        course_list,
        index=idx_inicial,
    )
    st.session_state["curso_selecionado"] = selected_course
    try:
        st.query_params["curso"] = selected_course
    except Exception:
        pass

    st.caption(
        "ℹ️ Cursos com menos de 5 discentes registrados não aparecem nesta lista — "
        "supressão ética (k-anonimato) para proteger a identidade de alunos em turmas pequenas."
    )

    row_course = df_gold[df_gold["curso"] == selected_course].iloc[0]
    n_curso = int(row_course["total_discentes_registrados"])
    st.markdown(
        f"**{br(n_curso)} alunos** ingressaram em "
        f"**{selected_course}** nas turmas de **{COORTE_SELECIONADA}** (ano de ingresso): "
        f"{br(int(row_course['total_formados']))} se formaram, "
        f"{br(int(row_course['total_evadidos_desligados']))} evadiram ou foram desligados e "
        f"{br(int(row_course['total_ainda_ativos']))} ainda estão ativos."
    )

    # Médias da UnB no recorte ativo para deltas comparativos
    _tot_unb = float(df_gold["total_discentes_registrados"].sum())
    _ev_unb = df_gold["total_evadidos_desligados"].sum() / _tot_unb * 100.0 if _tot_unb else float("nan")
    _fo_unb = df_gold["total_formados"].sum() / _tot_unb * 100.0 if _tot_unb else float("nan")
    _atraso_unb = _media_ponderada(df_gold, "desvio_medio_semestres")

    # Metadados do curso com deltas comparativos vs. UnB
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        _tm = row_course["tempo_medio_real_semestres"]
        st.metric("Tempo Médio Real",
                  f"{dec(_tm, 1)} sem." if pd.notna(_tm) else "—",
                  help="Média de semestres do ingresso à formatura, só entre quem se formou.")
    with m2:
        st.metric("Tempo Ideal da Matriz",
                  f"{dec(row_course['semestre_ideal_previsto'], 0)} sem.",
                  help="Duração prevista na estrutura curricular do curso (publicada em 10/2020), aplicada a todos os ingressantes analisados.")
    with m3:
        _desv = row_course["desvio_medio_semestres"]
        st.metric("Atraso Médio",
                  (f"{'+' if _desv >= 0 else '-'}{dec(abs(_desv), 1)} sem.") if pd.notna(_desv) else "—",
                  delta=delta_pp(_desv, _atraso_unb, 1, "sem.", " vs. UnB") if pd.notna(_desv) else None,
                  delta_color="inverse",
                  help="Tempo médio real menos o tempo ideal da matriz. Positivo = formam depois do ideal; negativo = antes.")
    with m4:
        st.metric("Taxa de Formatura",
                  f"{dec(row_course['taxa_formatura_pct'], 1)}%",
                  delta=delta_pp(row_course["taxa_formatura_pct"], _fo_unb, 1, "p.p.", " vs. UnB"),
                  delta_color="normal",
                  help="Alunos formados ÷ alunos que ingressaram nas turmas analisadas.")
    with m5:
        st.metric("Taxa de Evasão",
                  f"{dec(row_course['taxa_evasao_pct'], 1)}%",
                  delta=delta_pp(row_course["taxa_evasao_pct"], _ev_unb, 1, "p.p.", " vs. UnB"),
                  delta_color="inverse",
                  help="Evadidos ou desligados ÷ alunos que ingressaram. Inclui mudança de curso.")

    # Intervalo de confiança de Wilson 95% (rigor estatístico para cursos pequenos)
    inf_ev, sup_ev, margem_ev = ic_wilson_pct(row_course["total_evadidos_desligados"], n_curso)
    _irc = row_course["indice_retencao_critica"]
    partes_ctx = []
    if pd.notna(_irc):
        _pos = int((df_gold["indice_retencao_critica"] > _irc).sum()) + 1
        partes_ctx.append(f"IRC {dec(_irc, 1)} ({_pos}º de {len(df_gold)} cursos; 100 = pior)")
    partes_ctx.append(f"Média UnB: evasão {dec(_ev_unb, 1)}% e formatura {dec(_fo_unb, 1)}%")
    if pd.notna(margem_ev):
        partes_ctx.append(
            f"IC 95% (Wilson) da evasão: {dec(inf_ev, 1)}% a {dec(sup_ev, 1)}% (±{dec(margem_ev, 1)} p.p., n={br(n_curso)})"
        )
    st.caption("Contexto: " + " · ".join(partes_ctx) + ".")
    if n_curso < 50 and pd.notna(margem_ev):
        st.info(
            f"Amostra reduzida ({br(n_curso)} ingressantes): a margem estatística da evasão é de "
            f"±{dec(margem_ev, 1)} p.p. (IC 95% de Wilson). Pequenas variações em números absolutos alteram "
            "fortemente o percentual."
        )

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
                "se formou (parece menor do que será). Não entra nos números oficiais do topo da página."
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
        fig_evol = px.line(
            df_evol, x="coorte", y="Percentual", color="Indicador",
            line_dash="Indicador", markers=True,
            color_discrete_map={
                "Formatura": CORES_DESFECHO["Formatura"],
                "Evasão / Desligamento": CORES_DESFECHO["Evasão / Desligamento"],
            },
            height=320,
        )
        fig_evol.update_traces(
            hovertemplate="Turma %{x}<br>%{y:.1f}% dos alunos<extra></extra>")
        fig_evol.update_xaxes(type="category", title="Ano de ingresso")
        grafico(fig_evol, width="stretch", key="coorte_evolucao")

        botao_csv(
            df_coortes,
            f"coortes_{selected_course.lower().replace(' ', '_')}.csv",
            label=f"📥 Baixar série de coortes de {selected_course} (CSV, Gold k ≥ 5)",
            key="csv_detalhe_coortes",
        )
