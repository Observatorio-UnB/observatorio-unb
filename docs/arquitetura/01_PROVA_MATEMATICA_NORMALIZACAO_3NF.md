# Prova Matemática de Normalização em 3ª Forma Normal (Camada Silver)

> **Autor**: Equipe Observatório UnB  
> **Disciplina**: Banco de Dados 2 — Universidade de Brasília  
> **Fundamentação Teórica**: Álgebra Relacional e Teoria da Normalização de Edgar F. Codd (1970, 1972)

---

## 1. Definição do Universo de Atributos e a Relação Não-Normalizada

Seja o esquema universal desnormalizado $R_{\mathrm{bruta}}$ que espelha os dados consolidados da graduação da UnB (SIGRA + SIGAA + Estruturas Curriculares):

$$U = \{ A, P, N, R, C, D, K, T, G, M, I, E, X, H, V, Y, Z, O, F, S \}$$

Onde cada símbolo representa o domínio semântico do atributo:
* $A$: Pseudônimo do Discente (`aluno`)
* $P$: Data de Nascimento (`data_nasc`)
* $N$: Sexo Biológico (`sexo`)
* $R$: Raça / Cor declarada (`raca_cor`)
* $C$: Identificador do Curso (`id_curso`)
* $D$: Nome Canônico do Curso (`nome_curso_norm`)
* $K$: Campus de Oferta (`campus`)
* $T$: Turno de Funcionamento (`turno`)
* $G$: Grau Acadêmico conferido (`grau_academico`)
* $M$: Grande Área de Conhecimento (`area_conhecimento`)
* $I$: Departamento Responsável (`departamento`)
* $E$: Identificador da Estrutura Curricular (`id_estrutura`)
* $X$: Semestre Mínimo Regulamentar (`semestre_minimo`)
* $H$: Semestre Ideal de Integralização (`semestre_ideal`)
* $V$: Semestre Máximo antes do Jubilamento (`semestre_maximo`)
* $Y$: Carga Horária Mínima Obrigatória (`ch_total_minima`)
* $Z$: Total de Créditos Mínimos (`cr_total_minimo`)
* $O$: Ano de Ingresso (`ano_ingresso`)
* $F$: Forma / Tipo de Saída Agrupada (`tipo_saida_grupo`)
* $S$: Semestres de Permanência Real (`semestres_permanencia`)

> **Nota Metodológica sobre o Semestre de Ingresso ($W$)**: Nem o SIGRA nem o extrato histórico do SIGAA publicam o semestre letivo de ingresso do aluno (apenas o ano civil de ingresso $O$). No catálogo físico do SGBD, a coluna `semestre_ingresso` é permitida como nula (`NULL`) por desenho de engenharia e encontra-se desprovida de valor em toda a série histórica. Logo, conforme os postulados fundamentais da Teoria Relacional, um atributo que admite valores nulos não pode compor chaves candidatas nem participar da determinação funcional unívoca de tuplas.

---

## 2. Conjunto de Dependências Funcionais Reais ($F$)

A partir das regras de negócio acadêmicas da UnB e da análise dos dados institucionais, estabelece-se o conjunto elementar de Dependências Funcionais $F$:

$$\begin{aligned}
f_1 &: A \rightarrow P, N, R \\
f_2 &: C \rightarrow D, K, T, G, M, I \\
f_3 &: C \rightarrow E \\
f_4 &: E \rightarrow X, H, V, Y, Z \\
f_5 &: A, C, O \rightarrow F, S
\end{aligned}$$

### 2.1. Determinação Formal das Chaves Candidatas
Para a relação universal $R_{\mathrm{bruta}}$:
* Os atributos $\{A, C, O\}$ não aparecem no lado direito de nenhuma dependência funcional elementar em $F$.
* Portanto, $\{A, C, O\}$ deve obrigatoriamente ser um subconjunto de toda e qualquer chave candidata de $R_{\mathrm{bruta}}$.

Calculando o **Fechamento dos Atributos** $(\{A, C, O\})^+$ sob $F$ aplicando os Axiomas de Armstrong:
1. **Reflexividade**: 
   $$X^{(0)} = \{A, C, O\}$$
2. **Aplicação de $f_1 (A \rightarrow P, N, R)$**:
   Como $A \subseteq X^{(0)}$, adicionam-se $\{P, N, R\}$:
   $$X^{(1)} = \{A, C, O, P, N, R\}$$
3. **Aplicação de $f_2 (C \rightarrow D, K, T, G, M, I)$**:
   Como $C \subseteq X^{(1)}$, adicionam-se $\{D, K, T, G, M, I\}$:
   $$X^{(2)} = \{A, C, O, P, N, R, D, K, T, G, M, I\}$$
