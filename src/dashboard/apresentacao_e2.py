"""
Apresentação da Entrega E2 (Ingestão em lote e captura de mudanças), no molde da apresentação
do ponto de controle da E1 (estilo LaTeX Beamer).
Disciplina: Banco de Dados 2 - Universidade de Brasília (UnB)
Acessível pelo parâmetro de URL ?ap2 ou ?apresentacao_e2.

As demonstrações ao vivo leem o lago local (data/lake/, gerado por src/db/exportar_lago.py e pelo
consumidor do CDC) e o banco configurado em src/db/conexao.py. Sem lago ou sem banco, o slide
mostra o erro e segue funcionando.
"""

import sys
import textwrap
import time
from pathlib import Path

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

LAGO_LOTE = BASE_DIR / "data" / "lake" / "lote"
LAGO_CDC = BASE_DIR / "data" / "lake" / "cdc"
VINCULOS_LOTE = LAGO_LOTE / "silver" / "movimentacoes_vinculos"
CURSOS_CDC = LAGO_CDC / "silver" / "cursos"

PARAMETROS = ("ap2", "apresentacao_e2")


def render_html(html_str: str):
    """Renderiza bloco HTML garantindo que a remoção de indentação previna interpretação como código Markdown."""
    st.markdown(textwrap.dedent(html_str).strip(), unsafe_allow_html=True)


def cabecalho(secao: str, n: int, total: int, titulo: str, subtitulo: str):
    render_html(
        f"""
        <div class="beamer-frame">
            <div class="beamer-header">
                <span>{secao}</span>
                <span>Slide {n} / {total}</span>
            </div>
            <div class="beamer-title">{titulo}</div>
            <div class="beamer-subtitle">{subtitulo}</div>
        </div>
        """
    )


def bloco(titulo: str, corpo: str, cor: str = ""):
    """Bloco Beamer; cor é '', 'green' ou 'amber'."""
    classe = f"beamer-block-header-{cor}" if cor else "beamer-block-header"
    render_html(
        f"""
        <div class="beamer-block">
            <div class="{classe}">{titulo}</div>
            <div class="beamer-block-body">{corpo}</div>
        </div>
        """
    )


def executar_query(sql: str, params=None):
    """Executa a consulta no PostgreSQL configurado e cronometra a latência."""
    from src.db.conexao import conectar

    inicio = time.perf_counter()
    try:
        with conectar() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                tempo_ms = (time.perf_counter() - inicio) * 1000
                if cur.description:
                    colunas = [d.name for d in cur.description]
                    return True, pd.DataFrame(cur.fetchall(), columns=colunas), tempo_ms, None
                return True, cur.rowcount, tempo_ms, None
    except Exception as exc:
        return False, None, (time.perf_counter() - inicio) * 1000, str(exc)


def mostrar_query(sql: str, rotulo: str, chave: str, se_vazio: str = "A consulta não devolveu linhas."):
    st.code(textwrap.dedent(sql).strip(), language="sql")
    if st.button(rotulo, key=chave):
        with st.spinner("Consultando o banco..."):
            ok, res, tempo, err = executar_query(sql)
        if ok:
            st.success(f"Consulta executada em **{tempo:.1f} ms**.")
            st.dataframe(res, width="stretch")
            if res.empty:
                st.info(se_vazio)
        else:
            st.error(f"Erro: {err}")


def _acoes(tabela):
    """Arquivos ativos de uma versão Delta (caminho, partição, tamanho, linhas)."""
    import pyarrow as pa

    return pa.table(tabela.get_add_actions(flatten=True)).to_pandas()


def historico_lote() -> pd.DataFrame:
    """Versões da tabela de vínculos do lago em lote, com as linhas de cada versão (pelo log)."""
    from deltalake import DeltaTable

    linhas = []
    for h in DeltaTable(str(VINCULOS_LOTE)).history(10):
        versao = h.get("version")
        parametros = h.get("operationParameters") or {}
        try:
            total = int(_acoes(DeltaTable(str(VINCULOS_LOTE), version=versao))["num_records"].sum())
        except Exception:
            total = None
        linhas.append({
            "versão": versao,
            "operação": f"{h.get('operation')} ({parametros.get('mode', '')})",
            "predicado": parametros.get("predicate", "— (tabela inteira)"),
            "linhas na versão": total,
        })
    return pd.DataFrame(linhas)


def _retrato_vinculos(rotulo: str) -> dict:
    """Versão, linhas, arquivos ativos e sha256 do conteúdo da tabela de vínculos do lago em lote."""
    import hashlib

    from deltalake import DeltaTable

    tabela = DeltaTable(str(VINCULOS_LOTE))
    dados = tabela.to_pyarrow_dataset().to_table(use_threads=False).sort_by("id_vinculo")
    return {
        "momento": rotulo,
        "versão Delta": tabela.version(),
        "linhas": dados.num_rows,
        "arquivos ativos": len(tabela.file_uris()),
        "sha256 do conteúdo": hashlib.sha256(dados.to_pandas().to_csv(index=False).encode()).hexdigest()[:12],
    }


