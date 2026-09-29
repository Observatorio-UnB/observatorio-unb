# Dicionário de Dados e Catálogo Ativo de Metadados

> **Universidade de Brasília (UnB)**  
> **Disciplina**: Banco de Dados 2  
> **Camada**: Catálogo Ativo do SGBD (PostgreSQL 17 — Supabase & PostgreSQL 16 — Docker)  
> **Esquemas**: `silver` (3NF Operacional & Físico) e `gold` (Star Schema Analítico)

---

## 1. Visão Geral do Catálogo

Este documento constitui o **Dicionário de Dados Oficial e Ativo** do Observatório UnB. Cada tabela, coluna, tipo de dado físico, restrição de integridade e valor padrão documentados abaixo refletem **com exatidão cirúrgica (1:1)** o catálogo do SGBD (`information_schema` e `pg_catalog`) em produção.

O catálogo está estruturado em três níveis de abstração conforme a **Arquitetura ANSI/SPARC de SGBD**:
1. **Camada Silver (Modelo Lógico Canônico em 3NF)**: 5 relações essenciais com integridade referencial estrita e ausência de redundâncias;
2. **Camada Silver (Mapeamento Físico do PostgreSQL)**: 4 partições declarativas (`movimentacoes_p*`) e 6 tabelas de carga, staging e auditoria de dados brutos;
3. **Camada Gold (Modelo Dimensional OLAP - Kimball)**: 4 dimensões conformadas, 3 tabelas fato granulares, 6 tabelas de governança/relatórios e 1 visão materializada executiva indexada.

---

## 2. Camada Silver: Modelo Lógico Canônico (3ª Forma Normal)

### 2.1 Tabela `silver.discentes`
* **Descrição**: Cadastro de pessoas físicas únicas que possuem ou possuíram vínculo de graduação na UnB.
* **Privacidade / LGPD**: Utiliza `pseudonimo` gerado institucionalmente, protegendo quase-identificadores sob princípio do privilégio mínimo.

| Coluna | Tipo Físico | Nulo? | Padrão / Restrição | Descrição Semântica |
|:---|:---|:---:|:---:|:---|
| `id_discente` | `BIGINT` | **NÃO** | **PK** (`GENERATED ALWAYS AS IDENTITY`) | Identificador numérico sintético do discente no ecossistema relacional. |
| `pseudonimo` | `TEXT` | **NÃO** | **UK** (`UNIQUE`) | Pseudônimo mascarado original do sistema acadêmico. Garante unicidade e impede reidentificação. |
| `data_nascimento` | `DATE` | SIM | - | Data de nascimento para cálculo de faixa etária agregada. |
| `sexo` | `CHAR(1)` | SIM | `CHECK (sexo IN ('F', 'M'))` | Sexo biológico registrado no ato do vestibular/PAS. |
| `raca_cor` | `TEXT` | SIM | - | Raça/cor autodeclarada pelo estudante. |
| `criado_em` | `TIMESTAMPTZ` | **NÃO** | `DEFAULT now()` | Carimbo temporal de inserção do registro. |

---

### 2.2 Tabela `silver.cursos`
* **Descrição**: Catálogo canônico de cursos de graduação da UnB normalizado em 3NF. Elimina a repetição de campus, turno e grande área.
* **Índice Especializado**: `idx_cursos_nome_trgm` utilizando GIN com operador de trigramas (`gin_trgm_ops`) sobre `nome_curso_norm`.

