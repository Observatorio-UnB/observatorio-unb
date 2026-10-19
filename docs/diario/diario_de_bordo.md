# Diário de bordo — Squad Observatório UnB

Registro semanal de processo, medições e decisões de engenharia da Squad (Semanas 01 a 10).

---

## Semana 01 — Ingestão CKAN, LGPD e Auditoria de Qualidade

**O que foi medido**

- Volume da base bruta: 60.695 registros no SIGRA (24,56 MB), 113 estruturas curriculares (76,4 KB) e 157 cursos catalogados (45,4 KB).
- Análise de quase-identificadores: cruzar `(curso, data_nascimento, sexo, raca_cor)` na base bruta do SIGRA resultou em 88,93% de indivíduos com $k = 1$ (reidentificação unívoca).
- Auditoria de qualidade: 8 anomalias identificadas, incluindo encoding ISO-8859-1 com acentos corrompidos, delimitação mista (`;` no SIGRA e `,` em Cursos) e campos com até 30 espaços em branco de padding.

**O que surpreendeu**

- 88,9% da base bruta de discentes era reidentificável unicamente cruzando apenas 4 atributos demográficos públicos, tornando inviável publicar dados individuais sem agregação.
- O portal de Dados Abertos da UnB não padronizava UTF-8 em todos os datasets, quebrando a ingestão programática padrão.

**O que foi decidido**

- Adotar a Arquitetura Medalhão (Bronze imutável, Silver tratada e Gold analítica). Registrado no [ADR 0001](../adr/0001-arquitetura-medalhao.md).
- Automatizar a ingestão programática via API CKAN 2.11 sem downloads manuais. Registrado no [ADR 0002](../adr/0002-ingestao-api-ckan.md).
- Garantir $k$-anonimato $\ge 5$ na Gold, excluindo identificadores pessoais da camada pública. Registrado no [ADR 0005](../adr/0005-privacidade-k-anonimato.md).
- Criar o Índice de Retenção Crítica (IRC) com peso 50% atraso e 50% evasão para neutralizar o viés de sobrevivência. Registrado no [ADR 0006](../adr/0006-indice-retencao-critica.md).

**Pendências para a Semana seguinte**

- [x] Construir o pipeline de transformação Silver e geração da Gold em CSV.
- [x] Desenvolver o dashboard interativo em Streamlit para o DEG.
- [x] Redigir minuta de issue técnica para o CPD sobre as inconsistências do portal.

---

## Semana 02 — Pipeline de Transformação, Harmonização e Dashboard

**O que foi medido**

- Taxa de casamento da junção heterogênea: subiu de 86,09% para 97,54% (59.202 vínculos casados) após normalização NFKD e tabela de 32 sinônimos de cursos.
- Tempo de execução do pipeline em Python/Pandas: ~18 segundos para gerar a camada Gold em CSV.
- Evasão por turno na primeira versão: 52,54% no noturno contra 29,43% no diurno.

**O que surpreendeu**

- O viés de sobrevivência em cursos de alta evasão: analisar apenas concluintes fazia cursos como Física Computacional parecerem mais rápidos porque apenas 25% dos alunos formavam e os outros 75% evadiam.
- Cursos com o mesmo nome exato possuíam habilitações duplas (Bacharelado e Licenciatura) com matrizes curriculares totalmente distintas.

**O que foi decidido**

- Categorizar cursos com oferta dupla e matrizes distintas como `MISTO`. Registrado no [ADR 0004](../adr/0004-cursos-oferta-dupla-misto.md).
- Implementar mapeamento canônico de sinônimos de cursos com tabela de de-para. Registrado no [ADR 0003](../adr/0003-harmonizacao-canonica-cursos.md).
- Publicar o painel analítico diretamente no GitHub Pages usando WebAssembly via `stlite`. Registrado no [ADR 0007](../adr/0007-painel-streamlit-stlite-pages.md).

**Pendências para a Semana seguinte**

- [x] Integrar dados de Iniciação Científica (PIBIC).
- [x] Implementar simulador What-If de decisão orçamentária do DEG.
- [x] Estruturar esteira de CI/CD para deploy estático no GitHub Pages.

---

## Semana 03 — Iniciação Científica (PIBIC), Modelo CBA e CI/CD

**O que foi medido**

- Volume PIBIC: 5.420 planos de trabalho de iniciação científica mapeados por curso e ano.
- Modelo CBA (*Cost-Benefit Analysis*) no simulador: cálculo do retorno econômico da evasão evitada com base no custo médio do discente na UnB (R$ 41.200/ano).
- Tempo de build e deploy no GitHub Actions com `stlite`: 2 minutos e 40 segundos.

