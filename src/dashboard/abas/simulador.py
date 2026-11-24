"""Tela: 💡 Simulador What-If & Custo da Retenção."""

import pandas as pd
import plotly.express as px
import streamlit as st
from formatacao import br, dec, grafico, reducao


def renderizar(g):
    """g: namespace com o que o app.py carregou (dados, metadados e helpers)."""
    UNB_GREEN = g.UNB_GREEN
    _COORTES = g._COORTES
    _anos_do_intervalo = g._anos_do_intervalo
    df_gold = g.df_gold
    global_meta = g.global_meta
    mostrar_escopo = g.mostrar_escopo
    n_pibic_evasao = g.n_pibic_evasao
    pibic_meta = g.pibic_meta
    r_pibic_evasao = g.r_pibic_evasao
    r_pibic_evasao_txt = g.r_pibic_evasao_txt

    st.subheader(
        "💡 Simulador What-If de Decisão do DEG & Impacto Orçamentário")
    mostrar_escopo("simulador")
    st.warning(
        "**Cenário hipotético, não é previsão.** Os resultados abaixo vêm de hipóteses fixas: cada 10% a mais de "
        "bolsas reduz a evasão em 2,5% do seu valor (fator 0,25), todo formado poupa o semestre reduzido, e o custo "
        "por aluno é o valor informado. Nenhum desses efeitos foi medido nos dados.")
    st.markdown(
        "Ferramenta de **Análise Prescritiva** para apoiar o Decanato de Ensino de Graduação (DEG) e Coordenações de Curso: "
        "simule intervenções pedagógicas e fomento à permanência, projetando a redução da retenção, a economia pública em Reais (R$) e o potencial de novas bolsas."
    )

    # Seletor de Escopo: Curso Específico ou UnB Global
    escopo = st.radio(
        "Escopo da Simulação:",
        ["🏛️ Curso Específico",
            "🌐 Toda a Universidade de Brasília (Global)"],
        horizontal=True,
    )

    if escopo == "🏛️ Curso Específico":
        _opcoes_sim = list(df_gold["curso"].unique())
        # Abre no curso com mais planos de IC: sem IC, o controle de bolsas não muda nada e o cenário parece quebrado.
        _padrao_sim = df_gold.sort_values("pibic_total_projetos", ascending=False)["curso"].iloc[0]
        curso_sim = st.selectbox(
            "Selecione o Curso para Simulação:",
            options=_opcoes_sim,
            index=_opcoes_sim.index(_padrao_sim),
        )
        df_curr = df_gold[df_gold["curso"] == curso_sim].iloc[0]

        nome_curso = df_curr["curso"]
        total_discentes = int(df_curr["total_discentes_registrados"])
        total_formados = int(df_curr["total_formados"])
        taxa_evasao_atual = float(df_curr["taxa_evasao_pct"])
        desvio_medio_atual = float(df_curr["desvio_medio_semestres"]) if pd.notna(
            df_curr["desvio_medio_semestres"]) else 0.0
        sem_ideal = float(df_curr["semestre_ideal_previsto"])
        tempo_real_atual = float(df_curr["tempo_medio_real_semestres"]) if pd.notna(
            df_curr["tempo_medio_real_semestres"]) else sem_ideal
        pibic_projetos = int(df_curr.get("pibic_total_projetos", 0))
    else:
        nome_curso = "Toda a UnB (Graduação Consolidada)"
        total_discentes = int(df_gold["total_discentes_registrados"].sum())
        total_formados = int(df_gold["total_formados"].sum())
        desvio_medio_atual = float(global_meta.get(
            "desvio_medio_global_semestres", 2.1))
        tempo_real_atual = float(global_meta.get(
            "tempo_medio_formatura_global_semestres", 11.2))
        sem_ideal = max(4.0, tempo_real_atual - desvio_medio_atual)
        taxa_evasao_atual = float((df_gold["total_evadidos_desligados"].sum(
        ) / total_discentes * 100)) if total_discentes else 35.0
        pibic_projetos = int(df_gold.get(
            "pibic_total_projetos", pd.Series([0])).sum())

    st.markdown("---")

    # Painel de Parâmetros de Intervenção (What-If)
    col_ctrl1, col_ctrl2, col_ctrl3 = st.columns(3)
    with col_ctrl1:
        st.markdown("##### ⏱️ 1. Pré-requisitos & Oferta")
        sem_atraso = desvio_medio_atual <= 0
        max_slider = 0.5 if sem_atraso else float(
            max(0.5, round(desvio_medio_atual * 4) / 4))
        val_slider = 0.0 if sem_atraso else float(min(1.0, max_slider))
        # select_slider no lugar de slider: o rótulo do valor sai com vírgula decimal (o slider usa o ponto).
        reducao_semestres = st.select_slider(
            "Meta de redução no atraso de formatura (semestres):",
            options=[i * 0.25 for i in range(int(round(max_slider / 0.25)) + 1)],
            value=val_slider,
            format_func=lambda v: dec(v, 2),
            disabled=sem_atraso,
            help="Ações: flexibilização de cadeias de pré-requisitos, monitoria em disciplinas-filtro (Cálculo, APC) e turmas de verão.",
        )
        if sem_atraso:
            st.caption(
                "Este escopo já forma no tempo ideal ou antes (atraso médio zero ou negativo): não há atraso a reduzir.")
    with col_ctrl2:
        st.markdown("##### 🔬 2. Fomento ao PIBIC & Apoio")
        aumento_pibic_pct = st.slider(
            "Aumento na oferta de bolsas de IC / Permanência (%):",
            min_value=0,
            max_value=100,
            value=25,
            step=5,
            help=(f"Nos dados, a correlação entre projetos de IC por 100 alunos e evasão é r = {r_pibic_evasao_txt} "
                  f"({n_pibic_evasao} cursos)"
                  + (": mais IC acompanha menos evasão" if r_pibic_evasao is not None and r_pibic_evasao < 0 else "")
                  + ". Correlação não prova causa "
                  "(ver a aba PIBIC). O simulador supõe que cada 10% a mais de bolsas reduz a taxa de evasão do "
                  "curso em 2,5% do seu valor (fator fixo de 0,25)."),
        )
    with col_ctrl3:
        st.markdown("##### 💰 3. Custo Público por Aluno")
        custo_anual_aluno = st.number_input(
            "Custo médio anual por aluno (R$) [TCU / UnB]:",
            min_value=15000,
            max_value=70000,
            value=38500,
            step=2500,
            help="Valor médio de referência do TCU e Relatório de Gestão da UnB (~R$ 38.500/ano = R$ 19.250 por semestre por aluno).",
        )

    custo_semestral = custo_anual_aluno / 2.0

    # Modelagem Matemática Prescritiva (Análise Custo-Benefício de Políticas Públicas)
    # 1. Economia gerada pela redução de semestres excedentes (formatura ágil)
    # O tempo projetado nunca passa do atual nem fica abaixo do ideal da matriz.
    tempo_real_projetado = min(tempo_real_atual, max(
        sem_ideal, tempo_real_atual - reducao_semestres))
    reducao_efetiva = tempo_real_atual - tempo_real_projetado
    meta_limitada = reducao_semestres - reducao_efetiva > 0.005
    semestres_poupados_totais = total_formados * reducao_efetiva
    economia_retencao_reais = semestres_poupados_totais * custo_semestral

    # 2. Redução de evasão projetada: fator fixo de 0,25, uma hipótese do simulador. A correlação
    # observada (r_pibic_evasao) só indica o sentido da relação, não a magnitude do efeito.
    # Projetos de IC cobrem vários anos: bolsas novas por ano = projetos / anos da série. Sem projeto de IC
    # no escopo, o aumento percentual não tem base e não há efeito (nem custo) a simular.
    anos_serie_ic = max(
        1, len((pibic_meta or {}).get("evolucao_anual", [])))
    novas_bolsas_pibic = int(round(max(1, pibic_projetos) / anos_serie_ic * (
        aumento_pibic_pct / 100.0))) if pibic_projetos > 0 else 0
    fator_reducao_evasao = (aumento_pibic_pct / 100.0) * \
        0.25 if novas_bolsas_pibic > 0 else 0.0
    taxa_evasao_projetada = max(
        5.0, taxa_evasao_atual * (1.0 - fator_reducao_evasao))
    discentes_salvos = int(
        round(total_discentes * (taxa_evasao_atual - taxa_evasao_projetada) / 100.0))

    # 3. Retorno Econômico-Social por Evasão Evitada:
    # Cada aluno que deixa de evadir e se forma preserva o investimento público acumulado (~1 ano letivo médio evitado de desperdício)
    valor_evasao_evitada_reais = discentes_salvos * custo_anual_aluno

    # 4. Investimento Adicional em Novas Bolsas de Iniciação Científica: 12 meses do valor vigente no CNPq
    # O custo cobre os mesmos anos de ingresso do benefício (ingressantes de _COORTES), para somar janelas iguais.
    custo_ampliacao_pibic = float(
        novas_bolsas_pibic * 12 *
        (pibic_meta or {}).get("valor_bolsa_ic_mensal_vigente", 700.0)
        * _anos_do_intervalo(_COORTES))

    # 5. Benefício Público Total e Saldo Líquido
    beneficio_total_reais = economia_retencao_reais + valor_evasao_evitada_reais
    saldo_liquido = beneficio_total_reais - custo_ampliacao_pibic
    roi_social = (beneficio_total_reais /
                  custo_ampliacao_pibic) if custo_ampliacao_pibic > 0 else 1.0

    # Razão de dois dígitos passa falsa precisão para uma hipótese: acima de 10x só se diz "acima".
    roi_texto = ("Sem custo de novas bolsas neste cenário" if custo_ampliacao_pibic <= 0
                 else f"Benefício ÷ custo: {dec(roi_social, 1)}x (hipótese)" if roi_social < 10
                 else "Benefício ÷ custo: acima de 10x (hipótese)")

    st.markdown("---")
    st.markdown(f"#### 🎯 Resultados da Simulação para: **{nome_curso}**")
    if meta_limitada:
        st.info(f"A meta de {dec(reducao_semestres, 2)} semestre(s) passa do que o curso pode ganhar: o tempo projetado não fica abaixo do "
                f"prazo ideal da matriz ({dec(sem_ideal, 0)} sem.). Redução efetiva usada: {dec(reducao_efetiva, 2)}.")
    if novas_bolsas_pibic == 0 and aumento_pibic_pct > 0:
        st.info("Neste escopo não há projetos de IC suficientes para gerar bolsas novas: o aumento percentual não "
                "tem base, então o efeito sobre a evasão fica em zero.")

    # 4 Cards de Impacto de Gestão
    r1, r2, r3, r4 = st.columns(4)
    with r1:
        st.metric(
            label="Benefício Público Total",
            value=f"R$ {br(beneficio_total_reais, 2)}" if beneficio_total_reais < 1e6 else f"R$ {dec(beneficio_total_reais/1e6, 2)} Mi",
            delta=reducao(semestres_poupados_totais, 0, "semestres excedentes"),
            delta_color="normal",
            help="Soma do ganho por formatura ágil (menos semestres excedentes) e do capital público preservado ao evitar a evasão.",
        )
    with r2:
        st.metric(
            label="Evasões Evitadas (hipótese)",
            value=f"{br(discentes_salvos)} discentes",
            delta=reducao(taxa_evasao_atual - taxa_evasao_projetada, 1, "p.p. na taxa de evasão"),
            delta_color="normal",
            help="Quantidade estimada de estudantes que concluirão a graduação em vez de desistir/serem desligados.",
        )
    with r3:
        st.metric(
            label="Novo Tempo Médio Real",
            value=f"{dec(tempo_real_projetado, 2)} sem.",
            delta=reducao(reducao_efetiva, 2, "semestres"),
            delta_color="normal",
            help="Novo tempo médio estimado de integralização curricular.",
        )
    with r4:
        st.metric(
            label="Saldo Líquido Poupado",
            value=f"R$ {br(saldo_liquido, 2)}" if abs(
                saldo_liquido) < 1e6 else f"R$ {dec(saldo_liquido/1e6, 2)} Mi",
            delta=roi_texto,
            delta_color="normal" if saldo_liquido >= 0 else "inverse",
            help="Benefício público total subtraído do custo das novas bolsas concedidas.",
        )

    st.markdown("---")

    # Visualização Gráfica do Antes vs. Depois
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        st.markdown(
            "##### 📊 Comparativo: Cenário Atual vs. Cenário Projetado")
        df_comp = pd.DataFrame([
            {"Métrica": "Tempo de Formatura (Semestres)", "Cenário Atual": tempo_real_atual,
             "Cenário Projetado": tempo_real_projetado},
            {"Métrica": "Taxa de Evasão (%)", "Cenário Atual": taxa_evasao_atual,
             "Cenário Projetado": taxa_evasao_projetada},
        ])
        fig_comp = px.bar(
            df_comp.melt(id_vars="Métrica",
                         var_name="Cenário", value_name="Valor"),
            x="Métrica",
            y="Valor",
            color="Cenário",
            barmode="group",
            text_auto=".1f",
            height=380,
            color_discrete_map={
                "Cenário Atual": "#94A3B8", "Cenário Projetado": UNB_GREEN},
        )
        grafico(fig_comp, width="stretch")

    with col_v2:
        st.markdown("##### 💵 Balanço Custo-Benefício da Intervenção (R$)")
        df_waterfall = pd.DataFrame({
            "Componente": [
                "Economia (Atraso Evitado)",
                "Retorno (Evasão Evitada)",
                "Custo (Novas Bolsas)",
                "Saldo Líquido Real",
            ],
            "Valor (R$)": [
                economia_retencao_reais,
                valor_evasao_evitada_reais,
                -custo_ampliacao_pibic,
                saldo_liquido,
            ],
        })
        fig_waterfall = px.bar(
            df_waterfall,
            x="Componente",
            y="Valor (R$)",
            color="Valor (R$)",
            color_continuous_scale=["#DC2626", "#10B981"],
            text_auto=",.0f",
            height=380,
            title="Balanço Orçamentário e Retorno Social",
        )
        fig_waterfall.update_layout(coloraxis_showscale=False)
        grafico(fig_waterfall, width="stretch")

    # Caixa de Exportação de Dossiê Executivo para o Colegiado
    st.markdown("---")
    st.markdown(
        "##### 📄 Exportação de Dossiê Executivo do Cenário para o Colegiado / NDE")
    st.markdown(
        "Gere um memorando técnico estruturado para apoiar reuniões do Decanato ou do Núcleo Docente Estruturante do curso:")

    texto_dossie = f"""# MEMORANDO TÉCNICO DE GESTÃO ACADÊMICA — DEG / UnB
**Destinatário**: Coordenação de Curso e Núcleo Docente Estruturante (NDE)
**Objeto**: Simulação de Intervenção Pedagógica e Redução de Retenção — {nome_curso}
**Data de Emissão**: {pd.Timestamp.now().strftime('%d/%m/%Y')}
**Origem**: Observatório de Retenção e Formatura da UnB (Medalhão Dados Abertos)

---

### 1. Diagnóstico da Situação Atual
* **Alunos que ingressaram nas turmas de ingresso analisadas ({_COORTES})**: {br(total_discentes)}
* **Tempo Ideal Previsto na Matriz Curricular**: {dec(sem_ideal, 1)} semestres
* **Tempo Médio Real Observado na Formatura**: {dec(tempo_real_atual, 2)} semestres
* **Atraso Médio de Conclusão**: {dec(desvio_medio_atual, 2)} semestres além da matriz
* **Taxa de Evasão e Desligamento**: {dec(taxa_evasao_atual, 1)}%

### 2. Parâmetros da Simulação Aplicada
* **Meta de Redução de Atraso Médio**: {dec(reducao_semestres, 2)} semestres (via oferta de turmas de disciplinas-filtro, nivelamento e monitoria).
* **Expansão de Bolsas de Permanência / IC**: +{br(aumento_pibic_pct)}% ({br(novas_bolsas_pibic)} bolsas adicionais)
* **Custo Orçamentário Referência (TCU / UnB)**: R$ {br(custo_anual_aluno, 2)} / aluno-ano (R$ {br(custo_semestral, 2)}/semestre)

### 3. Impacto Estimado da Intervenção (Análise Custo-Benefício)
* **Economia por Formatura Ágil (Atraso Evitado)**: R$ {br(economia_retencao_reais, 2)} ({br(semestres_poupados_totais, 0)} semestres poupados)
* **Capital Público Preservado (Evasão Evitada)**: R$ {br(valor_evasao_evitada_reais, 2)} ({br(discentes_salvos)} discentes diplomados)
* **Benefício Público Total**: R$ {br(beneficio_total_reais, 2)}
* **Investimento em Novas Bolsas (+{br(aumento_pibic_pct)}%)**: R$ {br(custo_ampliacao_pibic, 2)}
* **Saldo Líquido aos Cofres Públicos**: R$ {br(saldo_liquido, 2)}
* **Benefício ÷ custo**: {roi_texto}
* **Novo Tempo Médio Real Projetado**: {dec(tempo_real_projetado, 2)} semestres

---
*Cenário hipotético, não é previsão: depende do fator fixo de 0,25 de redução de evasão por aumento de bolsas e do custo por aluno informado.*
*Documento gerado automaticamente pelo Observatório de Retenção e Formatura da UnB.*
"""
    st.download_button(
        label=f"📥 Baixar Dossiê Técnico ({nome_curso}) [.md]",
        data=texto_dossie,
        file_name=f"dossie_deg_{nome_curso.lower().replace(' ', '_')}.md",
        mime="text/markdown",
    )