4. **Aplicação de $f_3 (C \rightarrow E)$**:
   Como $C \subseteq X^{(2)}$, adiciona-se $E$:
   $$X^{(3)} = \{A, C, O, P, N, R, D, K, T, G, M, I, E\}$$
5. **Aplicação de $f_4 (E \rightarrow X, H, V, Y, Z)$**:
   Como $E \subseteq X^{(3)}$, adicionam-se $\{X, H, V, Y, Z\}$:
   $$X^{(4)} = \{A, C, O, P, N, R, D, K, T, G, M, I, E, X, H, V, Y, Z\}$$
6. **Aplicação de $f_5 (A, C, O \rightarrow F, S)$**:
   Como $\{A, C, O\} \subseteq X^{(4)}$, adicionam-se $\{F, S\}$:
   $$X^{(5)} = U$$

Como $(\{A, C, O\})_{F}^+ = U$ e nenhum subconjunto próprio de $\{A, C, O\}$ determina $U$, conclui-se formalmente:
$$\mathrm{PK}(R_{\mathrm{bruta}}) = \underline{\{A, C, O\}}$$

---

## 3. Demonstração Formal das Violações

### 3.1. Violação da 2ª Forma Normal (2NF)
> **Definição Teórica (Codd, 1971)**: Uma relação $R$ está na 2NF se e somente se está na 1NF e nenhum atributo não-chave é funcionalmente dependente de um subconjunto próprio de qualquer chave candidata (inexistência de dependências parciais).

* A chave primária é composta: $\{A, C, O\}$.
* **Dependência Parcial 1**: $f_1: A \rightarrow P, N, R$.
  * $\{A\} \subset \{A, C, O\}$ (subconjunto próprio da chave).
  * Os dados pessoais $\{P, N, R\}$ dependem apenas de parte da chave primária.
* **Dependência Parcial 2**: $f_2: C \rightarrow D, K, T, G, M, I$.
  * $\{C\} \subset \{A, C, O\}$ (subconjunto próprio da chave).
  * Os dados institucionais do curso dependem exclusivamente de $C$.

$$\text{Conclusão: } R_{\mathrm{bruta}} \notin \text{2NF}$$

### 3.2. Violação da 3ª Forma Normal (3NF)
> **Definição Teórica (Codd, 1972)**: Uma relação $R$ está na 3NF se e somente se está na 2NF e para toda dependência funcional não-trivial $X \rightarrow Y$, pelo menos uma das seguintes condições é satisfeita:
> 1. $X$ é uma superchave de $R$; ou
> 2. $Y$ é um atributo primo de $R$ (isto é, $Y$ é membro de alguma chave candidata).

Mesmo que resolvêssemos as dependências parciais agrupando atributos por curso, observe a cadeia transitiva:
$$\{A, C, O\} \rightarrow C \rightarrow E \rightarrow \{X, H, V, Y, Z\}$$
* Na dependência funcional $E \rightarrow \{X, H, V, Y, Z\}$:
  * $E$ **não é superchave** de $R_{\mathrm{bruta}}$ (uma matriz curricular sozinha não identifica discentes nem vínculos).
  * Os atributos $\{X, H, V, Y, Z\}$ **não são atributos primos** (não pertencem à chave candidata $\{A, C, O\}$).

$$\text{Conclusão: } R_{\mathrm{bruta}} \notin \text{3NF}$$

---

## 4. Algoritmo de Decomposição sem Perdas e com Preservação de Dependências

Aplicando o algoritmo formal de síntese de Bernstein e decomposição de Codd, projetamos $U$ em esquemas normalizados em 3NF:

$$S = \{ R_{\mathrm{discentes}}, R_{\mathrm{cursos}}, R_{\mathrm{estruturas}}, R_{\mathrm{movimentacoes}}, R_{\mathrm{pibic}} \}$$

### 4.1. Definição Formal dos Esquemas Resultantes