**O que surpreendeu**

- O Stlite (WebAssembly) falhava ao tentar acessar arquivos locais do sistema operacional, exigindo empacotamento em tarball estático no CI.
- A base do PIBIC não continha a matrícula do bolsista no arquivo público, inviabilizando junção direta com discentes e exigindo agregação por departamento.

**O que foi decidido**

- Integrar a tabela de vigências históricas do CNPq para estimar o valor monetário das bolsas de IC por ano. Registrado no [ADR 0023](../adr/0023-valor-bolsa-ic-pela-tabela-do-cnpq.md).
- Automatizar o build e publicação dos artefatos do painel no GitHub Pages via job `deploy-pages` no workflow `.github/workflows/medalhao.yml`, conforme definido no [ADR 0007](../adr/0007-painel-streamlit-stlite-pages.md).

**Pendências para a Semana seguinte**

- [x] Ingerir a base do Censo da Educação Superior (INEP 2019) para benchmark nacional.
- [x] Iniciar a transição do pipeline baseado em CSVs para o PostgreSQL.

---

## Semana 04 — Benchmark Nacional INEP e Migrações PostgreSQL

**O que foi medido**

- Volume do Censo da Educação Superior 2019 (INEP): microdados de cursos com ~40.000 linhas processadas para comparar taxas de evasão e conclusão da UnB com outras IFES.
- Catálogo de migrações SQL: migrações versionadas criadas e rastreadas na tabela `public.schema_migrations`.
- Tempo de carga inicial das camadas no PostgreSQL: 32 segundos via Docker Compose.

**O que surpreendeu**

- O endpoint de download do Censo no INEP sofria instabilidades frequentes e erros de cadeia de certificados TLS, quebrando o CI quando a dependência era síncrona.
- Agregações de federais precisavam somar matrículas antes de aplicar o corte de relevância estatística, caso contrário cursos pequenos distorciam a mediana nacional.

**O que foi decidido**

- Adicionar fallback com cache local do arquivo do INEP e tratar exceções de rede no CI para não interromper a esteira. Registrado no [ADR 0008](../adr/0008-benchmark-inep-censo-2019.md).
- Formalizar o versionamento do banco via migrações SQL com checksum SHA-256 e advisory lock `70402026`, orquestrando a infraestrutura local com `docker-compose up -d db`. Registrado no [ADR 0009](../adr/0009-postgres-migracoes-contrato.md).

**Pendências para a Semana seguinte**

- [x] Implementar busca semântica vetorial com `pgvector` dentro do PostgreSQL.
- [x] Criar dicionário de dados automatizado a partir do catálogo do banco.
- [x] Unir a base do SIGAA à base histórica do SIGRA.

---

## Semana 05 — Busca Semântica pgvector e Unificação SIGAA + SIGRA

**O que foi medido**

- Índice HNSW no `pgvector`: 438 documentos vetorizados (cursos, planos PIBIC e documentação) com modelo local multilíngue `paraphrase-multilingual-MiniLM-L12-v2` (384 dimensões).
- Latência de busca por similaridade de cosseno: $< 5$ ms para consultas em linguagem natural no PostgreSQL.
- Base unificada SIGRA + SIGAA: expansão para 152.680 vínculos discentes (100% casados com matriz curricular).
- Janela de maturação estatística: corte de 8 anos fixado em 2016 (coortes com tempo suficiente para consolidação do desfecho).

**O que surpreendeu**

- O SIGAA e o SIGRA utilizavam convenções divergentes para desfechos: o SIGAA não trazia o semestre formal de saída para formados, apenas a data de registro do diploma.
- Arquivos nominais do SIGAA continham nomes completos de discentes e professores, violando princípios da LGPD.

**O que foi decidido**

- Unificar SIGAA e SIGRA como fontes oficiais, adotando o SIGAA como fonte primária. Registrado no [ADR 0012](../adr/0012-sigaa-uniao-com-sigra.md).
- Estimar o semestre de conclusão no SIGAA a partir da data de registro do diploma. Registrado no [ADR 0015](../adr/0015-semestre-de-saida-estimado.md).
- Definir evasão estritamente como qualquer saída do curso sem diploma registrado. Registrado no [ADR 0013](../adr/0013-evasao-saida-sem-diploma.md).
- Estabelecer janela de maturação mínima de 8 anos para análise de coortes na Gold. Registrado no [ADR 0014](../adr/0014-janela-maturacao-8-anos.md).
- Excluir sumariamente arquivos com identificação nominal da esteira de ingestão. Registrado no [ADR 0017](../adr/0017-arquivos-nominais-fora.md).
- Implementar busca semântica com extensão `pgvector`. Registrado no [ADR 0011](../adr/0011-busca-semantica-pgvector.md).

