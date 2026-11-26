# Registro de decisões de arquitetura (ADRs)

Cada arquivo registra uma decisão: o contexto que a motivou, o que foi decidido e o que isso custa. Uma decisão revista ganha um ADR novo que a substitui; o antigo fica, marcado como substituído.

## Portfólio dos 5 ADRs (E1 a E4)

Estes cinco ADRs formam o portfólio principal do semestre (um por entrega, com a E2 dividida em armazenamento e ingestão), todos com seção `## Gatilhos de revisão` explícita e estado auditado contra o semestre:

| Entrega | # | Decisão | Estado dos gatilhos no semestre |
|---|---|---|---|
| E1 | [0032](0032-modelagem-do-sistema-de-origem.md) | Sistema de origem em 3NF, recarregado por inteiro, com o tempo de evento em cada vínculo | Nenhum gatilho disparou: a pergunta não passou a exigir trajetória, o OLTP continua com um escritor só (a fila da E4 fica no esquema `operacional`), o volume não mudou de ordem e 0 de 152.680 vínculos divergem no `id_curso`. Decisão mantida |
| E2 (Lago) | [0024](0024-lago-delta-parquet-zstd.md) | Camada analítica em Delta Lake, Parquet com ZSTD e partição por quinquênio | 1 gatilho disparou e foi corrigido na carga (`ORDER BY dg.id` contra não-determinismo); 3 mantidos |
| E2 (Ingestão) | [0025](0025-mecanismo-de-ingestao-recarga-e-cdc.md) | Recarga periódica como mecanismo principal, CDC como caminho opcional | Nenhum gatilho disparou; decisão mantida |
| E3 | [0030](0030-modelagem-analitica-e-ferramentas.md) | Modelagem estrela no grão do curso, dbt e Dagster | 1 gatilho disparou e gerou extensão (macro de arredondamento e snapshot SCD 2 no dbt); 4 mantidos |
| E4 | [0033](0033-disponibilizacao-camada-semantica-e-etl-reverso.md) | Camada semântica feita à mão no dbt, painel público por arquivo e ETL reverso por push, com o CSV agendado como opção nula | Decisão desta entrega: nenhum gatilho disparou. As três divergências de métrica achadas na E4 foram corrigidas antes da decisão e viraram os testes que a sustentam |

