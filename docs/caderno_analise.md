# Caderno de Análise e Evidências (Dia 2 - Semana 2)

**Projeto**: Retenção, Tempo Real de Formatura e Evasão nos Cursos de Graduação da UnB  
**Stakeholder**: Decanato de Ensino de Graduação (DEG/DAA)  
**Base Analítica**: Camada Gold (`data/gold/retencao_cursos_unb.csv`)  

---

## 1. Respostas Estruturadas às Cinco Guiding Questions (GQs)

### **GQ 1: Qual o percentual de concluintes que se forma no tempo mínimo, ideal e acima do ideal?**
- **Evidência Global**:
  - Na média de toda a UnB, **62.43%** dos formados integralizam o curso dentro do prazo ideal previsto pela matriz curricular.
  - **37.57%** dos egressos necessitam de semestres adicionais além do prazo ideal para conseguir outorga de grau.
  - Formatura no tempo mínimo regulamentar é rara, ocorrendo em média para apenas **4.8%** dos concluintes da instituição.
- **Disparidade Extrema entre Cursos**:
  - Cursos com maior taxa de formatura no tempo ideal: *Direito* (92.45%), *Gestão do Agronegócio* (89.18%), *Engenharia de Redes* (88.48%) e *Engenharia Civil* (88.16%).
  - Cursos com menor taxa de formatura no tempo ideal (alta retenção): *Física Computacional* (25.0%), *Línguas Estrangeiras Aplicadas* (32.4%), *Ciência da Computação* (42.5%) e *Música* (46.1%).

---

### **GQ 2: Qual é a diferença média (em semestres) entre a duração prevista e a duração real?**
- **Evidência Global**:
  - O tempo médio real de formatura na UnB é de **10.85 semestres** (~5.4 anos).
  - O desvio médio global em relação ao tempo ideal é de cerca de $\pm 0$ semestres quando ponderado por todos os cursos, mas varia drasticamente por área.
- **Áreas com Maior Atraso Real**:
  - *Ciências Exatas e Engenharias*: apresentam atraso médio de **+1.8 a +3.4 semestres** além do tempo ideal (ex: Ciência da Computação tem tempo médio real de 12.37 semestres para uma matriz ideal de 9 semestres, desvio de **+3.37 semestres**).

---

### **GQ 3: Qual a proporção de saídas por formatura versus desligamentos críticos?**
- **Evidência Global**:
  - Do total de 59.202 discentes analisados com registros de saída concluídos no SIGRA, **42.05%** saíram por *Formatura* e **53.8%** saíram por *Evasão/Desligamento* (abandono de curso, não cumprimento de condição ou jubilamento).
- **Cursos com Maior Evasão Crítica** (a habilitação genérica de ingresso comum "Engenharia" — onde a habilitação terminal ainda não foi escolhida — foi excluída da análise por não ser um curso válido; ver `docs/dicionario_dados_gold.md`):
  - *Física Computacional*: 76.19% de evasão.
  - *Computação*: 73.47% de evasão.
  - *Letras - Língua e Literatura Japonesa*: 71.80% de evasão.
  - *Teoria, Crítica e História da Arte*: 68.05% de evasão.

---

### **GQ 4: Cursos noturnos apresentam desvio de tempo significativamente maior que os diurnos?**
- **Metodologia de Turno**: Cursos que se autodesignam no catálogo bruto como `MATUTINO`, `VESPERTINO` ou `MATUTINO E VESPERTINO` são unificados em **Diurno** (juntos cobrem o período diurno completo), restando apenas a comparação Diurno (78 cursos) vs. Noturno (15 cursos).
- **Evidência Comparativa**:
  - *Desvio de tempo em relação à matriz*: Cursos noturnos possuem matrizes curriculares que já preveem semestres adicionais em seu desenho curricular (tempo ideal médio de 11.3 semestres vs. 10.5 no diurno). Por isso, o desvio médio em relação à própria matriz é levemente negativo no noturno (**-0.47 semestres**) contra **+0.51 semestres** no diurno — quem se forma no noturno tende a cumprir (ou até antecipar) o prazo já estendido da sua matriz.
  - *Impacto na Taxa de Evasão*: Cursos noturnos apresentam taxa média de evasão de **52.55%**, comparada a **45.81%** nos cursos diurnos (matutino + vespertino unificados).
  - **Veredito**: A dificuldade no noturno se manifesta prioritariamente na **permanência e evasão** (abandono por conciliação de trabalho/estudo), e não no atraso de semestres de quem consegue formar — cuja matriz já prevê prazo mais longo.
- **Recorte Complementar por Grau Acadêmico (Bacharelado vs. Licenciatura)**: cursos de Licenciatura (21) apresentam evasão média de **55.16%**, acima dos **44.48%** dos cursos de Bacharelado (72, incluindo habilitações profissionais como Engenharia, Medicina e Arquitetura).

---

### **GQ 5: Existe correlação entre a carga horária total da matriz e o atraso na formatura?**
- **Coeficiente de Correlação de Pearson**: $r = -0.044$ (correlação linear nula).
- **Interpretação**:
  - O atraso na formatura não decorre simplesmente da quantidade absoluta de horas do curso, pois cursos com altíssima carga horária (como Medicina e Engenharias) já possuem maior número de semestres regulamentares atribuídos.
  - O atraso está associado à **estrutura de pré-requisitos encadeados**, disciplinas com alta taxa de reprovação e oferta insuficiente de turmas.

---

## 2. Dinâmica Obrigatória: "A Correlação Suspeita"

> **Hipótese Ingênua**: *"Cursos noturnos têm menor atraso na formatura, portanto são mais fáceis que os diurnos."*

- **Por que a correlação é espúria / perigosa**:
  1. **Confundidor de Matriz**: O tempo ideal cadastrado para cursos noturnos é deliberadamente estendido (ex: 10 ou 12 semestres em vez de 8).
  2. **Viés de Sobrevivência (Survival Bias)**: Quem não aguenta o ritmo do curso noturno abandona (52.5% de evasão). Os poucos que chegam ao final são os discentes altamente resilientes que conseguem cumprir o prazo.
  3. **Conclusão para Decisão Institucional**: Avaliar a dificuldade de um curso exclusivamente pelo tempo de formatura sem considerar a taxa de evasão levaria o DEG a tomar decisões errôneas sobre a saúde acadêmica do curso.

---

## 3. Incerteza Residual e Limitações Declaradas
1. **Margem Temporal de $\pm 1$ Semestre**: Decorrente da ausência do semestre de ingresso no arquivo bruto do SIGRA (`ano_ingresso` de 4 dígitos).
2. **Mudanças de Habilitação**: Discentes que migraram entre habilitações (ex: Licenciatura para Bacharelado) herdam tempo acumulado da habilitação anterior.
3. **Casamento de 97.54%**: 2.46% dos registros não puderam ser correlacionados a estruturas ativas atuais por corresponderem a cursos extintos.