**Pendências para a Semana seguinte**

- [x] Modelar a normalização formal em 3NF da Silver e Star Schema da Gold.
- [x] Eliminar completamente os CSVs intermediários do repositório e do pipeline.

---

## Semana 06 — Normalização 3NF, Star Schema e Eliminação dos CSVs

**O que foi medido**

- Prova matemática de normalização: eliminação de anomalias de redundância e atualização na Silver, decomposta em 4 relações normalizadas (`discentes`, `cursos`, `estruturas_curriculares`, `movimentacoes_vinculos`).
- Modelo Star Schema na Gold: `dim_curso`, `dim_tempo`, `dim_situacao` e tabelas fato (`fato_retencao_curso`, `fato_alunos_ativos_curso`).
- Particionamento por faixa de ano (`PARTITION BY RANGE (ano_ingresso)`) na tabela `silver.movimentacoes_vinculos`.
- Remoção de todos os arquivos `.csv` versionados no git, reduzindo o tamanho do repositório em mais de 30 MB.

**O que surpreendeu**

- Alunos ativos no SIGAA possuíam semestres de permanência que ultrapassavam o prazo máximo do curso sem evasão lançada (casos de retenção em processo de jubilamento ou com trancamentos justificados).
- Variações nas matrizes curriculares entre anos letivos exigiam versionamento completo do catálogo de cursos.

**O que foi decidido**

- Criar tabela de alunos ativos com contagem conservadora de atraso. Registrado no [ADR 0019](../adr/0019-ativos-hoje.md) e [ADR 0020](../adr/0020-lista-de-ativos-com-minimizacao.md).
- Inicialmente decidiu-se fixar o catálogo de cursos na versão de 2022 ([ADR 0016](../adr/0016-catalogo-cursos-fixo-2022.md)), mas a decisão foi revista para manter todas as versões publicadas, valendo a mais recente ([ADR 0021](../adr/0021-catalogo-todas-as-versoes.md)).
- Excluir cursos-tronco (ABI) das visões individuais por curso. Registrado no [ADR 0022](../adr/0022-cursos-tronco.md).
- Configurar pipeline mensal automatizado no GitHub Actions commitando diretamente na `main`. Registrado no [ADR 0018](../adr/0018-atualizacao-mensal-commit-na-main.md).

**Pendências para a Semana seguinte**

- [x] Criar pipeline ELT com SQL puro sem passar por Pandas.
- [x] Elaborar prova formal da normalização para o dossiê da disciplina.

---

## Semana 07 — Pipeline Direto no Banco, Silver 3NF e Star Schema

**O que foi medido**

- Volume do modelo relacional Silver em 3NF: 152.680 registros em `silver.movimentacoes_vinculos`, 158 cursos em `silver.cursos` e 112 matrizes curriculares ativas em `silver.estruturas_curriculares`.
- Tempo de execução da carga com SQL puro (`povoar_silver_3nf.py` + `povoar_dimensional.py`): 46 segundos para o pipeline completo, sem gravação de arquivos intermediários em disco.
- Eliminação de CSVs: remoção de 4 arquivos CSV intermediários que antes transitavam entre scripts.
- Cobertura de casamento de vínculos com matrizes curriculares: 100% dos 152.680 vínculos associados a uma estrutura canônica após harmonização.

**O que surpreendeu**

- 109 vínculos da base bruta não casavam com nenhuma estrutura curricular porque os códigos de habilitação do SIGRA divergiam da nomenclatura canônica das matrizes. A junção interna descartava esses alunos silenciosamente.
- O pipeline baseado em DataFrames do Pandas alocava picos de memória desnecessários e gerava dessincronização de estado entre os arquivos locais e as tabelas do PostgreSQL.

**O que foi decidido**

- Eliminar os CSVs intermediários e transformar o PostgreSQL no repositório transacional de todas as camadas (Bronze, Silver e Gold). Registrado no [ADR 0009](../adr/0009-postgres-migracoes-contrato.md).
- Implementar tabela de harmonização de nomes (`gold.regras_harmonizacao_canonicas`) para recuperar os 109 vínculos órfãos. Registrado no [ADR 0003](../adr/0003-harmonizacao-canonica-cursos.md).
- Segregar o acesso a dados de discentes (`silver.discentes` fora do papel `observatorio_leitura`) para conformidade estrita com LGPD. Registrado no [ADR 0010](../adr/0010-controle-de-acesso-leitura.md).