| Coluna | Tipo Físico | Nulo? | Padrão / Restrição | Descrição Semântica |
|:---|:---|:---:|:---:|:---|
| `id_curso` | `INTEGER` | **NÃO** | **PK** | Código numérico primário do curso (origem: SIGRA/SIGAA). |
| `codigo_sigaa` | `TEXT` | SIM | - | Código alfanumérico institucional no SIGAA. |
| `nome_curso_norm` | `TEXT` | **NÃO** | - | Denominação canônica normalizada (sem acentos duplicados/caixa alta). |
| `campus` | `TEXT` | **NÃO** | - | Campus universitário (Darcy Ribeiro, Planaltina, Ceilândia, Gama). |
| `turno` | `TEXT` | **NÃO** | `CHECK (turno IN ('DIURNO', 'NOTURNO', 'INTEGRAL', 'DIURNO E NOTURNO', 'MATUTINO', 'VESPERTINO', 'MATUTINO E VESPERTINO'))` | Turno de funcionamento acadêmico regulamentar (7 valores aceitos). |
| `grau_academico` | `TEXT` | **NÃO** | - | Grau conferido (Bacharelado, Licenciatura). |
| `categoria_grau` | `TEXT` | **NÃO** | `CHECK (categoria_grau IN ('BACHARELADO', 'LICENCIATURA', 'MISTO'))` | Agrupamento de grau acadêmico. |
| `area_conhecimento`| `TEXT` | **NÃO** | - | Grande área do saber segundo taxonomia CAPES/CNPq. |
| `departamento` | `TEXT` | SIM | - | Unidade acadêmica de lotação pedagógica. |
| `is_tronco_abi` | `BOOLEAN` | **NÃO** | `DEFAULT false` | Indicador de Área Básica de Ingresso (ABI - Engenharias Gama). |
| `ativo` | `BOOLEAN` | **NÃO** | `DEFAULT true` | Situação de oferta ativa na graduação da UnB. |

---

### 2.3 Tabela `silver.estruturas_curriculares`
* **Descrição**: Prazos e cargas horárias regulamentares de cada matriz curricular aprovada pelo CEPE/UnB por curso canônico.

| Coluna | Tipo Físico | Nulo? | Padrão / Restrição | Descrição Semântica |
|:---|:---|:---:|:---:|:---|
| `id_estrutura` | `INTEGER` | **NÃO** | **PK** (`GENERATED ALWAYS AS IDENTITY`) | Identificador sequencial da versão de matriz curricular. |
| `nome_curso_canonico` | `TEXT` | **NÃO** | **UK** (`UNIQUE`) | Nome canônico harmonizado do curso. Destino da harmonização SIGRA/SIGAA/PIBIC e chave natural de `gold.dim_curso`. |
| `id_curso` | `INTEGER` | **NÃO** | **FK** $\rightarrow$ `silver.cursos(id_curso)` | Curso do catálogo dono da matriz (pode ter outro nome institucional). |
| `semestre_minimo` | `NUMERIC(4,1)` | **NÃO** | `CHECK (semestre_minimo > 0)` | Prazo mínimo de semestres letivos para formatura antecipada. |
| `semestre_ideal` | `NUMERIC(4,1)` | **NÃO** | `CHECK (semestre_ideal >= semestre_minimo)` | Tempo padrão recomendado para integralização curricular. |
| `semestre_maximo` | `NUMERIC(4,1)` | **NÃO** | - | Prazo limite regulamentar antes do desligamento por jubilamento. |
| `ch_total_minima` | `INTEGER` | SIM | `CHECK (ch_total_minima >= 0)` | Carga horária total obrigatória exigida para colação de grau. |
| `cr_total_minimo` | `INTEGER` | SIM | `CHECK (cr_total_minimo >= 0)` | Total de créditos mínimos necessários. |

* **Restrições de Unicidade**: `CONSTRAINT estruturas_curriculares_nome_curso_canonico_key UNIQUE (nome_curso_canonico)` e `CONSTRAINT uk_curso_estrutura UNIQUE (id_curso, semestre_ideal)`.
* **Ação Referencial**: `ON DELETE RESTRICT` na chave estrangeira de curso.

---

### 2.4 Tabela `silver.movimentacoes_vinculos` (Tabela Lógica Particionada)
* **Descrição**: Fato operacional com o histórico de cada matrícula/vínculo do aluno, particionado por ano de ingresso.
* **Estratégia Física de SGBD**: `PARTITION BY RANGE (ano_ingresso)`.

