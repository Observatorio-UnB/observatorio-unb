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
| FK  sk_curso (INTEGER, UNIQUE) ------------------+------>| UK  nome_curso, vigente_de         |
| FK  sk_campus (INTEGER)                          |       |     id_curso_origem (INT, tipo 1)  |
|     total_ingressantes (INT, CHECK >= 5)         |       |     grau_academico (TEXT)          |
|     total_formados (INT, CHECK >= 0)             |       |     categoria_grau (TEXT)          |
|     total_evadidos (INT, CHECK >= 0)             |       |     area_conhecimento (TEXT)       |
|     total_ainda_ativos (INT, CHECK >= 0)         |       |     departamento (TEXT)            |
|     taxa_formatura_pct (NUMERIC(5,2))            |       |     is_tronco_abi (BOOLEAN)        |
|     taxa_evasao_pct (NUMERIC(5,2))               |       |     vigente_de (TIMESTAMPTZ)       |
|     formados_tempo_ideal_pct (NUMERIC(5,2))      |       |     vigente_ate (TIMESTAMPTZ)      |
|     atraso_medio_semestres (NUMERIC(5,2))        |       |     is_atual (BOOLEAN)             |
|     indice_retencao_critica (NUMERIC(4,1))       |       +----+--------------------------+----+
|     classificacao_retencao (TEXT)                |            | 1                        | 1
|     atualizado_em (TIMESTAMPTZ)                  |            | N                        | N
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
  $$\mathrm{IRC} = \left[ 0{,}3 \times \left( \frac{\text{Atraso} - \text{Atraso}_{\min}}{\text{Atraso}_{\max} - \text{Atraso}_{\min}} \right) + 0{,}7 \times \left( \frac{\text{Evasão} - \text{Evasão}_{\min}}{\text{Evasão}_{\max} - \text{Evasão}_{\min}} \right) \right] \times 100$$

  Antes da normalização, cada termo é saturado nos percentis 5 e 95, para um curso extremo não achatar os demais, e o atraso negativo conta como zero ([ADR 0006](../adr/0006-indice-retencao-critica.md); `gold.atualizar_gold` na migração 0022 e `int_irc_curso` no dbt).

---

## 4. O Grão da Decisão: Segregação por Processo de Negócio

Um dos erros mais comuns em análise universitária é misturar discentes recém-ingressos com discentes que já tiveram tempo regulamentar suficiente para se formar (o chamado **Viés de Maturação**).

O nosso Star Schema resolve essa armadilha acadêmica separando três Tabelas Fato especializadas. O grão de cada uma está escrito no catálogo (`COMMENT ON TABLE`, migração 0023), sai no dicionário de dados e é imposto por uma chave única igual a ele:

| Fato | Grão | Chave do grão | Linhas na carga de 11/2026 |
|:---|:---|:---|---:|
| `fato_retencao_curso` | Um registro por curso canônico, sobre as coortes maduras | `UNIQUE (sk_curso)` | 95 |
| `fato_alunos_ativos` | Um registro por curso canônico no semestre da lista de ativos mais recente (snapshot) | `UNIQUE (sk_curso)` | 95 |
| `fato_pibic_perfil` | Um registro por curso canônico e perfil social do bolsista, somando todos os editais | `UNIQUE (sk_curso, sk_perfil)` | 286 |

1. **`fato_retencao_curso` (Histórico de Coortes Maduras)**:
   * **Grão**: um registro por curso canônico, agregando as coortes de ingresso com pelo menos **8 anos de percurso** (`ano_ingresso` até o último ano da base menos 8; na carga de 11/2026, de 2010 a 2016). O campus é atributo do curso (MULTICAMPUS quando o nome é oferecido em mais de um campus), e não parte do grão.
   * **Finalidade**: Avaliar a taxa real de conclusão, jubilamento e evasão consolidada sem interferência de matrículas ativas recentes.
2. **`fato_alunos_ativos` (O Momento Presente)**:
   * **Grão**: snapshot de discentes com matrícula regular ativa, um registro por curso no semestre da lista de ativos mais recente publicada (`sk_tempo_referencia`; na carga de 11/2026, 2025/1). A carga substitui o snapshot, sem histórico.
   * **Finalidade**: Identificar estudantes que estão estourando o prazo máximo regulamentar hoje, permitindo intervenção pedagógica preventiva do DEG/DAA.
