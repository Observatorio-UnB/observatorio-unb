# Dicionário de Dados da Tabela Gold: `gold.retencao_cursos_unb`

Este documento descreve a semântica, os tipos de dados e os métodos de cálculo de todas as colunas da tabela analítica da camada Gold (`gold.retencao_cursos_unb`), gerada para suportar a tomada de decisão do Decanato de Ensino de Graduação (DEG).

---

## 1. Metadados do Artefato
- **Tabela**: `gold.retencao_cursos_unb` (PostgreSQL). O dicionário de todas as tabelas do banco, gerado do esquema, está em [dicionario_dados_banco.md](dicionario_dados_banco.md).
- **Granularidade**: 1 linha por curso canônico de graduação da UnB. Cursos com oferta dupla de Bacharelado e Licenciatura sob o mesmo nome no catálogo (ex. Química, Física, Matemática — ver seção 3) permanecem em uma única linha, com `categoria_grau = "MISTO"`.
- **Total de Cursos Consolidados**: 88 cursos. O curso-tronco de ingresso comum `ENGENHARIA` (habilitação escolhida posteriormente pelo discente, ex. modelo FGA/FT) permanece na tabela e nas métricas globais — compõe o panorama geral da UnB — mas é descartado apenas nas telas de Visão Executiva e Detalhe por Curso do dashboard (`EXCLUDED_GENERIC_COURSES` em `src/dashboard/app.py`), por não ser um curso terminal válido para um raio-x individual.
- **Fontes Primárias**: `sigra_discentes.csv` (24.5 MB) + `estrutura_curricular.csv` (76 KB) + `cursos_graduacao.csv` (45 KB).
- **Taxa de Casamento dos Joins**: 100.00%.

---

## 2. Dicionário de Campos

| Nome da Coluna | Tipo de Dado | Exemplo | Descrição e Regra de Cálculo |
| :--- | :--- | :--- | :--- |
| `curso` | String | `CIENCIA DA COMPUTACAO` | Nome canônico e normalizado do curso de graduação da UnB (sem acentos, uppercase). |
| `departamento` | String | `DEPTO CIENCIA DA COMPUTACAO` | Departamento acadêmico de vinculação principal da matriz. |
| `campus` | String | `DARCY RIBEIRO` | Campus de oferta (Darcy Ribeiro, FGA - Gama, FCE - Ceilândia, FUP - Planaltina). |
| `turno` | String | `DIURNO` | Turno de oferta, normalizado para `DIURNO`, `NOTURNO` ou `INTEGRAL`. Cursos autodesignados como `MATUTINO`, `VESPERTINO` ou `MATUTINO E VESPERTINO` no catálogo bruto são unificados em `DIURNO`, já que juntos cobrem o período diurno completo. |
| `area_conhecimento` | String | `CIENCIAS EXATAS E DA TERRA` | Grande área de conhecimento do CNPq/MEC. |
| `grau_academico` | String | `BACHAREL` | Titulação literal conferida ao egresso, conforme cadastrada (Bacharel, Licenciado, Engenheiro Civil, Médico etc.). |
| `categoria_grau` | String | `BACHARELADO` | Agrupamento de `grau_academico` em três classes de análise: `LICENCIATURA` (titulações de Licenciado), `BACHARELADO` (Bacharel e todas as titulações profissionais — Engenheiro\*, Médico, Enfermeiro, Nutricionista, Geólogo, Arquiteto e Urbanista, Cirurgião Dentista, Médico Veterinário) e `MISTO` para os 15 cursos com oferta dupla sob o mesmo nome (ver seção 3). |
| `semestre_minimo_previsto` | Float | `8.0` | Quantidade mínima regulamentar de semestres para conclusão cadastrada na estrutura curricular. |
| `semestre_ideal_previsto` | Float | `9.0` | Duração padrão/ideal em semestres para integralização da matriz curricular. |
| `semestre_maximo_previsto` | Float | `16.0` | Prazo máximo de permanência antes da abertura de processo de jubilamento. |
| `carga_horaria_minima` | Float | `3600.0` | Carga horária total mínima (horas-aula) exigida para conclusão. |
| `total_discentes_registrados` | Inteiro | `1450` | Volume total de discentes com registro de movimentação acadêmica no curso. |
| `total_formados` | Inteiro | `580` | Quantidade total de discentes cuja forma de saída foi `Formatura`. |
| `total_evadidos_desligados` | Inteiro | `850` | Total de discentes desligados (abandono, jubilamento, reprovação 3x na mesma disciplina). |
| `taxa_formatura_pct` | Float (%) | `40.00` | Percentual de discentes que concluíram o curso: $\frac{\text{total\_formados}}{\text{total\_discentes}} \times 100$. |
| `taxa_evasao_pct` | Float (%) | `58.62` | Percentual de discentes evadidos/desligados: $\frac{\text{total\_evadidos}}{\text{total\_discentes}} \times 100$. |
| `formados_tempo_minimo_pct` | Float (%) | `5.17` | Proporção de egressos que integralizaram o curso em prazo $\le \text{semestre\_minimo\_previsto}$. |
| `formados_tempo_ideal_pct` | Float (%) | `42.50` | Proporção de egressos que integralizaram o curso em prazo $\le \text{semestre\_ideal\_previsto}$. |
| `formados_acima_ideal_pct` | Float (%) | `57.50` | Proporção de egressos que ultrapassaram o tempo ideal ($100 - \text{formados\_tempo\_ideal\_pct}$). |
| `formados_limite_maximo_pct` | Float (%) | `8.20` | Proporção de egressos que se formaram no limite do jubilamento ($\ge \text{semestre\_maximo\_previsto}$). |
| `tempo_medio_real_semestres` | Float | `12.37` | Duração média observada em semestres entre o ingresso e a outorga de grau. |
| `tempo_mediano_real_semestres` | Float | `12.00` | Mediana do tempo de integralização em semestres (robusta a outliers). |
| `desvio_medio_semestres` | Float | `3.37` | Diferença média em semestres: $\text{tempo\_medio\_real} - \text{semestre\_ideal\_previsto}$. |
| `indice_retencao_critica` | Float (0-100) | `59.7` | Índice composto normalizado: $0.5 \times \text{norm}(desvio) + 0.5 \times \text{norm}(evasao)$. |
| `classificacao_retencao` | String | `RETENÇÃO CRÍTICA` | Nível de urgência institucional: `RETENÇÃO CRÍTICA` (Top 25%), `ALTA`, `MÉDIA`, `BAIXA`. |