```text
1. DISCENTES
   Esquema: silver.discentes(id_discente, pseudonimo, data_nascimento, sexo, raca_cor, criado_em)
   Chave Primária: id_discente
   Chave Candidata: pseudonimo
   Dependências Preservadas: pseudonimo -> data_nascimento, sexo, raca_cor

2. CURSOS
   Esquema: silver.cursos(id_curso, codigo_sigaa, nome_curso_norm, campus, turno, 
                          grau_academico, categoria_grau, area_conhecimento, departamento, 
                          is_tronco_abi, ativo)
   Chave Primária: id_curso
   Dependências Preservadas: id_curso -> nome_curso_norm, campus, turno, grau, area, depto

3. ESTRUTURAS_CURRICULARES
   Esquema: silver.estruturas_curriculares(id_estrutura, nome_curso_canonico, id_curso, 
                                           semestre_minimo, semestre_ideal, semestre_maximo, 
                                           ch_total_minima, cr_total_minimo)
   Chave Primária: id_estrutura
   Chaves Únicas: nome_curso_canonico; (id_curso, semestre_ideal)
   Chave Estrangeira: id_curso REFERENCES silver.cursos(id_curso) ON DELETE RESTRICT
   Dependências Preservadas: id_estrutura -> id_curso, semestres, ch_total, cr_total

4. MOVIMENTACOES_VINCULOS [PARTITION BY RANGE (ano_ingresso)]
   Esquema: silver.movimentacoes_vinculos(id_vinculo, id_discente, id_curso, id_estrutura, 
                                          ano_ingresso, semestre_ingresso, forma_saida, 
                                          tipo_saida_grupo, ano_saida, semestre_saida, 
                                          semestres_permanencia, semestres_permanencia_valida, 
                                          periodo_saida_estimado, status_aluno, fonte)
   Chave Primária Composta: (id_vinculo, ano_ingresso)
   Chaves Estrangeiras:
     - id_discente REFERENCES silver.discentes(id_discente) ON DELETE RESTRICT
     - id_curso REFERENCES silver.cursos(id_curso) ON DELETE RESTRICT
     - id_estrutura REFERENCES silver.estruturas_curriculares(id_estrutura) [ON DELETE NO ACTION]

5. PIBIC_PROJETOS
   Esquema: silver.pibic_projetos(id_projeto, id_discente, id_curso, id_estrutura, ano_edital, 
                                  tipo_bolsa, linha_pesquisa, is_cotista, cota_detalhe, 
                                  faixa_renda, perfil_social_macro, valor_bolsa_total, 
                                  titulo_pesquisa, status_projeto)
   Chave Primária: id_projeto
   Chaves Estrangeiras:
     - id_discente REFERENCES silver.discentes(id_discente) [ON DELETE NO ACTION]
     - id_curso REFERENCES silver.cursos(id_curso) [ON DELETE NO ACTION]
     - id_estrutura REFERENCES silver.estruturas_curriculares(id_estrutura) [ON DELETE NO ACTION]
```

---

## 5. Teoremas de Validação da Decomposição

### Teorema 1: Junção sem Perdas de Informação (*Lossless-Join*)
Para que a decomposição de $R$ em $\{R_1, R_2\}$ seja sem perdas com relação a $F$, é condição necessária e suficiente que:
$$(R_1 \cap R_2) \rightarrow R_1 \quad \text{ou} \quad (R_1 \cap R_2) \rightarrow R_2$$

* **Prova para Discentes e Movimentações**:
  $$R_{\mathrm{discentes}} \cap R_{\mathrm{movimentacoes}} = \{ \text{id\_discente} \}$$
  Como o atributo `id_discente` é a chave primária de $R_{\mathrm{discentes}}$, temos:
  $$\text{id\_discente} \rightarrow R_{\mathrm{discentes}}$$
  Logo, a junção natural $\pi_{R_{\mathrm{discentes}}}(R) \bowtie \pi_{R_{\mathrm{movimentacoes}}}(R)$ reconstitui a informação sem gerar tuplas espúrias.

* **Prova para Cursos e Movimentações**:
  $$R_{\mathrm{cursos}} \cap R_{\mathrm{movimentacoes}} = \{ \text{id\_curso} \}$$
  Como o atributo `id_curso` é a chave primária de $R_{\mathrm{cursos}}$, temos:
  $$\text{id\_curso} \rightarrow R_{\mathrm{cursos}}$$

* **Prova para Estruturas Curriculares e Cursos**:
  $$R_{\mathrm{estruturas}} \cap R_{\mathrm{cursos}} = \{ \text{id\_curso} \}$$
  Como `id_curso` é chave primária em $R_{\mathrm{cursos}}$, a junção é sem perdas.

A indução finita sobre todas as relações do esquema $S$ confirma:
$$\bowtie_{i=1}^{5} \pi_{R_i}(R_{\mathrm{bruta}}) \equiv R_{\mathrm{bruta}}$$

### Teorema 2: Preservação de Dependências Funcionais
A união das projeções de dependências funcionais em cada relação resultante cobre todas as dependências do conjunto original $F$:
$$(\bigcup_{i=1}^{5} \pi_{R_i}(F))^+ \equiv F^+$$
* Nenhuma dependência funcional elementar foi perdida na transição para o modelo normalizado.
* Todas as restrições de integridade são verificadas localmente em cada relação ou via restrições declarativas de chave estrangeira (`FOREIGN KEY`) com suporte de índice $O(\log N)$ no PostgreSQL.

