# Verificação da E3 do zero

Conferência feita em 11/11/2026, dia da entrega, para responder a duas perguntas: cada item do checklist da E3 roda de verdade, e não só tem evidência no repositório? Algo do projeto está quebrado? A base é a `main` em `9d1c444`, com o mesmo conteúdo da tag `e3`.

## Como foi feita

- **Ambiente limpo:** clone da `main`, `.venv` nova com `requirements.txt` e `requirements-orquestracao.txt` (Python 3.12.3, dagster 1.13.29, dbt-core 1.12.6, dbt-postgres 1.11.0, pandas 3.1.1, streamlit 1.67.0) e um PostgreSQL 16 vazio, num projeto do compose à parte.
- **O mesmo caminho do agendamento:** `dagster job execute -m orquestracao -j pipeline_mensal`, que é o que o `atualiza-dados.yml` dispara no dia 1. O CI (`medalhao.yml`) roda as etapas uma a uma e não exercita esse job.
- **Depois da carga:** a suíte inteira de testes, as demonstrações de `docs/orquestracao.md`, o `EXPLAIN` de `docs/explain/`, as medições do ADR 0030 e o painel aberto como o README manda.
- **O que o CI já cobre:** o Medalhão + Pages está verde em `9d1c444` (190 testes, `dbt build` com PASS=78 e WARN=1), e o frescor diário passou em 08, 09 e 10/11.

## Resultado por item do checklist

| Item | O que foi rodado | Resultado |
|---|---|---|
| Fato e dimensão com grão declarado e SCD | Contagens depois da carga e `docs/adr/medicoes/0030_granularidade_do_fato.sql` | `dbt_marts.fct_retencao_curso` e `gold.fato_retencao_curso` com 95 cursos cada. `dim_curso` com 112 cursos no dbt, no snapshot e na gold. Medição do ADR 0030 idêntica: 68.339 vínculos, 101 cursos (6 suprimidos pelo k ≥ 5), 633 e 14.359 linhas nos outros grãos. `test_dbt_scd2` e `test_banco_scd2` passaram |
| Transformações versionadas em dbt, em camadas | `camadas_dbt` dentro do job mensal | 1 snapshot, 12 modelos e 65 testes: PASS=78, WARN=1, ERROR=0, como no CI. A reconciliação com a gold passou |
| Testes de esquema, volume, unicidade, integridade e distribuição | `python -m unittest discover -s tests -p "test_*.py"` | 190 testes, nenhum pulado, todos OK; com as correções abaixo e os 3 testes novos, 193. Inclui `test_dbt_dado_ruim` (cada teste falha com o dado injetado). O único aviso do dbt é a anomalia conhecida de `docs/testes_de_dados.md` (9 vínculos com saída estimada antes do ingresso) |
| Orquestração com grafo, retry e backfill | Job mensal; demonstrações 1 e 3 de `docs/orquestracao.md` | Job: as 15 etapas com sucesso, na ordem do grafo, em 8 min 14 s (3 min 55 s de vetorização). Retry: com o banco parado, `star_schema` falhou, pediu nova tentativa em 10 s e passou na 2ª, com o banco de volta; só então `view_painel` rodou. Backfill: com a janela de 2015 apagada do lago, o comando do README regravou os 6 quinquênios em 17,8 s, com os 152.680 vínculos e nenhum id repetido |
| Consulta otimizada com `EXPLAIN (ANALYZE, BUFFERS)` | `docs/explain/distribuicao_formatura_por_curso.sql`, com e sem o índice da migração 0024 (o "sem" numa transação desfeita) | Sem o índice, 1.566 buffers e 22,4 ms. Com ele, 13 buffers e 0,39 ms. O documento registra 1.566, 14, 35,6 ms e 0,42 ms: os buffers batem, e o tempo varia com a máquina |
| Frescor e SLA de uma tabela de consumo | `python src/db/frescor.py --fonte` | SLA cumprido nas 6 verificações: a view do painel e as 5 fontes do portal |
| ADR de modelagem analítica e ferramentas | Reexecução das medições do ADR 0030 | Números idênticos (linha do primeiro item) |
| Painel que responde à pergunta da E1 | `streamlit run src/dashboard/app.py`, com o banco carregado | **Quebrado antes desta verificação:** o painel mostrava "Sem dados da gold" (problema 1 abaixo). Depois da correção: "23 cursos estão em retenção crítica", com Física Computacional em primeiro, lidos de `dbt_marts.painel_cursos_criticos`, como diz o roteiro do README |

