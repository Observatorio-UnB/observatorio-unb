# Guia de Apresentacao: Ponto de Controle de Arquitetura e Modelagem

Este documento serve como roteiro estrategico e guia de oratoria para a apresentacao de ponto de controle da disciplina de Banco de Dados 2. O foco principal e demonstrar maturidade arquitetural, rigor teorico na modelagem e engenharia fisica de desempenho, deixando evidente a transicao de uma solucao ad-hoc de analise de dados para uma infraestrutura empresarial de Relational Lakehouse no PostgreSQL.

---

## 1. Diretrizes Gerais da Apresentacao

- **Duracao ideal**: 3 a 5 minutos.
- **Foco da sua fala**: Arquitetura em camadas, normalizacao formal (3NF), modelagem dimensional (Star Schema), engenharia fisica (particionamento, indices e tuning) e governanca (LGPD).
- **Postura**: Firme, tecnica e academica. Utilize os termos consagrados da literatura de banco de dados (Edgar F. Codd, Ralph Kimball, arquitetura ANSI/SPARC em 3 niveis, $k$-anonimato).
- **Abordagem das bases de dados**: Mencione as fontes apenas como insumo da camada Bronze (Dados Abertos da UnB: ingressantes, formados e evadidos de 2014 a 2024), direcionando imediatamente a discussao para a engenharia e tratamento no banco de dados.

---

## 2. Roteiro Passo a Passo de Apresentacao

### Bloco 1: Abertura e Visao Geral da Arquitetura (Aprox. 45 segundos)

**O que mostrar na tela**:
- Abrir o arquivo `docs/arquitetura/README.md` (Secao do Diagrama em Camadas).

**O que falar**:
> "Boa tarde professora, boa tarde turma. Hoje apresento o ponto de controle da arquitetura de dados do Observatorio UnB.
> Nosso objetivo principal nesta etapa foi transformar o processamento de dados do projeto. Abandonamos pipelines legados dependentes de manipulacao manual de planilhas e scripts isolados em Pandas para instituir uma infraestrutura corporativa de **Relational Lakehouse** executada 100% dentro do PostgreSQL.
> Estruturamos o banco em tres camadas conceituais bem definidas:
> 1. **Bronze**: Area de staging bruto com ingestao e auditoria;
> 2. **Silver**: Camada operacional totalmente normalizada na Terceira Forma Normal de Codd;
> 3. **Gold**: Camada analitica modelada no padrao Star Schema de Ralph Kimball, alimentando dashboards e consultas de alta velocidade."

---

### Bloco 2: Camada Silver e Rigor de Normalizacao (Aprox. 60 segundos)

**O que mostrar na tela**:
- Abrir a imagem vetorial `docs/arquitetura/assets/der_silver_3nf.svg` ou o arquivo `docs/arquitetura/DER_MODELO_CONCEITUAL_E_LOGICO.md`.

**O que falar**:
> "Na camada Silver, o foco absoluto foi integridade relacional e eliminacao de redundancias.
> Modelamos o dominio academico em entidades canonicamente desacopladas: Institutos, Cursos, Matrizes Curriculares, Alunos e Movimentacoes Academicas.
> Garantimos que todas as relacoes obedecem rigorosamente a **Terceira Forma Normal (3NF)**. Todas as dependencias funcionais tem como determinante uma superchave, eliminando dependencias parciais e transitivas.
> Isso significa que o banco esta imune a anomalias de insercao, delecao e atualizacao. No nosso repositorio, disponibilizamos a demonstracao matematica formal baseada no fecho de atributos e na decomposicao com juncao sem perdas para todas as tabelas da Silver."

---

### Bloco 3: Camada Gold e Modelagem Dimensional (Aprox. 60 segundos)

**O que mostrar na tela**:
- Abrir a imagem vetorial `docs/arquitetura/assets/der_gold_star_schema.svg`.

