# Engenharia Física, Indexação Especializada e Tuning de Consultas

> **Universidade de Brasília (UnB)**  
> **Disciplina**: Banco de Dados 2  
> **Camada**: Projeto Físico, Métodos de Acesso e Otimizador de Consultas (PostgreSQL 16/17)  
> **Status**: Implementado e Homologado no SGBD (PostgreSQL 17 / Supabase & PostgreSQL 16 / Docker)

---

## 1. Introdução e Racional de Projeto Físico

O projeto físico de um banco de dados relacional visa mapear o esquema lógico para estruturas de armazenamento em disco que minimizem o custo de entrada/saída ($I/O$) e maximizem a vazão de transações e consultas analíticas.

Em versões legadas deste projeto universitário, as agregações e filtros eram executados em memória através da biblioteca Pandas em scripts Python. Essa abordagem viola os princípios fundamentais de engenharia de banco de dados por:

1. Transferir volumes maciços de dados brutos pela rede (_High Network Overhead_);
2. Desperdiçar as capacidades de paralelismo e poda de partições nativas do SGBD;
3. Impedir o reuso de páginas do _Buffer Pool_ do motor relacional.

As agregações da Gold que ainda restavam em Pandas (retenção, ativos, benchmark INEP e PIBIC) migraram para procedures SQL na migração `0022_gold_agregacoes_sql.sql` (ADR 0027); o Python só dispara `CALL gold.atualizar_gold(...)`.

A reengenharia física implementada nas migrações do Observatório (`0011_silver_3nf.sql`, `0012_gold_star_schema.sql`, `0013_views_materializadas.sql`, `0014_carga_3nf_star.sql` e `0015_fato_pibic_perfil.sql`) transfere a responsabilidade computacional para o PostgreSQL, utilizando **particionamento horizontal declarativo**, **métodos de acesso especializados (B-Tree, GIN, HNSW)** e **materialização assíncrona concorrente**.

---

## 2. Particionamento Declarativo por Intervalo (_Range Partitioning_)

### 2.1 Justificativa de Engenharia

A relação `silver.movimentacoes_vinculos` representa a série temporal de histórico acadêmico dos discentes desde os anos 2000. Em escala real, esta tabela acumula dezenas de milhares de tuplas operacionais.

Consultas do DEG/DAA e relatórios institucionais frequentemente restringem o escopo de análise a recortes temporais (ex: coortes maduras para cálculo de retenção ou coortes recentes para acompanhamento de evasão inicial). A varredura sequencial (_Sequential Scan_) em uma tabela monotrilho exigiria leitura integral de páginas de dados.

### 2.2 Estrutura DDL Implementada

A tabela foi criada utilizando o particionamento declarativo nativo do PostgreSQL:

```sql
CREATE TABLE silver.movimentacoes_vinculos (
    id_vinculo                   BIGINT GENERATED ALWAYS AS IDENTITY,
    id_discente                  BIGINT NOT NULL REFERENCES silver.discentes (id_discente) ON DELETE RESTRICT,
    id_curso                     INTEGER NOT NULL REFERENCES silver.cursos (id_curso) ON DELETE RESTRICT,
    id_estrutura                 INTEGER NOT NULL REFERENCES silver.estruturas_curriculares (id_estrutura),
    ano_ingresso                 SMALLINT NOT NULL,
    semestre_ingresso            SMALLINT CHECK (semestre_ingresso IN (0, 1, 2)),
    forma_saida                  TEXT,
    tipo_saida_grupo             TEXT NOT NULL CHECK (tipo_saida_grupo IN ('FORMATURA', 'EVASAO', 'ATIVO', 'OUTROS')),
    ano_saida                    SMALLINT,
    semestre_saida               SMALLINT CHECK (semestre_saida IN (0, 1, 2)),
    semestres_permanencia        SMALLINT,
    semestres_permanencia_valida SMALLINT CHECK (semestres_permanencia_valida BETWEEN 1 AND 35),
    periodo_saida_estimado       BOOLEAN NOT NULL DEFAULT false,
    status_aluno                 TEXT,
    fonte                        TEXT NOT NULL CHECK (fonte IN ('SIGRA', 'SIGAA')),
    PRIMARY KEY (id_vinculo, ano_ingresso)
) PARTITION BY RANGE (ano_ingresso);
```