## Problemas encontrados e corrigidos

**1. O painel aberto pelo `streamlit run` não lia o banco.** O `app.py` só punha no `sys.path` a pasta do próprio app. Com o `streamlit run src/dashboard/app.py` do README (e do `CMD` do Dockerfile), o `from src.db.exportar_gold import montar_snapshot` falhava, a exceção era engolida, e o painel caía no `export/gold.json` ou, sem ele, em "Sem dados da gold". Com `python -m streamlit run`, que põe a pasta atual no caminho, o mesmo painel respondia normalmente. O GitHub Pages lê o export e não era afetado.

`tests/test_painel_e1.py` não pegava o erro porque já põe a raiz do projeto no `sys.path` antes de abrir o app. A correção põe a raiz no caminho dentro do `app.py`, como os outros scripts fazem. O teste novo (`test_04_le_o_banco_sem_a_raiz_no_sys_path`) abre o app num interpretador isolado (`python -I`): sem a correção, ele falha com "Sem dados da gold".

**2. O relatório de qualidade dependia da versão do pandas.** O achado 11 conta os ativos de graduação da lista do SIGAA e descarta os vínculos sem grau com `if row["grau"]`. Com o pandas 2, o grau nulo vem como `None`, que é falso. Com o pandas 3, que o `pandas>=2.0.0` do `requirements.txt` instala hoje no CI e no agendamento, ele vem como `NaN`, que é verdadeiro, e os vínculos sem grau entravam na conta:

| Lista de ativos de 06/2025 | pandas 2 (versionado) | pandas 3 (CI e agendamento) |
|---|---|---|
| Coorte de 2022 | 5.698 | 5.772 |
| Coorte de 2023 | 7.011 | 7.785 |

A diferença é exatamente o número de vínculos sem grau (74 e 774). Por isso o número já tinha alternado no histórico de `docs/relatorio_qualidade.md`, e a próxima atualização mensal ia versionar o valor errado. A contagem passou para `ativos_de_graduacao_por_coorte`, que confere o grau como texto, e `tests/test_unit_auditoria.py` cobre `None`, `NaN` e `pd.NA`. Com a correção, o relatório gerado com o pandas 3 é idêntico ao versionado.

## Conferido sem problema

- **Versionamento do agendamento mensal.** O `atualiza-dados.yml` falhou em 01/10 e 01/11 no passo "Versiona dados atualizados": o `git add` com caminho explícito sai com erro para o JSON do CNPq, que fica em `data/`, pasta ignorada. Num clone descartável, o comando atual (`git add -u`, PRs #46 e #62) sai com código 0, sem mudança e com mudança, e põe o JSON na área de preparação. O comando antigo sai com código 1.
- **Documentos gerados.** Regenerado do banco vazio, `docs/dicionario_dados_banco.md` saiu idêntico ao versionado.
- **Links.** Os 205 links locais do README, do relatório geral e de `docs/` apontam para arquivos que existem.
- **Docker.** `docker compose build` e o serviço `pipeline` (o `scripts/rodar_pipeline.sh`, que nem o CI nem o job do Dagster exercitam), num banco vazio: imagem em 3 min 36 s e pipeline completo em 17 min 27 s, com saída 0. O dbt deu PASS=78 e WARN=1, e foram vetorizados os 95 cursos, os 12.548 planos de IC e a documentação. Só a sincronização com o Supabase foi pulada, por falta de URL. O painel do Docker usa o mesmo `streamlit run` e tinha o problema 1.

## Pendências fora do código

Não foram alteradas aqui, porque são decisões do time:

- **A tag `e3` aponta para `020c993`, que não está no histórico da `main`.** A `main` foi reescrita depois da tag e está em `9d1c444`, com o mesmo conteúdo. O CI de `020c993` falhou na ingestão do portal CKAN, e o de `9d1c444`, com o mesmo conteúdo, passou. Com as correções acima na `main`, vale mover a tag para a commit delas.
- **A tag `e2` não existe.** O diário de bordo lista a criação dela como pendente. A entrega da E2 está marcada só pela `v1.0.0-r2`.
- **A branch `docs/adr-0009-e-tag-e3` não tem PR.** Foi criada a partir de `020c993` e precisa de rebase sobre a `main`.
- **O job do Dagster no agendamento só roda de verdade em 01/12.** Aqui ele rodou inteiro num banco vazio, e o versionamento foi simulado. A primeira execução agendada com as correções ainda não aconteceu.
- **A issue #17**, da rota `?ap1` no deploy, segue aberta desde a E1.