**Pendências para a Semana seguinte**

- [x] Implementar atualização concorrente da view materializada do painel analítico.
- [x] Otimizar ingestão da base externa do Censo da Educação Superior (INEP).
- [x] Desenhar a camada analítica em formato aberto (Parquet / Delta Lake).

---

## Semana 08 — Camada Analítica em Delta Lake e Ingestão em Chunks

**O que foi medido**

- Benchmark de serialização e compressão para os 152.680 vínculos (`silver.movimentacoes_vinculos`), medindo mediana de 15 consultas de agregação colunar no DuckDB:
  - Sem compressão: 3.319 KB | Escrita: 62 ms | Leitura: 17 ms
  - Snappy (padrão PyArrow): 2.222 KB | Escrita: 66 ms | Leitura: 22 ms
  - GZIP: 1.462 KB | Escrita: 3.527 ms | Leitura: 19 ms
  - ZSTD nível 3: 1.434 KB | Escrita: 173 ms | Leitura: 25 ms
- Particionamento por quinquênio de ingresso (`quinquenio_ingresso`): arquivos de 370 KB a 560 KB por partição (2010, 2015, 2020), contra fragmentação de arquivos de ~100 KB se particionado por ano individual.
- Ingestão do Censo INEP: leitura em blocos de 50.000 linhas com tabela de staging, reduzindo o pico de memória de 1,2 GB para 85 MB.

**O que surpreendeu**

- GZIP e ZSTD nível 3 empataram no tamanho final comprimido (~1,4 MB), mas o GZIP levou 3.527 ms na escrita — 20 vezes mais lento que o ZSTD (173 ms) para o mesmo arquivo.
- O Apache Iceberg em Python (`pyiceberg`) exigiria subir um catálogo de metadados dedicado (REST, SQL ou Glue) no `docker-compose.yml`, adicionando dependências de infraestrutura. O Delta Lake via `deltalake` (delta-rs) opera nativamente em Rust/Python sobre o sistema de arquivos local sem catálogo externo.

**O que foi decidido**

- Adotar **Delta Lake sobre Parquet com compressão ZSTD nível 3**, particionado exclusivamente por quinquênio de ingresso nos vínculos. Registrado no [ADR 0024](../adr/0024-lago-delta-parquet-zstd.md).
- Implementar procedure para provisionamento dinâmico de partições futuras no PostgreSQL (`silver.provisionar_particoes_movimentacoes`), automatizando a partição de vínculos da [ADR 0024](../adr/0024-lago-delta-parquet-zstd.md).
- Configurar retenção de 7 dias para o `VACUUM` do Delta Lake para viabilizar auditoria temporal (*time travel*), conforme definido no [ADR 0024](../adr/0024-lago-delta-parquet-zstd.md).

**Pendências para a Semana seguinte**

- [x] Subir infraestrutura de captura de mudanças via WAL (CDC com Debezium e Kafka).
- [x] Implementar consumidor com escrita idempotente no Delta Lake.
- [x] Formalizar e testar a semântica de entrega do transporte e do efeito no lago.

---

## Semana 09 — Captura de Mudanças (CDC), Debezium e Semântica de Entrega

**O que foi medido**

