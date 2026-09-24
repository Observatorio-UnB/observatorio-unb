# 🎓 Observatório de Retenção, Formatura e Evasão da UnB

> **Challenge 2 de Dados Abertos da UnB** — Metodologia *Challenge Based Learning* (CBL)  
> **Tema**: Mapeamento do tempo real de integralização curricular, retenção crítica e evasão nos cursos de graduação.  
> **Stakeholder**: Decanato de Ensino de Graduação (DEG/DAA) e Coordenações de Curso da UnB.  
> **Portal de Origem**: [dados.unb.br](https://dados.unb.br) (API CKAN 2.11).  
> 
> 📄 **Documento de Síntese Completo**: Veja [RELATORIO_GERAL_PROJETO_SEMANAS_1_E_2.md](RELATORIO_GERAL_PROJETO_SEMANAS_1_E_2.md) para a explicação detalhada de como o projeto atende a 100% das duas primeiras semanas, a lógica das bases e o valor para o DEG.

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
│   └── caderno_analise.md           # Caderno de análise com respostas às 5 GQs e dinâmicas
├── db/
│   └── migrations/                  # Esquema versionado do PostgreSQL (0001 ... 0007)
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
│   │   └── build_gold.py
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

# 3. Camada Gold com join heterogêneo: silver.* -> gold.* (Semana 2 - Dia 1)
python3 src/pipeline/build_gold.py

# 4. Auditoria de qualidade (8 achados) e análise de k-anonimato, lidas da bronze (Semana 1 - Dias 4 e 5)
python3 src/audit/quality_auditor.py
python3 src/privacy/lgpd_check.py

# 5. Busca semântica e dicionário de dados do banco
python3 src/busca/vetorizar.py
python3 src/db/gerar_dicionario.py
```
Os passos 0 a 5 estão em sequência em `bash scripts/rodar_pipeline.sh` (com o banco no ar).

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
a cada `push` na `main`, em cada Pull Request, semanalmente (segunda 06:00 UTC) e
sob demanda (`workflow_dispatch`):

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

**Configuração única necessária:** em *Settings → Pages*, definir *Source* =
**GitHub Actions**.

---

## 📄 Licença

Código licenciado sob **GNU General Public License v3.0** — ver [LICENSE](LICENSE).
Os dados brutos são do portal [dados.unb.br](https://dados.unb.br); as camadas
derivadas (Gold) seguem os termos de uso do portal de origem.

---

## 📊 3. Principais Resultados e Achados

1. **Taxa de Formatura no Tempo Ideal**: Apenas **62.43%** dos formados na UnB concluem o curso dentro do prazo regulamentar da matriz curricular.
2. **Tempo Médio Global de Conclusão**: **10.85 semestres** (~5.4 anos).
3. **Cursos com Maior Retenção Crítica (IRC)**: *Engenharias*, *Física Computacional*, *Ciência da Computação* e *Computação* combinam atrasos médios de mais de 3 semestres e taxas de evasão superiores a 58%.
4. **Cursos com Maior Pontualidade**: *Direito* (92.45% no tempo ideal), *Gestão do Agronegócio* (89.18%) e *Engenharia de Redes* (88.48%).
5. **Cursos Noturnos**: Apresentam taxas de evasão significativamente maiores (**52.54%** vs. **29.43%** no diurno) devido à conciliação com trabalho.
6. **Taxa de Casamento dos Joins**: **97.54%** de cobertura de discentes integrados com estruturas curriculares.
