# Registro de Risco de Privacidade e Avaliação LGPD (Dia 5 - Semana 1)

**Projeto**: Análise de Retenção e Formatura nos Cursos da UnB
**Base Analisada**: `bronze.sigra_discentes` (Graduação)

---

## 1. Avaliação Analítica de Quase-Identificadores e k-Anonimato

- **Total de Registros de Graduação Avaliados**: 60,695
- **Quase-identificadores Testados**: `(curso, data_nascimento, sexo, raca_cor)`
- **Registros com k = 1 (Unicidade Absoluta)**: 53,977 (88.93% dos discentes)
- **k-Anonimato Mínimo da Base Bruta**: k = 1

### Distribuição de Frequência de Grupos de Equivalência:
| Tamanho do Grupo (k) | Quantidade de Grupos | Descrição |
| :--- | :--- | :--- |
| k = 1 | 53,977 grupos | Identificação unívoca (risco máximo) |
| k = 2 | 3,055 grupos | Grupo com 2 pessoas indistinguíveis |
| k = 3 | 178 grupos | Grupo com 3 pessoas indistinguíveis |
| k = 4 | 16 grupos | Grupo com 4 pessoas indistinguíveis |
| k = 5 | 2 grupos | Grupo com 5 pessoas indistinguíveis |

---

## 2. Enquadramento Legal e Princípios da LGPD (Lei nº 13.709/2018)

1. **Dado Pessoal vs. Anonimizado (Art. 5º, I e III)**:
   - Embora nomes e CPFs completos tenham sido retirados no SIGRA, a presença conjunta de data de nascimento exata, sexo, raça e cota configura *dados pessoais indiretos* (quase-identificadores).
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