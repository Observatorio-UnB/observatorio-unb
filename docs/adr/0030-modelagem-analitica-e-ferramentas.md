# ADR 0030: Modelagem analítica em estrela com fato no grão do curso, transformação em dbt e orquestração em Dagster

- **Status:** Aceita
- **Data:** 2026-11-01

## Contexto

A pergunta de gestão da E1 (`docs/challenge_canvas.md`) é quais cursos de graduação têm a retenção e o atraso mais críticos, para o DEG priorizar a intervenção. A E3 pede três escolhas: o modelo analítico que responde a ela, o grão do fato, e as ferramentas de transformação e orquestração.

### Evidência da E2: quantas fontes e quanto o esquema muda

**Fontes integradas: 8.** São 7 tabelas na bronze e um JSON:

| Fonte | Tabela | Colunas |
|---|---|---:|
| Discentes SIGRA (até 2020) | `bronze.sigra_discentes` | 16 |
| Discentes SIGAA (desde 2021) | `bronze.sigaa_discentes` | 15 |
| Ativos SIGAA | `bronze.sigaa_ativos` | 6 |
| Catálogo de cursos (todas as versões) | `bronze.cursos_graduacao` | 27 |
| Estruturas curriculares | `bronze.estrutura_curricular` | 27 |
| Bolsistas de IC | `bronze.bolsistas_iniciacao_cientifica` | 11 |
| Censo da Educação Superior (INEP) | `bronze.inep_censo_superior_federais` | 19 |
| Valor da bolsa IC (CNPq) | `data/bronze/cnpq_valor_bolsa_ic.json` | — |

**Todas convergem numa chave de negócio só, o curso.** O que varia entre fontes e versões é a forma da chave e das colunas, não o conceito:

- Os dois sistemas acadêmicos têm esquemas diferentes para o mesmo fato (o vínculo). O SIGAA não publica o período de saída (ADR 0015).
- O catálogo muda de colunas entre versões: as versões novas não trazem `unidade_responsavel` e deixam de listar códigos (ADR 0021).
- O portal publica versões novas dos arquivos com outros nomes (ADR 0002).
- O nome do curso difere entre discentes, matriz e IC (ADR 0003).
- O esquema do banco teve 21 migrações entre 24/09 e 13/10, 11 delas de 28/09 em diante.

Todas essas mudanças foram absorvidas entre a bronze e a silver: harmonização do nome canônico, consolidação do catálogo e contrato de carga que recusa coluna nova (`src/db/tabelas.py`). A bronze guarda o dado bruto, e `bronze.ingestoes` guarda o hash, o tamanho e o metadado de cada arquivo. O volume é pequeno: 152.680 vínculos.

## Alternativas e decisão

Cada uma das quatro escolhas abaixo compara as alternativas numa tabela e termina na decisão.

### 1. Modelo: esquema estrela, com tabela larga só na camada de consumo

**Alternativas:**

| Critério | Estrela (Kimball) | Data Vault 2.0 | One big table (OBT) |
|---|---|---|---|
| Fontes que integram na mesma chave | Dimensões conformadas no curso | Hub de curso, links e satélites por fonte | Uma tabela com tudo desnormalizado |
| Mudança de esquema da fonte | Absorvida na silver; o star não muda | Absorvida com satélite novo, sem mexer no resto | Cada coluna nova muda a tabela inteira |
| Histórico de atributo | SCD tipo 2 na dimensão (ADR 0028) | Nativo nos satélites | Duplicado em cada linha |
| Tabelas para responder à E1 | 1 fato e 2 dimensões | Hubs (curso, matriz, vínculo), links entre eles e um satélite por fonte, mais um mart em estrela por cima | 1 |
| Auditoria de carga | `bronze.ingestoes` (hash por arquivo) | Nativa (carimbo e fonte por linha) | Nenhuma |

- **Data Vault foi descartado.** Ele compensa quando muitas fontes, com chaves de negócio diferentes, mudam de esquema com frequência, e quando cada linha precisa de auditoria própria. Aqui as 8 fontes convergem numa chave só, e as mudanças de esquema já são absorvidas na silver. A auditoria por arquivo existe na bronze. O vault multiplicaria as tabelas e ainda exigiria um mart em estrela para o painel.
- **OBT foi descartada como modelo.** Ela fica só como forma de consumo, que é o que `gold.mv_dashboard_executivo` (e `painel_cursos_criticos`, no dbt) já é. Como modelo, repetiria os atributos do curso em cada linha e perderia o histórico da SCD.

**Decisão:** fica a estrela que existe desde a E2 (migração 0012), com a `dim_curso` em SCD tipo 2 (ADR 0028).

### 2. Grão: o fato de retenção no grão do curso

**Alternativas (medidas):**

Para medir os grãos, calculei cada nível sobre as coortes maduras da base atual (consulta em [`medicoes/0030_granularidade_do_fato.sql`](medicoes/0030_granularidade_do_fato.sql)): ingresso de 2010 a 2016, 68.339 vínculos, 101 cursos. Os grupos com menos de 5 vínculos são suprimidos (k-anonimato, ADR 0005):