| Coluna | Tipo Físico | Nulo? | Padrão / Restrição | Descrição Semântica |
|:---|:---|:---:|:---:|:---|
| `id_vinculo` | `BIGINT` | **NÃO** | **PK** (composta com `ano_ingresso`) | Identificador sintético da movimentação acadêmica. |
| `id_discente` | `BIGINT` | **NÃO** | **FK** $\rightarrow$ `silver.discentes(id_discente)` | Discente titular do vínculo (`ON DELETE RESTRICT`). |
| `id_curso` | `INTEGER` | **NÃO** | **FK** $\rightarrow$ `silver.cursos(id_curso)` | Curso cursado durante o vínculo (`ON DELETE RESTRICT`). |
| `id_estrutura` | `INTEGER` | **NÃO** | **FK** $\rightarrow$ `silver.estruturas_curriculares(id_estrutura)` | Matriz curricular canônica do vínculo (`ON DELETE NO ACTION`). |
| `ano_ingresso` | `SMALLINT` | **NÃO** | **PK** / Chave de Partição | Ano civil de ingresso na UnB (ex: 2018). |
| `semestre_ingresso`| `SMALLINT` | SIM | `CHECK (semestre_ingresso IN (0, 1, 2))` | Semestre de admissão (0=verão, 1=1º sem, 2=2º sem). Nulo na série histórica bruta. |
| `forma_saida` | `TEXT` | SIM | - | Descrição textual da saída (ex: Formatura, Desligamento Voluntário). |
| `tipo_saida_grupo` | `TEXT` | **NÃO** | `CHECK IN ('FORMATURA','EVASAO','ATIVO','OUTROS')` | Macro-classificação da situação do vínculo. |
| `ano_saida` | `SMALLINT` | SIM | - | Ano civil do encerramento do vínculo. |
| `semestre_saida` | `SMALLINT` | SIM | `CHECK (semestre_saida IN (0, 1, 2))` | Semestre letivo de conclusão ou desligamento. |
| `semestres_permanencia` | `SMALLINT`| SIM | - | Quantidade total de semestres letivos em que o discente esteve vinculado. |
| `semestres_permanencia_valida`| `SMALLINT`| SIM | `CHECK (semestres_permanencia_valida BETWEEN 1 AND 35)` | Filtro sanitizado de permanência válida para evitar *outliers*. |
| `periodo_saida_estimado` | `BOOLEAN` | **NÃO** | `DEFAULT false` | Indicador se o ano/semestre de saída foi inferido por algoritmo. |
| `status_aluno` | `TEXT` | SIM | - | Estado descritivo textual original do sistema acadêmico. |
| `fonte` | `TEXT` | **NÃO** | `CHECK (fonte IN ('SIGRA', 'SIGAA'))` | Sistema de origem dos dados de registro acadêmico. |

---

### 2.5 Tabela `silver.pibic_projetos`
* **Descrição**: Planos de pesquisa de Iniciação Científica e Tecnológica normalizados em 3NF, associando o projeto à matriz do curso canônico.

| Coluna | Tipo Físico | Nulo? | Padrão / Restrição | Descrição Semântica |
|:---|:---|:---:|:---:|:---|
| `id_projeto` | `BIGINT` | **NÃO** | **PK** (`GENERATED ALWAYS AS IDENTITY`) | Identificador primário unívoco do projeto de pesquisa. |
| `id_discente` | `BIGINT` | SIM | **FK** $\rightarrow$ `silver.discentes(id_discente)` | Vínculo discente (nulo na carga devido à minimização LGPD de matrículas). |
| `id_curso` | `INTEGER` | SIM | **FK** $\rightarrow$ `silver.cursos(id_curso)` | Curso de graduação dono da matriz. |
| `id_estrutura` | `INTEGER` | SIM | **FK** $\rightarrow$ `silver.estruturas_curriculares(id_estrutura)` | Matriz curricular canônica do curso do bolsista. |
| `ano_edital` | `SMALLINT` | **NÃO** | - | Ano do edital institucional da Diretoria de Fomento à IC (DPG/UnB). |
| `tipo_bolsa` | `TEXT` | **NÃO** | `CHECK (tipo_bolsa IN ('REMUNERADA', 'VOLUNTARIA', 'NAO INFORMADO'))` | Modalidade de fomento da bolsa de IC. |
| `linha_pesquisa` | `TEXT` | SIM | - | Linha temática de pesquisa declarada pelo orientador. |
| `is_cotista` | `BOOLEAN` | **NÃO** | - | Indicador se o discente ingressou na UnB por política de cotas. |
| `cota_detalhe` | `TEXT` | SIM | - | Modalidade detalhada de cota (PPI, Escola Pública, Renda Inferior). |
| `faixa_renda` | `TEXT` | SIM | - | Faixa socioeconômica declarada no cadastro de assistência social. |
| `perfil_social_macro` | `TEXT` | SIM | - | Classificação agregada de perfil social (origem de `gold.dim_perfil_social`). |
| `valor_bolsa_total`| `NUMERIC(10,2)`| **NÃO** | `DEFAULT 0.00 CHECK (valor_bolsa_total >= 0)` | Montante financeiro pago ao longo da vigência do edital. |
| `titulo_pesquisa` | `TEXT` | **NÃO** | - | Título acadêmico do plano de trabalho de IC. |
| `status_projeto` | `TEXT` | SIM | - | Situação de homologação e entrega do relatório final no Decanato. |