def reexecutar_lote() -> tuple:
    """Roda o export dos vínculos duas vezes seguidas no lago real e, para contraste, grava a mesma
    tabela duas vezes em modo append numa pasta temporária. Devolve (retratos, linhas do append)."""
    import tempfile

    from deltalake import DeltaTable, write_deltalake

    from src.db import exportar_lago

    vinculos = next(t for t in exportar_lago.TABELAS if t.origem == "silver.movimentacoes_vinculos")
    retratos = [_retrato_vinculos("antes")]
    for n in (1, 2):
        exportar_lago.exportar(tabelas=[vinculos])
        retratos.append(_retrato_vinculos(f"depois da execução {n}"))

    colunas, linhas = exportar_lago.ler_do_banco(vinculos.origem)
    tabela = exportar_lago.montar_tabela_arrow(colunas, linhas, particionada=True)
    with tempfile.TemporaryDirectory() as tmp:
        for _ in range(2):
            write_deltalake(tmp, tabela, mode="append", partition_by=[exportar_lago.COLUNA_QUINQUENIO])
        linhas_append = DeltaTable(tmp).to_pyarrow_dataset().count_rows()
    return pd.DataFrame(retratos), linhas_append


def arquivos_lote() -> pd.DataFrame:
    """Arquivos da versão atual, lidos com o pyarrow.parquet (sem o Delta): codec e linhas pelo rodapé."""
    import pyarrow.parquet as pq
    from deltalake import DeltaTable

    acoes = _acoes(DeltaTable(str(VINCULOS_LOTE)))
    linhas = []
    for _, a in acoes.sort_values("path").iterrows():
        meta = pq.ParquetFile(VINCULOS_LOTE / a["path"]).metadata
        linhas.append({
            "partição": a["path"].split("/")[0],
            "tamanho (KB)": round(a["size_bytes"] / 1024),
            "linhas (rodapé do Parquet)": meta.num_rows,
            "row groups": meta.num_row_groups,
            "compressão": meta.row_group(0).column(0).compression,
        })
    return pd.DataFrame(linhas)


def estado_cdc() -> dict:
    """Estado do lago CDC de cursos: linhas, marcadas como excluídas e última posição no WAL."""
    import pyarrow.compute as pc
    from deltalake import DeltaTable

    tabela = DeltaTable(str(CURSOS_CDC))
    dados = tabela.to_pyarrow_dataset().to_table(columns=["_deletado", "_commit_lsn"], use_threads=False)
    return {
        "versão Delta": tabela.version(),
        "linhas no lago": dados.num_rows,
        "marcadas como excluídas (_deletado)": pc.sum(dados["_deletado"]).as_py() or 0,
        "maior _commit_lsn": pc.max(dados["_commit_lsn"]).as_py(),
    }


def impressao_digital_cdc():
    """sha256 do lago CDC inteiro, o mesmo de src/cdc/demonstrar_reprocessamento.py."""
    from src.cdc.consumidor import carregar_tabelas
    from src.cdc.demonstrar_reprocessamento import impressao_digital

    return impressao_digital(carregar_tabelas())


def kafka_no_ar() -> tuple:
    """(no ar?, endereço) do Kafka do CDC, por uma conexão TCP rápida."""
    import socket

    from src.db.conexao import ler_variavel

    endereco = (ler_variavel("KAFKA_BOOTSTRAP_SERVERS") or "localhost:9092").split(",")[0]
    host, _, porta = endereco.rpartition(":")
    try:
        with socket.create_connection((host or "localhost", int(porta)), timeout=2):
            return True, endereco
    except OSError:
        return False, endereco


