# 🎓 Observatório de Retenção, Formatura e Evasão da UnB

> **Challenge 2 de Dados Abertos da UnB** — Metodologia *Challenge Based Learning* (CBL)  
> **Tema**: Mapeamento do tempo real de integralização curricular, retenção crítica e evasão nos cursos de graduação.  
> **Stakeholder**: Decanato de Ensino de Graduação (DEG/DAA) e Coordenações de Curso da UnB.  
> **Portal de Origem**: [dados.unb.br](https://dados.unb.br) (API CKAN 2.11).  
> 
> 📄 **Síntese das Semanas 1 e 2** (histórico, anterior à E2): [RELATORIO_GERAL_PROJETO_SEMANAS_1_E_2.md](RELATORIO_GERAL_PROJETO_SEMANAS_1_E_2.md) para a explicação detalhada de como o projeto atende a 100% das duas primeiras semanas, a lógica das bases e o valor para o DEG.

---

## 📌 1. Visão Geral e Estrutura dos Entregáveis

Este repositório contém a solução completa para o desafio de 2 semanas, estruturada de forma modular, versionada e 100% reprodutível do zero:

```
bd2/
├── docs/
│   ├── challenge_canvas.md          # Challenge Canvas v2 (Stakeholder, EQ, Challenge, 5 GQs)
│   ├── relatorio_qualidade.md       # Relatório de Qualidade (8 achados com evidência + Issue CPD)
│   ├── registro_privacidade_lgpd.md # Análise de privacidade, quase-identificadores e k-anonimato
│   ├── datasheet_gold.md            # Datasheet for Datasets (padrão Gebru et al.)
│   ├── dicionario_dados_gold.md     # Dicionário de dados formal da tabela Gold
│   ├── dicionario_dados_banco.md    # Dicionário de TODAS as tabelas do banco (gerado do catálogo)
│   ├── caderno_analise.md           # Caderno de análise com respostas às 5 GQs e dinâmicas
│   └── adr/                         # Decisões de arquitetura (ADRs), uma por arquivo
├── db/
│   └── migrations/                  # Esquema versionado do PostgreSQL (0001 ... 0021)
├── scripts/
│   └── rodar_pipeline.sh            # Pipeline completo: portal -> medalhão -> banco -> vetores
├── src/
│   ├── ingestion/                   # Ingestão via API CKAN e INEP, direto para bronze.*
│   │   ├── ckan_client.py
│   │   ├── inep_censo_superior.py
│   │   └── procedencia.py           # Registro de cada download em bronze.ingestoes
│   ├── audit/                       # Auditoria automatizada de inconsistências
│   │   └── quality_auditor.py
│   ├── privacy/                     # Avaliação de conformidade LGPD
│   │   └── lgpd_check.py
│   ├── pipeline/                    # Pipeline em camadas (Bronze -> Silver -> Gold)
│   │   ├── transform_silver.py
│   │   └── build_gold.py            # semeia as regras e dispara CALL gold.atualizar_gold (ADR 0027)
│   ├── db/                          # Banco: migrações, leitura/gravação das camadas, export e dicionário
│   │   ├── migrar.py
│   │   ├── tabelas.py               # gravar(df, tabela) / ler(tabela): o contrato com o esquema
│   │   ├── exportar_gold.py         # Gold -> export/gold.json para o GitHub Pages (gerado no CI)
│   │   └── gerar_dicionario.py
│   ├── busca/                       # Busca semântica (embeddings + pgvector)
│   │   ├── vetorizar.py
│   │   └── buscar.py
│   └── dashboard/                   # Produto interativo em Streamlit
│       ├── app.py
│       └── pages/busca_semantica.py # Página de busca semântica (requer o banco)
├── tests/
│   ├── test_pipeline.py             # Testes automatizados de esquema e integridade
│   └── test_banco.py                # Contrato do banco, reconciliação entre camadas, acesso e busca
├── docker-compose.yml               # Banco + pipeline + painel
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## 🧾 Entrega E2 — Ingestão em lote e captura de mudanças

| Item do checklist | Evidência |
|---|---|
| Ingestão em lote idempotente | `bash scripts/rodar_pipeline.sh`; `src/db/exportar_lago.py` regrava sem duplicar |
| Fluxo de mudanças a partir do OLTP | [Captura de mudanças](#captura-de-mudanças-cdc-com-debezium): `src/cdc/demonstrar.py` |
| Camada analítica em formato aberto | [Lago Delta/Parquet](#lago-em-formato-aberto-delta-lake), [ADR 0024](docs/adr/0024-lago-delta-parquet-zstd.md) |
| Semântica de entrega declarada e demonstrada | `src/cdc/demonstrar_reprocessamento.py`, [ADR 0025](docs/adr/0025-mecanismo-de-ingestao-recarga-e-cdc.md) |
| Dado atrasado e reprocessamento de janela | [ADR 0026](docs/adr/0026-dado-atrasado-marca-dagua.md), `exportar_lago.py --janelas-alteradas` |
| Serialização e compressão justificadas | ADR 0024 (ZSTD 3 medido contra Snappy e GZIP; partição por quinquênio) |
| ADR com a opção nula | ADR 0025 (recarga agendada contra CDC) |
| Diário das semanas 7 a 10 | [docs/diario/diario_de_bordo.md](docs/diario/diario_de_bordo.md) |
| Testes sem banco nem Kafka no CI | `python -m unittest discover -s tests -p "test_unit_*.py"` (job `testes-unitarios`) |

---

## 🚀 2. Como Reproduzir o Projeto do Zero

### Atalho: tudo com Docker (um comando)
```bash
docker compose up --build
```
Sobe o PostgreSQL, roda o pipeline inteiro (API CKAN → bronze → silver → gold →
banco → vetorização) e abre o painel em http://localhost:8501. A primeira execução
baixa o modelo de embedding (~240 MB) e vetoriza ~12,5 mil planos de IC, o que leva
de vários minutos a meia hora em CPU, conforme a máquina; as seguintes só vetorizam o
que mudou. Para pular os planos de IC: `VETORIZAR_TIPOS=curso,documentacao`.

### A. Instalação do Ambiente
```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```
Todos os comandos abaixo assumem o `.venv` ativado (`deactivate` para sair).

### B. Execução do Pipeline de Dados (Bronze $\rightarrow$ Silver $\rightarrow$ Gold)
Cada etapa lê a camada anterior do PostgreSQL e grava a sua nele; nenhuma gera arquivo.
```bash
# 0. Banco: sobe o PostgreSQL e aplica as migrações do esquema
docker compose up -d db
python3 src/db/migrar.py

# 1. Ingestão automatizada via API CKAN e do Censo INEP -> bronze.* (Semana 1 - Dia 3)
python3 src/ingestion/ckan_client.py
python3 src/ingestion/inep_censo_superior.py

# 2. Transformação Silver: bronze.* -> silver.* (Semana 2 - Dia 1)
python3 src/pipeline/transform_silver.py

# 3. Camada Gold: silver.* -> gold.*, agregada em SQL no banco (gold.atualizar_gold, ADR 0027)
python3 src/pipeline/build_gold.py

# 4. Auditoria de qualidade (12 achados) e análise de k-anonimato, lidas da bronze (Semana 1 - Dias 4 e 5)
python3 src/audit/quality_auditor.py
python3 src/privacy/lgpd_check.py

# 5. Povoamento dimensional (Silver 3NF e Star Schema da gold) e export para o lago Delta
python3 src/db/povoar_dimensional.py
python3 src/db/exportar_lago.py --janelas-alteradas

# 6. Busca semântica e dicionário de dados do banco
python3 src/busca/vetorizar.py
python3 src/db/gerar_dicionario.py
```
Os passos 0 a 6 estão em sequência em `bash scripts/rodar_pipeline.sh` (com o banco no ar).

### C. Execução dos Testes Automatizados
```bash
python3 -m unittest discover -s tests -p "test_*.py"
```
Os testes de `tests/test_banco.py` são pulados se o banco não estiver acessível.

### D. Execução do Dashboard Interativo (Streamlit)
```bash
streamlit run src/dashboard/app.py
```
O painel lê a gold do banco. Sem banco, lê `export/gold.json`, se existir
(`python3 src/db/exportar_gold.py`), que é o que a versão do GitHub Pages usa. Com o
banco no ar, a página **busca semântica** aparece no menu lateral.

---

## 🗄️ Banco de Dados (PostgreSQL + pgvector)

O banco guarda o medalhão inteiro, um esquema por camada:

| Esquema | Conteúdo | Dado pessoal? |
| :--- | :--- | :--- |
| `bronze` | Recursos do portal como vieram, tudo em texto, e a procedência de cada download (`bronze.ingestoes`) | Sim (nascimento, raça/cor, nome de bolsista) |
| `silver` | Dado limpo e tipado, com PK, FK e `CHECK` | Sim (registro individual) |
| `gold` | Agregados por curso, com `CHECK (total >= 5)` garantindo o k-anonimato | Não |
| `busca` | Documentos vetorizados (pgvector, 384 dimensões, índice HNSW) | Não |

- **Esquema versionado:** as migrações em `db/migrations/` rodam em ordem, uma vez cada
  (`python3 src/db/migrar.py`); editar uma migração já aplicada é erro, e a mudança
  entra numa migração nova.
- **Contrato:** `gravar(df, tabela)` (`src/db/tabelas.py`) recusa DataFrame com coluna
  que a tabela não tem, ou sem coluna obrigatória. Coluna nova no pipeline exige migração.
- **Gravação idempotente:** cada tabela (e a silver inteira) é esvaziada e regravada
  numa transação só, preservando a ordem das linhas (`_ordem`), da qual a gold depende.
- **Sem arquivo em disco:** a ingestão lê o recurso baixado na memória e grava a
  bronze; encoding, separador, tamanho e sha256 de cada download ficam em
  `bronze.ingestoes`, que é a evidência usada pela auditoria de qualidade.
- **Privilégio mínimo:** o papel `observatorio_leitura` lê `gold` e `busca` e não
  enxerga `bronze` nem `silver` (`GRANT observatorio_leitura TO <usuario>`).
- **Dicionário:** `docs/dicionario_dados_banco.md` é gerado do catálogo do banco
  (`COMMENT ON` das migrações), então não desatualiza em relação ao esquema.

Conexão: variável `DATABASE_URL` (ou arquivo `.env`, ver `.env.example`). Sem ela, os
scripts usam o banco do `docker-compose.yml` em `localhost:5435`.

> ⚠️ **Banco remoto (ex.: Supabase):** o pipeline grava as três camadas em
> `DATABASE_URL`, e bronze e silver têm registro individual de discente. Rode o
> pipeline num banco local ou restrito; o que é público (painel no GitHub Pages) só
> recebe a gold, pelo export `export/gold.json` que o CI gera a partir do banco.

**Supabase:** a última etapa do pipeline, `src/db/sincronizar_supabase.py`, envia a gold, o
Star Schema e `busca.documentos` do banco local para `SUPABASE_DATABASE_URL`. A comparação é
pela chave natural: insere o que é novo, atualiza o que mudou (`--somente-inserir` desliga a
atualização) e não apaga nada; rodar de novo sem mudança não escreve nenhuma linha. No CI a
etapa usa o secret `SUPABASE_DATABASE_URL` e não roda em pull request.

### Lago em formato aberto (Delta Lake)
`src/db/exportar_lago.py` exporta a Silver 3NF (sem `silver.discentes`) e o Star Schema da
gold para tabelas Delta Lake em `data/lake/lote/` (não versionado). São arquivos Parquet com
ZSTD e o log de transações do Delta, que DuckDB, Spark, Polars ou pandas leem sem o banco.
Escolha do formato, da compressão e do particionamento: [ADR 0024](docs/adr/0024-lago-delta-parquet-zstd.md).

```bash
python3 src/db/exportar_lago.py                      # regrava todas as tabelas (idempotente)
python3 src/db/exportar_lago.py --quinquenio 2020    # reprocessa só essa janela dos vínculos
```

Cada execução é uma versão nova da tabela com o mesmo conteúdo, e não linhas a mais.
`silver.movimentacoes_vinculos` é particionada por quinquênio de ingresso, como no
PostgreSQL. `--quinquenio` regrava só as partições pedidas e deixa as outras intactas.
Leitura com DuckDB:

```sql
INSTALL delta; LOAD delta;
SELECT quinquenio_ingresso, tipo_saida_grupo, count(*)
FROM delta_scan('data/lake/lote/silver/movimentacoes_vinculos')
GROUP BY ALL ORDER BY ALL;
```

### Captura de mudanças (CDC com Debezium)
O segundo caminho até o lago, opcional (fora do pipeline e do CI). Por que a recarga
periódica é o mecanismo principal e o CDC é opcional, com latência e custo medidos:
[ADR 0025](docs/adr/0025-mecanismo-de-ingestao-recarga-e-cdc.md).
O OLTP aqui é a Silver 3NF, o modelo transacional da E1: as mudanças de `silver.cursos`,
`silver.estruturas_curriculares` e `silver.movimentacoes_vinculos` saem do WAL do PostgreSQL
por decodificação lógica (`pgoutput`, publicação `observatorio_cdc` da migração 0020), passam
pelo Debezium e pelo Kafka e chegam a tabelas Delta em `data/lake/cdc/`.

O serviço `db` sobe sempre com `wal_level=logical`, com ou sem o profile `cdc`. Todas as portas publicadas (PostgreSQL 5435, painel 8501, Kafka 9092 e Kafka Connect 8093) só
escutam em `127.0.0.1`: Kafka e Connect não têm autenticação.
`scripts/cdc.sh` usa `curl` e `jq`.

```bash
docker compose --profile cdc up -d db kafka connect   # banco, Kafka e Debezium
python3 src/db/migrar.py                               # cria a publicação
bash scripts/cdc.sh registrar                          # conector + slot de replicação (faz o snapshot inicial)
python3 src/cdc/consumidor.py                          # aplica as mudanças no lago (Ctrl+C para parar)
python3 src/cdc/demonstrar.py                          # INSERT, UPDATE e DELETE atravessando o fluxo
```

A demonstração insere, altera e exclui um curso sentinela no banco e mede quanto cada mudança
leva até aparecer no lago. No fim, o banco volta ao estado de antes. No lago, o sentinela
(`id_curso = 990001`) fica como linha marcada (`_deletado = true`). A demonstração usa um grupo
de consumidores próprio e pode rodar junto com o consumidor:

```
passo     latência   estado no lago
INSERT       0.87s   turno=DIURNO ativo=True _deletado=False _commit_lsn=2447817312
UPDATE       0.44s   turno=NOTURNO ativo=False _deletado=False _commit_lsn=2448437072
DELETE       0.64s   turno=NOTURNO ativo=False _deletado=True _commit_lsn=2448437288
```

- **Idempotente:** o consumidor aplica cada lote por `MERGE` na chave primária, e um evento
  só altera a linha se vier depois, no WAL, da última mudança aplicada nela. O offset só é
  confirmado no Kafka depois da gravação. Se o lote vier de novo, nada muda no lago, e
  reprocessar os tópicos inteiros (`--do-inicio`) também não.
- **Semântica de entrega:** o transporte é *no mínimo uma vez* e o efeito no lago é de
  *exatamente uma vez*. `python3 src/cdc/demonstrar_reprocessamento.py` força os
  reprocessamentos possíveis. Primeiro, o consumidor grava um lote de 100 mudanças e cai antes
  de confirmar o offset, e o Kafka entrega o lote de novo. Os 50 INSERTs são gravados antes de
  o UPDATE acontecer, e o UPDATE, numa transação própria, entra por outro `MERGE`: ele só vence
  a linha do lago pelo commit da transação (`_commit_lsn`). Depois, o grupo relê os tópicos
  do primeiro offset. Por fim, os sentinelas são excluídos, e o grupo relê tudo outra vez, com
  os INSERTs antigos, sem ressuscitar nenhum. A demonstração usa um grupo de consumidores
  próprio (`observatorio-reprocessamento`) e pode rodar junto com o consumidor.
  A impressão digital do lago (sha256 de todas as linhas, inclusive `_gravado_em`) não muda
  com o reprocessamento: nenhuma linha é sequer regravada. A demonstração também confere que
  o lote mudou o lago e chegou com o valor do UPDATE (turno `NOTURNO`), com commit posterior
  ao do INSERT:

  ```
  cenário                                    mensagens lidas  linhas no lago  sentinelas vivos   impressão digital
  estado inicial (tópicos esvaziados)                      0         153,001                 0   c44e70a2ae08
  lote gravado, queda antes de confirmar                 100         153,001                50   8ced07c73c2c
  retomada: o lote é entregue de novo                    100         153,001                50   8ced07c73c2c
  reprocessamento do primeiro offset                 766,353         153,001                50   8ced07c73c2c
  sentinelas excluídos do banco                           50         153,001                 0   0954a3c5f0fb
  reprocessamento depois da exclusão                 766,403         153,001                 0   0954a3c5f0fb
  ```

  Os números variam de uma execução para outra: a impressão digital inclui a hora da gravação,
  e as mensagens lidas crescem com o histórico dos tópicos. O que vale é a igualdade dentro de
  cada execução. Depois da primeira, os 50 sentinelas ficam no lago marcados com
  `_deletado = true`, e por isso a linha "estado inicial" já tem 153.001 linhas. Numa primeira
  execução, ela teria 50 a menos.

  Confirmar o offset antes de gravar daria *no máximo uma vez*: uma queda entre as duas
  operações perderia o lote em silêncio. Só um reprocessamento manual do tópico (`--do-inicio`)
  o recuperaria, e só enquanto o tópico ainda tiver o histórico: os tópicos não têm volume, e
  recriar o container do Kafka apaga tudo. Não há transação entre o Kafka e o Delta, e o
  exatamente-uma-vez de ponta a ponta sai da idempotência do MERGE.
- **Exclusão:** um DELETE vira marca (`_deletado = true`), para que um INSERT antigo
  reprocessado não ressuscite a linha. Quem lê filtra por `NOT _deletado`.
- **TRUNCATE:** a recarga da Silver 3NF começa com `TRUNCATE`, que marca as linhas anteriores
  a ele. Depois de rodar `src/db/povoar_silver_3nf.py` com o CDC no ar, o lago ficou idêntico
  ao banco, tupla a tupla (152.680 vínculos).
- **Arquivos pequenos:** cada `MERGE` grava arquivos novos. O consumidor os junta
  (`optimize.compact`) a cada 50 lotes e ao esvaziar os tópicos.
- **Slot de replicação:** o slot segura WAL enquanto o conector está parado. `bash scripts/cdc.sh remover`
  apaga o conector, os offsets dele e o slot. `max_slot_wal_keep_size=2GB` limita o estrago se
  ninguém remover.
- **Fluxo interrompido:** há três jeitos de o fluxo perder eventos: o slot é invalidado
  pelo `max_slot_wal_keep_size`, o container do Kafka é recriado (os tópicos não têm volume) ou
  os tópicos foram criados antes da retenção sem limite de tempo. Em qualquer um deles,
  `remover` e `registrar` refazem o snapshot. O snapshot só traz as linhas que ainda existem.
  Por isso, ao fim do snapshot de cada tabela, o consumidor marca como excluídas as linhas do
  lago anteriores a ele: assim, um DELETE perdido não deixa a linha viva. O conector cria os
  tópicos com `retention.ms=-1`: um consumidor parado não perde eventos por tempo.
- **Banco recriado ou restaurado:** o WAL recomeça numa posição menor que a do lago, e os
  eventos novos perderiam o `MERGE` para as linhas antigas. O consumidor compara o lago com
  `pg_current_wal_lsn()` quando chega um lote mais antigo que o lago. Se o lago estiver à
  frente, ele aborta e pede para apagar `data/lake/cdc/`.
- **Mudança de esquema:** as colunas e a chave são lidas do catálogo só quando o consumidor sobe.
  Uma coluna nova na Silver é ignorada sem aviso. Alterou a Silver? Apague `data/lake/cdc/` e
  reprocesse com `python3 src/cdc/consumidor.py --do-inicio --ate-esvaziar`.

### Dado atrasado e reprocessamento de janela
Uma saída só entra no arquivo do portal quando é registrada (a formatura, com o registro do
diploma), então um semestre continua recebendo vínculos depois de terminar. No SIGAA publicado
em 15/07/2024, o 2023/1 tem 4.176 formaturas, e o 2024/1, só 651. Cada carga da Silver 3NF
grava a marca d'água (o último período dado como fechado: fim do semestre mais 4 meses de
tolerância, antes da publicação) e um retrato dos vínculos por ano de ingresso, desfecho e
período de saída. A view `silver.chegadas_por_carga` compara cada carga com a anterior:

| Chegada | Período de saída | Tratamento |
|---|---|---|
| `NO_PRAZO` | depois da marca d'água da carga anterior, ainda aberto | aceita |
| `ATRASADA` | até a marca d'água da carga anterior, já dado como fechado | aceita e registrada; aviso no log quando revisa coorte já publicada na gold |
| `SEM_PERIODO` | sem período (ativo, cancelado no SIGAA, formado sem diploma) | aceita |

Nada é descartado: a fonte é a referência, e a gold é recalculada a cada carga. No lago,
`--janelas-alteradas` regrava só os quinquênios que diferem do banco, e as outras partições
ficam com os mesmos arquivos. Decisão e medições: [ADR 0026](docs/adr/0026-dado-atrasado-marca-dagua.md).

```bash
python3 src/db/dado_atrasado.py                       # o que chegou na última carga, por quinquênio
python3 src/db/dado_atrasado.py --medir               # atraso do registro do diploma no SIGRA
python3 src/db/exportar_lago.py --janelas-alteradas   # regrava só as janelas que mudaram
python3 src/db/demonstrar_dado_atrasado.py            # uma publicação no prazo e uma atrasada, desfeitas no fim
```

### Busca semântica
Cada curso da gold, cada plano de iniciação científica (título, ano, curso e linha,
sem nome nem matrícula) e cada seção da documentação em `docs/` vira um documento
vetorizado com o modelo multilíngue `paraphrase-multilingual-MiniLM-L12-v2`.
A busca compara a consulta por distância de cosseno no pgvector:

```bash
python3 src/busca/buscar.py "inteligência artificial na saúde" --tipo projeto_pibic -k 10
python3 src/busca/buscar.py "risco de reidentificação dos alunos" --tipo documentacao
python3 src/busca/buscar.py "engenharias com formatura muito atrasada" --tipo curso
```

**Limite medido:** o embedding capta tema, não número. Nos planos de IC e na
documentação a busca acerta bem (ex.: 0,83 de similaridade no primeiro resultado de
"inteligência artificial na saúde"). Já "cursos noturnos com muita evasão" acerta o
turno mas mistura faixas de evasão, mesmo com o texto de cada curso descrevendo a
faixa ("evasão alta", "formatura com muito atraso"). Para filtrar por atributo, use
SQL em `gold.retencao_cursos_unb` ou o painel.

---

## 🔄 CI/CD e Publicação

O workflow [`.github/workflows/medalhao.yml`](.github/workflows/medalhao.yml) roda
a cada `push` na `main`, em cada Pull Request e sob demanda (`workflow_dispatch`):

1. **Job `pipeline`** — executa o medalhão do zero numa máquina limpa, com um
   PostgreSQL com pgvector como serviço: migrações → ingestão CKAN e INEP (bronze) →
   Silver → Gold → auditoria → privacidade → vetorização de cursos e documentação, cada
   etapa gravando direto no banco. Roda a suíte de testes como verificação
   determinística dos contratos da camada Gold e do banco. As camadas Bronze/Silver
   (que contêm dado pessoal) **nunca** saem do runner; só o export da Gold agregada
   (k ≥ 5, `export/gold.json`) e os relatórios em `docs/` são empacotados.
2. **Job `deploy`** — publica o dashboard Streamlit completo no **GitHub Pages**
   via [`stlite`](https://github.com/whitphx/stlite) (Python roda no navegador do
   usuário, sem servidor): **https://observatorio-unb.github.io/observatorio-unb/**

A atualização dos dados fica em [`.github/workflows/atualiza-dados.yml`](.github/workflows/atualiza-dados.yml),
que roda no dia 1 de cada mês (06:00 UTC) e sob demanda: coleta as fontes (portal
dados.unb.br, INEP e valor da bolsa IC do CNPq), roda `scripts/rodar_pipeline.sh` e os
testes e, se algo mudou, commita a Gold, os metadados do CKAN
(`data/bronze/metadata_*.json`), a série do valor da bolsa e os relatórios gerados direto
na `main` pelo `github-actions[bot]`. Em seguida dispara o `medalhao.yml` para republicar
o painel.

**Configuração única necessária:** em *Settings → Pages*, definir *Source* =
**GitHub Actions**.

---

## 📄 Licença

Código licenciado sob **GNU General Public License v3.0** — ver [LICENSE](LICENSE).
Os dados brutos são do portal [dados.unb.br](https://dados.unb.br); as camadas
derivadas (Gold) seguem os termos de uso do portal de origem.

---

## 📊 3. Principais Resultados e Achados

Recorte: SIGRA + SIGAA, coortes de ingresso 2010-2016 (as com 8 anos ou mais de acompanhamento). Os números abaixo são da Gold de 09/2026; a atualização mensal pode alterá-los.

1. **Taxa de Formatura no Tempo Ideal**: Apenas **50.36%** dos formados na UnB concluem o curso dentro do prazo regulamentar da matriz curricular.
2. **Tempo Médio Global de Conclusão**: **11.77 semestres** (~5.9 anos).
3. **Cursos com Maior Retenção Crítica (IRC)**: *Física Computacional*, *Computação*, *Ciência da Computação* e *Línguas Estrangeiras Aplicadas - MSI* combinam atrasos médios de 2,8 a 4,3 semestres e taxas de evasão acima de 59%.
4. **Cursos com Maior Pontualidade**: *Medicina* (83.72% no tempo ideal), *Direito* (82.75%) e *Língua de Sinais Brasileira - Português como Segunda Língua* (81.82%).
5. **Cursos Noturnos**: Apresentam evasão média maior (**50.90%** vs. **40.85%** no diurno; cursos com oferta diurna e noturna sob o mesmo nome ficam fora da comparação).
6. **Taxa de Casamento dos Joins**: **100%** dos 152.680 vínculos de graduação integrados com estruturas curriculares.