---

## 3. Camada Silver: Mapeamento Físico e Partições no Catálogo do SGBD

O PostgreSQL gerencia tabelas particionadas criando relações físicas filhas no catálogo `pg_class`. No total, existem **15 tabelas físicas** no schema `silver`:

```
+-----------------------------------------------------------------------------------------+
|                    MAPEAMENTO FÍSICO DO SGBD: TABELAS CANÔNICAS VS FILHAS               |
+--------------------------+-----------------------+--------------------------------------+
| Tabela no Catálogo Físico| Tipo de Estrutura     | Finalidade de Engenharia             |
+--------------------------+-----------------------+--------------------------------------+
| `discentes`              | Tabela Base Canônica  | Relação 3NF de indivíduos únicos     |
| `cursos`                 | Tabela Base Canônica  | Relação 3NF com índice GIN Trigram   |
| `estruturas_curriculares`| Tabela Base Canônica  | Relação 3NF de matrizes pedagógicas  |
| `movimentacoes_vinculos` | Tabela Particionada   | Tabela-mãe declarativa (Lógica)      |
| `movimentacoes_p2000_2015`| Partição Física Filha | Bucket de dados históricos (2000-2015)|
| `movimentacoes_p2016_2020`| Partição Física Filha | Bucket de coortes maduras (2016-2020)|
| `movimentacoes_p2021_atual`| Partição Física Filha| Bucket de coortes recentes (2021-2035)|
| `movimentacoes_p_default`| Partição Física Filha | Bucket default de salvaguarda        |
| `pibic_projetos`         | Tabela Base Canônica  | Relação 3NF de projetos de pesquisa  |
| `cursos_graduacao`       | Staging / Origem      | Catálogo bruto de cursos             |
| `discentes_graduacao`    | Staging / Origem      | Base unificada histórica de discentes|
| `estrutura_curricular`   | Staging / Origem      | Matrizes curriculares brutas         |
| `inep_censo_superior`    | Staging / Origem      | Dados do Censo da Educação Superior  |
| `pibic_bolsistas`        | Staging / Auditoria   | Relação legada para auditoria da IC  |
| `sigaa_ativos`           | Staging / Origem      | Extrato de alunos ativos do SIGAA    |
+--------------------------+-----------------------+--------------------------------------+
```

---

## 4. Camada Gold: Modelo Dimensional (Star Schema de Kimball)

### 4.1 Dimensão `gold.dim_curso`
* **Tipo**: Dimensão Conformada (SCD Tipo 1).
* **Chave Natural Única**: `nome_curso TEXT NOT NULL UNIQUE`. A surrogate key `sk_curso` não muda ao inserir cursos.

| Coluna | Tipo Físico | Nulo? | Padrão / Restrição | Descrição Semântica |
|:---|:---|:---:|:---:|:---|
| `sk_curso` | `INTEGER` | **NÃO** | **PK** (`GENERATED ALWAYS AS IDENTITY`) | Chave substituta (*Surrogate Key*) dimensional. |
| `nome_curso` | `TEXT` | **NÃO** | **UK** (`UNIQUE`) | Nome canônico do curso (chave natural da dimensão). |
| `id_curso_origem` | `INTEGER` | SIM | - | Identificador numérico do curso dono da matriz no catálogo. |
| `grau_academico` | `TEXT` | **NÃO** | - | Bacharelado vs Licenciatura. |
| `categoria_grau` | `TEXT` | **NÃO** | `CHECK (categoria_grau IN ('BACHARELADO', 'LICENCIATURA', 'MISTO'))` | Categoria agregada de titulação. |
| `area_conhecimento`| `TEXT` | **NÃO** | - | Grande área acadêmica. |
| `departamento` | `TEXT` | SIM | - | Departamento de lotação. |
| `is_tronco_abi` | `BOOLEAN` | **NÃO** | `DEFAULT false` | Indicador de curso de tronco comum (Área Básica de Ingresso). |

