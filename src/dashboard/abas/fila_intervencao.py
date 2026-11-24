"""Tela: 📋 Fila de Intervenção (Coordenações).

O consumidor do ETL reverso (src/etl_reverso/fila_intervencao.py): a coordenação vê os cursos em
retenção crítica e registra o andamento. Lê e grava como coordenacao_academica
(src/etl_reverso/coordenacao.py): o banco, e não a tela, garante que só o andamento é gravado.
"""

import streamlit as st


def renderizar(g):
    """g: namespace com o que o app.py carregou (dados, metadados e helpers)."""
    st.subheader("📋 Fila de Intervenção: cursos em retenção crítica")
    st.markdown(
        "Cada curso em **RETENÇÃO CRÍTICA** entra nesta fila depois de cada carga mensal, com os mesmos "
        "números do ranking. A coordenação registra o **responsável**, o **plano de ação** e o **status**; o "
        "DEG acompanha os cursos ainda sem andamento e se os que tiveram plano saíram da fila nos ciclos seguintes."
    )
    try:
        from src.db.conexao import conectar
        from src.etl_reverso.coordenacao import STATUS, alteracoes, ler_fila, registrar_andamento
        with conectar(connect_timeout=3) as conn:
            fila = ler_fila(conn)
    except Exception as erro:  # GitHub Pages (sem banco) ou banco fora do ar
        st.info(
            "A fila vive no banco operacional (`operacional.fila_intervencao`) e só é aberta pelas "
            "coordenações, com o papel `coordenacao_academica`. Esta versão pública do painel não tem "
            f"acesso a ela. ({type(erro).__name__})"
        )
        return
    if fila.empty:
        st.warning("Fila vazia: rode `python3 src/etl_reverso/fila_intervencao.py` depois do dbt.")
        return

    na_fila = fila[fila["na_fila"]]
    k1, k2, k3 = st.columns(3)
    k1.metric("Cursos na fila", len(na_fila))
    k2.metric("Sem andamento (NOVO)", int((na_fila["status"] == "NOVO").sum()))
    k3.metric("Saíram da fila", int((~fila["na_fila"]).sum()))
    editada = st.data_editor(
        fila[["posicao", "nome_curso", "campus", "status", "responsavel", "plano_de_acao",
              "indice_retencao_critica", "taxa_evasao_pct", "atraso_medio_semestres",
              "entrou_na_fila_em", "na_fila"]],
        column_config={
            "status": st.column_config.SelectboxColumn("Status", options=list(STATUS), required=True),
            "responsavel": st.column_config.TextColumn("Responsável"),
            "plano_de_acao": st.column_config.TextColumn("Plano de ação", width="large"),
            "posicao": "Posição", "nome_curso": "Curso", "campus": "Campus",
            "indice_retencao_critica": "IRC", "taxa_evasao_pct": "Evasão (%)",
            "atraso_medio_semestres": "Atraso (sem.)", "entrou_na_fila_em": "Na fila desde",
            "na_fila": "Na fila",
        },
        disabled=["posicao", "nome_curso", "campus", "indice_retencao_critica", "taxa_evasao_pct",
                  "atraso_medio_semestres", "entrou_na_fila_em", "na_fila"],
        hide_index=True, width="stretch", key="fila_editor",
    )
    mudancas = alteracoes(fila, editada)
    if st.button(f"Salvar andamento ({len(mudancas)} curso(s) alterado(s))", disabled=not mudancas):
        try:
            with conectar(connect_timeout=3) as conn:
                for m in mudancas:
                    registrar_andamento(conn, m["nome_curso"], m["status"], m["responsavel"], m["plano_de_acao"])
            st.success(f"Andamento de {len(mudancas)} curso(s) registrado.")
        except Exception as erro:
            st.error(f"Não foi possível registrar: {erro}")
    st.caption(f"Definição das métricas: {fila['versao_metricas'].iloc[0]}. As métricas vêm do ETL "
               "reverso e não são editáveis aqui; o banco só deixa a coordenação gravar o andamento.")
