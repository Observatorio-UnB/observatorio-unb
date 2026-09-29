# Relatório de Auditoria de Qualidade de Dados (Dia 4 - Semana 1)

**Projeto**: Retenção, Tempo Real de Formatura e Evasão nos Cursos da UnB
**Portal Auditado**: [dados.unb.br](https://dados.unb.br)
**Total de Inconsistências Auditadas**: 12 achados comprovados com evidência.

---

## 1. Tabela de Achados de Qualidade

| ID | Arquivo / Tabela | Linha | Campo | Problema Detectado | Impacto na Análise (GQ) | Decisão Metodológica |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **ACHADO-01** | `bronze.estrutura_curricular` | 2 | `nome_matriz / nome_curso` | Encoding corrompido (arquivo codificado em ISO-8859-1 / Latin-1 em vez de UTF-8 padronizado) | Distorce e inviabiliza o join textual com a tabela de discentes se não for decodificado explicitamente em latin-1. | Configurar parser do pipeline com encoding='latin-1' e aplicar normalização NFKD (remoção de acentos e conversão para maiúsculas). |
| **ACHADO-02** | `bronze.sigra_discentes vs bronze.cursos_graduacao` | 1 | `delimitador de colunas (CSV dialect)` | Inconsistência de delimitador entre datasets do mesmo portal (ponto-e-vírgula ';' vs vírgula ',') | Falha na leitura automática por bibliotecas padrão caso o delimitador seja assumido como padrão RFC 4180. | Declarar explicitamente o dialect/delimiter para cada arquivo no pipeline de ingestão e Silver. |
| **ACHADO-03** | `bronze.sigra_discentes` | 2 | `curso / departamento / forma_saida / nivel` | Espaçamento em branco (padding fixo de dezenas de caracteres) ao final das strings de texto | Impede o casamento exato de chaves em consultas SQL / joins com outras tabelas. | Aplicar .strip() e regex de normalização de espaços contínuos em todas as colunas de texto. |
| **ACHADO-04** | `bronze.sigra_discentes` | 2 | `ano_ingresso vs periodo_saida` | Granularidade temporal assimétrica: ano_ingresso possui apenas o ano (ex: 2010), enquanto periodo_saida traz ano e semestre (ex: 20141) | Gera uma margem de incerteza metodológica de +/- 1 semestre no cálculo do tempo real de permanência. | Documentar formalmente a incerteza residual e adotar o semestre 1 como baseline primário com cálculo de faixa de erro (cenário min/max). |
| **ACHADO-05** | `bronze.estrutura_curricular` | Múltiplas | `id_curriculo / ano_entrada_vigor / semestre_conclusao_ideal` | Multiplicidade de matrizes curriculares ativas/históricas para o mesmo curso com prazos ideais distintos | Um join ingênuo geraria produto cartesiano (duplicação de discentes) ou cálculo com matriz incorreta. | Filtrar a matriz curricular vigente de referência mais consolidada por curso ou parear pelo ano de ingresso. |
| **ACHADO-06** | `bronze.cursos_graduacao` | 2 | `nivel_ensino / convenio_academico` | Uso da string literal 'NULL' em vez de valor nulo/vazio padrão | Consultas que filtram 'IS NOT NULL' interpretam a string 'NULL' como valor válido com 4 caracteres. | Substituir strings literais 'NULL', 'None', '-' e vazias por NaN/None na camada Silver. |
| **ACHADO-07** | `bronze.sigra_discentes vs bronze.estrutura_curricular` | Diversas | `curso (SIGRA) vs nome_curso (Estrutura) vs nome (Cursos)` | Variações sintáticas e de especialização em nomes de cursos entre sistemas acadêmicos | Join direto perde cerca de 15% dos discentes caso não haja um dicionário de sinônimos/normalização canônica. | Implementar tabela de sinônimos de cursos (alias mapping) e normalização textual rigorosa na camada Silver, alcançando >95% de casamento. |
| **ACHADO-08** | `bronze.sigra_discentes` | Todas | `data_nascimento + sexo + raca_cor + cota_ingresso + curso` | Presença de múltiplos quase-identificadores em alta granularidade permitindo reidentificação individual de discentes | Violação potencial de privacidade caso dados individuais sejam expostos no dashboard ou em apresentações públicas. | Garantir que a camada Gold e o produto final exponham apenas métricas agregadas por curso/departamento (k-anonimato >= 5 por agregação). |
| **ACHADO-09** | `bronze.sigaa_discentes` | 2 | `status_aluno / data_registro_diploma / ano_ingresso` | O SIGAA não publica período nem motivo de saída, e grava o ano de ingresso com separador de milhar | Evasão não distingue abandono de mudança de curso, e o tempo de conclusão dos formados após 2020 precisa ser estimado pela data do diploma. | Evasão definida como saída sem diploma nas duas bases; semestre de conclusão estimado pela data do diploma (regra validada em 94,6% no SIGRA) e marcado em periodo_saida_estimado. |
| **ACHADO-10** | `bronze.sigaa_discentes` | 56224, 93684 | `data_registro_diploma` | Datas de registro de diploma posteriores à publicação do arquivo (07/2024) | Sem tratamento, o semestre de conclusão estimado cai no futuro e distorce o tempo de formatura. | Datas depois da publicação do recurso no CKAN são descartadas antes da estimativa do semestre; o vínculo continua contado como formado. |
| **ACHADO-11** | `bronze.sigaa_discentes` | Todas | `status_aluno` | O extrato do SIGAA mantém como ATIVO vínculos que já não estão na lista de ativos seguinte, sem virar CANCELADO | A evasão de coortes recentes fica subestimada no extrato: o cancelamento é registrado com atraso. | A Gold de retenção só usa coortes com 8 anos de acompanhamento. O retrato de ativos usa a lista de ativos do semestre mais recente, não o status do extrato. |
| **ACHADO-12** | `bronze.estrutura_curricular` | N/A | `nome_curso` | A estrutura curricular publicada é de 10/2020 e não cobre todos os cursos do catálogo vigente | Sem prazos ideal e máximo, esses cursos ficam fora das métricas de atraso. | Cursos sem estrutura ficam de fora das tabelas por curso. |

---

## 2. Detalhamento e Evidências dos Achados

### ACHADO-01: Encoding corrompido (arquivo codificado em ISO-8859-1 / Latin-1 em vez de UTF-8 padronizado)
- **Origem**: `bronze.estrutura_curricular`
- **Linha**: `2`
- **Evidência no Dado Bruto**: `Byte 0xca inválido em UTF-8: b'141;2291/-3;CI\xcaNCIAS NATURAIS                                                   '`
- **Impacto Direto**: Distorce e inviabiliza o join textual com a tabela de discentes se não for decodificado explicitamente em latin-1.
- **Tratamento Implementado no Pipeline**: Configurar parser do pipeline com encoding='latin-1' e aplicar normalização NFKD (remoção de acentos e conversão para maiúsculas).

### ACHADO-02: Inconsistência de delimitador entre datasets do mesmo portal (ponto-e-vírgula ';' vs vírgula ',')
- **Origem**: `bronze.sigra_discentes vs bronze.cursos_graduacao`
- **Linha**: `1`
- **Evidência no Dado Bruto**: `sigra.csv utiliza separador ';' enquanto curso_graduacao.csv utiliza separador ','`
- **Impacto Direto**: Falha na leitura automática por bibliotecas padrão caso o delimitador seja assumido como padrão RFC 4180.
- **Tratamento Implementado no Pipeline**: Declarar explicitamente o dialect/delimiter para cada arquivo no pipeline de ingestão e Silver.

### ACHADO-03: Espaçamento em branco (padding fixo de dezenas de caracteres) ao final das strings de texto
- **Origem**: `bronze.sigra_discentes`
- **Linha**: `2`
- **Evidência no Dado Bruto**: `Campo 'curso' contém 'DIREITO                            ' (tamanho 35 caracteres com espaços ao invés de 7)`
- **Impacto Direto**: Impede o casamento exato de chaves em consultas SQL / joins com outras tabelas.
- **Tratamento Implementado no Pipeline**: Aplicar .strip() e regex de normalização de espaços contínuos em todas as colunas de texto.

### ACHADO-04: Granularidade temporal assimétrica: ano_ingresso possui apenas o ano (ex: 2010), enquanto periodo_saida traz ano e semestre (ex: 20141)
- **Origem**: `bronze.sigra_discentes`
- **Linha**: `2`
- **Evidência no Dado Bruto**: `ano_ingresso='2010' e periodo_saida='20141'`
- **Impacto Direto**: Gera uma margem de incerteza metodológica de +/- 1 semestre no cálculo do tempo real de permanência.
- **Tratamento Implementado no Pipeline**: Documentar formalmente a incerteza residual e adotar o semestre 1 como baseline primário com cálculo de faixa de erro (cenário min/max).

### ACHADO-05: Multiplicidade de matrizes curriculares ativas/históricas para o mesmo curso com prazos ideais distintos
- **Origem**: `bronze.estrutura_curricular`
- **Linha**: `Múltiplas`
- **Evidência no Dado Bruto**: `O curso 'CIÊNCIAS NATURAIS' possui 7 matrizes curriculares cadastradas com anos de entrada em vigor diferentes.`
- **Impacto Direto**: Um join ingênuo geraria produto cartesiano (duplicação de discentes) ou cálculo com matriz incorreta.
- **Tratamento Implementado no Pipeline**: Filtrar a matriz curricular vigente de referência mais consolidada por curso ou parear pelo ano de ingresso.

### ACHADO-06: Uso da string literal 'NULL' em vez de valor nulo/vazio padrão
- **Origem**: `bronze.cursos_graduacao`
- **Linha**: `2`
- **Evidência no Dado Bruto**: `Linha 2: nivel_ensino='NULL', convenio_academico='NULL'`
- **Impacto Direto**: Consultas que filtram 'IS NOT NULL' interpretam a string 'NULL' como valor válido com 4 caracteres.
- **Tratamento Implementado no Pipeline**: Substituir strings literais 'NULL', 'None', '-' e vazias por NaN/None na camada Silver.

### ACHADO-07: Variações sintáticas e de especialização em nomes de cursos entre sistemas acadêmicos
- **Origem**: `bronze.sigra_discentes vs bronze.estrutura_curricular`
- **Linha**: `Diversas`
- **Evidência no Dado Bruto**: `SIGRA registra 'CONTROLE E AUTOMACAO', Estrutura registra 'ENGENHARIA MECATRONICA - CONTROLE E AUTOMACAO'; SIGRA 'LETRAS - LINGUA PORTUGUESA...', Estrutura 'LETRAS'`
- **Impacto Direto**: Join direto perde cerca de 15% dos discentes caso não haja um dicionário de sinônimos/normalização canônica.
- **Tratamento Implementado no Pipeline**: Implementar tabela de sinônimos de cursos (alias mapping) e normalização textual rigorosa na camada Silver, alcançando >95% de casamento.

### ACHADO-08: Presença de múltiplos quase-identificadores em alta granularidade permitindo reidentificação individual de discentes
- **Origem**: `bronze.sigra_discentes`
- **Linha**: `Todas`
- **Evidência no Dado Bruto**: `A combinação de data de nascimento exata (DD/MM/AAAA) com sexo, raça e curso produz registros unívocos (k-anonimato = 1 em cursos pequenos).`
- **Impacto Direto**: Violação potencial de privacidade caso dados individuais sejam expostos no dashboard ou em apresentações públicas.
- **Tratamento Implementado no Pipeline**: Garantir que a camada Gold e o produto final exponham apenas métricas agregadas por curso/departamento (k-anonimato >= 5 por agregação).

### ACHADO-09: O SIGAA não publica período nem motivo de saída, e grava o ano de ingresso com separador de milhar
- **Origem**: `bronze.sigaa_discentes`
- **Linha**: `2`
- **Evidência no Dado Bruto**: `ano_ingresso='2,010'; status_aluno='CANCELADO' sem motivo nem data; formados só têm data_registro_diploma.`
- **Impacto Direto**: Evasão não distingue abandono de mudança de curso, e o tempo de conclusão dos formados após 2020 precisa ser estimado pela data do diploma.
- **Tratamento Implementado no Pipeline**: Evasão definida como saída sem diploma nas duas bases; semestre de conclusão estimado pela data do diploma (regra validada em 94,6% no SIGRA) e marcado em periodo_saida_estimado.

### ACHADO-10: Datas de registro de diploma posteriores à publicação do arquivo (07/2024)
- **Origem**: `bronze.sigaa_discentes`
- **Linha**: `56224, 93684`
- **Evidência no Dado Bruto**: `linha 56224: '11/01/2202'; linha 93684: '08/01/2027' (provável erro de digitação do ano).`
- **Impacto Direto**: Sem tratamento, o semestre de conclusão estimado cai no futuro e distorce o tempo de formatura.
- **Tratamento Implementado no Pipeline**: Datas depois da publicação do recurso no CKAN são descartadas antes da estimativa do semestre; o vínculo continua contado como formado.

### ACHADO-11: O extrato do SIGAA mantém como ATIVO vínculos que já não estão na lista de ativos seguinte, sem virar CANCELADO
- **Origem**: `bronze.sigaa_discentes`
- **Linha**: `Todas`
- **Evidência no Dado Bruto**: `coorte de 2022: 8.530 ativos no extrato de 07/2024 contra 5.772 na lista de ativos de 06/2025. com 1.487 cancelados no extrato; coorte de 2023: 8.935 ativos no extrato de 07/2024 contra 7.785 na lista de ativos de 06/2025. com 525 cancelados no extrato. A queda em pouco tempo é grande demais para ser só formatura.`
- **Impacto Direto**: A evasão de coortes recentes fica subestimada no extrato: o cancelamento é registrado com atraso.
- **Tratamento Implementado no Pipeline**: A Gold de retenção só usa coortes com 8 anos de acompanhamento. O retrato de ativos usa a lista de ativos do semestre mais recente, não o status do extrato.

### ACHADO-12: A estrutura curricular publicada é de 10/2020 e não cobre todos os cursos do catálogo vigente
- **Origem**: `bronze.estrutura_curricular`
- **Linha**: `N/A`
- **Evidência no Dado Bruto**: `Cursos do catálogo vigente sem estrutura curricular: 'MÚSICA - TROMPA'.`
- **Impacto Direto**: Sem prazos ideal e máximo, esses cursos ficam fora das métricas de atraso.
- **Tratamento Implementado no Pipeline**: Cursos sem estrutura ficam de fora das tabelas por curso.


---

## 3. Minuta de Issue Oficial para o CPD / Mantenedor do Portal

> **Entregável Cívico**: Rascunho estruturado pronto para submissão no canal de suporte de Dados Abertos da UnB.

```markdown
[BUG/DADOS] Inconsistência de encoding em estrutura-curricular.csv e assimetria de granularidade temporal em discentes

**1. Descrição do Problema**
Durante a ingestão automatizada via API CKAN (dados.unb.br), foram identificados problemas que afetam a interoperabilidade dos dados abertos:
a) O recurso `estrutura-curricular.csv` está codificado em ISO-8859-1 (Latin-1) contendo bytes quebrados ao ser consumido como UTF-8 padronizado, além de conter múltiplos registros para o mesmo curso sem chave temporal explícita.
b) O recurso `sigra.csv` apresenta padding de espaços em branco ao final dos campos de texto (ex: mais de 30 espaços ao final do nome do curso) e assimetria temporal (ano_ingresso em AAAA vs periodo_saida em AAAA/S).
c) O recurso `cursos_graduacao.csv` utiliza a string literal 'NULL' em colunas com valores ausentes.
d) O recurso `sigaa.csv` não traz período nem motivo de saída (só `status_aluno` e a data de registro do diploma) e grava `ano_ingresso` com separador de milhar ('2,010').
e) O recurso `sigaa.csv` mantém como ATIVO vínculos que já deixaram o curso (ver ACHADO-11) e tem datas de registro de diploma no futuro (ver ACHADO-10).
f) O recurso `estrutura-curricular.csv` não cobre todos os cursos do catálogo vigente (ver ACHADO-12).

**2. Evidência Técnica**
- `estrutura-curricular.csv`: Linha 2 contém byte 0xCA em 'CIÊNCIAS NATURAIS'.
- `sigra.csv`: Linha 2 contém 'DIREITO                            ' com 28 espaços de preenchimento.
- `cursos_graduacao.csv`: Linha 2 contém campo nivel_ensino='NULL'.

**3. Impacto**
Dificulta o cruzamento automatizado de bases por estudantes e pesquisadores, exigindo rotinas complexas de limpeza para evitar produtos cartesianos e falhas de decodificação.

**4. Sugestão de Correção**
1. Reexportar `estrutura-curricular.csv` em UTF-8 nativo (sem BOM) e com delimitador padronizado RFC 4180 (vírgula).
2. Aplicar rotina de TRIM nos campos textuais do SIGRA antes da publicação no CKAN.
3. Padronizar campos nulos como strings vazias no CSV.
4. Incluir em `sigaa.csv` o período letivo de saída e o motivo do cancelamento, como o `sigra.csv` já fazia, e gravar `ano_ingresso` como inteiro.
5. Publicar a data de referência do extrato em `sigaa.csv` e a data do último status de cada vínculo.
6. Publicar a estrutura curricular vigente, com os cursos criados depois da última versão.
```