---

### 4.2 Dimensão `gold.dim_campus`
* **Tipo**: Dimensão Organizacional e Geográfica.

| Coluna | Tipo Físico | Nulo? | Padrão / Restrição | Descrição Semântica |
|:---|:---|:---:|:---:|:---|
| `sk_campus` | `INTEGER` | **NÃO** | **PK** (`GENERATED ALWAYS AS IDENTITY`) | Chave substituta do campus. |
| `campus` | `TEXT` | **NÃO** | **UK** (`UNIQUE`) | Nome oficial do campus (Darcy Ribeiro, FGA, FCE, FUP). |
| `regiao_admin` | `TEXT` | **NÃO** | - | Região Administrativa do Distrito Federal. |
| `municipio` | `TEXT` | **NÃO** | `DEFAULT 'Brasília'::text` | Município sede da unidade federativa. |

---

### 4.3 Dimensão `gold.dim_tempo`
* **Tipo**: Dimensão Temporal do Calendário Acadêmico.

| Coluna | Tipo Físico | Nulo? | Padrão / Restrição | Descrição Semântica |
|:---|:---|:---:|:---:|:---|
| `sk_tempo` | `INTEGER` | **NÃO** | **PK** | Código compacto no formato `AAAAS` (ex: 20241 para 2024/1). |
| `ano` | `SMALLINT` | **NÃO** | - | Ano calendário civil. |
| `semestre` | `SMALLINT` | **NÃO** | `CHECK (semestre IN (1, 2))` | Semestre letivo acadêmico. |
| `rotulo` | `TEXT` | **NÃO** | - | Rótulo formatado para gráficos (ex: '2024/1'). |
| `decada` | `SMALLINT` | **NÃO** | - | Ano base da década (ex: 2020 para os anos 2020 a 2029). |

---

### 4.4 Dimensão `gold.dim_perfil_social`
* **Tipo**: Dimensão Demográfica de Inclusão e Ações Afirmativas.
* **Restrição de Unicidade**: `UNIQUE NULLS NOT DISTINCT (perfil_macro, categoria_cota, faixa_renda, is_cotista)`.

| Coluna | Tipo Físico | Nulo? | Padrão / Restrição | Descrição Semântica |
|:---|:---|:---:|:---:|:---|
| `sk_perfil` | `INTEGER` | **NÃO** | **PK** (`GENERATED ALWAYS AS IDENTITY`) | Chave substituta do perfil social. |
| `perfil_macro` | `TEXT` | **NÃO** | - | Classificação agregada (Ampla Concorrência, Cota PPI, Cota Escola Pública). |
| `categoria_cota` | `TEXT` | **NÃO** | - | Modalidade detalhada da política de cotas (Lei nº 12.711/2012). |
| `faixa_renda` | `TEXT` | SIM | - | Estrato socioeconômico per capita do estudante. |
| `is_cotista` | `BOOLEAN` | **NÃO** | - | Flag booleano de admissão por ação afirmativa. |

---

### 4.5 Tabela Fato `gold.fato_retencao_curso`
* **Tipo**: Fato de *Snapshot de Coortes Maduras*.
* **Grão Físico**: Um registro por par `(sk_curso, sk_campus)`.
* **Privacidade e LGPD**: Constraint declarativa de $k$-anonimato estrito (`CHECK (total_ingressantes >= 5)`).