As partições físicas declarativas cobrem períodos históricos, coortes maduras, coortes vigentes e partição default para salvaguarda:

```sql
-- Partição 1: Histórico de 2000 a 2015
CREATE TABLE silver.movimentacoes_p2000_2015
    PARTITION OF silver.movimentacoes_vinculos FOR VALUES FROM (2000) TO (2016);

-- Partição 2: Coortes maduras de 2016 a 2020
CREATE TABLE silver.movimentacoes_p2016_2020
    PARTITION OF silver.movimentacoes_vinculos FOR VALUES FROM (2016) TO (2021);

-- Partição 3: Coortes recentes e vigentes (2021 a 2035)
CREATE TABLE silver.movimentacoes_p2021_atual
    PARTITION OF silver.movimentacoes_vinculos FOR VALUES FROM (2021) TO (2035);

-- Partição 4: Salvaguarda para anos fora dos intervalos mapeados
CREATE TABLE silver.movimentacoes_p_default
    PARTITION OF silver.movimentacoes_vinculos DEFAULT;
```

### 2.3 Poda de Partições (_Partition Pruning_)

O planejador de consultas (_Query Planner_) avalia os predicados da cláusula `WHERE` e elimina imediatamente as partições irrelevantes antes do acesso ao disco:

```
[ Consulta Recebida ] ---> WHERE ano_ingresso = 2023
          |
          v
[ Otimizador de Consultas ]
          |
          +---> [ silver.movimentacoes_p2000_2015  ] --> (DESCARTADA / PRUNED)
          +---> [ silver.movimentacoes_p2016_2020  ] --> (DESCARTADA / PRUNED)
          +---> [ silver.movimentacoes_p_default   ] --> (DESCARTADA / PRUNED)
          +---> [ silver.movimentacoes_p2021_atual ] --> [ SCAN EXECUTADO ]
```

Essa eliminação em tempo de planejamento reduz drasticamente o número de páginas lidas (_buffers read_), eliminando I/O espúrio de anos anteriores.

### 2.4 Provisionamento Automático de Partições Futuras

A função `silver.provisionar_particoes_movimentacoes(ano_referencia, anos_a_frente)` (migração 0019) cria partições por quinquênio a partir do maior limite existente (`movimentacoes_p2035_2039`, `movimentacoes_p2040_2044`, ...) até `ano_referencia + anos_a_frente` (padrão: ano corrente + 5). Ela é chamada por `src/db/povoar_silver_3nf.py` antes de cada carga, de modo que um ano letivo novo já encontra sua partição dedicada.

```sql
SELECT silver.provisionar_particoes_movimentacoes();      -- ano corrente + 5
SELECT silver.provisionar_particoes_movimentacoes(2040);  -- simula a chegada de 2040
```

- **Idempotência**: o ponto de partida é lido do catálogo (`pg_inherits`); uma segunda chamada não cria nada.
- **Linhas já na default**: se ingressos de um quinquênio novo já tiverem caído na `movimentacoes_p_default`, elas são movidas para a partição criada na mesma transação.

### 2.5 Política de Ciclo de Vida das Partições Legadas

A Silver 3NF é recriada a cada execução do pipeline (`TRUNCATE` + carga a partir da bronze), e o `gold.fato_retencao_curso` usa **todas** as coortes maduras (ingresso até o último ano menos `ANOS_MATURACAO_COORTE` = 8). Por isso:

1. **Nenhuma partição é removida ou desanexada enquanto suas coortes alimentam a gold.** Hoje isso vale para todas (2000 em diante).
2. **Partições fechadas** (todas as coortes com saída registrada, sem vínculo `ATIVO`) são candidatas a `VACUUM (FREEZE, ANALYZE)` após a carga, evitando reescrita futura por _wraparound_.
3. **Compressão**: o PostgreSQL não comprime o _heap_; as colunas textuais longas podem usar `ALTER TABLE ... ALTER COLUMN ... SET COMPRESSION lz4` (TOAST). O ganho é pequeno no volume atual (~150 mil vínculos) e não justifica a mudança agora.
4. **Arquivamento**: se um período sair do escopo analítico da gold, a partição é desanexada sem bloquear leituras (`ALTER TABLE silver.movimentacoes_vinculos DETACH PARTITION ... CONCURRENTLY`), exportada com `pg_dump -Fc` (formato comprimido) e só então removida. Como a Silver contém dado pessoal pseudonimizado, o arquivo segue as mesmas regras de acesso do banco (LGPD) e nunca vai para o repositório.
5. **Partição default**: deve ficar vazia para anos a partir de 2000. Linhas nela indicam ano de ingresso fora do intervalo mapeado (ex.: anterior a 2000) e devem ser investigadas.

