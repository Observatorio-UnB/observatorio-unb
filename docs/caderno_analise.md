# Caderno de Análise e Evidências (Dia 2 - Semana 2)

**Projeto**: Retenção, Tempo Real de Formatura e Evasão nos Cursos de Graduação da UnB  
**Stakeholder**: Decanato de Ensino de Graduação (DEG/DAA)  
**Base Analítica**: Camada Gold (`data/gold/retencao_cursos_unb.csv`)  
**Recorte**: vínculos de graduação do SIGRA (encerrados até 2020/1) e do SIGAA (extrato de 07/2024), coortes de ingresso 2010-2016 — as que têm pelo menos 8 anos de acompanhamento. Números da versão da Gold de 09/2026; a atualização mensal do portal pode alterá-los.  

---

## 1. Respostas Estruturadas às Cinco Guiding Questions (GQs)

### **GQ 1: Qual o percentual de concluintes que se forma no tempo mínimo, ideal e acima do ideal?**
- **Evidência Global**:
  - Na média de toda a UnB, **50.14%** dos formados integralizam o curso dentro do prazo ideal previsto pela matriz curricular.
  - **49.43%** dos egressos necessitam de semestres adicionais além do prazo ideal para conseguir outorga de grau (os 0.43% restantes são formados sem data de conclusão publicada).
  - A versão anterior, só com o SIGRA, mostrava 62.05% no prazo: ela enxergava apenas quem saiu até 2020, isto é, os que se formaram mais rápido. Os formados depois da migração, que só aparecem no SIGAA, são justamente os mais demorados.
- **Disparidade Extrema entre Cursos**:
  - Cursos com maior taxa de formatura no tempo ideal: *Medicina* (83.72%) e *Direito* (82.53%).
  - Cursos com menor taxa de formatura no tempo ideal (alta retenção): *Engenharia Aeroespacial* (3.3%), *Letras - Tradução - Inglês* (4.0%) e *Línguas Estrangeiras Aplicadas - MSI* (5.8%).

---

### **GQ 2: Qual é a diferença média (em semestres) entre a duração prevista e a duração real?**
- **Evidência Global**:
  - O tempo médio real de formatura na UnB é de **11.77 semestres** (~5.9 anos).
  - O desvio médio global em relação ao tempo ideal é de **+0.82 semestre** quando ponderado por todos os formados, mas varia drasticamente por área.
- **Áreas com Maior Atraso Real** (média entre cursos):
  - *Linguística, Letras e Artes* (**+2.06**), *Engenharias* (**+1.82**) e *Ciências Exatas e da Terra* (**+1.46 semestre**) além do tempo ideal (ex: Ciência da Computação tem tempo médio real de 13.25 semestres para uma matriz ideal de 9 semestres, desvio de **+4.25 semestres**).

---

### **GQ 3: Qual a proporção de saídas por formatura versus desligamentos críticos?**
- **Evidência Global**:
  - Do total de 68.339 vínculos das coortes 2010-2016, **51.28%** terminaram em *Formatura*, **44.07%** em *Evasão* (saída do curso sem diploma: abandono, desligamento, jubilamento, mudança de curso ou cancelamento no SIGAA) e **2.85%** seguiam ativos ou trancados em 07/2024.
  - Evasão inclui mudança de curso porque o SIGAA só marca o vínculo como CANCELADO, sem o motivo; é a definição de "evasão de curso" da Comissão Especial MEC/SESu (1996).
- **Cursos com Maior Evasão Crítica**:
  - *Física Computacional*: 76.19% de evasão.
  - *Matemática*: 73.40%.
  - *Computação*: 72.39%.
  - *Física*: 71.68%.
  - *Engenharia* (habilitação genérica de ingresso comum, onde a habilitação terminal ainda não foi escolhida) chega a 93.43%, porque a escolha da habilitação encerra o vínculo com o curso-tronco e conta como mudança de curso. Permanece na tabela e nas métricas globais por representar discentes reais da UnB, mas é descartada nas telas de Visão Executiva e Detalhe por Curso do dashboard por não ser um curso terminal válido para um raio-x individual (ver `docs/dicionario_dados_gold.md`).

---