| Coluna | Tipo Físico | Nulo? | Padrão / Restrição | Descrição Semântica |
|:---|:---|:---:|:---:|:---|
| `id_fato` | `BIGINT` | **NÃO** | **PK** (`GENERATED ALWAYS AS IDENTITY`) | Identificador primário do registro de fato. |
| `sk_curso` | `INTEGER` | **NÃO** | **FK** $\rightarrow$ `gold.dim_curso` | Chave substituta para o curso em análise. |
| `sk_campus` | `INTEGER` | **NÃO** | **FK** $\rightarrow$ `gold.dim_campus` | Chave substituta para o campus universitário. |
| `total_ingressantes` | `INTEGER` | **NÃO** | `CHECK (total_ingressantes >= 5)` | **Métrica Aditiva**: Total de discentes ingressantes na coorte madura ($k \ge 5$). |
| `total_formados` | `INTEGER` | **NÃO** | `CHECK (total_formados >= 0)` | **Métrica Aditiva**: Total de discentes diplomados. |
| `total_evadidos` | `INTEGER` | **NÃO** | `CHECK (total_evadidos >= 0)` | **Métrica Aditiva**: Total de discentes evadidos/desligados sem diploma. |
| `total_ainda_ativos`| `INTEGER` | **NÃO** | `DEFAULT 0 CHECK (total_ainda_ativos >= 0)` | **Métrica Aditiva**: Discentes retidos cursando além do prazo normal. |
| `taxa_formatura_pct`| `NUMERIC(5,2)`| SIM | `CHECK (BETWEEN 0 AND 100)` | **Métrica Não-Aditiva**: Percentual de conclusão da coorte. |
| `taxa_evasao_pct` | `NUMERIC(5,2)`| SIM | `CHECK (BETWEEN 0 AND 100)` | **Métrica Não-Aditiva**: Percentual de evasão da coorte. |
| `formados_tempo_ideal_pct`| `NUMERIC(5,2)`| SIM | `CHECK (BETWEEN 0 AND 100)` | **Métrica Não-Aditiva**: Percentual de formados dentro do prazo ideal. |
| `atraso_medio_semestres`| `NUMERIC(5,2)`| SIM | - | **Métrica Não-Aditiva**: Média de semestres extras para integralização. |
| `indice_retencao_critica`| `NUMERIC(4,1)`| SIM | `CHECK (BETWEEN 0 AND 100)` | **Métrica Calculada (IRC)**: Indicador ponderado de retenção crítica (0 a 100). |
| `classificacao_retencao`| `TEXT` | SIM | `CHECK IN ('RETENÇÃO CRÍTICA', 'RETENÇÃO ALTA', 'RETENÇÃO MÉDIA', 'RETENÇÃO BAIXA')` | Classificação institucional oficial de severidade de retenção. |
| `atualizado_em` | `TIMESTAMPTZ`| **NÃO** | `DEFAULT now()` | Carimbo de atualização da carga ELT in-database. |

* **Restrição de Unicidade**: `CONSTRAINT uk_fato_curso UNIQUE (sk_curso, sk_campus)`.

---

### 4.6 Tabela Fato `gold.fato_alunos_ativos`
* **Tipo**: Fato de *Snapshot Periódico de Alunos Matriculados no Semestre Atual*.
* **Grão Físico**: Um registro por curso canônico no semestre de referência ativo (`sk_curso` é **UNIQUE**).

| Coluna | Tipo Físico | Nulo? | Padrão / Restrição | Descrição Semântica |
|:---|:---|:---:|:---:|:---|
| `id_fato_ativo` | `BIGINT` | **NÃO** | **PK** (`GENERATED ALWAYS AS IDENTITY`) | Identificador unívoco do snapshot de matrícula. |
| `sk_curso` | `INTEGER` | **NÃO** | **UK / FK** $\rightarrow$ `gold.dim_curso` | Curso analisado (cada curso tem no máximo 1 linha no snapshot). |
| `sk_tempo_referencia`| `INTEGER`| **NÃO** | **FK** $\rightarrow$ `gold.dim_tempo` | Semestre letivo do snapshot (ex: 20241). |
| `total_ativos` | `INTEGER` | **NÃO** | `CHECK (total_ativos >= 5)` | **Métrica Semi-Aditiva**: Total de discentes com matrícula regular ativa. |
| `ativos_acima_prazo_ideal`| `INTEGER`| **NÃO** | `CHECK (ativos_acima_prazo_ideal >= 0)` | **Métrica Semi-Aditiva**: Alunos cursando além do prazo previsto. |
| `ativos_acima_prazo_maximo`| `INTEGER`| **NÃO** | `CHECK (ativos_acima_prazo_maximo >= 0)`| **Métrica Semi-Aditiva**: Alunos sob risco iminente de jubilamento regulamentar. |
| `pct_acima_prazo_ideal`| `NUMERIC(5,2)`| **NÃO** | `CHECK (BETWEEN 0 AND 100)` | **Métrica Não-Aditiva**: Proporção de discentes retidos no semestre corrente. |
| `atualizado_em` | `TIMESTAMPTZ`| **NÃO** | `DEFAULT now()` | Carimbo temporal da carga. |

---