---

## 3. Estratégias Avançadas de Indexação

O catálogo físico do banco de dados conta com métodos de acesso adaptados à álgebra de cada operador:

```
+-----------------------------------------------------------------------------------------+
|                                    TAXONOMIA DE ÍNDICES                                 |
+--------------------------+------------------------------+-------------------------------+
| Tipo de Índice           | Estrutura Física             | Caso de Uso no Observatório   |
+--------------------------+------------------------------+-------------------------------+
| B-Tree Balanceada        | Árvore balanceada multinível | Chaves Primárias, UKs e Datas |
| GIN (Trigramas)          | Índice Invertido Generalizado| Busca textual difusa de cursos|
| HNSW (pgvector)          | Grafo Hierárquico Pequeno    | Busca Semântica em Embeddings |
+--------------------------+------------------------------+-------------------------------+
```

### 3.1 B-Tree e Índices em Chaves Estrangeiras

No PostgreSQL, a criação de uma constraint `FOREIGN KEY` **não cria automaticamente** um índice B-Tree na tabela referenciadora. Índices devem ser construídos explicitamente onde há padrões frequentes de filtragem ou junção.

No Observatório UnB, além das árvores B-Tree automáticas em todas as `PRIMARY KEY` e `UNIQUE`, foram construídos índices compostos e parciais sob medida:

```sql
-- Índice composto para acelerar agregações por curso e ano de ingresso:
CREATE INDEX idx_mov_curso_ano ON silver.movimentacoes_vinculos (id_curso, ano_ingresso);

-- Índice parcial direcionado para análise imediata de evasão:
CREATE INDEX idx_mov_evasao ON silver.movimentacoes_vinculos (id_curso)
    WHERE tipo_saida_grupo = 'EVASAO';
```

O índice parcial `idx_mov_evasao` armazena apenas tuplas onde `tipo_saida_grupo = 'EVASAO'`, ocupando uma fração do espaço em disco de um índice global e permitindo leituras ultrarrápidas das coortes de evasão.

A chave estrangeira `id_estrutura`, pela qual o curso canônico chega aos vínculos, ficou sem índice até a migração 0024. O índice dela saiu da leitura de um plano real, e não de antemão (seção 5.1):

```sql
-- Vínculos de um curso canônico por tipo de saída e coorte (migração 0024):
CREATE INDEX idx_mov_estrutura_saida_ano ON silver.movimentacoes_vinculos
    (id_estrutura, tipo_saida_grupo, ano_ingresso) INCLUDE (semestres_permanencia_valida);
```

### 3.2 GIN com `pg_trgm` (Generalized Inverted Index para Trigrama)

A busca por cursos universitários frequentemente envolve erros de digitação, acentuação ausente ou termos parciais (ex: "Engenharia Mecatrônica" digitado como "mecatronica" ou "eng mecat").

O operador padrão `ILIKE '%termo%'` com índice B-Tree não pode utilizar o índice devido ao caractere curinga inicial `%`, forçando um _Sequential Scan_.

**Solução Implementada**:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_cursos_nome_trgm
ON silver.cursos
USING gin (nome_curso_norm gin_trgm_ops);
```

- **Mecanismo Físico**: O algoritmo decompõe cada cadeia de caracteres em fatias de 3 letras (_trigramas_). O índice GIN mapeia cada trigrama para a lista de tuplas que o contém.
- **Complexidade**: Reduz o custo de busca textual de $O(N \cdot L)$ para $O(K \cdot \log N)$, viabilizando buscas por similaridade fonética e ortográfica instantâneas.

### 3.3 HNSW com `pgvector` (Hierarchical Navigable Small World)

Para a busca semântica em linguagem natural (ex: _"quero cursos que envolvam inteligência artificial e matemática discreta"_), o banco armazena vetores de embeddings em `busca.documentos` gerados pelo modelo multilíngue `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384 dimensões).

