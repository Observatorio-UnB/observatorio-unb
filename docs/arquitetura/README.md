# Dossiê de Engenharia de Dados e Arquitetura de SGBD

> **Universidade de Brasília (UnB)**  
> **Disciplina**: Banco de Dados 2  
> **Projeto**: Observatório de Retenção, Formatura e Evasão da Graduação  
> **Ambiente**: PostgreSQL 17 (Nuvem / Supabase) & PostgreSQL 16 (Local / Docker)

---

## Sumário Executivo

Este diretório consolida a especificação técnica formal e os artefatos de engenharia de banco de dados do **Observatório UnB**. O projeto adota a arquitetura de **Data Lakehouse Relacional**, combinando armazenamento em camadas (Medalhão), normalização em **3ª Forma Normal (3NF)** para os dados cadastrais/operacionais e **Modelagem Dimensional (Star Schema)** para suporte analítico à decisão do Decanato de Ensino de Graduação (DEG/DAA).

---

## Estrutura dos Artefatos de Engenharia

| Documento | Foco Teórico e Técnico | Destaques |
|:---|:---|:---|
| [`DER_MODELO_CONCEITUAL_E_LOGICO.md`](DER_MODELO_CONCEITUAL_E_LOGICO.md) | **Modelagem Conceitual e Lógica (Chen & Crow's Foot)** | Diagramas DER em ASCII/Unicode de alta resolução, cardinalidades $(min, max)$, chaves PK/FK e matriz de integridade referencial. |
| [`01_PROVA_MATEMATICA_NORMALIZACAO_3NF.md`](01_PROVA_MATEMATICA_NORMALIZACAO_3NF.md) | **Teoria Relacional Clássica (Edgar F. Codd)** | Prova matemática de Dependências Funcionais (DFs), fechamento de atributos, eliminação de anomalias (1NF $\rightarrow$ 3NF) e prova de junção sem perdas. |
| [`02_MODELAGEM_DIMENSIONAL_E_MATRIZ_KIMBALL.md`](02_MODELAGEM_DIMENSIONAL_E_MATRIZ_KIMBALL.md) | **Engenharia Analítica / OLAP (Ralph Kimball)** | Matriz de Barramento Corporativo (*Enterprise Bus Matrix*), definição formal de grão analítico, medidas aditivas/não-aditivas e Star Schema. |
| [`03_ENGENHARIA_FISICA_E_TUNING_SGBD.md`](03_ENGENHARIA_FISICA_E_TUNING_SGBD.md) | **Performance, Física de Dados e Otimização** | Particionamento declarativo por ano, índices GiST/GIN (`pg_trgm`), busca vetorial HNSW (`pgvector`) e planos de execução (`EXPLAIN ANALYZE`). |
| [`04_DICIONARIO_DE_DADOS_CATALOGO_ATIVO.md`](04_DICIONARIO_DE_DADOS_CATALOGO_ATIVO.md) | **Governança e Metadados do SGBD** | Ficha técnica completa de todos os esquemas (`silver` e `gold`), tipos de dados físicos, constraints `CHECK`, chaves primárias e integridade referencial. |

---

## Visão Geral da Arquitetura em Camadas

```
+-------------------------------------------------------------------------------+
|                       FONTE PRIMÁRIA: PORTAL DADOS.UNB.BR                     |
|            Extratos do SIGRA, SIGAA, Matrizes Curriculares, Censo INEP        |
+---------------------------------------+---------------------------------------+
                                        | (Ingestão Programática / API CKAN)
                                        v
+-------------------------------------------------------------------------------+
|                          SGBD POSTGRESQL / SUPABASE                           |
|                                                                               |
|  [ SCHEMA bronze ] Staging Imutável (Raw Data)                                |
|  +-------------------------------------------------------------------------+  |
|  | Cargas brutas sem tipagem, auditoria de hashes e integridade de origem. |  |
|  +------------------------------------+------------------------------------+  |
|                                       | (Transformação ELT in-Database)       |
|                                       v                                       |
|  [ SCHEMA silver ] Modelo Relacional Normalizado em 3NF                       |
|  +-------------------------------------------------------------------------+  |
|  | - silver.discentes (Pessoas físicas únicas com pseudônimo UK / LGPD)    |  |
|  | - silver.cursos (Catálogo canônico normalizado em 3NF)                  |  |
|  | - silver.estruturas_curriculares (Matrizes e prazos regulamentares)     |  |
|  | - silver.movimentacoes_vinculos (PARTITION BY RANGE [ano_ingresso])     |  |
|  | - silver.pibic_projetos (Planos de pesquisa com integridade referencial)|  |
|  +------------------------------------+------------------------------------+  |
|                                       | (Agregações e Joins Dimensionais)     |
|                                       v                                       |
|  [ SCHEMA gold ] Modelagem Dimensional em Star Schema (Kimball)               |
|  +-------------------------------------------------------------------------+  |
|  | - Dimensões Conformadas: dim_curso (SCD 2), dim_campus, dim_tempo, dim_perfil_social |
|  | - Tabelas Fato: fato_retencao_curso, fato_alunos_ativos, fato_pibic_perfil |
|  | - View Materializada Concorrente: mv_dashboard_executivo (0,065 ms)     |  |
|  +------------------------------------+------------------------------------+  |
|                                       |                                       |
|  [ SCHEMA busca ] Inteligência Vetorial com pgvector                          |
|  +-------------------------------------------------------------------------+  |
|  | Embeddings de 384 dimensões (MiniLM-L12) indexados com HNSW               |  |
|  +-------------------------------------------------------------------------+  |
+---------------------------------------+---------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
|                 INTERFACE DE DECISÃO: STREAMLIT / GITHUB PAGES                |
|           Consumo sub-milissegundo via View Materializada e Busca Semântica   |
+-------------------------------------------------------------------------------+
```

---

## Camadas acrescentadas na E2 e na E3

O diagrama acima é o núcleo relacional. Em volta dele, o projeto ganhou:

- **Lago em formato aberto (E2):** a Silver 3NF e o Star Schema exportados para Delta Lake sobre Parquet com ZSTD, particionados por quinquênio de ingresso, em `data/lake/lote/` ([ADR 0024](../adr/0024-lago-delta-parquet-zstd.md)). Um segundo caminho opcional leva as mudanças do WAL ao lago por CDC, com Debezium e Kafka ([ADR 0025](../adr/0025-mecanismo-de-ingestao-recarga-e-cdc.md)).
- **Camada transformada em dbt (E3):** `transform/` reconstrói a camada de consumo a partir da Silver 3NF em quatro esquemas: `dbt_staging`, `dbt_intermediate`, `dbt_marts` (fato, dimensões e `painel_cursos_criticos`) e `dbt_snapshots` (histórico da `dim_curso`). Ver o [ADR 0029](../adr/0029-transformacoes-em-dbt.md) e [`docs/testes_de_dados.md`](../testes_de_dados.md).
- **Orquestração (E3):** um grafo de assets do Dagster com retry e backfill ([`docs/orquestracao.md`](../orquestracao.md), [ADR 0030](../adr/0030-modelagem-analitica-e-ferramentas.md)).
- **Frescor:** SLA de 35 dias para a view do painel ([`docs/frescor_sla.md`](../frescor_sla.md)).
