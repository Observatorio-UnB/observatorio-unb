# Modelagem Dimensional OLAP e a Matriz de Kimball (Camada Gold)

> **Autor**: Equipe Observatório UnB  
> **Disciplina**: Banco de Dados 2 — Universidade de Brasília  
> **Referência Técnica**: *The Data Warehouse Toolkit: The Definitive Guide to Dimensional Modeling* (Ralph Kimball & Margy Ross, 3ª Edição)

---

## 1. A Matriz de Barramento Corporativo (Enterprise Bus Matrix)

Na engenharia de dados analíticos, a consistência de um Data Lakehouse depende do compartilhamento de **Dimensões Conformadas** entre múltiplos processos de negócio. A matriz abaixo mapeia os processos centrais da graduação da UnB contra as dimensões analíticas padronizadas no catálogo PostgreSQL:

| Processo de Negócio (Linha da Matriz) | dim_curso | dim_campus | dim_tempo | dim_perfil_social | Tabela Fato Gerada | Grão Analítico Declarado |
|:---|:---:|:---:|:---:|:---:|:---|:---|
| **1. Retenção e Formatura Histórica** | **X** | **X** | | | `gold.fato_retencao_curso` | Um registro por Curso por Campus sobre Coortes Maduras |
| **2. Alunos Cursando no Presente** | **X** | | **X** | | `gold.fato_alunos_ativos` | Um registro por Curso no Semestre de Referência Vigente |
| **3. Inclusão Social na Ciência (PIBIC)**| **X** | | | **X** | `gold.fato_pibic_perfil` | Um registro por Curso por Perfil Social do Bolsista |

*Legenda: **X** indica que o processo de negócio consome a dimensão conformada compartilhada.*

> **Nota sobre o Censo da Educação Superior (INEP)**: Os dados de benchmark externo com outras Instituições Federais de Ensino Superior (IFES) são disponibilizados em tabela tabular de referência analítica (`gold.inep_benchmark_cursos_unb`), sem relacionamento dimensional direto via chave estrangeira no Star Schema.

---

## 2. Diagrama Estrutural do Star Schema (Esquema Estrela)

O esquema estrela desacopla as métricas numéricas das entidades de contexto, permitindo fatiamentos multidimensionais (*slicing and dicing*) de alta performance centrados na dimensão conformada `gold.dim_curso`:

```text
       +------------------------------------+
       |          gold.dim_campus           |
       +------------------------------------+
       | PK  sk_campus (INTEGER)            |
       | UK  campus (TEXT)                  |
       |     regiao_admin (TEXT)            |
       |     municipio (TEXT)               |
       +-----------------+------------------+
                         |
                         | 1
                         |
                         | N
+------------------------v-------------------------+       +------------------------------------+
|             gold.fato_retencao_curso             |       |           gold.dim_curso           |
+--------------------------------------------------+       +------------------------------------+
| PK  id_fato (BIGINT)                             |  N  1 | PK  sk_curso (INTEGER)             |
| FK  sk_curso (INTEGER) --------------------------+------>| UK  nome_curso (TEXT)              |
| FK  sk_campus (INTEGER)                          |       |     id_curso_origem (INTEGER)      |
|     total_ingressantes (INT, CHECK >= 5)         |       |     grau_academico (TEXT)          |
|     total_formados (INT, CHECK >= 0)             |       |     categoria_grau (TEXT)          |
|     total_evadidos (INT, CHECK >= 0)             |       |     area_conhecimento (TEXT)       |
|     total_ainda_ativos (INT, CHECK >= 0)         |       |     departamento (TEXT)            |
|     taxa_formatura_pct (NUMERIC(5,2))            |       |     is_tronco_abi (BOOLEAN)        |
|     taxa_evasao_pct (NUMERIC(5,2))               |       +----+--------------------------+----+
|     formados_tempo_ideal_pct (NUMERIC(5,2))      |            |                          |
|     atraso_medio_semestres (NUMERIC(5,2))        |            | 1                        | 1
|     indice_retencao_critica (NUMERIC(4,1))       |            |                          |
|     classificacao_retencao (TEXT)                |            | N                        | N
|     atualizado_em (TIMESTAMPTZ)                  |            |                          |
+--------------------------------------------------+            |                          |
                                                                |                          |
+--------------------------------------------------+            |                          |
|             gold.fato_alunos_ativos              |            |                          |
+--------------------------------------------------+            |                          |
| PK  id_fato_ativo (BIGINT)                       |            |                          |
| FK  sk_curso (INTEGER, UNIQUE) ------------------+------------+                          |
| FK  sk_tempo_referencia (INTEGER) ---------------+                                       |
|     total_ativos (INT, CHECK >= 5)               |                                       |
|     ativos_acima_prazo_ideal (INT, CHECK >= 0)   |                                       |
|     ativos_acima_prazo_maximo (INT, CHECK >= 0)  |                                       |
|     pct_acima_prazo_ideal (NUMERIC(5,2))         |                                       |
|     atualizado_em (TIMESTAMPTZ)                  |                                       |
+------------------------+-------------------------+                                       |
                         |                                                                 |
                         | N                                                               |
                         |                                                                 |
                         | 1                                                               |
+------------------------v-------------------------+       +-------------------------------v----+
|                  gold.dim_tempo                  |       |        gold.fato_pibic_perfil      |
+--------------------------------------------------+       +------------------------------------+
| PK  sk_tempo (INTEGER, ex: 20241)                |       | PK  id_fato (BIGINT)               |
|     ano (SMALLINT)                               |       | FK  sk_curso (INTEGER)             |
|     semestre (SMALLINT, 1 ou 2)                  |       | FK  sk_perfil (INTEGER) -----------+
|     rotulo (TEXT, '2024/1')                      |       |     total_projetos (INT, >= 5)     |
|     decada (SMALLINT)                            |       |     total_remuneradas (INT, >= 0)  |
+--------------------------------------------------+       |     total_voluntarias (INT, >= 0)  |
                                                           |     valor_total_investido (NUMERIC)|
                                                           |     atualizado_em (TIMESTAMPTZ)    |
                                                           +-----------------+------------------+
                                                                             |
                                                                             | N
                                                                             |
                                                                             | 1
                                                           +-----------------v------------------+
                                                           |       gold.dim_perfil_social       |
                                                           +------------------------------------+
                                                           | PK  sk_perfil (INTEGER)            |
                                                           | UK  (perfil_macro, categoria_cota, |
                                                           |      faixa_renda, is_cotista)      |
                                                           +------------------------------------+
```

