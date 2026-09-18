# 🎓 Observatório de Retenção, Formatura e Evasão da UnB

> **Challenge 2 de Dados Abertos da UnB** — Metodologia *Challenge Based Learning* (CBL)  
> **Tema**: Mapeamento do tempo real de integralização curricular, retenção crítica e evasão nos cursos de graduação.  
> **Stakeholder**: Decanato de Ensino de Graduação (DEG/DAA) e Coordenações de Curso da UnB.  
> **Portal de Origem**: [dados.unb.br](https://dados.unb.br) (API CKAN 2.11).  
> 
> 📄 **Documento de Síntese Completo**: Veja [RELATORIO_GERAL_PROJETO_SEMANAS_1_E_2.md](file:///Users/quigonjinx/Documents/ultimoUnb/bd2/RELATORIO_GERAL_PROJETO_SEMANAS_1_E_2.md) para a explicação detalhada de como o projeto atende a 100% das duas primeiras semanas, a lógica das bases e o valor para o DEG.

---

## 📌 1. Visão Geral e Estrutura dos Entregáveis

Este repositório contém a solução completa para o desafio de 2 semanas, estruturada de forma modular, versionada e 100% reprodutível do zero:

```
bd2/
├── data/
│   ├── bronze/                      # Dados brutos baixados via API CKAN (imutáveis)
│   ├── silver/                      # Dados limpos, tipados e normalizados
│   └── gold/                        # Tabela analítica consolidada e métricas
├── docs/
│   ├── challenge_canvas.md          # Challenge Canvas v2 (Stakeholder, EQ, Challenge, 5 GQs)
│   ├── relatorio_qualidade.md       # Relatório de Qualidade (8 achados com evidência + Issue CPD)
│   ├── registro_privacidade_lgpd.md # Análise de privacidade, quase-identificadores e k-anonimato
│   ├── datasheet_gold.md            # Datasheet for Datasets (padrão Gebru et al.)
│   ├── dicionario_dados_gold.md     # Dicionário de dados formal da tabela Gold
│   └── caderno_analise.md           # Caderno de análise com respostas às 5 GQs e dinâmicas
├── src/
│   ├── ingestion/                   # Ingestão programática via API CKAN
│   │   └── ckan_client.py
│   ├── audit/                       # Auditoria automatizada de inconsistências
│   │   └── quality_auditor.py
│   ├── privacy/                     # Avaliação de conformidade LGPD
│   │   └── lgpd_check.py
│   ├── pipeline/                    # Pipeline em camadas (Bronze -> Silver -> Gold)
│   │   ├── transform_silver.py
│   │   └── build_gold.py
│   └── dashboard/                   # Produto interativo em Streamlit
│       └── app.py
├── tests/
│   └── test_pipeline.py             # Testes automatizados de esquema e integridade
├── requirements.txt
└── README.md
```

---

## 🚀 2. Como Reproduzir o Projeto do Zero

### A. Instalação do Ambiente
```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```
Todos os comandos abaixo assumem o `.venv` ativado (`deactivate` para sair).

### B. Execução do Pipeline de Dados (Bronze $\rightarrow$ Silver $\rightarrow$ Gold)
```bash
# 1. Ingestão automatizada via API CKAN (Semana 1 - Dia 3)
python3 src/ingestion/ckan_client.py

# 2. Auditoria de qualidade e geração do relatório com 8 achados (Semana 1 - Dia 4)
python3 src/audit/quality_auditor.py

# 3. Análise de privacidade e k-anonimato (Semana 1 - Dia 5)
python3 src/privacy/lgpd_check.py

# 4. Transformação Silver (Semana 2 - Dia 1)
python3 src/pipeline/transform_silver.py

# 5. Construção da Camada Gold com join heterogêneo (Semana 2 - Dia 1)
python3 src/pipeline/build_gold.py
```

### C. Execução dos Testes Automatizados
```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

### D. Execução do Dashboard Interativo (Streamlit)
```bash
streamlit run src/dashboard/app.py
```

---

## 🔄 CI/CD e Publicação

O workflow [`.github/workflows/medalhao.yml`](.github/workflows/medalhao.yml) roda
a cada `push` na `main`, em cada Pull Request, semanalmente (segunda 06:00 UTC) e
sob demanda (`workflow_dispatch`):

1. **Job `pipeline`** — executa o medalhão do zero numa máquina limpa
   (ingestão CKAN → Silver → Gold → auditoria → privacidade) e roda a suíte de
   testes como verificação determinística dos contratos da camada Gold. As
   camadas Bronze/Silver (que contêm dado pessoal) **nunca** saem do runner; só a
   Gold agregada (k ≥ 5) e os relatórios em `docs/` são empacotados.
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
