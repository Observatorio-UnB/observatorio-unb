"""Tela: 🛠️ Auditoria & Qualidade de Dados."""

import pandas as pd
import streamlit as st
from formatacao import br, dec, mostrar_tabela


def renderizar(g):
    """g: namespace com o que o app.py carregou (dados, metadados e helpers)."""
    DOCS_DIR = g.DOCS_DIR
    _COORTES = g._COORTES
    df_ativos = g.df_ativos
    df_gold = g.df_gold
    df_inep = g.df_inep
    join_meta = g.join_meta
    pibic_meta = g.pibic_meta
    regras_meta = g.regras_meta

    st.subheader("🛠️ Auditoria de Qualidade de Dados Abertos")
    st.markdown(
        "Verificação de integridade nas bases brutas do portal `dados.unb.br`.")

    _n_vinc = int(join_meta.get("total_discentes_graduacao", 0)) if join_meta else 0
    _n_ativos = int(df_ativos["total_ativos_hoje"].sum()) if df_ativos is not None and len(df_ativos) else 0
    _universos = pd.DataFrame([
        ("Vínculos de graduação lidos (SIGRA e SIGAA, todas as turmas)", _n_vinc, "base bruta; nenhuma tela mostra esse total"),
        (f"Ingressantes de {_COORTES} nos cursos do painel", int(df_gold["total_discentes_registrados"].sum()),
         "Visão Executiva, Detalhe, Turnos, Simulador"),
        ("Alunos ativos hoje (todas as turmas)", _n_ativos, "Alunos Ativos"),
        ("Planos de iniciação científica (2018-2023)", int(pibic_meta["total_projetos_ic"]) if pibic_meta else 0, "PIBIC"),
        ("Cursos da UnB comparados com o INEP (10+ federais)", int((df_inep["n_ies_comparadas"] >= 10).sum()) if df_inep is not None else 0, "Benchmark Nacional"),
    ], columns=["Universo", "Total", "Onde aparece"])
    st.markdown("#### 🗺️ De onde vem cada número do painel")
    st.caption("Cada tela usa um recorte diferente: os totais não são comparáveis entre telas.")
    mostrar_tabela(_universos, width="stretch", hide_index=True)

    st.markdown(
        "#### 📑 Relatório de Qualidade de Dados")
    st.caption(
        "Termos do relatório: **bronze, silver e gold** são as camadas do banco (dado bruto, dado limpo e dado "
        "pronto para o painel); **CKAN** é o sistema do portal dados.unb.br de onde vêm os arquivos; "
        "**alias mapping** é a tabela que liga o nome antigo de um curso ao nome atual; **k-anonimato** é a "
        "regra de não publicar grupos com menos de 5 pessoas; **p.p.** é ponto percentual.")

    relatorio_path = DOCS_DIR / "relatorio_qualidade.md"
    if relatorio_path.exists():
        texto_rel = relatorio_path.read_text(encoding="utf-8")
        # Resumo: ID, problema e decisão de cada achado, lidos da tabela da seção 1 do relatório.
        linhas_tab = [ln for ln in texto_rel.split(
            "## 2.")[0].splitlines() if ln.startswith("|")][2:]
        celulas = [[c.strip() for c in ln.strip().strip("|").split("|")]
                   for ln in linhas_tab]
        celulas = [c for c in celulas if len(c) >= 7]
        if celulas:
            st.caption(f"{len(celulas)} achados comprovados com evidência no portal dados.unb.br. "
                       "O detalhe de cada um está no relatório completo, logo abaixo.")
            mostrar_tabela(pd.DataFrame(
                [(c[0].replace("*", ""), c[4], c[6]) for c in celulas],
                columns=["Achado", "Problema detectado", "Decisão metodológica"]),
                width="stretch", hide_index=True)
        with st.expander("Ver o relatório completo (achados com evidência)"):
            st.markdown(texto_rel)
    else:
        st.info("Relatório de qualidade não encontrado.")

    st.markdown("---")
    with st.expander("🔧 Para a engenharia de dados: como os joins chegam a 100%", expanded=False):
        # Seção de Governança de Dados: Entity Resolution (Casamento 100%)
        st.subheader(
            "🔍 Governança de Dados: Como Alcançamos 100% de Casamento nos Joins?")
        st.markdown(
            """
                A integração entre o **SIGRA** (sistema acadêmico legado) e o **SIGAA** (sistema atual) com a tabela de **Estrutura Curricular** (matrizes ativas)
                exigiu **Entity Resolution (Harmonização Canônica)** para não descartar discentes de habilitações específicas.
                """
        )

        c_h1, c_h2, c_h3 = st.columns(3)
        with c_h1:
            st.metric("Taxa de Casamento Final", f"{dec(join_meta.get('taxa_de_casamento_pct', 100.0), 2)}%",
                      help=f"{br(join_meta.get('discentes_com_estrutura_casada', 0))} de {br(join_meta.get('total_discentes_graduacao', 0))} vínculos de graduação (SIGRA + SIGAA) casados com suas matrizes.".replace(",", "."))
        with c_h2:
            st.metric("Discentes Harmonizados", f"{br(join_meta.get('total_discentes_harmonizados', 0))}",
                      help="Discentes que tiveram nomes legados conciliados via regras de vocabulário controlado.")
        with c_h3:
            st.metric("Registros Descartados", f"{br(int(join_meta.get('discentes_sem_casamento', 0)))}",
                      help="Vínculos de graduação sem matriz curricular correspondente depois da harmonização "
                           "(total de vínculos menos os casados). Zero indica que nenhum foi descartado.")

        if regras_meta and "regras" in regras_meta:
            with st.container():
                st.markdown("**📋 Tabela auditável de resolução de entidades (regras canônicas de join)**")
                df_regras = pd.DataFrame(regras_meta["regras"])
                _sem_alunos = int(
                    (df_regras["discentes_impactados"] == 0).sum())
                df_regras = df_regras[df_regras["discentes_impactados"] > 0]
                if _sem_alunos:
                    st.caption(
                        f"{_sem_alunos} regras sem nenhum aluno impactado nesta carga ficam ocultas.")
                mostrar_tabela(
                    df_regras[[
                        "origem_sigra",
                        "destino_estrutura",
                        "categoria",
                        "discentes_impactados",
                        "justificativa",
                    ]].rename(columns={
                        "origem_sigra": "Nome na Origem (SIGRA, SIGAA ou PIBIC)",
                        "destino_estrutura": "Matriz Oficial Equivalente",
                        "categoria": "Tipo de Descompasso",
                        "discentes_impactados": "Discentes Conciliados",
                        "justificativa": "Justificativa Metodológica / Pedagógica",
                    }),
                    width="stretch",
                    height=320,
                )