**O que falar**:
> "Para servir o consumo analitico e o dashboard com tempo de resposta imperceptivel, construimos a camada Gold utilizando a metodologia dimensional de **Ralph Kimball**.
> Criamos uma arquitetura centrada em duas tabelas de fatos complementares e quatro dimensoes compartilhadas (`dim_curso`, `dim_tempo`, `dim_unidade_academica` e `dim_perfil_estudante`):
> 1. **`fato_retencao_fluxo`**: Analisa coortes historicas fechadas, medindo taxas de retencao, formacao, evasao e o indicador de graduacao no tempo regulamentar.
> 2. **`fato_alunos_ativos`**: Monitora o contingente atual matriculado no semestre letivo.
> Essa separacao foi uma decisao arquitetural deliberada para sanar o **vies de maturacao**: uma coorte recente que acabou de entrar possui taxa de graduacao aparente proxima de zero, o que distorceria qualquer analise se estivesse misturada a coortes historicas consolidadas.
> Alem disso, embutimos no SGBD a regra de **$k$-anonimato** da LGPD: nenhuma celula analitica e exposta se representar menos de cinco estudantes."

---

### Bloco 4: Engenharia Fisica e Desempenho no SGBD (Aprox. 60 segundos)

**O que mostrar na tela**:
- Abrir o arquivo `docs/arquitetura/03_ENGENHARIA_FISICA_E_TUNING_SGBD.md` (Secao dos planos de execucao `EXPLAIN ANALYZE`).

**O que falar**:
> "Nao nos limitamos ao modelo logico; realizamos um trabalho profundo de engenharia fisica no SGBD:
> 1. **Particionamento Declarativo por Intervalo**: A tabela mais volumosa da Silver, `silver_movimentacoes_academicas`, foi particionada horizontalmente por faixas temporais (`p2000_2015`, `p2016_2020` e `p2021_atual`). O otimizador do Postgres aplica *partition pruning* imediato, ignorando particoes fora do escopo da consulta.
> 2. **Indexacao Avancada**: Alem das B-Trees para chaves estrangeiras, implementamos indices **GIN Trigram** (`pg_trgm`) para busca textual difusa de nomes de cursos e criamos suporte a busca semantica vetorial com indices **HNSW** (`pgvector`).
> 3. **Materializacao e Latencia**: As agregacoes analiticas sao servidas por Views Materializadas com atualizacao concorrente (`REFRESH MATERIALIZED VIEW CONCURRENTLY`). Nossos testes com `EXPLAIN (ANALYZE, BUFFERS)` comprovaram tempo de execucao de **0.042 milissegundos**, com custo computacional nulo de leitura em disco devido ao isolamento em buffer cache."

---

### Bloco 5: Dossie Documental e Conclusao (Aprox. 30 segundos)

**O que mostrar na tela**:
- Navegar rapidamente pela pasta `docs/arquitetura/`.

**O que falar**:
> "Finalizando, consolidamos todo esse trabalho em um **Dossiê Arquitetural Completo** no repositorio, contendo:
> - O DER conceitual de Peter Chen com cardinalidades $(min, max)$ e o modelo logico relacional;
> - A prova matematica formal de normalizacao 3NF;
> - A Matriz de Ciclo de Vida de Ralph Kimball;
> - O dossie de tuning fisico com benchmarks reais de execucao;
> - O dicionario de dados ativo sincronizado 1:1 com o catalogo do PostgreSQL.
> Com isso, a base de dados esta estavel, normalizada, testada e pronta para a sustentacao do produto final."

---

## 3. Guia de Defesa: Perguntas Provaveis da Professora e Como Responder

### Pergunta 1: *"Por que voces modelaram tanto em 3NF quanto em Star Schema? Nao daria para usar so um dos dois?"*
- **Resposta**:
  > "Optamos por essa separacao para respeitar o desacoplamento de responsabilidades em bancos de dados. A camada Silver em 3NF garante integridade transacional, idempotencia e ausencia de redundancias para operacoes de escrita e manutencao.
  > Ja a camada Gold em Star Schema atende a analise OLAP: nela, desnormalizamos de forma controlada as dimensoes para evitar juncoes excessivas em consultas analiticas complexas. Tentar usar apenas uma das abordagens forcaria um compromisso ruim: ou consultas lentas e complexas no dashboard (se usassemos apenas 3NF), ou risco de corrupcao e inconsistencia de dados na ingestao (se usassemos apenas tabelas desnormalizadas)."

