# Challenge Canvas v2 (Semanas 1 e 2)

## 1. Identificação do Projeto
- **Título**: Mapeamento da Retenção, Tempo Real de Formatura e Evasão nos Cursos de Graduação da UnB
- **Trilha Temática**: Vida Acadêmica, Formação e Permanência (T1 / T2 / T4)
- **Portal de Origem**: [dados.unb.br](https://dados.unb.br) (API CKAN 2.11)

---

## 2. Stakeholder e Decisão Real
- **Stakeholder**: Decanato de Ensino de Graduação (DEG/DAA) e Coordenações de Curso da UnB.
- **Decisão que Precisa Tomar**:
  > *"Em quais cursos a taxa de retenção e atraso na integralização curricular é mais crítica, demandando intervenções institucionais prioritárias (como revisão de pré-requisitos, ampliação de prazos máximos de formatura, reestruturação pedagógica de disciplinas-filtro ou reforço de turmas com alta reprovação)?"*

---

## 3. Essential Question (EQ) & Challenge
- **Essential Question (EQ)**:
  > **Quanto tempo os discentes da UnB realmente levam para se formar em comparação ao planejado pela estrutura curricular, e quais cursos apresentam os maiores índices de retenção e jubilamento?**
- **Challenge Statement**:
  > **Mapear, quantificar e ranquear a discrepância entre o tempo regulamentar e o tempo real de conclusão nos cursos de graduação da UnB, construindo um painel interativo de suporte à decisão pedagógica do DEG.**

---

## 4. As Cinco Guiding Questions (GQs)

| GQ | Pergunta Menor | Métrica Associada | Conjuntos de Dados Candidatos |
| :--- | :--- | :--- | :--- |
| **GQ 1** | Qual o percentual de concluintes que se forma no tempo mínimo, ideal e acima do ideal por curso? | `% no Prazo Ideal` e `% Acima do Ideal` | `sigra_discentes.csv` + `sigaa_discentes.csv` + `estrutura_curricular.csv` |
| **GQ 2** | Qual é a diferença média (em semestres) entre a duração prevista na estrutura curricular e a duração real da graduação? | `Desvio Médio de Integralização (semestres)` | `sigra_discentes.csv` + `sigaa_discentes.csv` + `estrutura_curricular.csv` |
| **GQ 3** | Qual a proporção de saídas por formatura versus evasão (saída sem diploma: abandono, jubilamento, 3 reprovações, mudança de curso, cancelamento) em cada curso? | `Taxa de Evasão / Desligamento Crítico (%)` | `sigra_discentes.csv` + `sigaa_discentes.csv` |
| **GQ 4** | Cursos noturnos apresentam desvio de tempo de formação significativamente maior que os cursos diurnos? | `Diferença de Desvio Médio: Noturno vs. Diurno` | `sigra_discentes.csv` + `cursos_graduacao.csv` |
| **GQ 5** | Existe correlação entre a carga horária total da matriz curricular e o tempo médio de atraso na formatura? | `Coeficiente de Correlação de Pearson (CH vs. Atraso)` | `estrutura_curricular.csv` + `sigra_discentes.csv` |

---

## 5. Slide Obrigatório: "O Que Este Dado NÃO Responde"

Para assegurar rigor científico e evitar conclusões precipitadas:
1. **Motivação Individual da Evasão/Atraso**: Os dados abertos não informam motivos pessoais, de saúde mental, necessidade de trabalhar, dificuldades socioeconômicas ou reprovações pontuais em disciplinas específicas.
2. **Semestre Exato de Ingresso e Saída**: SIGRA e SIGAA registram apenas o ano de ingresso (`2010`). O SIGRA publica o período de saída (`20141`); no SIGAA ele é estimado pela data de registro do diploma. Há uma incerteza residual de $\pm 1$ semestre metodológico.
3. **Mudanças Curriculares Individuais**: Alunos que mudaram de habilitação, transferiram de curso ou ingressaram sob uma matriz curricular antiga e migraram para uma nova não têm esse histórico de transição individualizado no arquivo estático.
4. **Cursos Descontinuados ou Muito Recentes**: Cursos novos com poucas turmas formadas ou cursos extintos possuem amostras estatísticas reduzidas.
