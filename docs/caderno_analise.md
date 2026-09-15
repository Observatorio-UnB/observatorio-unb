# Caderno de Análise e Evidências (Dia 2 - Semana 2)

**Projeto**: Retenção, Tempo Real de Formatura e Evasão nos Cursos de Graduação da UnB  
**Stakeholder**: Decanato de Ensino de Graduação (DEG/DAA)  
**Base Analítica**: Camada Gold (`data/gold/retencao_cursos_unb.csv`)  

---

## 1. Respostas Estruturadas às Cinco Guiding Questions (GQs)

### **GQ 1: Qual o percentual de concluintes que se forma no tempo mínimo, ideal e acima do ideal?**
- **Evidência Global**:
  - Na média de toda a UnB, **62.05%** dos formados integralizam o curso dentro do prazo ideal previsto pela matriz curricular.
  - **37.95%** dos egressos necessitam de semestres adicionais além do prazo ideal para conseguir outorga de grau.
- **Disparidade Extrema entre Cursos**:
  - Cursos com maior taxa de formatura no tempo ideal: *Direito* (92.45%) e *Gestão do Agronegócio* (89.18%).
  - Cursos com menor taxa de formatura no tempo ideal (alta retenção): *Engenharia Aeroespacial* (8.24%), *Línguas Estrangeiras Aplicadas - MSI* (9.47%) e *Ciência da Computação* (11.27%).

---

### **GQ 2: Qual é a diferença média (em semestres) entre a duração prevista e a duração real?**
- **Evidência Global**:
  - O tempo médio real de formatura na UnB é de **10.84 semestres** (~5.4 anos).
  - O desvio médio global em relação ao tempo ideal é de cerca de $\pm 0$ semestres (**-0.03**) quando ponderado por todos os cursos, mas varia drasticamente por área.
- **Áreas com Maior Atraso Real**:
  - *Ciências Exatas e Engenharias*: apresentam atraso médio de **+1.8 a +3.4 semestres** além do tempo ideal (ex: Ciência da Computação tem tempo médio real de 12.37 semestres para uma matriz ideal de 9 semestres, desvio de **+3.37 semestres**).

---

### **GQ 3: Qual a proporção de saídas por formatura versus desligamentos críticos?**
- **Evidência Global**:
  - Do total de 60.695 discentes analisados, **42.16%** saíram por *Formatura* e **45.94%** saíram por *Evasão/Desligamento* (abandono de curso, não cumprimento de condição ou jubilamento).
- **Cursos com Maior Evasão Crítica**:
  - *Física Computacional*: 76.19% de evasão.
  - *Engenharia* (habilitação genérica de ingresso comum, onde a habilitação terminal ainda não foi escolhida): 74.00% de evasão. Permanece na tabela e nas métricas globais por representar discentes reais da UnB, mas é descartada nas telas de Visão Executiva e Detalhe por Curso do dashboard por não ser um curso terminal válido para um raio-x individual (ver `docs/dicionario_dados_gold.md`).
  - *Computação*: 73.47% de evasão.
  - *Letras - Língua e Literatura Japonesa*: 71.80% de evasão.

---

### **GQ 4: Cursos noturnos apresentam desvio de tempo significativamente maior que os diurnos?**
- **Metodologia de Turno**: Cursos que se autodesignam no catálogo bruto como `MATUTINO`, `VESPERTINO` ou `MATUTINO E VESPERTINO` são unificados em **Diurno** (juntos cobrem o período diurno completo), restando apenas a comparação Diurno (72 cursos) vs. Noturno (16 cursos).
- **Evidência Comparativa**:
  - *Desvio de tempo em relação à matriz*: Cursos noturnos possuem matrizes curriculares que já preveem semestres adicionais em seu desenho curricular (tempo ideal médio de 11.28 semestres vs. 10.61 no diurno). Por isso, o desvio médio em relação à própria matriz é levemente negativo no noturno (**-0.49 semestres**) contra **+0.42 semestres** no diurno — quem se forma no noturno tende a cumprir (ou até antecipar) o prazo já estendido da sua matriz.
  - *Impacto na Taxa de Evasão*: Cursos noturnos apresentam taxa média de evasão de **50.99%**, comparada a **44.48%** nos cursos diurnos (matutino + vespertino unificados).
  - **Veredito**: A dificuldade no noturno se manifesta prioritariamente na **permanência e evasão** (abandono por conciliação de trabalho/estudo), e não no atraso de semestres de quem consegue formar — cuja matriz já prevê prazo mais longo.
- **Recorte Complementar por Grau Acadêmico (Bacharelado vs. Licenciatura)**: cursos de Licenciatura (12) apresentam evasão média de **56.39%**, acima dos **41.60%** dos cursos de Bacharelado (61, incluindo habilitações profissionais como Engenharia, Medicina e Arquitetura). Cursos com grau **Misto** (Bacharelado e Licenciatura sob o mesmo nome, sem forma confiável de separar os discentes — ex.: Química) ficam fora dessa comparação por não terem um grau único atribuível.

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
3. **Casamento de 100%**: todos os 60.695 discentes analisados foram correlacionados a estruturas curriculares ativas via harmonização canônica de nomes de curso (ver `regras_harmonizacao_canonicas.json`).