Além do portfólio acima, também trazem gatilhos de revisão o [ADR 0001](0001-arquitetura-medalhao.md) (arquitetura medalhão, base desde a E0: 2 gatilhos dispararam e geraram revisão, a migração de CSV para PostgreSQL e a orquestração em Dagster; 2 mantidos), o [ADR 0031](0031-escopo-disponibilizacao-online-supabase-lgpd.md) (disponibilização online no Supabase e LGPD), o [ADR 0010](0010-controle-de-acesso-leitura.md) (atualizado com RLS/coluna na E4, PR #84). A consolidação na retrospectiva do ciclo de vida fica na issue #79 (`docs/diario/diario_de_bordo.md`).

## Todos os ADRs

| # | Decisão | Data |
|---|---|---|
| 0001 | [Arquitetura medalhão (Bronze, Silver, Gold)](0001-arquitetura-medalhao.md) | 2026-08-31 (revista em 2026-11-09) |
| 0002 | [Ingestão pela API CKAN, escolhendo o recurso pelo nome do arquivo](0002-ingestao-api-ckan.md) | 2026-08-31 (revista em 2026-09-26, 2026-11-09) |
| 0003 | [Harmonização canônica dos nomes de curso](0003-harmonizacao-canonica-cursos.md) | 2026-09-09 (revista em 2026-11-09) |
| 0004 | [Cursos com bacharelado e licenciatura sob o mesmo nome ficam como MISTO](0004-cursos-oferta-dupla-misto.md) | 2026-09-09 |
| 0005 | [Privacidade: k-anonimato ≥ 5 na Gold e dado pessoal fora do que é publicado](0005-privacidade-k-anonimato.md) | 2026-08-31 (revista em 2026-09-26) |
| 0006 | [Índice de Retenção Crítica (IRC) com peso maior para evasão](0006-indice-retencao-critica.md) | 2026-08-31 |
| 0007 | [Painel em Streamlit publicado no GitHub Pages via stlite](0007-painel-streamlit-stlite-pages.md) | 2026-09-07 |
| 0008 | [Benchmark nacional pelo Censo da Educação Superior 2019](0008-benchmark-inep-censo-2019.md) | 2026-09-24 |
| 0009 | [PostgreSQL com migrações versionadas e contrato estrito de carga](0009-postgres-migracoes-contrato.md) | 2026-09-24 |
| 0010 | [Papel de leitura que só enxerga gold e busca (e os marts do dbt, desde a E3)](0010-controle-de-acesso-leitura.md) | 2026-09-24 (revista em 2026-11-09) |
| 0011 | [Busca semântica com pgvector e embedding multilíngue local](0011-busca-semantica-pgvector.md) | 2026-09-24 |
| 0012 | [SIGAA como fonte principal, unido ao SIGRA](0012-sigaa-uniao-com-sigra.md) | 2026-09-26 |
| 0013 | [Evasão é toda saída do curso sem diploma](0013-evasao-saida-sem-diploma.md) | 2026-09-26 |
| 0014 | [Só entram na análise coortes com 8 anos de acompanhamento](0014-janela-maturacao-8-anos.md) | 2026-09-26 |
| 0015 | [Semestre de conclusão do SIGAA estimado pela data do diploma](0015-semestre-de-saida-estimado.md) | 2026-09-26 |
| 0016 | [Catálogo de cursos fixo na versão de 2022](0016-catalogo-cursos-fixo-2022.md) (substituída pela 0021) | 2026-09-26 |
| 0017 | [Arquivos nominais do SIGAA ficam fora da ingestão](0017-arquivos-nominais-fora.md) | 2026-09-26 |
| 0018 | [Atualização automática com commit direto na main](0018-atualizacao-mensal-commit-na-main.md) | 2026-09-26 (revista em 2026-11-09) |
| 0019 | [Tabela de alunos ativos hoje com contagem conservadora de atraso](0019-ativos-hoje.md) | 2026-09-26 |
| 0020 | [Lista de ativos do SIGAA com minimização de colunas](0020-lista-de-ativos-com-minimizacao.md) | 2026-09-26 |
| 0021 | [Catálogo de cursos com todas as versões, a mais recente valendo](0021-catalogo-todas-as-versoes.md) | 2026-09-26 |
| 0022 | [Cursos-tronco (ABI) fora das visões por curso](0022-cursos-tronco.md) | 2026-09-26 |
| 0023 | [Valor da bolsa IC por uma tabela de vigências lida do CNPq](0023-valor-bolsa-ic-pela-tabela-do-cnpq.md) | 2026-09-26 |
| 0024 | [Camada analítica em Delta Lake, Parquet com ZSTD e partição por quinquênio](0024-lago-delta-parquet-zstd.md) | 2026-10-10 |
| 0025 | [Recarga periódica como mecanismo principal de ingestão, CDC como caminho opcional](0025-mecanismo-de-ingestao-recarga-e-cdc.md) | 2026-10-10 |
| 0026 | [Dado atrasado aceito e registrado pela marca d'água, com reprocessamento só da janela alterada](0026-dado-atrasado-marca-dagua.md) | 2026-10-13 |
| 0027 | [Agregações da Gold em SQL nativo no PostgreSQL, sem Pandas nem PySpark](0027-agregacoes-gold-em-sql-nativo.md) | 2026-10-29 |
| 0028 | [`gold.dim_curso` como dimensão de variação lenta tipo 2](0028-dim-curso-scd-tipo-2.md) | 2026-11-01 |
| 0029 | [Transformações da gold em dbt, em três camadas](0029-transformacoes-em-dbt.md) | 2026-11-01 (revista em 2026-11-09) |
| 0030 | [Modelagem analítica em estrela com fato no grão do curso, transformação em dbt e orquestração em Dagster](0030-modelagem-analitica-e-ferramentas.md) | 2026-11-01 |
| 0031 | [Escopo de disponibilização online do banco no Supabase e salvaguardas de privacidade (LGPD)](0031-escopo-disponibilizacao-online-supabase-lgpd.md) | 2026-11-02 |
| 0032 | [Sistema de origem em 3NF, recarregado por inteiro, com o tempo de evento em cada vínculo](0032-modelagem-do-sistema-de-origem.md) | 2026-11-24 |
| 0033 | [Camada semântica feita à mão no dbt, painel público por arquivo e ETL reverso por push](0033-disponibilizacao-camada-semantica-e-etl-reverso.md) | 2026-11-24 |
| 0034 | [Chat com LLM local sobre a gold](0034-chat-llm-local.md) | 2026-11-24 |