**Solução Implementada**:

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE INDEX documentos_embedding_hnsw
ON busca.documentos
USING hnsw (embedding vector_cosine_ops);
```

- **Estrutura Física**: O algoritmo HNSW constrói um grafo de múltiplas camadas onde as camadas superiores realizam saltos longos (análogo a uma _Skip List_) e a camada base contém as conexões locais de alta densidade.
- **Operador de Distância**: `vector_cosine_ops` calcula a distância de cosseno:
  $$D_{\mathrm{cos}}(u, v) = 1 - \frac{u \cdot v}{\|u\|_2 \|v\|_2}$$
- **Vantagem sobre IVFFlat**: O HNSW não degrada com o aumento do volume de dados e não requer reconstrução (_retrain_) ao inserir novas matrizes ou documentos. A busca dos vizinhos mais próximos executa em complexidade logarítmica $O(\log N)$.

---

## 4. Materialização e Atualização Concorrente (_Concurrent Refresh_)

### 4.1 O Problema da Agregação em Tempo de Consulta

Consultas analíticas executivas que consolidam taxas de retenção, evasão, diplomação no tempo ideal e discentes ativos envolvem junções entre tabelas dimensionais (`fato_retencao_curso`, `dim_curso`, `dim_campus`, `fato_alunos_ativos`). Executar esses joins a cada requisição do painel geraria gargalos de CPU e I/O desnecessários.

### 4.2 Definição da View Materializada

A relação consolidada foi materializada na view `gold.mv_dashboard_executivo`:

```sql
CREATE MATERIALIZED VIEW gold.mv_dashboard_executivo AS
SELECT
    c.sk_curso,
    c.id_curso_origem,
    c.nome_curso,
    c.area_conhecimento,
    c.categoria_grau,
    camp.campus,
    f.total_ingressantes,
    f.total_formados,
    f.total_evadidos,
    f.total_ainda_ativos,
    f.taxa_formatura_pct,
    f.taxa_evasao_pct,
    f.formados_tempo_ideal_pct,
    f.atraso_medio_semestres,
    f.indice_retencao_critica,
    f.classificacao_retencao,
    COALESCE(fa.total_ativos, 0) AS ativos_hoje_total,
    COALESCE(fa.ativos_acima_prazo_ideal, 0) AS ativos_hoje_atrasados,
    COALESCE(fa.pct_acima_prazo_ideal, 0.0) AS pct_ativos_hoje_atrasados,
    now() AS gerado_em
FROM gold.fato_retencao_curso f
JOIN gold.dim_curso c ON f.sk_curso = c.sk_curso
JOIN gold.dim_campus camp ON f.sk_campus = camp.sk_campus
LEFT JOIN gold.fato_alunos_ativos fa ON c.sk_curso = fa.sk_curso
WHERE c.is_tronco_abi = false;
```

### 4.3 Índice Único e Atualização Não-Bloqueante

A instrução padrão `REFRESH MATERIALIZED VIEW` adquire um lock exclusivo `AccessExclusiveLock`, bloqueando consultas simultâneas (`SELECT`) durante toda a atualização.

Para permitir disponibilidade contínua sem travamento de leitores, criamos um índice exclusivo na chave composta `(sk_curso, campus)` e executamos a atualização via `CONCURRENTLY`:

```sql
-- Índice exclusivo (requisito mandatório do PostgreSQL para REFRESH CONCURRENTLY)
CREATE UNIQUE INDEX idx_mv_executivo_sk
ON gold.mv_dashboard_executivo (sk_curso, campus);

