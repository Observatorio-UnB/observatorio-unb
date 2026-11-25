"""Tela: 🔬 PIBIC & Inclusão Social na Ciência."""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from formatacao import br, dec, grafico, mostrar_tabela


def renderizar(g):
    """g: namespace com o que o app.py carregou (dados, metadados e helpers)."""
    _COORTES = g._COORTES
    EH_COORTE_OFICIAL = getattr(g, "EH_COORTE_OFICIAL", True)
    df_gold = getattr(g, "df_gold_oficial", g.df_gold)
    df_pibic = g.df_pibic
    mostrar_escopo = g.mostrar_escopo
    n_pibic_evasao = g.n_pibic_evasao
    pibic_meta = g.pibic_meta
    r_pibic_evasao = g.r_pibic_evasao
    r_pibic_evasao_txt = g.r_pibic_evasao_txt

    st.subheader(
        "🔬 Iniciação Científica & Democratização da Ciência na UnB (PIBIC / PIVIC)")
    mostrar_escopo("pibic")
    if not EH_COORTE_OFICIAL:
        st.caption(
            f"ℹ️ Esta tela cruza planos de IC (2018–2023) com o recorte oficial de coortes maduras (**{_COORTES}**) "
            "e não é filtrada pelo seletor lateral."
        )
    if pibic_meta:
        anos_pibic = [int(a["ano"])
                      for a in pibic_meta.get("evolucao_anual", [])]
        periodo_pibic = f" ({min(anos_pibic)}–{max(anos_pibic)})" if anos_pibic else ""
        st.markdown(
            f"Análise do fomento público de pesquisa (~R$ {dec(pibic_meta['investimento_publico_total_estimado'] / 1e6, 0)} milhões), "
            f"inclusão de cotistas e disparidades socioeconômicas e territoriais{periodo_pibic}."
        )

    if pibic_meta and df_pibic is not None:
        # KPIs Principais
        kp1, kp2, kp3, kp4 = st.columns(4)
        with kp1:
            st.metric(
                label="Planos de IC Cadastrados",
                value=f"{br(pibic_meta['total_projetos_ic'])}",
                help=("Todos os planos de iniciação científica cadastrados no período, inclusive os ainda em "
                      "avaliação ou apenas enviados (sobretudo 2023). Não é só o que foi aprovado."),
            )
        with kp2:
            invest_mi = pibic_meta['investimento_publico_total_estimado'] / 1e6
            st.metric(
                label="Investimento Público Estimado",
                value=f"R$ {dec(invest_mi, 2)} Mi",
                help=("Estimativa: bolsas pagas x 12 meses x valor mensal da bolsa de IC no CNPq (R$ 400 até jan/2023, R$ 700 desde "
                      "fev/2023). Não considera a duração real de cada bolsa, e 2022 e 2023 estão incompletos nos dados. "
                      "As bolsas são de UnB, CNPq e FAPDF e o valor não distingue a origem."),
            )
        with kp3:
            st.metric(
                label="Inserção de Cotistas na Pesquisa",
                value=f"{dec(pibic_meta['taxa_inclusao_cotistas_pct'], 1)}%",
                help="% dos planos de IC (com bolsa ou voluntários) cujo discente ingressou por Ações Afirmativas (PPI, Escola Pública, Baixa Renda, PCD).",
            )
        with kp4:
            st.metric(
                label="Pesquisa Voluntária (Sem Bolsa)",
                value=f"{dec(pibic_meta['taxa_trabalho_voluntario_pct'], 1)}%",
                help="Planos de pesquisa voluntários (PIVIC) onde o discente trabalha sem receber remuneração.",
            )

        _planos_tabela = int(df_pibic["total_projetos"].sum())
        _planos_kpi = int(pibic_meta["total_projetos_ic"])
        if _planos_tabela != _planos_kpi:
            st.caption(
                f"Os KPIs acima somam {br(_planos_kpi)} planos (todos os cadastrados); a tabela por curso abaixo soma "
                f"{br(_planos_tabela)}, porque só inclui cursos do painel (5+ alunos, sem curso-tronco). Por isso "
                "os percentuais e o investimento da tabela diferem um pouco dos KPIs.")

        lacuna_bolsa = int(df_pibic["total_projetos"].sum() - df_pibic["total_remuneradas"].sum()
                           - df_pibic["total_voluntarias_pivic"].sum())
        if lacuna_bolsa > 0:
            st.caption(f"{br(lacuna_bolsa)} planos não informam se são com bolsa ou voluntários: ficam fora de "
                       "'Bolsas Pagas' e de 'Voluntários (PIVIC)' na tabela abaixo.".replace(",", "."))

        _serie = pibic_meta.get("evolucao_anual", [])
        if _serie:
            _contagens = [int(a["total_projetos"]) for a in _serie]
            _txt_serie = " · ".join(
                f"{int(a['ano'])}: {br(a['total_projetos'])}" for a in _serie)
            _incompleto = len(
                _contagens) > 2 and _contagens[-1] < 0.5 * float(np.median(_contagens))
            st.caption(f"Planos por ano: {_txt_serie}."
                       + (f" O último ano ({int(_serie[-1]['ano'])}) parece incompleto: a queda reflete o corte dos "
                          "dados, e não menos iniciação científica." if _incompleto else ""))

        st.markdown("---")

        # Alerta Teórico-Metodológico: os percentuais saem dos dados, e não de um texto fixo que envelhece.
        _areas = pd.DataFrame(pibic_meta["distribuicao_grande_area"])
        _areas = _areas[_areas["area_conhecimento"] != "OUTRA"].sort_values(
            "pct_cotistas", ascending=False)
        if len(_areas) >= 3:
            _a1, _a2, _az = _areas.iloc[0], _areas.iloc[1], _areas.iloc[-1]
            _texto_areas = (
                f"enquanto {str(_a1['area_conhecimento']).title()} ({dec(_a1['pct_cotistas'], 1)}%) e {str(_a2['area_conhecimento']).title()} "
                f"({dec(_a2['pct_cotistas'], 1)}%) têm a maior presença de cotistas, em **{str(_az['area_conhecimento']).title()} "
                f"essa taxa cai para {dec(_az['pct_cotistas'], 1)}%**. ")
        else:
            _texto_areas = ""
        st.info(
            "💡 **Dimensão Social da Ciência:** A iniciação científica é um dos principais instrumentos de fixação do discente na universidade. "
            f"Contudo, a distribuição das oportunidades reflete desigualdades estruturais: {_texto_areas}"
            f"Além disso, **{dec(pibic_meta['taxa_trabalho_voluntario_pct'], 1)}% dos planos são voluntários (PIVIC)**, "
            "criando uma barreira invisível para quem precisa de renda imediata."
        )

        # Linha 1: Democratização por Grande Área e Desigualdade Territorial
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.markdown(
                "##### 🏛️ Presença de Cotistas por Grande Área de Pesquisa")
            df_area = pd.DataFrame(pibic_meta["distribuicao_grande_area"])
            fig_area = px.bar(
                df_area[df_area["area_conhecimento"] != "OUTRA"],
                x="area_conhecimento",
                y=["pct_cotistas"],
                title="Taxa de Inclusão de Cotistas por Área (%)",
                labels={"area_conhecimento": "Grande Área",
                        "value": "% de Cotistas"},
                color="area_conhecimento",
                text_auto=".1f",
                height=380,
            )
            fig_area.update_layout(showlegend=False, yaxis_range=[0, 60])
            grafico(fig_area, width="stretch")
            st.caption(
                "A categoria OUTRA (planos de cursos sem área definida no cruzamento por nome) fica de fora.")

        with col_g2:
            st.markdown(
                "##### 📍 Descentralização Territorial: Planos de IC por Campus")
            df_campi = pd.DataFrame(pibic_meta["distribuicao_campi"])
            fig_campi = px.pie(
                df_campi,
                names="campus",
                values="total_projetos",
                title="Participação no Total de Projetos por Campus",
                hole=0.45,
                height=380,
                color_discrete_sequence=px.colors.qualitative.Safe,
            )
            grafico(fig_campi, width="stretch")

        # "% Cotistas" acima mede a composição interna do programa de IC (quem, entre os
        # bolsistas, é cotista); esta segunda métrica mede penetração real na área (quantos
        # dos alunos matriculados têm bolsa de IC) — perguntas distintas e complementares.
        st.markdown(
            "##### 🎓 Projetos de IC em Relação ao Tamanho da Área")
        st.caption(
            f"Projetos de IC de {periodo_pibic.strip(' ()') or '2018–2023'} divididos pelos alunos que ingressaram em "
            f"{_COORTES} na área. São períodos diferentes: leia como intensidade de IC por área, e não como a "
            "parcela de alunos que fez IC.")
        df_area_part = df_area[df_area["area_conhecimento"] != "OUTRA"]
        fig_participacao = px.bar(
            df_area_part,
            x="area_conhecimento",
            y="taxa_participacao_pibic_pct",
            title="Projetos de IC por 100 alunos da área",
            labels={"area_conhecimento": "Grande Área",
                    "taxa_participacao_pibic_pct": "Projetos de IC por 100 alunos"},
            color="area_conhecimento",
            text_auto=".1f",
            height=380,
        )
        fig_participacao.update_layout(showlegend=False)
        grafico(fig_participacao, width="stretch")

        # Linha 2: O Fator "PIBIC vs. Evasão" (A Dinâmica da 'Correlação Suspeita')
        st.markdown("---")
        st.markdown(
            "##### 🎯 Cruzamento Estratégico: O PIBIC Protege Contra a Evasão?")
        st.markdown(
            "Cruzamento entre o Observatório de Retenção e a base de Iniciação Científica "
            f"({n_pibic_evasao} cursos com ao menos um projeto de IC; projetos de {periodo_pibic.strip(' ()') or '2018–2023'}, "
            f"evasão dos ingressantes de {_COORTES}). "
            f"**Correlação encontrada: r = {r_pibic_evasao_txt}**"
            + (" (cursos com mais projetos de IC por 100 alunos tendem a ter menor evasão)."
               if r_pibic_evasao is not None and r_pibic_evasao < 0 else ".")
        )

        st.caption(f"{int((df_gold['pibic_total_projetos'].fillna(0) == 0).sum())} cursos sem nenhum projeto de IC "
                   "ficam fora do gráfico e do cálculo da correlação.")
        df_scatter = df_gold[df_gold["pibic_total_projetos"] > 0].dropna(
            subset=["pibic_projetos_por_100_alunos", "taxa_evasao_pct"]
        )
        fig_pibic_evas = px.scatter(
            df_scatter,
            x="pibic_projetos_por_100_alunos",
            y="taxa_evasao_pct",
            size="pibic_total_projetos",
            color="campus",
            hover_name="curso",
            hover_data={
                "pibic_total_projetos": True,
                "pibic_investimento_total": ":,.0f",
                "taxa_evasao_pct": ":.1f",
            },
            labels={
                "pibic_projetos_por_100_alunos": "Projetos de IC por 100 Alunos Registrados",
                "taxa_evasao_pct": "Taxa de Evasão / Desligamento (%)",
                "pibic_total_projetos": "Planos de IC",
                "pibic_investimento_total": "Investimento em bolsas (R$)",
                "campus": "Campus",
            },
            title="Projetos de IC per capita vs. Taxa de Evasão dos Cursos",
            height=450,
        )

        # Linha de tendência calculada nativamente com numpy (sem dependência de statsmodels)
        if len(df_scatter) > 1:
            x_vals = df_scatter["pibic_projetos_por_100_alunos"].values.astype(
                float)
            y_vals = df_scatter["taxa_evasao_pct"].values.astype(float)
            slope, intercept = np.polyfit(x_vals, y_vals, 1)
            x_line = np.linspace(x_vals.min(), x_vals.max(), 50)
            y_line = slope * x_line + intercept
            fig_pibic_evas.add_trace(
                go.Scatter(
                    x=x_line,
                    y=y_line,
                    mode="lines",
                    name=f"Tendência Linear (r = {r_pibic_evasao_txt})",
                    line=dict(color="#DC2626", dash="dash", width=2),
                )
            )

        grafico(fig_pibic_evas, width="stretch")

        st.warning(
            "🔎 **Correlação não é causa:** "
            "Embora os dados apontem que mais PIBIC correlaciona com menor evasão, há **fatores de confusão (confundidores)** e um desencontro de períodos: "
            "boa parte da evasão dos ingressantes de 2010 a 2016 aconteceu antes de os projetos de IC aqui contados começarem. "
            "Hipótese (não medida neste painel): cursos de altíssima concorrência no vestibular (como Medicina e Direito) podem concentrar mais projetos de pesquisa e atrair estudantes com maior renda prévia, "
            "que já evadem menos independentemente da bolsa. Cursos noturnos podem ter oferta menor de pesquisa por incompatibilidade de horário."
        )

        # Linha 3: Tabela Detalhada com Busca
        st.markdown("---")
        st.markdown(
            "##### 📋 Consulta de Fomento e Inclusão por Curso / Unidade")
        filtro_campus = st.multiselect(
            "Filtrar por Campus:",
            options=df_pibic["campus"].unique(),
            default=df_pibic["campus"].unique(),
        )
        df_pibic_view = df_pibic[df_pibic["campus"].isin(
            filtro_campus)].copy()
        df_pibic_view["valor_total_investido_formatado"] = df_pibic_view["valor_total_investido"].apply(
            lambda v: f"R$ {br(v, 2)}")

        mostrar_tabela(
            df_pibic_view[[
                "curso_pibic_norm",
                "campus",
                "area_conhecimento",
                "total_projetos",
                "total_remuneradas",
                "total_voluntarias_pivic",
                "taxa_cotistas_pct",
                "taxa_voluntario_pct",
                "valor_total_investido_formatado",
            ]].rename(columns={
                "curso_pibic_norm": "Curso / Habilitação",
                "area_conhecimento": "Grande Área",
                "total_projetos": "Total Projetos",
                "total_remuneradas": "Bolsas Pagas",
                "total_voluntarias_pivic": "Voluntários (PIVIC)",
                "taxa_cotistas_pct": "% Cotistas",
                "taxa_voluntario_pct": "% Voluntários",
                "valor_total_investido_formatado": "Total Investido (R$)",
            }),
            width="stretch",
            height=350,
        )
        st.caption(f"Esta tabela soma {br(int(df_pibic['total_projetos'].sum()))} planos, um pouco menos que o indicador do "
                   "topo: planos de áreas sem curso correspondente no cruzamento por nome ficam de fora.")
    else:
        st.warning(
            "Dados analíticos do PIBIC não encontrados na camada Gold. Execute `build_gold.py`.")
