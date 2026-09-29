# Registro de Risco de Privacidade e Avaliação LGPD (Dia 5 - Semana 1)

**Projeto**: Análise de Retenção e Formatura nos Cursos da UnB
**Bases Analisadas**: `bronze.sigra_discentes`, `bronze.sigaa_discentes` (Graduação)

---

## 1. Avaliação Analítica de Quase-Identificadores e k-Anonimato

- **Quase-identificadores Testados**: `(curso, data_nascimento, sexo, raca_cor)`
- Cada base é avaliada em separado: são arquivos distintos no portal, com pseudônimos que não se ligam.

- **Risco de reidentificação**: registro com k = 1 é o único aluno com aquela combinação de curso, nascimento, sexo e raça/cor; quem conhece esses dados de um colega o encontra na base e descobre forma de ingresso, cota e forma de saída. Por isso a base individual não é publicada.

| Base | Registros de Graduação | Registros com k = 1 (Unicidade Absoluta) | k Mínimo |
| :--- | :--- | :--- | :--- |
| SIGRA | 60,695 | 53,977 (88.93%) | k = 1 |
| SIGAA | 91,985 | 60,366 (65.63%) | k = 1 |

### Distribuição de Frequência de Grupos de Equivalência (SIGRA):
| Tamanho do Grupo (k) | Quantidade de Grupos | Descrição |
| :--- | :--- | :--- |
| k = 1 | 53,977 grupos | Identificação unívoca (risco máximo) |
| k = 2 | 3,055 grupos | Grupo com 2 pessoas indistinguíveis |
| k = 3 | 178 grupos | Grupo com 3 pessoas indistinguíveis |
| k = 4 | 16 grupos | Grupo com 4 pessoas indistinguíveis |
| k = 5 | 2 grupos | Grupo com 5 pessoas indistinguíveis |

### Distribuição de Frequência de Grupos de Equivalência (SIGAA):
| Tamanho do Grupo (k) | Quantidade de Grupos | Descrição |
| :--- | :--- | :--- |
| k = 1 | 60,366 grupos | Identificação unívoca (risco máximo) |
| k = 2 | 4,258 grupos | Grupo com 2 pessoas indistinguíveis |
| k = 3 | 1,785 grupos | Grupo com 3 pessoas indistinguíveis |
| k = 4 | 1,326 grupos | Grupo com 4 pessoas indistinguíveis |
| k = 5 | 906 grupos | Grupo com 5 pessoas indistinguíveis |

---

## 2. Enquadramento Legal e Princípios da LGPD (Lei nº 13.709/2018)

1. **Dado Pessoal vs. Anonimizado (Art. 5º, I e III)**:
   - Embora nomes e CPFs completos tenham sido retirados no SIGRA e no SIGAA, a presença conjunta de data de nascimento exata, sexo, raça e cota configura *dados pessoais indiretos* (quase-identificadores).
   - Pseudonimização não equivale a anonimização: a reidentificação é viável cruzando com listas de vestibular ou diários oficiais.
2. **Princípio da Finalidade e Necessidade (Art. 6º, I e III)**:
   - O portal da transparência visa a prestação de contas pública. Contudo, dados demográficos sensíveis (raça/cor, data de nascimento) não são necessários para a finalidade de auditar o tempo de curso individualmente.
3. **O que é ESTRITAMENTE PROIBIDO neste Projeto**:
   - ❌ Executar qualquer rotina de cruzamento com fontes externas para reidentificar discentes;
   - ❌ Republicar ou expor microdados de discentes em nível individual no repositório ou no dashboard;
   - ❌ Realizar inferências sobre indivíduos específicos.

---

## 3. Salvaguardas Metodológicas e Regras da Camada Gold

Para mitigar 100% dos riscos e garantir conformidade ética:
1. **Agregação Obrigatória**: Todas as métricas de tempo real de formatura, retenção e evasão são calculadas e agregadas exclusivamente por `curso` e `departamento`.
2. **Supressão de Pequenos Grupos**: Qualquer agregação que envolva menos de 5 discentes terá os detalhes suprimidos para assegurar $k \ge 5$.
3. **Descarte de Quase-Identificadores Sensíveis**: As colunas `data_nascimento`, `sexo` e `raca_cor` são eliminadas na transformação da camada Silver para a Gold.
4. **Minimização dos Arquivos Nominais**: O portal publica `SIGAA_Concluintes_*` e a lista `sigaa_ativos_AAAA_S.csv` com nome completo e CPF parcial. Os de concluintes não são baixados. Da lista de ativos, a ingestão (`src/ingestion/ckan_client.py`) lê o arquivo em memória e grava só `grau`, `curso`, `ano_ingresso` e `periodo_ingresso`: nome, CPF e nacionalidade nunca chegam ao disco, ao banco nem ao CI (LGPD, art. 6º, III). O mesmo vale para os bolsistas de IC: a ingestão grava só ano, título, tipo de bolsa, linha de pesquisa, cota, vigência, unidade e situação, sem nome e matrícula do discente nem nome do orientador.