-- Atualização assíncrona concorrente (sem bloqueio de leituras)
REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_dashboard_executivo;
```

- **Mecanismo de Concorrência**: O motor do PostgreSQL gera uma tabela temporária de trabalho, computa o diff das alterações contra o índice exclusivo `idx_mv_executivo_sk` e aplica as mudanças através de operações pontuais mantendo as páginas servidas sem interrupção.

---


## 5. Análise Empírica de Performance: `EXPLAIN (ANALYZE, BUFFERS)`

Os planos desta seção estão versionados em [`docs/explain/`](../explain/), junto com a consulta que os gera. Foram medidos no PostgreSQL 16 do `docker compose`, com o banco do pipeline completo (152.680 vínculos), depois do autovacuum. Cada consulta rodou duas vezes, e o plano guardado é o da segunda, com o cache quente: antes e depois são comparados nas mesmas condições.

### 5.1 Detalhamento de um curso na Silver 3NF (otimizado)

**Consulta** ([`distribuicao_formatura_por_curso.sql`](../explain/distribuicao_formatura_por_curso.sql)): distribuição de semestres até a formatura dos formados de Ciência da Computação nas coortes maduras (2010 a 2016). É o detalhamento por curso do painel e o caso de uso de orientação ao calouro ("em quantos semestres os formados deste curso de fato se formam?").

```sql
SELECT m.semestres_permanencia_valida AS semestres, count(*) AS formados
FROM silver.movimentacoes_vinculos m
JOIN silver.estruturas_curriculares e USING (id_estrutura)
WHERE e.nome_curso_canonico = 'CIENCIA DA COMPUTACAO'
  AND m.tipo_saida_grupo = 'FORMATURA'
  AND m.ano_ingresso BETWEEN 2010 AND 2016
GROUP BY 1 ORDER BY 1;
```

**Antes** ([`antes_distribuicao_formatura_por_curso.txt`](../explain/antes_distribuicao_formatura_por_curso.txt)):

```text
->  Hash Join  (actual time=0.086..35.215 rows=235)
      Hash Cond: (m.id_estrutura = e.id_estrutura)
      ->  Append  (actual rows=35046)
            ->  Seq Scan on movimentacoes_p2000_2015 m_1   Rows Removed by Filter: 27921   Buffers: shared hit=848
            ->  Seq Scan on movimentacoes_p2016_2020 m_2   Rows Removed by Filter: 55120   Buffers: shared hit=713
Buffers: shared hit=1566     Execution Time: 35.593 ms
```

**Leitura do plano.** A poda de partições funcionou: só as duas partições que cobrem 2010 a 2016 entram no `Append`. Mas, dentro delas, as duas são lidas inteiras (1.561 páginas, cerca de 118 mil linhas), 83 mil linhas são descartadas pelo filtro e outras 34.811 pelo `Hash Join`, para sobrarem 235. O problema é a chave da junção: o curso canônico chega ao vínculo por `id_estrutura`, que não tinha índice. O índice existente, `idx_mov_curso_ano (id_curso, ano_ingresso)`, não é usado porque a consulta não filtra por `id_curso`.

**Alternativas medidas.**

| Alternativa | Plano | Buffers | Tempo |
|:---|:---|---:|---:|
| Sem mudança (antes) | Seq Scan nas 2 partições + Hash Join | 1.566 | 35,6 ms |
| Reescrever a junção para casar também por `id_curso` (`ON m.id_estrutura = e.id_estrutura AND m.id_curso = e.id_curso`), usando o índice existente | Bitmap Heap Scan por `idx_mov_curso_ano` | 474 | 4,1 ms |
| **Índice `(id_estrutura, tipo_saida_grupo, ano_ingresso) INCLUDE (semestres_permanencia_valida)`** | **Index Only Scan nas 2 partições** | **14** | **0,42 ms** |

A reescrita funciona porque todo vínculo tem o mesmo `id_curso` da sua matriz (conferido: 0 de 152.680 divergem). Mas ela ainda lê as páginas de todos os vínculos do curso (601 + 112 linhas) para filtrar formatura na heap, e o planejador erra a estimativa (3 linhas previstas, 198 reais), porque não sabe que as duas condições da junção são redundantes. Ela também obriga cada consulta futura a lembrar da chave redundante. Por isso a escolha foi o índice.

**Mudança** ([migração 0024](../../db/migrations/0024_indice_vinculos_por_estrutura.sql)): as colunas de igualdade (`id_estrutura`, `tipo_saida_grupo`) vêm antes da de intervalo (`ano_ingresso`), e a coluna agregada vai no `INCLUDE`. Assim o intervalo de coortes é uma faixa contígua do índice e a contagem não precisa da heap. Criado na tabela particionada, o índice nasce em cada partição, inclusive nas que a [migração 0019](../../db/migrations/0019_provisionar_particoes.sql) provisionar depois.

**Depois** ([`depois_distribuicao_formatura_por_curso.txt`](../explain/depois_distribuicao_formatura_por_curso.txt)):

```text
->  Nested Loop  (actual time=0.067..0.219 rows=235)
      ->  Seq Scan on estruturas_curriculares e   (rows=1)
      ->  Append
            ->  Index Only Scan using movimentacoes_p2000_2015_id_estrutura_tipo_saida_grupo_ano__idx   Heap Fetches: 0   Buffers: shared hit=5
            ->  Index Only Scan using movimentacoes_p2016_2020_id_estrutura_tipo_saida_grupo_ano__idx   Heap Fetches: 0   Buffers: shared hit=4