---

### Pergunta 2: *"No visualizador do banco aparecem mais tabelas do que as 5 entidades do modelo logico da Silver. Por que essa diferenca?"*
- **Resposta**:
  > "Essa e uma aplicacao direta da **arquitetura ANSI/SPARC em tres niveis**, separando o modelo logico do modelo fisico.
  > No nivel logico, temos as 5 entidades essenciais: Unidades, Cursos, Matrizes, Alunos e Movimentacoes.
  > No nivel fisico no PostgreSQL, a tabela de movimentacoes foi particionada horizontalmente em 3 tabelas fisicas filhas (`p2000_2015`, `p2016_2020`, `p2021_atual`) para ganho de desempenho. Alem disso, existem tabelas fisicas de staging e auditoria de ingestao. Portanto, o diagrama conceitual/logico expressa o negocio, enquanto o catalogo do SGBD reflete a distribuicao fisica dos dados no disco."

---

### Pergunta 3: *"Como voces garantem a privacidade dos dados de acordo com a LGPD?"*
- **Resposta**:
  > "Adotamos privacidade por design (*privacy by design*) implementada diretamente no motor do banco de dados.
  > Primeiro, na camada Silver, os identificadores unicos dos discentes sao anonimizados por hash criptografico (nao ha armazenamento de nomes ou CPFs).
  > Segundo, na camada Gold, aplicamos uma clausula de checagem formal (`CHECK (total_ingressantes >= 5)`) que implementa a regra de **$k$-anonimato**. Se um determinado curso ou recorte demografico tiver menos de cinco alunos, o dado agregado e omitido ou unificado para evitar reidentificacao por inferencia."

---

### Pergunta 4: *"O que e o viés de maturação e como o banco de dados evita esse erro analitico?"*
- **Resposta**:
  > "O vies de maturacao ocorre quando comparamos turmas que acabaram de entrar na universidade com turmas de anos anteriores. Por exemplo, ingressantes de 2023 ainda estao no inicio do curso, portanto sua taxa de formacao real e temporariamente zero. Se calcularmos a taxa de evasao ou formacao misturando todas as turmas em uma unica tabela rasa, as turmas novas puxam a media para baixo, gerando graficos enganosos.
  > Resolvemos isso na engenharia da Gold separando a `fato_retencao_fluxo` (que calcula coortes consolidadas apos o tempo limite de integralizacao) da `fato_alunos_ativos` (que conta matriculados do semestre corrente)."

---

### Pergunta 5: *"Quais indices voces criaram e qual foi o ganho real de desempenho medido?"*
- **Resposta**:
  > "Alem das chaves primarias e indices B-Tree nas chaves estrangeiras, criamos indices GIN Trigram na coluna de busca de cursos e habilitamos a extensao `pgvector` com indice HNSW para busca semantica.
  > Para consultas de agregacao do painel, criamos views materializadas indexadas. Ao rodar `EXPLAIN (ANALYZE, BUFFERS)`, medimos um tempo de execucao de **0.042 milissegundos** e zero operacoes de I/O em disco, pois o conjunto de dados reduzido permanece 100% retido no shared buffers do PostgreSQL."

---

## 4. Dicas de Oratoria e Navegacao Durante a Apresentacao

1. **Abra as abas antes de comecar**: Deixe abertos no VS Code ou navegador os seguintes arquivos:
   - `docs/arquitetura/README.md`
   - `docs/arquitetura/assets/der_silver_3nf.svg`
   - `docs/arquitetura/assets/der_gold_star_schema.svg`
   - `docs/arquitetura/03_ENGENHARIA_FISICA_E_TUNING_SGBD.md`
2. **Nao peca desculpas pelo escopo**: Em apresentacoes de ponto de controle, enfatize a solidez do que foi construido ate o momento: *"Focamos em solidificar a fundacao estrutural do banco para garantir que as proximas entregas tenham custo de manutencao reduzido e alta performance."*
3. **Mantenha o ritmo calmo**: 3 a 5 minutos e tempo suficiente para cobrir todos os 5 blocos com clareza se voce evitar enrolar nos detalhes de CSVs e focar na arquitetura do banco.