---

## 3. Cursos com Oferta Dupla (Bacharelado e Licenciatura) — `categoria_grau = "MISTO"`

15 cursos da UnB oferecem, sob o mesmo nome no catálogo (`silver.cursos_graduacao`), tanto uma habilitação de Bacharelado quanto uma de Licenciatura: `QUIMICA`, `FISICA`, `MATEMATICA`, `ARTES VISUAIS`, `CIENCIAS BIOLOGICAS`, `CIENCIAS SOCIAIS`, `EDUCACAO FISICA`, `FILOSOFIA`, `GEOGRAFIA`, `HISTORIA`, `MUSICA`, `PSICOLOGIA` e 3 habilitações de Letras (Francesa, Inglesa, Portuguesa). O catálogo de cursos não traz uma coluna que ligue o código de `opcao` do SIGRA (identificador da opção de ingresso do discente) ao grau conferido, e essa tabela de correspondência não foi localizada em nenhum dataset aberto da UnB (`dados.unb.br`) nem em documentos institucionais públicos (editais de mudança de curso, guias de vestibular) acessíveis no momento da construção deste pipeline.

Uma primeira tentativa separou esses cursos usando o código `opcao` do SIGRA como proxy (o menor código observado por curso = Bacharelado, os demais = Licenciatura). Isso funciona de forma limpa apenas quando o curso tem exatamente 2 códigos de `opcao` distintos — o caso de Química (1449/1503). Nos outros 14 cursos há 3 a 6 códigos distintos (entradas por vestibular, SiSU, transferência, mudança de curso etc. registradas em anos diferentes), e não há como saber quais códigos pertencem a qual grau: aplicar a mesma regra em Física, por exemplo, isolava um subgrupo minoritário de 55 discentes (código de opção mais baixo) como "Bacharelado" com 0% de formatura — um resultado claramente incorreto, não apenas incompleto.

**Decisão final**: em vez de dividir apenas os cursos onde a heurística funciona (criando uma experiência inconsistente — alguns cursos duplos separados, outros não) ou arriscar atribuições erradas nos demais, todos os 15 cursos permanecem como uma única linha na Gold, com `grau_academico = "MISTO (BACHARELADO + LICENCIATURA)"` e `categoria_grau = "MISTO"`. As métricas de retenção/evasão dessa linha somam as duas habilitações. Caso uma tabela oficial `opcao → curso/grau` do SIGRA seja obtida no futuro, essa lógica em `src/pipeline/build_gold.py` (função `build_gold_layer`, comentário "2.1") pode ser refeita para separar os discentes com uma correspondência real.
