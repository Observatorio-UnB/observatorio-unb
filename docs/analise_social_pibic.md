# 🔬 Caderno de Análise Social do PIBIC da UnB
## Democratização da Ciência, Fomento Público e a Dinâmica da "Correlação Suspeita"

> **Disciplina**: Banco de Dados 2 (UnB)  
> **Ciclo CBL**: Challenge 2 — Dados Abertos da UnB (Trilha T4: Pesquisa e Formação / Trilha T2: Assistência)  
> **Base de Dados**: `bolsistas-de-iniciacao-cientifica.csv` (Portal dados.unb.br)  
> **Cobertura**: 2018 a 2023 (12.793 planos de pesquisa aprovados)  
> **Camadas**: Processado via Arquitetura Medalhão (`bronze.*` $\rightarrow$ `silver.*` $\rightarrow$ `gold.*` no PostgreSQL)

---

## 1. O Fomento Público: Quantidade e Custo Total

Entre 2018 e 2023, a Universidade de Brasília registrou **12.793 planos de trabalho de Iniciação Científica aprovados**.

* **Bolsas Remuneradas**: **8.741 bolsas** concedidas via CNPq, FAPDF e Decanato de Pós-Graduação/Pesquisa (DPG/UnB).
* **Pesquisa Voluntária (PIVIC)**: **3.274 discentes** desenvolvendo pesquisa formal sem remuneração financeira direta.
* **Investimento Público Total Estimado**: **R$ 43.069.200,00**
  * *Metodologia de cálculo*: 12 parcelas de R$ 400,00/mês (R$ 4.800/ano) para bolsas vigentes entre 2018 e 2022, e reajuste federal para R$ 700,00/mês (R$ 8.400/ano) a partir de 2023.

### Evolução Histórica do Fomento Anual
| Ano | Total de Projetos | Bolsas Remuneradas | Voluntários (PIVIC) | Cotistas | Volume Investido (R$) |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **2018** | 3.025 | 2.169 | 856 | 1.105 | R$ 10.411.200,00 |
| **2019** | 2.516 | 1.816 | 700 | 1.073 | R$ 8.716.800,00 |
| **2020** | 2.623 | 1.839 | 782 | 1.140 | R$ 8.827.200,00 |
| **2021** | 2.374 | 1.746 | 627 | 965 | R$ 8.380.800,00 |
| **2022** | 1.896 | 862 | 259 | 539 | R$ 4.137.600,00 |
| **2023** | 359 | 309 | 50 | 154 | R$ 2.595.600,00 |

---

## 2. A Dimensão Social: Hipóteses, Evidências e Vereditos

### 🏛️ Dimensão 1: A Inserção de Ações Afirmativas na Ciência (Democratização)
* **Hipótese**: O acesso à Iniciação Científica na UnB reflete uma democratização homogênea entre todas as áreas do saber.
* **Evidência Empírica**:
  * No cômputo global, **38,9% dos bolsistas (4.976 discentes)** ingressaram por cotas sociais ou raciais (Escola Pública Baixa Renda, PPI - Pretos, Pardos e Indígenas, Negros, Indígenas e PCD).
  * **Disparidade por Grande Área** (classificação oficial CNPq/MEC do curso de origem, não a linha de pesquisa autodeclarada do projeto — ver nota metodológica ao final desta seção):
    * *Ciências Humanas*: **45,89%** de cotistas;
    * *Ciências da Saúde*: **44,15%** de cotistas;
    * *Ciências Sociais Aplicadas*: **41,84%** de cotistas;
    * *Ciências Agrárias*: **40,34%** de cotistas;
    * *Linguística, Letras e Artes*: **35,71%** de cotistas;
    * *Ciências Biológicas*: **35,06%** de cotistas;
    * *Engenharias*: **31,12%** de cotistas;
    * *Ciências Exatas e da Terra*: apenas **29,07%** de cotistas.
* **Veredito**: **Refutada Parcialmente**. Existe expressiva adesão de cotistas em Humanas, Saúde e Sociais Aplicadas, mas as áreas de Ciência, Tecnologia, Engenharia e Matemática (STEM — Exatas e Engenharias) ainda apresentam uma barreira de entrada para estudantes de ações afirmativas.

> **Nota metodológica**: a base bruta de bolsistas classifica cada projeto em apenas 3 "linhas de pesquisa" autodeclaradas (Artes e Humanidade, Saúde e Vida, Exatas e Tecnológicas), que não correspondem ao curso do discente — por exemplo, projetos de Farmácia (Ciências da Saúde) apareciam sob "Artes e Humanidade". A tabela Gold do PIBIC (`pibic_social_unb.csv`) usa em vez disso a Grande Área oficial (CNPq/MEC) do curso de graduação do discente, já presente no catálogo de cursos da UnB.

---