### 4.7 Tabela Fato `gold.fato_pibic_perfil`
* **Tipo**: Fato de *Planos de Iniciação Científica por Perfil Social e Ações Afirmativas*.
* **Grão Físico**: Um registro por par `(sk_curso, sk_perfil)`.
* **Privacidade e LGPD**: Constraint declarativa de $k$-anonimato estrito (`CHECK (total_projetos >= 5)`).

| Coluna | Tipo Físico | Nulo? | Padrão / Restrição | Descrição Semântica |
|:---|:---|:---:|:---:|:---|
| `id_fato` | `BIGINT` | **NÃO** | **PK** (`GENERATED ALWAYS AS IDENTITY`) | Identificador primário do registro de fato. |
| `sk_curso` | `INTEGER` | **NÃO** | **FK** $\rightarrow$ `gold.dim_curso` | Chave substituta para o curso canônico. |
| `sk_perfil` | `INTEGER` | **NÃO** | **FK** $\rightarrow$ `gold.dim_perfil_social`| Chave substituta para o perfil social do bolsista. |
| `total_projetos` | `INTEGER` | **NÃO** | `CHECK (total_projetos >= 5)` | **Métrica Aditiva**: Quantidade total de planos de trabalho ($k \ge 5$). |
| `total_remuneradas` | `INTEGER` | **NÃO** | `CHECK (total_remuneradas >= 0)` | **Métrica Aditiva**: Planos com bolsa remunerada (PIBIC). |
| `total_voluntarias` | `INTEGER` | **NÃO** | `CHECK (total_voluntarias >= 0)` | **Métrica Aditiva**: Planos com bolsa voluntária (PIVIC). |
| `valor_total_investido`| `NUMERIC(14,2)`| **NÃO** | `CHECK (valor_total_investido >= 0)` | **Métrica Aditiva**: Soma estimada das bolsas concedidas (em R$). |
| `atualizado_em` | `TIMESTAMPTZ`| **NÃO** | `DEFAULT now()` | Carimbo temporal de geração. |

* **Restrição de Unicidade**: `CONSTRAINT uk_fato_pibic_perfil UNIQUE (sk_curso, sk_perfil)`.
* **Regra de Consistência**: `CHECK (total_remuneradas + total_voluntarias <= total_projetos)`.

---

### 4.8 Visão Materializada Concorrente: `gold.mv_dashboard_executivo`
* **Tipo**: *Indexed Materialized View* pré-computada para o Streamlit/DEG.
* **Índice Único**: `CREATE UNIQUE INDEX idx_mv_executivo_sk ON gold.mv_dashboard_executivo (sk_curso, campus);`
* **Estratégia de Atualização**: `REFRESH MATERIALIZED VIEW CONCURRENTLY` (garante zero bloqueio de consultas de leitura).
* **Tempo de Execução Medido**: **0.054 ms** via `Index Scan` com leitura em cache (*Shared Buffers*).

---

## 5. Resumo Global de Governança de Esquema

```
+-----------------------------------------------------------------------------------------+
|                        INVENTÁRIO CONSOLIDADO DO CATÁLOGO DO SGBD                       |
+--------------------------+--------------------------------------------------------------+
| Métrica de Catálogo      | Quantidade Homologada no PostgreSQL 16/17                    |
+--------------------------+--------------------------------------------------------------+
| Relações Lógicas Canônicas| 5 tabelas em 3NF (Silver) + 7 relações dimensionais (Gold)   |
| Tabelas Físicas em Disco | 15 tabelas no schema silver + 13 tabelas no schema gold      |
| Visões Materializadas    | 1 view materializada indexada com suporte concorrente        |
| Restrições de Unicidade  | 24 Chaves Primárias + 11 Restrições Únicas|
| Integridade Referencial  | 14 Chaves Estrangeiras declaradas (3 com ON DELETE RESTRICT) |
| Regras de Domínio (CHECK)| 81 restrições CHECK ativas no motor                   |
| Métodos de Acesso        | B-Tree Balanceada, GIN Trigram (pg_trgm) e HNSW (pgvector)   |
+--------------------------+--------------------------------------------------------------+
```

Este catálogo assegura que **100% da integridade, governança e conformidade com a LGPD sejam aplicadas diretamente no motor relacional do PostgreSQL**, sem dependência de lógica frágil em código de aplicação.