def rodar_demonstracao_reprocessamento(saida) -> int:
    """Roda src/cdc/demonstrar_reprocessamento.py num processo à parte, mostrando a saída em `saida`
    (um st.empty) enquanto ela chega. Devolve o código de saída do script.

    Processo à parte porque o script encerra com sys.exit e cria consumidores do Kafka próprios.
    """
    import subprocess

    linhas = []
    processo = subprocess.Popen(
        [sys.executable, "-u", str(BASE_DIR / "src" / "cdc" / "demonstrar_reprocessamento.py")],
        cwd=BASE_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    for linha in processo.stdout:
        linhas.append(linha.rstrip("\n"))
        saida.code("\n".join(linhas[-40:]), language="text")
    return processo.wait()


def voltar_ao_painel():
    for p in PARAMETROS:
        if p in st.query_params:
            del st.query_params[p]
    st.rerun()


def render_apresentacao():
    # Mesmo estilo da apresentação da E1 (Tema Madrid / UnB Corporate)
    st.html(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Latin+Modern+Roman:ital,wght@0,400;0,700;1,400&family=Source+Sans+3:wght@400;600;700&display=swap');

        .beamer-frame {
            background-color: #ffffff;
            color: #1e293b;
            border-radius: 6px;
            padding: 1.8rem 2.2rem;
            margin-bottom: 1.5rem;
            border: 1px solid #cbd5e1;
            box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08);
            font-family: 'Source Sans 3', sans-serif;
        }
        .beamer-header {
            font-size: 0.8rem;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-weight: 700;
            border-bottom: 2px solid #133E79;
            padding-bottom: 4px;
            margin-bottom: 1.2rem;
            display: flex;
            justify-content: space-between;
        }
        .beamer-title {
            font-size: 1.85rem;
            font-weight: 700;
            color: #133E79;
            font-family: 'Georgia', 'Latin Modern Roman', serif;
            margin-bottom: 0.3rem;
            line-height: 1.25;
        }
        .beamer-subtitle {
            font-size: 1.05rem;
            color: #475569;
            margin-bottom: 1.4rem;
            font-style: italic;
        }
        .beamer-block {
            border: 1px solid #cbd5e1;
            border-radius: 5px;
            margin-bottom: 1.1rem;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.04);
        }
        .beamer-block-header {
            background-color: #133E79;
            color: #ffffff;
            padding: 7px 14px;
            font-weight: 700;
            font-size: 0.92rem;
            letter-spacing: 0.02em;
        }
        .beamer-block-header-green {
            background-color: #008940;
            color: #ffffff;
            padding: 7px 14px;
            font-weight: 700;
            font-size: 0.92rem;
        }
        .beamer-block-header-amber {
            background-color: #b45309;
            color: #ffffff;
            padding: 7px 14px;
            font-weight: 700;
            font-size: 0.92rem;
        }
        .beamer-block-body {
            background-color: #f8fafc;
            padding: 12px 16px;
            font-size: 0.92rem;
            color: #334155;
            line-height: 1.55;
        }
        .beamer-block-body table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.88rem;
        }
        .beamer-block-body th, .beamer-block-body td {
            border-bottom: 1px solid #e2e8f0;
            padding: 4px 8px;
            text-align: left;
        }
        .beamer-block-body th {
            color: #133E79;
        }
        .beamer-destaque {
            background-color: #ecfdf5;
            font-weight: 700;
        }
        .beamer-footer {
            margin-top: 1.5rem;
            padding-top: 6px;
            border-top: 1px solid #e2e8f0;
            font-size: 0.78rem;
            color: #94a3b8;
            display: flex;
            justify-content: space-between;
        }
        </style>
        """
    )

    SLIDES = [
        "1. Capa & Identificação Acadêmica",
        "2. Dois caminhos até o lago",
        "3. Caminho em lote: idempotente e reexecutável",
        "4. Camada analítica em formato aberto (Delta sobre Parquet)",
        "5. Serialização e compressão pelo padrão de acesso",
        "6. Caminho de mudanças: CDC pelo WAL com Debezium",
        "7. Semântica de entrega demonstrada",
        "8. Dado atrasado e reprocessamento de janela",
        "9. ADR 0025: CDC contra a opção nula, com números",
        "10. Como cada caminho falhou",
        "11. Checklist de aceite e conclusão",
    ]

    if "slide_idx_e2" not in st.session_state:
        st.session_state.slide_idx_e2 = 0

    col_nav1, col_nav2, col_nav3, col_nav4 = st.columns([1.5, 5, 1.5, 2.5])
    with col_nav1:
        if st.button("Anterior", width="stretch", disabled=st.session_state.slide_idx_e2 == 0):
            st.session_state.slide_idx_e2 -= 1
            st.rerun()
    with col_nav2:
        selecionado = st.selectbox(
            "Slide Atual",
            options=range(len(SLIDES)),
            format_func=lambda i: SLIDES[i],
            index=st.session_state.slide_idx_e2,
            label_visibility="collapsed",
        )
        if selecionado != st.session_state.slide_idx_e2:
            st.session_state.slide_idx_e2 = selecionado
            st.rerun()
    with col_nav3:
        if st.button("Próximo", width="stretch",
                     disabled=st.session_state.slide_idx_e2 == len(SLIDES) - 1):
            st.session_state.slide_idx_e2 += 1
            st.rerun()
    with col_nav4:
        if st.button("Ir para o Dashboard", width="stretch"):
            voltar_ao_painel()

    st.markdown("---")
    idx = st.session_state.slide_idx_e2
    total = len(SLIDES)

    # =========================================================================
    # SLIDE 1: CAPA
    # =========================================================================
    if idx == 0:
        render_html(
            f"""
            <div class="beamer-frame">
                <div class="beamer-header">
                    <span>Universidade de Brasília (UnB) · Faculdade UnB Gama (FGA)</span>
                    <span>Engenharia de Software · Banco de Dados 2</span>
                </div>
                <div style="text-align: center; padding: 2.2rem 1rem;">
                    <div style="font-size: 1.05rem; color: #008940; font-weight: 700; letter-spacing: 0.05em; margin-bottom: 0.6rem;">
                        ENTREGA E2 · INGESTÃO EM LOTE E CAPTURA DE MUDANÇAS
                    </div>
                    <div class="beamer-title" style="font-size: 2.2rem; margin-bottom: 0.8rem;">
                        Observatório UnB: do OLTP ao lago em formato aberto, por dois caminhos
                    </div>
                    <div class="beamer-subtitle" style="font-size: 1.1rem; color: #475569; margin-bottom: 2rem;">
                        Recarga periódica idempotente, CDC com Debezium, Delta Lake sobre Parquet e dado atrasado tratado pela marca d'água
                    </div>
                    <div style="background: #f1f5f9; padding: 1.1rem 1.4rem; border-radius: 6px; display: inline-block; text-align: left; font-size: 0.95rem; border-left: 4px solid #133E79; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
                        <strong>Curso:</strong> Engenharia de Software (FGA / UnB)<br>
                        <strong>Docente:</strong> Profa. Dra. Carla Rocha<br>
                        <strong>Disciplina:</strong> Banco de Dados 2<br>
                        <strong>Equipe:</strong> Squad Observatório UnB<br>
                        <strong>Ambiente:</strong> PostgreSQL 16, Kafka 3.7 (KRaft), Debezium 2.7 e delta-rs no <code>docker-compose.yml</code>
                    </div>
                </div>
                <div class="beamer-footer">
                    <span>Observatório UnB · Entrega E2</span>
                    <span>Slide 1 / {total}</span>
                </div>
            </div>
            """
        )

    # =========================================================================
    # SLIDE 2: DOIS CAMINHOS
    # =========================================================================
    elif idx == 1:
        cabecalho("Seção 1 · Visão Geral", 2, total, "Dois caminhos até o lago, de natureza diferente",
                  "Fazer os dois é o ponto: eles falham de maneiras distintas, e nós vimos as duas falhas")
        c1, c2 = st.columns(2)
        with c1:
            bloco("Caminho em lote (recarga periódica)",
                  "Fonte pública (API CKAN da UnB e Censo do INEP) &rarr; bronze &rarr; silver &rarr; "
                  "<strong>Silver 3NF</strong> e Star Schema no PostgreSQL &rarr; <code>src/db/exportar_lago.py</code> "
                  "&rarr; <code>data/lake/lote/</code>.<br>"
                  "• Roda uma vez por mês (<code>atualiza-dados.yml</code>, dia 1, 06:00 UTC).<br>"
                  "• É o <strong>mecanismo principal</strong> (ADR 0025).")
        with c2:
            bloco("Caminho de mudanças (CDC)",
                  "WAL do PostgreSQL (decodificação lógica, <code>pgoutput</code>, publicação "
                  "<code>observatorio_cdc</code>) &rarr; Debezium &rarr; Kafka &rarr; "
                  "<code>src/cdc/consumidor.py</code> &rarr; <code>data/lake/cdc/</code>.<br>"
                  "• Profile <code>cdc</code> do compose, fora do pipeline e do CI.<br>"
                  "• É o <strong>caminho opcional</strong> (ADR 0025).", "green")
        bloco("O OLTP é a Silver 3NF da E1",
              "<code>silver.cursos</code>, <code>silver.estruturas_curriculares</code> e "
              "<code>silver.movimentacoes_vinculos</code>: modelo transacional normalizado, com chaves primárias, "
              "chaves estrangeiras e partições. <code>silver.discentes</code> fica fora dos dois caminhos, porque "
              "guarda nascimento, sexo e raça/cor por pessoa.", "amber")

    # =========================================================================
    # SLIDE 3: LOTE IDEMPOTENTE
    # =========================================================================
    elif idx == 2:
        cabecalho("Seção 2 · Caminho em Lote", 3, total, "Ingestão em lote idempotente e reexecutável",
                  "Rodar duas vezes dá as mesmas linhas: substituição numa transação, e não acréscimo")
        c1, c2 = st.columns(2)
        with c1:
            bloco("No banco",
                  "• <code>TRUNCATE</code> + <code>COPY</code> numa transação só (<code>tabelas.gravar_varias</code>).<br>"
                  "• Uma falha no meio não deixa a tabela pela metade: a transação volta inteira.<br>"
                  "• Procedência de cada arquivo em <code>bronze.ingestoes</code> (hash, encoding, linhas e linhas descartadas).")
        with c2:
            bloco("No lago",
                  "• Cada exportação é um <code>overwrite</code> numa versão nova do log do Delta.<br>"
                  "• <code>--quinquenio 2020</code> regrava só aquela janela (overwrite com predicado).<br>"
                  "• Testado em <code>tests/test_unit_lago.py</code>: regravar dá as mesmas linhas e o mesmo número de arquivos ativos.",
                  "green")

        st.markdown("#### Demonstração: o histórico do lago depois de várias execuções")
        st.markdown("Cada linha é uma execução do export. O número de linhas não cresce entre as versões: "
                    "rodar de novo substitui, não duplica.")
        if st.button("Ler o histórico do Delta de movimentacoes_vinculos", key="hist_lote"):
            try:
                st.dataframe(historico_lote(), width="stretch", hide_index=True)
            except Exception as exc:
                st.error(f"Lago em lote indisponível ({exc}). Gere com: python3 src/db/exportar_lago.py")

        st.markdown("#### Demonstração ao vivo: reexecutar o export agora, duas vezes")
        st.markdown("Roda `exportar_lago.py` para `silver.movimentacoes_vinculos` duas vezes seguidas no lago real. "
                    "A versão do Delta sobe, e as linhas, os arquivos ativos e o conteúdo ficam iguais. "
                    "Para contraste, a mesma tabela é gravada duas vezes em modo *append* numa pasta temporária.")
        if st.button("Reexecutar o export dos vínculos duas vezes", key="reexecutar_lote"):
            try:
                with st.spinner("Lendo o banco e regravando o lago duas vezes..."):
                    retratos, linhas_append = reexecutar_lote()
                st.dataframe(retratos, width="stretch", hide_index=True)
                depois = retratos.iloc[1:]
                iguais = depois[["linhas", "arquivos ativos", "sha256 do conteúdo"]].nunique().eq(1).all()
                linhas = f"{retratos['linhas'].iloc[-1]:,}".replace(",", ".")
                if iguais:
                    st.success(f"Duas execuções, duas versões novas, e o mesmo resultado: **{linhas}** linhas, "
                               "mesmos arquivos ativos e mesmo conteúdo. Idempotente.")
                else:
                    st.warning("As duas execuções deram resultados diferentes: confira a tabela acima.")
                dobro = f"{linhas_append:,}".replace(",", ".")
                st.error(f"Contraste: em modo append, a mesma tabela gravada duas vezes dá **{dobro}** linhas, o dobro.")
            except Exception as exc:
                st.error(f"Não foi possível reexecutar ({exc}). É preciso o banco no ar com a Silver 3NF carregada.")

    # =========================================================================
    # SLIDE 4: FORMATO ABERTO
    # =========================================================================
    elif idx == 3:
        cabecalho("Seção 3 · Armazenamento Analítico", 4, total, "Delta Lake sobre Parquet: o dado não fica refém do motor",
                  "Iceberg ou Delta? Escolha com critério explícito (ADR 0024)")
        c1, c2 = st.columns(2)
        with c1:
            bloco("Por que Delta, e não Iceberg",
                  "• <strong>Escrita sem JVM nem catálogo:</strong> o <code>deltalake</code> (delta-rs) grava de Python, "
                  "com o log na própria pasta. O <code>pyiceberg</code> exige um catálogo (REST, SQL ou Glue), mais um serviço no compose.<br>"
                  "• <strong>Overwrite com predicado:</strong> troca só as partições de uma janela numa transação.<br>"
                  "• <strong>Leitura:</strong> DuckDB, Spark, Polars e pandas leem Delta; os arquivos são Parquet comum.")
        with c2:
            bloco("O que se perde, e o particionamento",
                  "• A evolução de esquema do Iceberg é mais rica (renomear e reordenar por id de campo). Aqui o esquema "
                  "vem das migrações do PostgreSQL, e a mudança é rara e deliberada.<br>"
                  "• <strong>Partição por quinquênio de ingresso</strong>, o filtro mais comum: um arquivo de 370 a 560 KB por partição.<br>"
                  "• Por ano seriam arquivos de uns 100 KB: <strong>arquivos pequenos</strong>, cada um com rodapé e abertura próprios na leitura.",
                  "amber")

        st.markdown("#### Demonstração: os arquivos da versão atual, abertos sem o Delta")
        st.markdown("O log do Delta diz quais arquivos valem. Cada um é aberto aqui com o `pyarrow.parquet`, "
                    "que não sabe nada de Delta: linhas e codec saem do rodapé do Parquet.")
        if st.button("Abrir os arquivos Parquet do lago em lote", key="arquivos_lote"):
            try:
                arquivos = arquivos_lote()
                st.dataframe(arquivos, width="stretch", hide_index=True)
                vinculos = f"{arquivos['linhas (rodapé do Parquet)'].sum():,}".replace(",", ".")
                st.info(f"**{vinculos}** vínculos em **{len(arquivos)}** arquivos, um por quinquênio.")
            except Exception as exc:
                st.error(f"Lago em lote indisponível ({exc}). Gere com: python3 src/db/exportar_lago.py")
        st.code("""INSTALL delta; LOAD delta;