### 💼 Dimensão 2: A Barreira Invisível da Pesquisa Voluntária (PIVIC)
* **Hipótese**: A iniciação científica voluntária (PIVIC) é uma opção pedagógica neutra em relação à renda do discente.
* **Evidência Empírica**:
  * **25,59% (mais de 3.200 alunos)** realizam pesquisa na UnB sem qualquer remuneração.
  * Cursos como **Direito (44,9% de voluntários)** e **Medicina (30,3% de voluntários)** apresentam altíssima proporção de pesquisadores não remunerados.
  * Estudantes de baixa renda ($\le 1,5$ salário mínimo) dependem da bolsa para garantir transporte e alimentação no campus, tendo menor liberdade para assumir 20h semanais de dedicação voluntária.
* **Veredito**: **Confirmada**. A escassez de bolsas e a expansão do PIVIC funcionam como um filtro socioeconômico excludente: quem tem suporte familiar pode pesquisar "de graça" para enriquecer o currículo; quem precisa se sustentar é forçado a abandonar a pesquisa acadêmica.

---

### 📍 Dimensão 3: Descentralização Territorial entre Campi
* **Hipótese**: A interiorização da UnB (Campi Ceilândia, Gama e Planaltina) é acompanhada de distribuição equilibrada do fomento de pesquisa.
* **Evidência Empírica**:
  * **Campus Darcy Ribeiro (Plano Piloto)**: concentra **83,24% dos projetos** (10.649) e R$ 35,85 milhões do fomento.
  * **Faculdade de Ceilândia (FCE)**: **10,79%** (1.380 projetos) — destaque para Fisioterapia, Enfermagem e Farmácia.
  * **Faculdade do Gama (FGA)**: **4,21%** (539 projetos) — engenharias automotiva, software, aeroespacial e energia.
  * **Faculdade de Planaltina (FUP)**: **1,76%** (225 projetos) — ciências naturais e agrárias.
* **Veredito**: **Refutada**. A concentração da atividade de pesquisa de graduação ainda permanece massivamente polarizada no Campus Darcy Ribeiro.

---

## 3. Dinâmica Obrigatória: "A Correlação Suspeita"

> **Exigência do CBL (Semana 2 · Dia 2)**: *Cada grupo apresenta uma correlação encontrada nos dados e é obrigado a argumentar por que ela pode ser espúria. Confundidores clássicos: tamanho da unidade, ano, turno, mudança de sistema de registro e cobertura entre campi.*

### O Achado Empírico
Ao cruzar a base de Iniciação Científica com o Observatório de Retenção e Formatura (73 cursos com casamento direto), calculamos a taxa de **Projetos de IC por 100 alunos registrados** contra a **Taxa de Evasão / Desligamento (%)**.

$$\text{Correlação de Pearson: } r = -0,514 \quad (\text{Forte correlação negativa})$$

À primeira vista, a interpretação simplista sugeriria: *"Aumentar bolsas de PIBIC em qualquer curso reduzirá a evasão pela metade."*

### Por que essa correlação pode ser ESPÚRIA? (Confundidores Reais)
1. **Confundidor 1: Prestígio do Curso e Nível Socioeconômico Pré-Universitário**:
   * Cursos tradicionais de altíssima concorrência (ex: Medicina, Direito) concentram mais grupos de pesquisa consolidados (CNPq) e, portanto, captam mais cotas de PIBIC.
   * Concomitantemente, esses cursos já atraem estudantes com maior capital econômico e familiar, que historicamente possuem as menores taxas de evasão da UnB independentemente da concessão da bolsa.
2. **Confundidor 2: O Fator "Turno Noturno vs. Diurno"**:
   * Cursos noturnos são frequentados massivamente por estudantes trabalhadores que não têm disponibilidade diurna para frequentar laboratórios de pesquisa.
   * A oferta de editais de PIBIC para cursos noturnos é historicamente residual.
   * A evasão no noturno decorre do cansaço da dupla jornada (trabalho + faculdade), e não unicamente da ausência de iniciação científica.
3. **Confundidor 3: Mudança de Cobertura Cadastral e Campi**:
   * Campi mais novos (FGA, FCE) possuem matrizes que ainda estão maturando seu corpo de pesquisadores credenciados perante os comitês de área da UnB.

---

## 4. Conformidade Ética e Governança de Dados (LGPD)

Conforme apontado no Catálogo de Armadilhas do Guia da Disciplina (página 7 e 16):
> *"bolsistas-de-iniciacao-cientifica traz nome completo e matrícula juntos em claro no portal."*

### Salvaguardas Implementadas no Pipeline:
1. **Camada Bronze**: O arquivo bruto é armazenado de forma imutável e restrito ao ambiente local de processamento.
2. **Camada Silver**: O nome completo (`discente`) é descartado e a `matricula` é mascarada (`***.***.***`), mantendo apenas os atributos contextuais necessários à pesquisa.
3. **Camada Gold**: Não há registros individualizados. Todos os dados são agregados por curso, grande área e campus, aplicando supressão ética para grupos com $k < 5$ discentes.