---

## 3. Tipologia Matemática das Medidas Analíticas

O projeto respeita rigorosamente a taxonomia de métricas dimensionais estabelecida por Kimball:

### 3.1. Medidas Totalmente Aditivas
Podem ser agregadas por soma ($\sum$) ao longo de **todas** as dimensões associadas:
* **Total Ingressantes** (`total_ingressantes`): $\sum (\text{vínculos de coortes maduras})$
* **Total Formados** (`total_formados`): $\sum (\text{vínculos concluídos com diploma})$
* **Total Evadidos** (`total_evadidos`): $\sum (\text{vínculos encerrados sem diploma})$
* **Total Projetos de IC** (`total_projetos`): $\sum (\text{planos de trabalho PIBIC/PIVIC})$
* **Bolsas Remuneradas e Voluntárias** (`total_remuneradas`, `total_voluntarias`): $\sum (\text{bolsas concedidas})$
* **Valor Total Investido em IC** (`valor_total_investido`): $\sum (\text{montante financeiro de fomento})$

### 3.2. Medidas Semi-Aditivas (Medidas de Estoque / Momento)
Podem ser somadas ao longo de algumas dimensões (curso), mas **nunca ao longo do tempo**:
* **Total de Alunos Ativos** (`total_ativos`): A soma dos ativos do curso de Medicina e Odontologia no semestre 2024/1 é válida. Porém, somar os ativos de 2023/2 com 2024/1 duplicaria a contagem do mesmo discente que permaneceu matriculado em semestres subsequentes.
* **Ativos Acima do Prazo Ideal e Máximo** (`ativos_acima_prazo_ideal`, `ativos_acima_prazo_maximo`): Contagens pontuais de discentes em risco retidos no semestre vigente.

### 3.3. Medidas Não-Aditivas (Cálculos de Intensidade e Proporção)
Não podem ser somadas sob nenhuma hipótese. O SGBD ou a camada de apresentação deve computar a razão das somas aditivas subjacentes:
* **Taxa de Evasão Global**:
  $$\text{Taxa de Evasão} = \frac{\sum \text{Evadidos}}{\sum \text{Ingressantes}} \times 100$$
* **Taxa de Formatura no Tempo Ideal**:
  $$\text{Taxa Ideal} = \frac{\sum \text{Formados no Prazo Ideal}}{\sum \text{Formados Totais}} \times 100$$
* **Percentual de Alunos Ativos em Atraso**:
  $$\text{Pct Acima do Ideal} = \frac{\sum \text{Ativos Acima do Prazo Ideal}}{\sum \text{Total de Ativos}} \times 100$$
* **Índice de Retenção Crítica (IRC)**:
  $$\mathrm{IRC} = 50\% \times \left( \frac{\text{Atraso} - \text{Atraso}_{\min}}{\text{Atraso}_{\max} - \text{Atraso}_{\min}} \right) + 50\% \times \left( \frac{\text{Evasão} - \text{Evasão}_{\min}}{\text{Evasão}_{\max} - \text{Evasão}_{\min}} \right)$$

---

## 4. O Grão da Decisão: Segregação por Processo de Negócio

Um dos erros mais comuns em análise universitária é misturar discentes recém-ingressos com discentes que já tiveram tempo regulamentar suficiente para se formar (o chamado **Viés de Maturação**).

O nosso Star Schema resolve essa armadilha acadêmica separando três Tabelas Fato especializadas:
1. **`fato_retencao_curso` (Histórico de Coortes Maduras)**:
   * **Grão**: Coortes de ingresso com pelo menos **8 anos de percurso** (`ano_ingresso` $\le 2016$).
   * **Finalidade**: Avaliar a taxa real de conclusão, jubilamento e evasão consolidada sem interferência de matrículas ativas recentes.
2. **`fato_alunos_ativos` (O Momento Presente)**:
   * **Grão**: Snapshot de discentes com matrícula regular ativa no semestre mais recente (2024/1).
   * **Finalidade**: Identificar estudantes que estão estourando o prazo máximo regulamentar hoje, permitindo intervenção pedagógica preventiva do DEG/DAA.
3. **`fato_pibic_perfil` (Fomento e Inclusão Social na Pesquisa)**:
   * **Grão**: Agregação de planos de Iniciação Científica por curso canônico e estrato de perfil social/ações afirmativas.
   * **Finalidade**: Mensurar a democratização da pesquisa acadêmica e o impacto das bolsas na permanência universitária, sob salvaguarda estrita de $k$-anonimato ($k \ge 5$).