3. **`fato_pibic_perfil` (Fomento e Inclusão Social na Pesquisa)**:
   * **Grão**: Agregação de planos de Iniciação Científica por curso canônico e estrato de perfil social/ações afirmativas.
   * **Finalidade**: Mensurar a democratização da pesquisa acadêmica e o impacto das bolsas na permanência universitária, sob salvaguarda estrita de $k$-anonimato ($k \ge 5$).

### 4.1 Por que a chave do fato de retenção é só o curso

Até a migração 0023, a chave de `fato_retencao_curso` era `UNIQUE (sk_curso, sk_campus)`, mais larga que o grão. Ela aceitava o mesmo curso em dois campi, e a view do painel, que lê o fato por curso, mostraria o curso duas vezes, com as contagens repetidas.

No banco local isso não acontece, porque o fato é recriado a cada carga. Mas a sincronização com o Supabase (`src/db/sincronizar_supabase.py`) faz upsert pela chave e nunca apaga linhas. Um curso que mudasse de campus ganharia uma segunda linha. O caso foi reproduzido com um segundo banco local fazendo o papel do Supabase: com a chave antiga, Ciência da Computação passou de DARCY RIBEIRO para MULTICAMPUS e ficou com 2 linhas no fato e 2 na view. Com a chave do grão, a sincronização atualiza o campus da linha que já existe. A migração 0023 remove duplicatas que já existam no destino, mantendo a atualizada por último, antes de criar a chave.

### 4.2 Avaliação de outros níveis de grão

O grão de decisão foi comparado com dois mais finos, sobre os mesmos vínculos das coortes maduras (carga de 11/2026, 68.339 vínculos de 2010 a 2016). Uma célula com menos de 5 vínculos é suprimida (k-anonimato).

| Grão | Células | Células com k ≥ 5 | Vínculos suprimidos | Mediana de vínculos por célula |
|:---|---:|---:|---:|---:|
| **Curso (atual)** | 101 | 95 | 12 (0,02%) | 588 |
| Curso × coorte (ano de ingresso) | 633 | 597 | 76 (0,11%) | 90 |
| Curso × coorte × semestre de ingresso | 633 | 597 | 76 (0,11%) | 90 |

* **Curso × coorte × semestre de ingresso não existe nos dados.** `semestre_ingresso` é nulo nos 152.680 vínculos, porque o SIGRA e o SIGAA publicam só o ano de ingresso (achado de qualidade do relatório da Semana 1). Esse grão é o mesmo que curso × coorte.
* **Curso × coorte é viável pela privacidade** (só 0,11% suprimido), **mas não serve à decisão.** A taxa de evasão do mesmo curso varia, na mediana, 18 pontos percentuais entre as 7 coortes, e 33 dos 77 cursos com as 7 coortes variam 20 pontos ou mais. Com mediana de 90 vínculos por célula, boa parte dessa variação é ruído amostral. Um ranking de intervenção por coorte trocaria de curso de um ano para o outro.
* **O grão por coorte expõe o viés de maturação dentro da janela madura.** A coorte de 2016 ainda tem 9,3% de vínculos ativos (contra 0,1% na de 2010), e por isso a evasão dela parece menor (39,7% contra 43% a 47% nas anteriores). No grão do curso, esse efeito se dilui nas 7 coortes.

| Coorte | Cursos com k ≥ 5 | Vínculos por curso (média) | Evasão média | Ainda ativos (média) |
|---:|---:|---:|---:|---:|
| 2010 | 80 | 112 | 42,9% | 0,1% |
| 2011 | 82 | 125 | 46,5% | 0,3% |
| 2012 | 83 | 109 | 44,9% | 0,7% |
| 2013 | 83 | 111 | 43,6% | 2,1% |
| 2014 | 88 | 121 | 46,6% | 2,7% |
| 2015 | 89 | 110 | 43,2% | 5,5% |
| 2016 | 92 | 113 | 39,7% | 9,3% |

**Decisão:** o fato de retenção fica no grão do curso, que é o grão da pergunta da E1 ("quais cursos apresentam os maiores índices de retenção?", `docs/challenge_canvas.md`). Uma linha por curso responde o ranking do IRC sem dupla agregação. O grão curso × coorte fica registrado como candidato a um segundo fato, para tendência entre coortes, e não para o ranking. A escolha da modelagem está no [ADR 0030](../adr/0030-modelagem-analitica-e-ferramentas.md), que mede quatro grãos.