Buffers: shared hit=14     Execution Time: 0.418 ms
```

**Resultado.** De 1.566 para 14 buffers (112 vezes menos páginas) e de 35,6 ms para 0,42 ms (85 vezes mais rápido). O `Hash Join` vira `Nested Loop`: com uma estrutura só do lado externo, cada partição faz uma busca no índice que já devolve só as 235 linhas da resposta.

**Custos e limites.**
- **Espaço:** o índice ocupa 5,8 MB nas partições, contra 15 MB da tabela.
- **Carga:** a recarga da Silver 3NF e do Star Schema (`povoar_dimensional.py`, que recria os vínculos) passou de 5,05 s para 5,39 s, média de 3 execuções. São +0,34 s por pipeline.
- **Mapa de visibilidade:** o `Heap Fetches: 0` depende do mapa de visibilidade, que a recarga zera. Logo depois de uma carga, antes do autovacuum, o plano usa o mesmo índice por `Bitmap Heap Scan` e lê 202 buffers em 0,79 ms: o ganho continua, só menor até o autovacuum passar.
- **Regressão:** `test_09_detalhamento_por_curso_usa_o_indice_da_estrutura` (em `tests/test_banco_3nf_star.py`) roda o `EXPLAIN` da consulta versionada e falha se alguma partição dos vínculos voltar a ser lida por `Seq Scan`.

### 5.2 Linha de um curso na view materializada do painel

**Consulta** ([`painel_curso_na_view_materializada.sql`](../explain/painel_curso_na_view_materializada.sql)): a linha de Ciência da Computação em `gold.mv_dashboard_executivo`, como a Visão Executiva lê.

```text
Seq Scan on mv_dashboard_executivo  (actual time=0.020..0.029 rows=1)
  Filter: ((sk_curso = $0) AND (campus = 'DARCY RIBEIRO'::text))
  Rows Removed by Filter: 93
  Buffers: shared hit=5
Execution Time: 0.065 ms
```

Com 94 linhas em poucas páginas, o PostgreSQL prefere ler a view inteira a passar pelo índice único: é o plano mais barato nesse tamanho. O índice `idx_mov_executivo_sk` continua necessário, mas para o `REFRESH MATERIALIZED VIEW CONCURRENTLY` (seção 4.3), e não para a leitura. A versão anterior desta seção mostrava um `Index Scan` (0,054 ms, 2 buffers) medido no PostgreSQL 17 do Supabase, sem plano versionado.

### 5.3 Comparação entre as abordagens

Só entram números com plano versionado em `docs/explain/`.

| Abordagem | Onde a agregação acontece | Plano | Buffers | Tempo |
|:---|:---|:---|---:|---:|
| Silver 3NF, sem índice na estrutura | Na consulta, sobre os vínculos | Seq Scan nas partições + Hash Join | 1.566 | 35,6 ms |
| Silver 3NF + índice da migração 0024 | Na consulta, sobre os vínculos | Index Only Scan | 14 | 0,42 ms |
| View materializada da Gold | Na carga (`REFRESH`) | Seq Scan numa view de 94 linhas | 5 | 0,065 ms |

A versão anterior desta tabela trazia uma linha "Legado (Pandas)", com cerca de 1.200 ms, e uma "Relacional bruto", com cerca de 45 ms, e concluía um ganho de cerca de 22.000 vezes. Nenhuma das duas tinha plano versionado, e o caminho por CSV saiu do projeto na E2. Por isso as duas linhas saíram da tabela.

A view responde mais rápido porque a agregação já foi feita na carga, mas só responde o que foi pré-agregado: uma linha por curso. O detalhamento da seção 5.1 (a distribuição de semestres) não existe na view, e é para ele que o índice na Silver serve.