| Grão | Linhas | Grupos com k < 5 | Vínculos perdidos | Tamanho | Responde à E1? |
|---|---:|---:|---:|---:|---|
| Vínculo (fato transacional) | 68.339 | 100% | 100% | 4,5 MB | Não pode ser publicado |
| **Curso** | **101** | 5,9% | **0,0%** (12) | 16 kB | **Sim: ranking por curso** |
| Curso × coorte (ano de ingresso) | 633 | 5,7% | 0,1% (76) | 72 kB | Sim, e mostra a tendência entre coortes |
| Curso × coorte × desfecho × semestre de saída | 14.359 | 67,6% | **28,1%** (19.196) | 1,5 MB | Não: perde um vínculo em cada quatro |

**Decisão:** o fato de retenção fica no grão do curso, declarado e imposto pela chave `UNIQUE (sk_curso)` (PR #48). A pergunta da E1 é um ranking de cursos, e esse grão a responde sem perder vínculo.

- **Curso × coorte é a extensão viável** quando o DEG quiser saber se um curso está piorando. Perde só 0,1% dos vínculos, mas hoje só há 7 coortes maduras. Fica registrado como o próximo fato, e não como substituto.
- **O grão fino demais estoura a supressão:** a granularidade por semestre de saída perde 28% dos vínculos para o k-anonimato.
- **O grão do vínculo serve à transformação, não ao consumo.** Ele já existe na Silver 3NF e no lago Delta, fora do alcance público.

### 3. Transformação: dbt

**Alternativas:**

| | dbt | SQLMesh | Opção nula: SQL em scripts Python (como na E2) |
|---|---|---|---|
| Grafo | Inferido dos `ref()` | Inferido do SQL | Escrito à mão, na ordem dos `execute` |
| Testes de dados | Genéricos e singulares, por modelo | Auditorias e testes unitários | `unittest` separado dos modelos |
| Documentação e linhagem | `dbt docs`, com página estática | UI própria (servidor) | Nenhuma |
| Backfill e ambientes | `--full-refresh`, variáveis, alvos | Planos e backfill por intervalo embutidos | Nenhum |

**A opção nula foi levada a sério.** Os modelos levam menos de 5 s, e o SQL já existe e é testado. Ela foi descartada porque não dá o que a E3 cobra: o grafo fica implícito, e não há testes por modelo nem linhagem. O SQLMesh brilha em modelos incrementais grandes, que aqui não existem.

**Decisão:** dbt, em três camadas (staging, intermediate e marts). O detalhamento está no ADR 0029.

### 4. Orquestração: Dagster, disparado pelo GitHub Actions

**Alternativas:**

| | Airflow | Dagster | Opção nula: cron do GitHub Actions + `rodar_pipeline.sh` |
|---|---|---|---|
| Infraestrutura | Agendador, webserver e banco de metadados sempre no ar | Biblioteca Python; a UI e o daemon são opcionais | Nenhuma (já existe) |
| Grafo | DAG de tarefas | Grafo de assets; os modelos dbt viram assets (`dagster-dbt`) | Linear, na ordem do script |
| Retry | Por tarefa | Por asset (`RetryPolicy`) | Só por job inteiro, ou laço manual no shell |
| Backfill | Por intervalo de execução | Por partição (ex.: quinquênio de ingresso, a partição do lago) | Escrito à mão (`workflow_dispatch` com parâmetros) |
| Execução no CI | Exige um servidor | `dagster asset materialize` roda dentro do job | Nativa |

- **A opção nula falha num ponto concreto.** Para ter grafo no GitHub Actions, cada etapa precisaria ser um job com `needs:`. Mas cada job tem o seu próprio container de Postgres, então as etapas não compartilham o banco. O pipeline teria de ficar num job só, com as etapas em fila. O retry viraria laço de shell e o backfill, parâmetro escrito à mão.
- **Airflow foi descartado pela infraestrutura.** Ele precisa de três serviços sempre no ar para um lote mensal, e o projeto não tem servidor: roda no runner do CI e no Supabase.

**Decisão:** Dagster. O grafo de assets inclui os modelos dbt, com retry por asset e backfill por partição. Ele roda como biblioteca dentro do job do GitHub Actions, que segue como o agendador (cron mensal do `atualiza-dados.yml`). Localmente, `dagster dev` mostra o grafo e os backfills na UI. A implementação, a falha forçada para exercitar o retry e o backfill demonstrado ficam na issue #40.

## Consequências

- O modelo não muda de forma: a estrela da E2 continua. O que muda é o grão declarado no catálogo (PR #48), o histórico na `dim_curso` (ADR 0028) e o lugar da transformação (dbt, ADR 0029).
- O painel deve ler o mart do dbt, `painel_cursos_criticos`, que é a OBT de consumo (issue #44).
- O fato curso × coorte fica medido e documentado como próximo passo. Ele entra quando a pergunta de tendência for feita e houver mais coortes maduras.
- Novas dependências quando a #40 for feita: `dagster` e `dagster-dbt`. O agendamento continua no GitHub Actions, sem servidor novo.
- As medições de grão foram feitas sobre a base de 10/10/2026 (silver local). Com uma carga nova, os números mudam, mas a ordem de grandeza da supressão não.