SELECT quinquenio_ingresso, tipo_saida_grupo, count(*)
FROM delta_scan('data/lake/lote/silver/movimentacoes_vinculos')
GROUP BY ALL ORDER BY ALL;""", language="sql")
        st.caption("A mesma tabela lida pelo DuckDB, outro motor (README, seção do lago).")

    # =========================================================================
    # SLIDE 5: COMPRESSÃO
    # =========================================================================
    elif idx == 4:
        cabecalho("Seção 4 · Serialização e Compressão", 5, total, "ZSTD 3, medido no padrão de acesso, e não o padrão da ferramenta",
                  "152.680 vínculos num Parquet; leitura = mediana de 15 execuções de uma agregação de evasão por curso e quinquênio no DuckDB")
        bloco("Medição (ADR 0024)",
              """
              <table>
                <tr><th>Compressão</th><th>Tamanho</th><th>Escrita</th><th>Leitura</th></tr>
                <tr><td>Nenhuma</td><td>3.319 KB</td><td>62 ms</td><td>17 ms</td></tr>
                <tr><td>Snappy (padrão do pyarrow)</td><td>2.222 KB</td><td>66 ms</td><td>22 ms</td></tr>
                <tr><td>GZIP</td><td>1.462 KB</td><td>3.527 ms</td><td>19 ms</td></tr>
                <tr><td>ZSTD 1</td><td>1.439 KB</td><td>60 ms</td><td>22 ms</td></tr>
                <tr class="beamer-destaque"><td>ZSTD 3 (escolhido)</td><td>1.434 KB</td><td>173 ms</td><td>25 ms</td></tr>
                <tr><td>ZSTD 9</td><td>1.364 KB</td><td>192 ms</td><td>18 ms</td></tr>
              </table>
              """)
        c1, c2 = st.columns(2)
        with c1:
            bloco("O padrão de acesso decide",
                  "• Leitura: varreduras de colunas inteiras agregadas por curso e coorte.<br>"
                  "• Escrita: uma vez por mês. O custo de escrita não pesa.<br>"
                  "• A diferença de leitura entre os codecs (17 a 25 ms) fica dentro do ruído da medição.", "green")
        with c2:
            bloco("Conclusão",
                  "• ZSTD ocupa <strong>35% menos que o Snappy</strong>, o padrão da ferramenta.<br>"
                  "• GZIP comprime parecido, mas escreve <strong>20 vezes mais devagar</strong>.<br>"
                  "• Para comparação, a mesma tabela ocupa 15 MB no PostgreSQL.", "amber")

    # =========================================================================
    # SLIDE 6: CDC
    # =========================================================================
    elif idx == 5:
        cabecalho("Seção 5 · Captura de Mudanças", 6, total, "CDC por decodificação lógica do WAL, com Debezium",
                  "Um CDC que viu mudança de verdade: um script altera linhas no OLTP e mede o efeito no lago")
        c1, c2 = st.columns(2)
        with c1:
            bloco("Como o evento vira linha no lago",
                  "• Publicação <code>observatorio_cdc</code> (migração 0020): INSERT, UPDATE, DELETE e TRUNCATE das três tabelas.<br>"
                  "• O consumidor aplica cada lote por <code>MERGE</code> na tabela Delta, pela posição no WAL "
                  "(<code>_commit_lsn</code>, <code>_lsn</code>).<br>"
                  "• DELETE vira marca (<code>_deletado = true</code>), para que um INSERT antigo reprocessado não ressuscite a linha.")
        with c2:
            bloco("src/cdc/demonstrar.py (INSERT, UPDATE e DELETE de um curso sentinela)",
                  """
                  <table>
                    <tr><th>Passo</th><th>Latência até o lago</th><th>Estado no lago</th></tr>
                    <tr><td>INSERT</td><td>0,87 s</td><td>turno DIURNO, ativo</td></tr>
                    <tr><td>UPDATE</td><td>0,44 s</td><td>turno NOTURNO</td></tr>
                    <tr><td>DELETE</td><td>0,64 s</td><td><code>_deletado = true</code></td></tr>
                  </table>
                  No fim, o banco volta ao estado de antes.
                  """, "green")

        st.markdown("#### Demonstração: a publicação e o slot de replicação no banco")
        mostrar_query(
            """
            SELECT p.pubname, p.schemaname, p.tablename, s.slot_name, s.plugin, s.active,
                   pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), s.confirmed_flush_lsn)) AS wal_retido
            FROM pg_publication_tables p
            LEFT JOIN pg_replication_slots s ON s.slot_type = 'logical'
            WHERE p.pubname = 'observatorio_cdc';
            """,
            "Consultar a publicação e o slot", "pub_cdc",
        )
        st.markdown("#### Demonstração: o estado do lago CDC de cursos")
        if st.button("Ler o lago CDC de silver.cursos", key="lago_cdc"):
            try:
                st.json(estado_cdc())
            except Exception as exc:
                st.error(f"Lago CDC indisponível ({exc}). Suba o profile cdc e rode src/cdc/consumidor.py.")

    # =========================================================================
    # SLIDE 7: SEMÂNTICA DE ENTREGA
    # =========================================================================
    elif idx == 6:
        cabecalho("Seção 6 · Semântica de Entrega", 7, total,
                  "No mínimo uma vez no transporte, exatamente uma vez no efeito",
                  "Demonstrado, não afirmado: src/cdc/demonstrar_reprocessamento.py força três reprocessamentos")
        c1, c2 = st.columns(2)
        with c1:
            bloco("Por que no mínimo uma vez",
                  "O offset só é confirmado no Kafka <strong>depois</strong> da gravação no lago. Se o consumidor cair "
                  "entre as duas, o lote volta.<br>"
                  "Confirmar antes de gravar daria <em>no máximo uma vez</em>: a queda perderia o lote em silêncio.")
        with c2:
            bloco("Por que exatamente uma vez no efeito",
                  "O <code>MERGE</code> só aplica um evento <strong>mais novo</strong>, pela posição no WAL, que a linha do lago. "
                  "Não há transação entre o Kafka e o Delta: o exatamente-uma-vez de ponta a ponta vem da idempotência do MERGE.",
                  "green")
        bloco("Os três reprocessamentos forçados (README)",
              """
              <table>
                <tr><th>Cenário</th><th>Mensagens lidas</th><th>Linhas no lago</th><th>Sentinelas vivos</th><th>Impressão digital</th></tr>
                <tr><td>estado inicial (tópicos esvaziados)</td><td>0</td><td>153.001</td><td>0</td><td><code>c44e70a2ae08</code></td></tr>
                <tr><td>lote gravado, queda antes de confirmar</td><td>100</td><td>153.001</td><td>50</td><td><code>8ced07c73c2c</code></td></tr>
                <tr class="beamer-destaque"><td>retomada: o lote é entregue de novo</td><td>100</td><td>153.001</td><td>50</td><td><code>8ced07c73c2c</code></td></tr>
                <tr class="beamer-destaque"><td>reprocessamento do primeiro offset</td><td>766.353</td><td>153.001</td><td>50</td><td><code>8ced07c73c2c</code></td></tr>
                <tr><td>sentinelas excluídos do banco</td><td>50</td><td>153.001</td><td>0</td><td><code>0954a3c5f0fb</code></td></tr>
                <tr class="beamer-destaque"><td>reprocessamento depois da exclusão</td><td>766.403</td><td>153.001</td><td>0</td><td><code>0954a3c5f0fb</code></td></tr>
              </table>
              A impressão digital é o sha256 de todas as linhas, inclusive a hora de gravação (<code>_gravado_em</code>):
              a entrega repetida não regrava nem uma linha, e nenhum sentinela excluído ressuscita.
              """, "amber")
        st.markdown("#### Demonstração: a impressão digital do lago CDC agora")
        st.markdown("Calcule antes e depois de rodar `python3 src/cdc/consumidor.py --do-inicio`: o valor não muda.")
        if st.button("Calcular o sha256 do lago CDC", key="digest_cdc"):
            try:
                with st.spinner("Lendo o lago CDC inteiro..."):
                    digest, linhas = impressao_digital_cdc()
                st.success(f"Impressão digital **{digest}** sobre **{linhas:,}** linhas.".replace(",", "."))
            except Exception as exc:
                st.error(f"Não foi possível calcular ({exc}). É preciso o banco no ar e o lago CDC gerado.")

        st.markdown("#### Demonstração ao vivo: forçar os três reprocessamentos agora")
        st.markdown("Roda `src/cdc/demonstrar_reprocessamento.py`: insere e altera 50 cursos sentinela no OLTP, "
                    "derruba o consumidor antes de confirmar o offset, relê os tópicos do primeiro offset, exclui os "
                    "sentinelas e relê tudo de novo. No fim, os sentinelas saem do banco. Precisa do profile `cdc` "
                    "no ar e do conector registrado. Leva de um a alguns minutos, porque relê os tópicos inteiros.")
        if st.button("Forçar os reprocessamentos do CDC agora", key="reprocessar_cdc"):
            no_ar, endereco = kafka_no_ar()
            if not no_ar:
                st.error(f"Kafka fora do ar em {endereco}. Suba com `docker compose --profile cdc up -d db kafka connect` "
                         "e `bash scripts/cdc.sh registrar`.")
            else:
                saida = st.empty()
                with st.spinner("Reprocessando os tópicos do CDC..."):
                    codigo = rodar_demonstracao_reprocessamento(saida)
                if codigo == 0:
                    st.success("O lago ficou idêntico depois da queda, da retomada e dos dois reprocessamentos: "
                               "no mínimo uma vez no transporte, exatamente uma vez no efeito.")
                else:
                    st.error(f"A demonstração falhou (código {codigo}). A saída acima diz em que passo.")

    # =========================================================================
    # SLIDE 8: DADO ATRASADO
    # =========================================================================
    elif idx == 7:
        cabecalho("Seção 7 · Dado Atrasado", 8, total, "Dado atrasado aceito e registrado pela marca d'água",
                  "Uma formatura só entra no arquivo quando o diploma é registrado: o semestre continua recebendo vínculos depois de terminar")
        c1, c2 = st.columns(2)
        with c1:
            bloco("Atraso medido no SIGRA (25.485 formados, ADR 0026)",
                  """
                  <table>
                    <tr><th>Mediana</th><th>p90</th><th>p95</th><th>p99</th><th>Mais de 4 meses</th></tr>
                    <tr><td>&minus;13 dias</td><td>19</td><td>40</td><td>105</td><td>0,8%</td></tr>
                  </table>
                  Dias do fim do semestre até o registro do diploma.
                  """)
            bloco("Marca d'água com 4 meses de tolerância",
                  "Último período cujo fim, somado a 4 meses, não passa da publicação do arquivo. Cobre o p99. "
                  "Cada carga grava a marca e um retrato das contagens (<code>silver.cargas_vinculos</code> e "
                  "<code>silver.cargas_vinculos_retrato</code>).", "green")
        with c2:
            bloco("O que escolhemos fazer com ele",
                  "• A view <code>silver.chegadas_por_carga</code> classifica cada diferença entre cargas: "
                  "<code>NO_PRAZO</code>, <code>ATRASADA</code> ou <code>SEM_PERIODO</code>, e marca a mudança em coorte já publicada.<br>"
                  "• <strong>Aceito, e não descartado:</strong> a fonte é a referência. Descartar deixaria a gold divergindo do portal para sempre.<br>"
                  "• <strong>Reprocessamento de janela:</strong> <code>exportar_lago.py --janelas-alteradas</code> regrava só os quinquênios que mudaram.",
                  "amber")
            bloco("Demonstração (src/db/demonstrar_dado_atrasado.py)",
                  """
                  <table>
                    <tr><th>Publicação</th><th>Chegada</th><th>Lago</th></tr>
                    <tr><td>No prazo (coorte 2019)</td><td><code>NO_PRAZO</code> +20</td><td>só a janela 2015</td></tr>
                    <tr><td>Atrasada (coorte 2012)</td><td><code>ATRASADA</code> +20, coorte publicada; 14 cursos revisados na gold</td><td>só a janela 2010</td></tr>
                  </table>
                  """)
        st.markdown("#### Demonstração: as cargas registradas e o que chegou em cada uma")
        mostrar_query(
            """
            SELECT c.id_carga, c.publicada_em, c.marca_dagua, c.total_vinculos,
                   x.chegada, sum(x.diferenca) AS saldo, bool_or(x.coorte_publicada) AS revisa_coorte_publicada
            FROM silver.cargas_vinculos c
            LEFT JOIN silver.chegadas_por_carga x USING (id_carga)
            GROUP BY c.id_carga, c.publicada_em, c.marca_dagua, c.total_vinculos, x.chegada
            ORDER BY c.id_carga DESC, x.chegada
            LIMIT 12;
            """,
            "Consultar as cargas e as chegadas", "cargas",
            se_vazio="Nenhuma carga registrada neste banco. A carga da Silver 3NF registra uma "
                     "(python3 src/db/povoar_silver_3nf.py); a comparação aparece a partir da segunda.",
        )

    # =========================================================================
    # SLIDE 9: ADR 0025
    # =========================================================================
    elif idx == 8:
        cabecalho("Seção 8 · A Decisão da Entrega", 9, total, "ADR 0025: recarga periódica como mecanismo principal",
                  "A opção nula medida contra o CDC, no mesmo ambiente (152.680 vínculos, 158 cursos, 112 matrizes)")
        bloco("Medições",
              """
              <table>
                <tr><th></th><th>Recarga agendada: <code>INSERT ... SELECT</code> e export (opção nula)</th><th>CDC</th></tr>
                <tr><td>Latência de uma mudança até o lago</td><td>até 1 mês (agendamento) + 0,9 s de export</td><td>0,25 a 0,87 s</td></tr>
                <tr><td>Recarga inteira da Silver 3NF</td><td>export completo em 0,9 s</td><td>152.953 eventos; lago em dia 6,6 s depois</td></tr>
                <tr><td>Serviços a mais</td><td>nenhum</td><td>Kafka e Connect: 1,9 GB de RAM</td></tr>
                <tr><td>Disco a mais</td><td>lago em lote: 5 MB</td><td>tópicos: 378 MB depois de 3 cargas</td></tr>
                <tr><td>Risco no banco</td><td>nenhum</td><td>slot segurando WAL (até 239 MB depois de uma recarga)</td></tr>
                <tr><td>Operação</td><td>um cron que já existe</td><td>conector, slot e compactação de arquivos pequenos</td></tr>
              </table>
              """)
        c1, c2 = st.columns(2)
        with c1:
            bloco("Decisão",
                  "• A opção nula é não ter CDC: a carga mensal já recarrega a Silver 3NF por "
                  "<code>TRUNCATE</code> + <code>INSERT ... SELECT</code>, e o export leva o resultado ao lago.<br>"
                  "• A fonte muda <strong>uma vez por mês</strong>: chegar ao lago em 0,5 s não adianta.<br>"
                  "• O mês vem do agendamento, não do mecanismo: um cron de hora em hora custaria praticamente o mesmo, "
                  "ainda sem Kafka nem slot.<br>"
                  "• O CDC fica opcional, para escrita fora do pipeline (uma correção manual de curso, por exemplo).",
                  "green")
        with c2:
            bloco("Quando a conta muda",
                  "Se o OLTP passar a receber escrita contínua fora do pipeline, como de uma aplicação de secretaria, "
                  "o CDC passa a ser o caminho principal, e os números precisam ser medidos de novo.", "amber")

    # =========================================================================
    # SLIDE 10: FALHAS
    # =========================================================================
    elif idx == 9:
        cabecalho("Seção 9 · Lições", 10, total, "Como cada caminho falhou, e o que foi feito",
                  "As falhas vistas durante a construção e a revisão (ADR 0025)")
        c1, c2 = st.columns(2)
        with c1:
            bloco("Lote",
                  "• <strong>Servidor do INEP fora do ar</strong> ou com a cadeia TLS incompleta &rarr; retentativas e a CA intermediária anexada; sem o arquivo, o pipeline segue sem o benchmark.<br>"
                  "• <strong>Reexecução duplicando linhas</strong> &rarr; <code>TRUNCATE</code> + <code>COPY</code> numa transação; <code>overwrite</code> no lago.<br>"
                  "• <strong>Coluna toda nula mudando de tipo</strong> e quebrando o overwrite do Delta &rarr; tipos tirados do catálogo do PostgreSQL, e não inferidos do dado.")
        with c2:
            bloco("CDC",
                  "• <strong>Debezium ignora TRUNCATE</strong> por padrão: as linhas apagadas ficariam vivas &rarr; <code>skipped.operations=none</code> e marca de exclusão.<br>"
                  "• <strong>DELETE seguido de INSERT antigo reprocessado</strong> ressuscitaria a linha &rarr; exclusão vira marca com a posição no WAL.<br>"
                  "• <strong>Banco recriado:</strong> o WAL recomeça abaixo do lago &rarr; o consumidor compara com <code>pg_current_wal_lsn()</code> e aborta.<br>"
                  "• <strong>Slot segurando WAL</strong> &rarr; <code>max_slot_wal_keep_size=2GB</code> e <code>scripts/cdc.sh remover</code>.<br>"
                  "• <strong>Cada MERGE grava arquivos novos</strong> &rarr; compactação a cada 50 lotes.",
                  "green")
        bloco("A diferença de natureza",
              "O lote falha <strong>alto</strong>: a carga inteira cai, e a transação volta. O CDC falha <strong>em silêncio</strong>: "
              "uma linha que deveria sumir fica viva, um evento é ignorado. Por isso a defesa do CDC é a idempotência "
              "do MERGE, com teste e com demonstração.", "amber")

    # =========================================================================
    # SLIDE 11: CHECKLIST E CONCLUSÃO
    # =========================================================================
    elif idx == 10:
        cabecalho("Seção 10 · Conclusão", 11, total, "Checklist de aceite da E2 e evidências",
                  "Tudo na main; a entrega é marcada pela tag e2")
        bloco("Checklist",
              """
              <table>
                <tr><th>Item</th><th>Evidência</th></tr>
                <tr><td>Ingestão em lote idempotente e reexecutável</td><td><code>scripts/rodar_pipeline.sh</code>, <code>src/db/exportar_lago.py</code>, <code>tests/test_unit_lago.py</code></td></tr>
                <tr><td>Fluxo de mudanças a partir do OLTP</td><td><code>src/cdc/</code>, <code>src/cdc/demonstrar.py</code></td></tr>
                <tr><td>Formato aberto (Parquet + Delta)</td><td>ADR 0024, <code>data/lake/</code></td></tr>
                <tr><td>Semântica de entrega demonstrada</td><td><code>src/cdc/demonstrar_reprocessamento.py</code>, ADR 0025</td></tr>
                <tr><td>Dado atrasado e reprocessamento de janela</td><td>ADR 0026, migração 0021, <code>--janelas-alteradas</code></td></tr>
                <tr><td>Serialização e compressão justificadas</td><td>ADR 0024 (ZSTD 3 medido contra Snappy e GZIP)</td></tr>
                <tr><td>ADR do mecanismo de ingestão com a opção nula</td><td>ADR 0025</td></tr>
                <tr><td>Diário de bordo das Semanas 7 a 10</td><td><code>docs/diario/diario_de_bordo.md</code></td></tr>
              </table>
              """, "green")
        render_html(
            """
            <div style="background-color: #f8fafc; border-left: 4px solid #133E79; padding: 1.2rem 1.5rem; border-radius: 6px; margin: 1.5rem 0; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
                <div style="font-size: 1.15rem; color: #1e293b; font-weight: 600; margin-bottom: 0.4rem;">
                    Testes sem banco nem Kafka no CI: job <code>testes-unitarios</code>
                </div>
                <div style="font-size: 0.95rem; color: #64748b;">
                    <code>python -m unittest discover -s tests -p "test_unit_*.py"</code> cobre o MERGE do CDC, o consumidor com um Kafka simulado, o lago e o dado atrasado.
                </div>
            </div>
            """
        )
        if st.button("Abrir o Painel Executivo do Observatório UnB", type="primary", width="stretch"):
            voltar_ao_painel()