### **GQ 4: Cursos noturnos apresentam desvio de tempo significativamente maior que os diurnos?**
- **Metodologia de Turno**: Cursos que se autodesignam no catálogo bruto como `MATUTINO`, `VESPERTINO` ou `MATUTINO E VESPERTINO` são unificados em **Diurno** (juntos cobrem o período diurno completo). Cursos com oferta diurna **e** noturna sob o mesmo nome (19, ex.: Direito, Física, Pedagogia) ficam como **Diurno e Noturno**: nenhuma fonte diz em qual oferta cada discente estudou, então eles não entram na comparação, que fica Diurno (64 cursos) vs. Noturno (12 cursos).
- **Evidência Comparativa**:
  - *Desvio de tempo em relação à matriz*: Cursos noturnos possuem matrizes curriculares que já preveem semestres adicionais em seu desenho curricular (tempo ideal médio de 11.25 semestres vs. 10.61 no diurno). Por isso, o desvio médio em relação à própria matriz é menor no noturno (**+0.78 semestre**) do que no diurno (**+1.56 semestre**; t de Welch ≈ −1,6, não significativo com só 12 cursos noturnos) — quem se forma no noturno atrasa menos em relação ao prazo já estendido da sua matriz.
  - *Impacto na Taxa de Evasão*: Cursos noturnos apresentam taxa média de evasão de **50.90%**, comparada a **40.85%** nos cursos diurnos (matutino + vespertino unificados). Os cursos com as duas ofertas ficam no meio (47.56%).
  - **Veredito**: A dificuldade no noturno se manifesta prioritariamente na **permanência e evasão** (abandono por conciliação de trabalho/estudo), e não no atraso de semestres de quem consegue formar — cuja matriz já prevê prazo mais longo.
- **Recorte Complementar por Grau Acadêmico (Bacharelado vs. Licenciatura)**: cursos de Licenciatura (13) apresentam evasão média de **52.96%**, acima dos **39.21%** dos cursos de Bacharelado (67, incluindo habilitações profissionais como Engenharia, Medicina e Arquitetura). Cursos com grau **Misto** (Bacharelado e Licenciatura sob o mesmo nome, sem forma confiável de separar os discentes — ex.: Química) ficam fora dessa comparação por não terem um grau único atribuível.

---

### **GQ 5: Existe correlação entre a carga horária total da matriz e o atraso na formatura?**
- **Coeficiente de Correlação de Pearson** (carga horária mínima × desvio médio, 95 cursos): $r = -0.160$ ($t \approx -1.56$, não significativa a 5%).
- **Interpretação**:
  - O atraso na formatura não decorre simplesmente da quantidade absoluta de horas do curso, pois cursos com altíssima carga horária (como Medicina e Engenharias) já possuem maior número de semestres regulamentares atribuídos.
  - O atraso está associado à **estrutura de pré-requisitos encadeados**, disciplinas com alta taxa de reprovação e oferta insuficiente de turmas.

---

## 2. Dinâmica Obrigatória: "A Correlação Suspeita"

> **Hipótese Ingênua**: *"Cursos noturnos têm menor atraso na formatura, portanto são mais fáceis que os diurnos."*

- **Por que a correlação é espúria / perigosa**:
  1. **Confundidor de Matriz**: O tempo ideal cadastrado para cursos noturnos é deliberadamente estendido (ex: 10 ou 12 semestres em vez de 8).
  2. **Viés de Sobrevivência (Survival Bias)**: Quem não aguenta o ritmo do curso noturno abandona (50.9% de evasão média nos cursos noturnos). Os poucos que chegam ao final são os discentes altamente resilientes que conseguem cumprir o prazo.
  3. **Conclusão para Decisão Institucional**: Avaliar a dificuldade de um curso exclusivamente pelo tempo de formatura sem considerar a taxa de evasão levaria o DEG a tomar decisões errôneas sobre a saúde acadêmica do curso.

---

## 3. Incerteza Residual e Limitações Declaradas
1. **Margem Temporal de $\pm 1$ Semestre**: Decorrente da ausência do semestre de ingresso nos arquivos brutos do SIGRA e do SIGAA (`ano_ingresso` de 4 dígitos).
2. **Semestre de Conclusão Estimado no SIGAA**: o SIGAA não publica o período de saída. Para os formados depois da migração ele é estimado pela data de registro do diploma (regra que acerta 94.6% no SIGRA), com possível erro de 1 semestre no calendário deslocado da pandemia (coluna `periodo_saida_estimado` na Silver).
3. **Mudanças de Habilitação**: Discentes que migraram entre habilitações (ex: Licenciatura para Bacharelado) herdam tempo acumulado da habilitação anterior.
4. **Casamento de 100%**: todos os 152.680 vínculos de graduação (SIGRA + SIGAA) foram correlacionados a estruturas curriculares ativas via harmonização canônica de nomes de curso (ver `regras_harmonizacao_canonicas.json`).
