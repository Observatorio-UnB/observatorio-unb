"""Tela: ⚠️ O Que Este Dado NÃO Responde."""

import streamlit as st


def renderizar(g):
    """g: namespace com o que o app.py carregou (dados, metadados e helpers)."""
    global_meta = g.global_meta

    st.subheader("⚠️ O Que Este Dado NÃO Responde")
    st.markdown(
        r"""
            Para manter o rigor metodológico e científico na tomada de decisão do DEG:
            
            1. **Motivos Individuais de Evasão**: Os dados abertos não informam razões socioeconômicas, de saúde mental, incompatibilidade de horário de trabalho ou insatisfação com a carreira.
            2. **Semestre Exato de Ingresso**: SIGRA e SIGAA registram só o `ano_ingresso` (ex: `2010`), sem discriminar 1º ou 2º semestre, gerando uma incerteza metodológica de $\pm 1$ semestre.
            3. **Semestre de Conclusão no SIGAA**: O SIGAA não publica o período de saída; para quem se formou depois da migração (2020 em diante) ele é estimado pela data de registro do diploma, regra que acerta 94,6% no SIGRA mas pode errar em 1 semestre no calendário deslocado da pandemia. O SIGAA também não informa o motivo do cancelamento, por isso a evasão inclui mudança de curso.
            4. **Turmas Recentes**: As taxas usam só as turmas com pelo menos 8 anos de acompanhamento (hoje, ingresso TURMAS_ANALISADAS). Turmas mais novas ainda estão majoritariamente ativas e não permitem medir formatura nem evasão.
            5. **Histórico de Migração Curricular Individual**: Discentes que ingressaram em matrizes antigas e migraram para matrizes novas não têm os créditos convalidados discriminados no dataset estático.
            6. **Efeito Causal Direto**: Uma alta taxa de retenção reflete uma combinação de complexidade de conteúdo, rigidez na cadeia de pré-requisitos, insuficiência de oferta de vagas e perfil de dedicação do estudante.
            """.replace("TURMAS_ANALISADAS", str((global_meta or {}).get("turmas_ingresso_analisadas", "n/d")))
    )