- Latência ponta a ponta do CDC (da transação no PostgreSQL até a visibilidade no Delta Lake): 0,25 s a 0,87 s (medido na branch de desenvolvimento do CDC `feat/cdc-debezium`, PR #24, via `src/cdc/demonstrar.py` para INSERT, UPDATE e DELETE de sentinela).
- Custo de infraestrutura da rota CDC: 1,9 GB de memória RAM alocada (Kafka KRaft 0,9 GB + Debezium Connect 1,0 GB), 378 MB em disco nos tópicos e slot de replicação retendo até 239 MB de WAL pós-recarga.
- Custo da rota em lote (opção nula): 0,9 s de exportação completa no final do pipeline, sem serviços adicionais no Compose.
- Teste de semântica de reprocessamento: releitura de 306.009 eventos dos tópicos desde o offset inicial; digest SHA-256 de todas as linhas do Delta Lake permaneceu inalterado (`8b379584a8f5`).

**O que surpreendeu**

- O Debezium ignora operações de `TRUNCATE` por padrão (`skipped.operations=default`). Quando a recarga mensal limpava a Silver 3NF com `TRUNCATE`, o evento não era emitido e o Delta Lake mantinha dados antigos como vivos. Foi obrigatório configurar `skipped.operations=none` e codificar o tratamento no consumidor.
- Confirmar o offset no Kafka antes da gravação no Delta Lake implementaria *at-most-once*: se o processo caísse entre a confirmação e a escrita, o lote seria perdido silenciosamente.

**O que foi decidido**

- Declarar a recarga periódica em lote como mecanismo principal de ingestão e o CDC como mecanismo opcional/sob demanda para atualizações transacionais fora do ciclo mensal. Registrado no [ADR 0025 (PR #26: docs/adr-mecanismo-ingestao)](https://github.com/Observatorio-UnB/observatorio-unb/pull/26).
- Semântica de entrega fixada como *at-least-once* no transporte (offset confirmado apenas após a gravação no Delta) e *exactly-once* no efeito via `MERGE` idempotente filtrado por LSN (`_commit_lsn`).
- Operações de exclusão convertidas em deleção lógica (`_deletado = true`) com carimbo de LSN para evitar que o reprocessamento de mensagens antigas ressuscite registros apagados.

**Pendências para a Semana seguinte**

- [x] Modelar empiricamente o atraso no registro de diplomas acadêmicos.
- [x] Implementar mecanismo de marca d'água e reprocessamento seletivo de partições alteradas.
- [x] Adicionar automação para evitar congelamento do banco Supabase por inatividade.

---

## Semana 10 — Dado Atrasado, Marca d'Água e Reprocessamento Granular

**O que foi medido**

- Atraso do registro do diploma em relação ao encerramento nominal do semestre de conclusão no SIGRA (25.485 registros de formados):
  - Mediana ($p50$): -13 dias (registro efetuado antes da virada do semestre letivo).
  - Percentil 90 ($p90$): 19 dias após o encerramento.
  - Percentil 95 ($p95$): 40 dias após o encerramento.
  - Percentil 99 ($p99$): 105 dias após o encerramento.
  - Acima de 4 meses: 0,8% do total de formados.
- Assimetria observada no SIGAA de 15/07/2024: 4.176 formaturas consolidadas no semestre 2023/1 e apenas 651 formaturas no semestre 2024/1 (semestre ainda aberto recebendo registros tardios).
- Reprocessamento granular no Delta Lake: `exportar_lago.py --janelas-alteradas` regrava unicamente o arquivo do quinquênio afetado em ~1,8 s, sem gerar novas versões de arquivo para as partições inalteradas.

**O que surpreendeu**

- Entre recargas idênticas da Silver 3NF precedidas de `ANALYZE`, o planejador de consultas do PostgreSQL alterava a ordem de execução da junção interna. Sem uma cláusula explícita de ordenação, os `id_vinculo` gerados por `IDENTITY` flutuavam, fazendo o Delta Lake interpretar todas as partições como alteradas. A adição de `ORDER BY dg.id` resolveu a não-determinação.
- No SIGAA, o semestre de saída é estimado pela própria data de registro (ADR 0015). Diplomas registrados com atraso caem num período recente e entram como `NO_PRAZO`; a condição de `ATRASADA` só ocorre em lançamentos retroativos ou correções do SIGRA.

**O que foi decidido**

- Fixar a marca d'água com tolerância de 4 meses a partir da data de publicação do arquivo de vínculos, cobrindo 99,2% das conclusões. Registrado no [ADR 0026](../adr/0026-dado-atrasado-marca-dagua.md).
- Criar a migração `0021_dado_atrasado.sql` com tabelas `silver.cargas_vinculos`, `silver.cargas_vinculos_retrato` (549 contagens agregadas por carga) e a view de classificação `silver.chegadas_por_carga` (`NO_PRAZO`, `ATRASADA`, `SEM_PERIODO`).
- Manter dados atrasados na base sem descarte, recalculando a camada Gold e sinalizando em log revisões em coortes já consolidadas.
- Adicionar o workflow `.github/workflows/supabase-keepalive.yml` executando `select 1` diário via `psql` às 12:00 UTC para contornar a pausa automática de 7 dias do plano gratuito.

**Pendências para a Semana seguinte**

- [ ] Ajustar apontamentos de code review na esteira de CDC (PRs #24 e #25: restringir portas no Compose para `127.0.0.1` e validações de timeout no DELETE).
- [ ] Consolidar a documentação final e ensaiar a demonstração prática da E2.
