# Dicionário de Dados do Banco (PostgreSQL)

> Gerado por `src/db/gerar_dicionario.py` a partir do catálogo do banco. **Não edite à mão**: as descrições são os `COMMENT ON` de `db/migrations/`.

O banco guarda o medalhão inteiro, um esquema por camada. Bronze e silver têm registro individual de discente; o papel `observatorio_leitura` (privilégio mínimo) só lê gold e busca.

| Esquema | Descrição | Leitura por `observatorio_leitura` |
| :--- | :--- | :--- |
| `bronze` | Dado bruto do portal dados.unb.br, como veio da API CKAN: todas as colunas em texto, sem limpeza. Contém dado pessoal. | não |
| `silver` | Dado limpo, tipado e normalizado por src/pipeline/transform_silver.py. Nível de registro individual: contém dado pessoal. | não |
| `gold` | Tabelas analíticas agregadas por curso (k >= 5), prontas para consumo pelo painel e pelo DEG. | sim |
| `busca` | Documentos vetorizados (pgvector) para busca semântica sobre cursos, projetos de IC e documentação do projeto. | sim |

## Esquema `bronze`

### `bronze.bolsistas_iniciacao_cientifica`

Bolsistas de iniciação científica PIBIC/PIVIC (bolsistas-de-iniciacao-cientifica.csv). Uma linha por plano de trabalho. Separador ",", Latin-1. Contém nome e matrícula do discente.

**Linhas na última carga:** 12.793

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `id_discente` | `text` | sim | Sempre 0 na fonte: chave zerada, não serve para junção. |
| `matricula` | `text` | sim | Matrícula do bolsista em claro (dado pessoal). Mascarada na silver. |
| `discente` | `text` | sim | Nome completo do bolsista (dado pessoal). Descartado na silver. |
| `titulo` | `text` | sim | Título do plano de trabalho. |
| `codigo_projeto` | `text` | sim | Sempre 0 na fonte. |
| `id_projeto_pesquisa` | `text` | sim | Sempre 0 na fonte. |
| `ano` | `text` | sim | Ano do edital. |
| `id_orientador` | `text` | sim | Sempre 0 na fonte. |
| `orientador` | `text` | sim | Nome do docente orientador. |
| `categoria` | `text` | sim | Sempre INICIAÇÃO CIENTÍFICA (IC). |
| `tipo_de_bolsa` | `text` | sim | REMUNERADA, VOLUNTÁRIA ou NÃO INFORMADO. |
| `linha_pesquisa` | `text` | sim | Grande linha: ARTES E HUMANIDADE, EXATAS E TECNOLÓGICAS ou SAÚDE E VIDA. |
| `id_grupo_pesquisa` | `text` | sim | Identificador do grupo de pesquisa. Sempre 0 ou vazio na fonte. |
| `grupo_pesquisa` | `text` | sim | Nome do grupo de pesquisa. Sempre vazio na fonte. |
| `cota` | `text` | sim | Cota de ingresso do bolsista: NÃO/NAO, NEGRO, INDÍGENA ou ESCOLA PÚB(LICA) com recortes de renda, PPI/NÃO PPI e PCD — grafia inconsistente. |
| `inicio` | `text` | sim | Início da vigência do plano, d/m/aaaa sem zero à esquerda. |
| `fim` | `text` | sim | Fim da vigência do plano, d/m/aaaa sem zero à esquerda. |
| `id_unidade` | `text` | sim | Sempre 0 na fonte. |
| `unidade` | `text` | sim | Campo composto "UNIDADE / CURSO", às vezes com sufixo de situação do aluno (- ALUNO: ATIVO, - FORMANDO). |
| `status` | `text` | sim | Situação da avaliação do plano: 2 - ENVIADA, 6 - AVALIADA ou 10 - RECURSO AVALIADO. |
| `_carregado_em` | `timestamp with time zone` | não | Momento em que a linha foi carregada no banco. |
| `_ordem` | `integer` | sim | Posição do registro no arquivo de origem (1 = primeiro registro depois do cabeçalho). |

### `bronze.cursos_graduacao`

Catálogo de cursos de graduação (curso_graduacao.csv). Uma linha por curso/habilitação. Separador ",", UTF-8.

**Linhas na última carga:** 157

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `id_curso` | `text` | sim | Identificador do curso no SIGAA. |
| `nome` | `text` | sim | Nome do curso com acento. |
| `id_coordenador` | `text` | sim | Identificador do coordenador no SIGAA ("NULL" literal quando não há). |
| `coordenador` | `text` | sim | Nome do coordenador do curso. |
| `situacao_curso` | `text` | sim | ATIVO ou INATIVO. |
| `nivel_ensino` | `text` | sim | Sempre vazio. |
| `grau_academico` | `text` | sim | Titulação conferida (Bacharel, Licenciado, Engenheiro Civil, Médico...). |
| `modalidade_educacao` | `text` | sim | Presencial ou A Distância. |
| `area_conhecimento` | `text` | sim | Grande Área CNPq/MEC; 13 cursos vêm como "Outra". |
| `tipo_oferta` | `text` | sim | Periodicidade da oferta (sempre Semestral). |
| `turno` | `text` | sim | Matutino e Vespertino, ou Noturno. |
| `tipo_ciclo_formacao` | `text` | sim | Sempre "Um ciclo". |
| `municipio` | `text` | sim | Sempre BRASÍLIA, inclusive para os campi de Gama, Ceilândia e Planaltina. |
| `campus` | `text` | sim | DARCY RIBEIRO, FACULDADE DO GAMA, FACULDADE DE CEILÂNDIA ou FACULDADE DE PLANALTINA. |
| `id_unidade_responsavel` | `text` | sim | Identificador da unidade acadêmica responsável. |
| `unidade_responsavel` | `text` | sim | Nome da unidade acadêmica responsável. |
| `website` | `text` | sim | Contato do curso; preenchido em só uma linha. |
| `data_funcionamento` | `text` | sim | Data de início de funcionamento, AAAA-MM-DD. |
| `codigo_inep` | `text` | sim | Código do curso no e-MEC/INEP. |
| `dou` | `text` | sim | Data de publicação do reconhecimento no Diário Oficial da União, AAAA-MM-DD. |
| `portaria_reconhecimento` | `text` | sim | Número da portaria de reconhecimento do curso. |
| `convenio_academico` | `text` | sim | Sempre vazio. |
| `_carregado_em` | `timestamp with time zone` | não | Momento em que a linha foi carregada no banco. |
| `_ordem` | `integer` | sim | Posição do registro no arquivo de origem (1 = primeiro registro depois do cabeçalho). |

### `bronze.estrutura_curricular`

Estruturas curriculares (estrutura-curricular.csv). Uma linha por matriz curricular. Separador ";", publicado em Latin-1.

**Linhas na última carga:** 500

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `id_curriculo` | `text` | sim | Identificador da matriz curricular no SIGAA. |
| `codigo` | `text` | sim | Código da matriz no formato opção/versão (ex.: 6912/1). |
| `nome_matriz` | `text` | sim | Campo composto: curso - município - habilitação - turno - titulação (ex.: "... - BRASÍLIA -  - N - Licenciado"). |
| `id_curso` | `text` | sim | Curso da matriz, no catálogo de cursos. |
| `nome_curso` | `text` | sim | Nome do curso com acento. |
| `semestre_conclusao_minimo` | `text` | sim | Prazo mínimo de conclusão, em semestres. |
| `semestre_conclusao_ideal` | `text` | sim | Duração padrão da matriz, em semestres. |
| `semestre_conclusao_maximo` | `text` | sim | Prazo máximo antes do jubilamento, em semestres. |
| `meses_conclusao_minimo` | `text` | sim | Prazo mínimo em meses. Sempre vazio na fonte. |
| `meses_conclusao_ideal` | `text` | sim | Prazo ideal em meses. Sempre vazio na fonte. |
| `meses_conclusao_maximo` | `text` | sim | Prazo máximo em meses. Sempre vazio na fonte. |
| `cr_total_minimo` | `text` | sim | Total mínimo de créditos. |
| `ch_total_minima` | `text` | sim | Carga horária total mínima, em horas. |
| `ch_optativas_minima` | `text` | sim | Carga horária mínima em disciplinas optativas, em horas. |
| `max_eletivos` | `text` | sim | Carga horária máxima em módulo livre (eletivas), em horas. |
| `ch_nao_atividade_obrigatoria` | `text` | sim | Carga horária obrigatória em disciplinas (exceto atividades), em horas. |
| `cr_nao_atividade_obrigatorio` | `text` | sim | Créditos obrigatórios em disciplinas (exceto atividades). |
| `ch_atividade_obrigatoria` | `text` | sim | Carga horária obrigatória em atividades (estágio, TCC...), em horas. |
| `cr_minimo_semestre` | `text` | sim | Mínimo de créditos por semestre. |
| `cr_maximo_semestre` | `text` | sim | Máximo de créditos por semestre. |
| `ch_minima_semestre` | `text` | sim | Carga horária mínima por semestre, em horas. |
| `ch_maxima_semestre` | `text` | sim | Carga horária máxima por semestre, em horas. |
| `periodo_entrada_vigor` | `text` | sim | Semestre (1 ou 2) em que a matriz entrou em vigor. |
| `ano_entrada_vigor` | `text` | sim | Ano em que a matriz entrou em vigor. |
| `observacao` | `text` | sim | Texto livre da coordenação sobre a matriz. |
| `_carregado_em` | `timestamp with time zone` | não | Momento em que a linha foi carregada no banco. |
| `_ordem` | `integer` | sim | Posição do registro no arquivo de origem (1 = primeiro registro depois do cabeçalho). |

### `bronze.inep_censo_superior_federais`

Censo da Educação Superior 2019 (INEP), recorte de cursos presenciais de universidades públicas federais. Uma linha por curso. Dado agregado por curso, sem registro individual de discente.

**Linhas na última carga:** 4.826

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `NU_ANO_CENSO` | `smallint` | não | Ano de referência do Censo. |
| `CO_IES` | `integer` | não | Código da instituição no INEP (UnB = 2). |
| `NO_CURSO` | `text` | não | Nome do curso na nomenclatura do INEP. |
| `CO_CURSO` | `bigint` | não | Código do curso no INEP. |
| `TP_GRAU_ACADEMICO` | `smallint` | sim | Grau (1 bacharelado, 2 licenciatura, 3 tecnológico...). Nulo em 175 cursos na fonte. |
| `TP_MODALIDADE_ENSINO` | `smallint` | não | Modalidade; o recorte só tem 1 (presencial). |
| `QT_VG_TOTAL` | `integer` | sim | Vagas totais oferecidas. |
| `QT_INSCRITO_TOTAL` | `integer` | sim | Inscritos no processo seletivo. |
| `QT_ING` | `integer` | sim | Ingressantes no ano. |
| `QT_MAT` | `integer` | sim | Matrículas no ano. |
| `QT_CONC` | `integer` | sim | Concluintes no ano. |
| `QT_SIT_TRANCADA` | `integer` | sim | Matrículas trancadas. |
| `QT_SIT_DESVINCULADO` | `integer` | sim | Matrículas desvinculadas do curso. |
| `QT_SIT_TRANSFERIDO` | `integer` | sim | Matrículas transferidas para outro curso da mesma instituição. |
| `TP_ORGANIZACAO_ACADEMICA` | `smallint` | não | Organização acadêmica; o recorte só tem 1 (universidade). |
| `TP_CATEGORIA_ADMINISTRATIVA` | `smallint` | não | Categoria administrativa; o recorte só tem 1 (pública federal). |
| `NO_IES` | `text` | não | Nome da instituição. |
| `_ordem` | `integer` | sim | Posição do registro no recorte gravado. |
| `_carregado_em` | `timestamp with time zone` | não | Momento em que a linha foi carregada no banco. |

### `bronze.ingestoes`

Procedência do último download de cada tabela bronze: de onde veio, quando, com que encoding e separador, e o hash do arquivo. Substitui o arquivo bruto em disco como evidência da auditoria de qualidade.

**Linhas na última carga:** 5

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `tabela` | `text` | não | Tabela bronze alimentada pelo arquivo. |
| `fonte` | `text` | não | dados.unb.br (API CKAN) ou INEP. |
| `pacote` | `text` | sim | Identificador do pacote no CKAN (vazio para o INEP). |
| `recurso_url` | `text` | não | URL de onde o arquivo foi baixado. |
| `baixado_em` | `timestamp with time zone` | não | Momento do download (hora de ingestão). |
| `tamanho_bytes` | `bigint` | não | Tamanho do arquivo baixado, em bytes. |
| `sha256` | `text` | não | Hash do arquivo baixado. Muda quando a fonte republica o dado. |
| `encoding` | `text` | não | Encoding usado para decodificar o arquivo (utf-8 ou latin-1). |
| `separador` | `text` | não | Separador de colunas do CSV de origem. |
| `registros` | `integer` | não | Registros gravados na tabela bronze. |
| `utf8_valido` | `boolean` | sim | Falso quando alguma das 15 primeiras linhas do arquivo não decodifica como UTF-8. Nulo quando não verificado (arquivo dentro de zip). |
| `linha_invalida` | `integer` | sim | Primeira linha do arquivo que não decodifica como UTF-8. |
| `evidencia_encoding` | `text` | sim | O byte inválido em UTF-8 e o início da linha em que aparece. |
| `metadados` | `jsonb` | sim | Resposta de package_show da API CKAN (título, recursos, datas de atualização). |

**Restrições:**

- Chave primária: `PRIMARY KEY (tabela)`
- Verificação: `CHECK ((registros >= 0))`
- Verificação: `CHECK ((tamanho_bytes > 0))`

### `bronze.sigra_discentes`

SIGRA (sigra.csv, pacote dados-referente-aos-alunos-de-graduacao-pos-graduacao-latu-sensu-mestrado-e-doutorado). Uma linha por vínculo de discente, todos os níveis. Separador ";", UTF-8. Contém quase-identificadores (nascimento, sexo, raça/cor).

**Linhas na última carga:** 85.121

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `aluno` | `text` | sim | Pseudônimo do discente (ex.: Aluno201086141). Repete quando o mesmo aluno tem mais de um vínculo. |
| `nivel` | `text` | sim | Nível do vínculo: Graduação, Mestrado ou Doutorado, com padding de espaços. |
| `opcao` | `text` | sim | Código da opção de ingresso (curso/habilitação) no SIGRA. |
| `curso` | `text` | sim | Nome do curso com acento e padding de até 30 espaços à direita. |
| `departamento` | `text` | sim | Unidade acadêmica do curso. |
| `ano_ingresso` | `text` | sim | Ano de ingresso, sem semestre. |
| `forma_ingresso` | `text` | sim | Via de ingresso (Vestibular, Novo Vestibular, Transferência, Acordo Cultural-PEC-G, Seleção...). |
| `cota_ingresso` | `text` | sim | Modalidade de cota no ingresso (Universal, Negro, Indígena, Escola Pública com recortes de renda, PPI e PcD). |
| `data_nascimento` | `text` | sim | Data de nascimento, dd/mm/aaaa. Quase-identificador. |
| `sexo` | `text` | sim | F ou M. |
| `raca_cor` | `text` | sim | Raça/cor autodeclarada, incluindo "Não cadastrada" e "Não quero declarar". Dado sensível. |
| `forma_saida` | `text` | sim | Motivo do encerramento do vínculo (Formatura, Desligamento Jubilamento, Repr 3 vezes na mesma disc obr, Mudança de Curso...). |
| `data_registro_livro` | `text` | sim | Data de registro do diploma, dd/mm/aaaa. Vazia para quem não se formou. |
| `periodo_saida` | `text` | sim | Período de saída no formato AAAAS (ex.: 20141). |
| `_carregado_em` | `timestamp with time zone` | não | Momento em que a linha foi carregada no banco (hora de ingestão, não do evento). |
| `_ordem` | `integer` | sim | Posição do registro no arquivo de origem (1 = primeiro registro depois do cabeçalho). |

## Esquema `silver`

### `silver.cursos_graduacao`

Catálogo de cursos limpo. Uma linha por curso/habilitação (id_curso). nome_curso_norm NÃO é único: cursos com bacharelado e licenciatura aparecem duas vezes com o mesmo nome.

**Linhas na última carga:** 157

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `id_curso` | `integer` | não | Identificador do curso no SIGAA. |
| `nome` | `text` | não | Nome do curso com acento, como na fonte. |
| `id_coordenador` | `integer` | sim | Identificador do coordenador no SIGAA. |
| `coordenador` | `text` | sim | Nome do coordenador do curso (servidor público, dado funcional). |
| `situacao_curso` | `text` | sim | ATIVO ou INATIVO. |
| `nivel_ensino` | `text` | sim | Sempre vazio na fonte. |
| `grau_academico` | `text` | sim | Titulação conferida, como na fonte. |
| `modalidade_educacao` | `text` | sim | Presencial ou A Distância. |
| `area_conhecimento` | `text` | sim | Grande Área como na fonte (inclui "Outra"). Use area_conhecimento_norm. |
| `tipo_oferta` | `text` | sim | Periodicidade da oferta (sempre Semestral). |
| `turno` | `text` | sim | Turno como na fonte. |
| `tipo_ciclo_formacao` | `text` | sim | Sempre "Um ciclo". |
| `municipio` | `text` | sim | Sempre BRASÍLIA na fonte, mesmo fora do Plano Piloto. |
| `campus` | `text` | sim | Campus como na fonte. |
| `id_unidade_responsavel` | `integer` | sim | Identificador da unidade acadêmica responsável. |
| `unidade_responsavel` | `text` | sim | Unidade acadêmica responsável, como na fonte. |
| `website` | `text` | sim | Contato do curso; preenchido em uma linha só. |
| `data_funcionamento` | `date` | sim | Início de funcionamento do curso. |
| `codigo_inep` | `integer` | sim | Código do curso no cadastro e-MEC/INEP. |
| `dou` | `date` | sim | Data de publicação do ato de reconhecimento no Diário Oficial da União. |
| `portaria_reconhecimento` | `integer` | sim | Número da portaria de reconhecimento. |
| `convenio_academico` | `text` | sim | Sempre vazio na fonte. |
| `nome_curso_norm` | `text` | não | Nome sem acento, em maiúsculas e sem espaços repetidos. Chave de junção com a estrutura curricular. |
| `turno_norm` | `text` | sim | Turno normalizado (ex.: MATUTINO E VESPERTINO, NOTURNO). |
| `campus_norm` | `text` | sim | Campus normalizado. |
| `grau_academico_norm` | `text` | sim | Titulação normalizada (ex.: BACHAREL, LICENCIADO). |
| `area_conhecimento_norm` | `text` | sim | Grande Área CNPq/MEC. Os 13 cursos classificados como "Outra" na fonte são remapeados à mão (AREA_CONHECIMENTO_OVERRIDES). |
| `unidade_responsavel_norm` | `text` | sim | Unidade acadêmica normalizada. |
| `_ordem` | `integer` | sim | Ordem de gravação. A gold pega o primeiro registro de cada nome de curso, então a ordem faz parte do resultado. |

**Restrições:**

- Chave primária: `PRIMARY KEY (id_curso)`

### `silver.estrutura_curricular`

Prazos regulamentares consolidados: uma linha por curso canônico, com a mediana dos semestres entre as matrizes do curso e a maior carga horária. Não há CHECK de máximo >= ideal porque a matriz de ENGENHARIA (curso-tronco) publica máximo 3 e ideal 5 — anomalia da fonte, coberta por teste.

**Linhas na última carga:** 113

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `nome_curso_norm` | `text` | não | Nome do curso normalizado. Destino da harmonização canônica do SIGRA. |
| `semestre_conclusao_minimo` | `numeric(4,1)` | não | Mediana do prazo mínimo de conclusão, em semestres, entre as matrizes do curso. |
| `semestre_conclusao_ideal` | `numeric(4,1)` | não | Mediana do prazo ideal (duração padrão) de conclusão, em semestres. |
| `semestre_conclusao_maximo` | `numeric(4,1)` | não | Mediana do prazo máximo antes do jubilamento, em semestres. |
| `ch_total_minima` | `integer` | sim | Maior carga horária total mínima entre as matrizes do curso, em horas. |
| `cr_total_minimo` | `integer` | sim | Maior total mínimo de créditos entre as matrizes do curso. |
| `id_curso` | `integer` | não | Curso da primeira matriz do grupo, no catálogo de cursos. |
| `_ordem` | `integer` | sim | Ordem de gravação (alfabética por curso). |

**Restrições:**

- Chave primária: `PRIMARY KEY (nome_curso_norm)`
- Única: `UNIQUE (id_curso)`
- Chave estrangeira: `FOREIGN KEY (id_curso) REFERENCES silver.cursos_graduacao(id_curso)`
- Verificação: `CHECK ((semestre_conclusao_ideal >= semestre_conclusao_minimo))`
- Verificação: `CHECK ((semestre_conclusao_minimo > (0)::numeric))`

### `silver.inep_censo_superior`

Cursos presenciais das federais no Censo 2019, com as taxas por curso que permitem comparar a UnB com as demais. Uma linha por curso (CO_CURSO).

**Linhas na última carga:** 4.826

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `NU_ANO_CENSO` | `smallint` | não | Ano de referência do Censo. |
| `CO_IES` | `integer` | não | Código da instituição no INEP (UnB = 2). |
| `NO_IES` | `text` | não | Nome da instituição. |
| `is_unb` | `boolean` | não | Verdadeiro para cursos da UnB (CO_IES = 2). |
| `CO_CURSO` | `bigint` | não | Código do curso no INEP. |
| `NO_CURSO` | `text` | não | Nome do curso na nomenclatura do INEP. Chave de comparação entre instituições. |
| `curso_inep_norm` | `text` | não | Nome do curso normalizado (sem acento, maiúsculas). |
| `QT_VG_TOTAL` | `integer` | sim | Vagas totais oferecidas. |
| `QT_INSCRITO_TOTAL` | `integer` | sim | Inscritos no processo seletivo. |
| `QT_ING` | `integer` | sim | Ingressantes no ano. |
| `QT_MAT` | `integer` | sim | Matrículas no ano. |
| `QT_CONC` | `integer` | sim | Concluintes no ano. |
| `QT_SIT_TRANCADA` | `integer` | sim | Matrículas trancadas. |
| `QT_SIT_DESVINCULADO` | `integer` | sim | Matrículas desvinculadas do curso. |
| `taxa_trancamento_pct` | `numeric(6,2)` | sim | QT_SIT_TRANCADA / QT_MAT x 100. Situação apurada no ano-censo, não por coorte. |
| `taxa_desvinculacao_pct` | `numeric(6,2)` | sim | QT_SIT_DESVINCULADO / QT_MAT x 100. Não é comparável com a taxa de evasão do SIGRA. |
| `concorrencia_vestibular` | `numeric(8,2)` | sim | QT_INSCRITO_TOTAL / QT_VG_TOTAL (inscritos por vaga). |
| `_ordem` | `integer` | sim | Ordem de gravação. |

**Restrições:**

- Chave primária: `PRIMARY KEY ("CO_CURSO")`

### `silver.pibic_bolsistas`

Planos de trabalho de iniciação científica, sem nome do bolsista e com matrícula mascarada. Uma linha por plano. Sem chave natural: a fonte traz 28 linhas idênticas.

**Linhas na última carga:** 12.793

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `id` | `bigint (identity)` | não | Chave substituta. |
| `matricula_mascarada` | `text` | não | 3 primeiros + *** + 2 últimos dígitos da matrícula. Mascarar não é anonimizar: combinada a curso e ano ainda pode identificar. |
| `ano` | `smallint` | não | Ano do edital. |
| `tipo_bolsa_norm` | `text` | não | REMUNERADA (PIBIC), VOLUNTARIA (PIVIC) ou NAO INFORMADO. |
| `linha_pesquisa_norm` | `text` | sim | Grande linha de pesquisa normalizada. |
| `campus` | `text` | não | Campus inferido do nome da unidade: DARCY RIBEIRO, FGA - GAMA, FCE - CEILANDIA ou FUP - PLANALTINA. |
| `departamento_pibic_norm` | `text` | sim | Unidade extraída do campo "unidade" (texto antes da barra). |
| `curso_pibic_norm` | `text` | sim | Curso extraído do campo "unidade" (texto após a barra), sem prefixos como BACHARELADO EM. |
| `perfil_social_macro` | `text` | sim | AMPLA CONCORRENCIA, PPI / ETNICO-RACIAL, ESCOLA PUBLICA ou OUTRAS COTAS. Atenção: a regra atual classifica cotas "NÃO PPI" como PPI. |
| `cota_detalhe` | `text` | sim | Grupo de cota detalhado (ex.: ESCOLA PUBLICA - PPI, COTAS RACIAIS (NEGRO/INDIGENA)). |
| `faixa_renda` | `text` | sim | BAIXA RENDA (<= 1.5 SM), INDEPENDENTE DE RENDA, NAO ESPECIFICADO ou NAO APLICAVEL (ampla concorrência). |
| `is_cotista` | `boolean` | não | Verdadeiro se o bolsista ingressou por qualquer cota. |
| `valor_bolsa_anual_estimado` | `numeric(10,2)` | não | Estimativa: 12 x R$ 700 a partir de 2023, 12 x R$ 400 antes; zero para voluntária. |
| `orientador_norm` | `text` | sim | Nome do docente orientador, normalizado. |
| `titulo_norm` | `text` | sim | Título do plano de trabalho, normalizado. É o texto vetorizado na busca semântica. |
| `status_norm` | `text` | sim | Situação da avaliação do plano. |

**Restrições:**

- Chave primária: `PRIMARY KEY (id)`
- Verificação: `CHECK ((tipo_bolsa_norm = ANY (ARRAY['REMUNERADA'::text, 'VOLUNTARIA'::text, 'NAO INFORMADO'::text])))`
- Verificação: `CHECK ((valor_bolsa_anual_estimado >= (0)::numeric))`

### `silver.sigra_graduacao`

Vínculos de graduação do SIGRA. Uma linha por vínculo (aluno + opção + ingresso + saída): o mesmo aluno aparece mais de uma vez quando muda de curso. Registro individual com quase-identificadores — nunca expor fora do banco.

**Linhas na última carga:** 60.695

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `id` | `bigint (identity)` | não | Chave substituta. A chave natural é (aluno, opcao, ano_ingresso, periodo_saida). |
| `aluno` | `text` | não | Pseudônimo do discente publicado pelo portal (ex.: Aluno201086141). Não é único: repete entre vínculos. |
| `nivel` | `text` | sim | Nível como na fonte (sempre Graduação nesta tabela, com padding). |
| `opcao` | `integer` | não | Código da opção de ingresso no SIGRA. Não há tabela pública que ligue opção a grau (bacharelado/licenciatura). |
| `curso` | `text` | sim | Nome do curso como na fonte, com padding de espaços. |
| `departamento` | `text` | sim | Unidade acadêmica como na fonte. |
| `ano_ingresso` | `smallint` | não | Ano de ingresso. A fonte não informa o semestre. |
| `forma_ingresso` | `text` | sim | Via de ingresso como na fonte. |
| `cota_ingresso` | `text` | sim | Modalidade de cota no ingresso como na fonte. |
| `data_nascimento` | `date` | sim | Quase-identificador (LGPD). Combinado a curso, sexo e raça/cor, deixa 88,9% dos registros com k = 1. |
| `sexo` | `character(1)` | sim | F ou M. Quase-identificador. |
| `raca_cor` | `text` | sim | Dado pessoal sensível (LGPD, art. 5º, II). |
| `forma_saida` | `text` | sim | Motivo do encerramento do vínculo como na fonte. |
| `data_registro_livro` | `date` | sim | Registro do diploma. Nulo para quem não se formou. |
| `periodo_saida` | `integer` | não | Ano e semestre da saída no formato AAAAS (ex.: 20141). Semestre 0 indica período de verão. |
| `nivel_norm` | `text` | não | Nível normalizado; esta tabela só guarda GRADUACAO. |
| `curso_raw` | `text` | sim | Nome do curso sem o padding, ainda com acento. |
| `curso_norm` | `text` | não | Nome do curso normalizado, antes da harmonização canônica (ver gold.regras_harmonizacao_canonicas). |
| `departamento_norm` | `text` | sim | Unidade acadêmica normalizada. |
| `forma_saida_norm` | `text` | sim | Motivo de saída normalizado, base de tipo_saida_grupo. |
| `tipo_saida_grupo` | `text` | não | forma_saida agrupada: FORMATURA, EVASAO_DESLIGAMENTO (abandono, jubilamento, 3 reprovações, desligamento), MUDANCA_INTERNA ou OUTROS. |
| `ano_saida` | `smallint` | sim | Ano extraído de periodo_saida. |
| `semestre_saida` | `smallint` | sim | Semestre extraído de periodo_saida: 1, 2 ou 0 (verão). |
| `semestres_permanencia` | `smallint` | sim | 2 * (ano_saida - ano_ingresso) + semestre_saida. Assume ingresso no 1º semestre (incerteza de ±1 semestre). |
| `semestres_permanencia_valida` | `smallint` | sim | semestres_permanencia quando está entre 1 e 30; nulo caso contrário. |

**Restrições:**

- Chave primária: `PRIMARY KEY (id)`
- Única: `UNIQUE (aluno, opcao, ano_ingresso, periodo_saida)`
- Verificação: `CHECK ((nivel_norm = 'GRADUACAO'::text))`
- Verificação: `CHECK ((semestre_saida = ANY (ARRAY[0, 1, 2])))`
- Verificação: `CHECK (((semestres_permanencia_valida >= 1) AND (semestres_permanencia_valida <= 30)))`
- Verificação: `CHECK ((sexo = ANY (ARRAY['F'::bpchar, 'M'::bpchar])))`
- Verificação: `CHECK ((tipo_saida_grupo = ANY (ARRAY['FORMATURA'::text, 'EVASAO_DESLIGAMENTO'::text, 'MUDANCA_INTERNA'::text, 'OUTROS'::text])))`

## Esquema `gold`

### `gold.inep_benchmark_cursos_unb`

Cada curso da UnB comparado com o mesmo curso nas demais universidades federais (Censo INEP 2019). Uma linha por curso da UnB com 50 ou mais matrículas.

**Linhas na última carga:** 96

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `curso_inep` | `text` | não | Nome do curso na nomenclatura do INEP. |
| `qt_matriculas_unb` | `integer` | não | Matrículas da UnB no curso, somando as ofertas (turnos e campi). |
| `qt_ingressantes_unb` | `integer` | sim | Ingressantes da UnB no curso. |
| `qt_concluintes_unb` | `integer` | sim | Concluintes da UnB no curso. |
| `qt_trancadas_unb` | `integer` | sim | Matrículas trancadas na UnB. |
| `qt_desvinculados_unb` | `integer` | sim | Matrículas desvinculadas na UnB. |
| `qt_vagas_unb` | `integer` | sim | Vagas oferecidas pela UnB. |
| `qt_inscritos_unb` | `integer` | sim | Inscritos no processo seletivo da UnB. |
| `taxa_trancamento_unb_pct` | `numeric(6,2)` | sim | qt_trancadas_unb / qt_matriculas_unb x 100. |
| `taxa_desvinculacao_unb_pct` | `numeric(6,2)` | sim | qt_desvinculados_unb / qt_matriculas_unb x 100. |
| `concorrencia_vestibular_unb` | `numeric(8,2)` | sim | Inscritos por vaga na UnB. |
| `n_ies_comparadas` | `integer` | sim | Outras federais que oferecem o curso. Nulo quando nenhuma oferece. |
| `mediana_trancamento_federais_pct` | `numeric(6,2)` | sim | Mediana da taxa de trancamento do curso nas demais federais. |
| `mediana_desvinculacao_federais_pct` | `numeric(6,2)` | sim | Mediana da taxa de desvinculação do curso nas demais federais. |
| `gap_trancamento_pp` | `numeric(6,2)` | sim | Trancamento da UnB menos a mediana das federais, em pontos percentuais. |
| `gap_desvinculacao_pp` | `numeric(6,2)` | sim | Desvinculação da UnB menos a mediana das federais, em pontos percentuais. |
| `razao_trancamento` | `numeric(8,2)` | sim | Trancamento da UnB dividido pela mediana das federais (1,9 = quase o dobro). |
| `razao_desvinculacao` | `numeric(8,2)` | sim | Desvinculação da UnB dividida pela mediana das federais. |
| `_ordem` | `integer` | sim | Ordem de gravação: do curso com mais para o com menos matrículas. |

**Restrições:**

- Chave primária: `PRIMARY KEY (curso_inep)`
- Verificação: `CHECK ((qt_matriculas_unb >= 0))`

### `gold.pibic_social_unb`

Iniciação científica por curso e campus: volume, bolsas e perfil social dos bolsistas. Só entram grupos com 5 ou mais planos.

**Linhas na última carga:** 92

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `curso_pibic_norm` | `text` | não | Curso do bolsista, já harmonizado com os nomes canônicos. |
| `campus` | `text` | não | Campus inferido da unidade do bolsista. |
| `area_conhecimento` | `text` | sim | Grande Área CNPq/MEC do curso. |
| `total_projetos` | `integer` | não | Planos de trabalho de IC. Mínimo 5 (k-anonimato). |
| `total_remuneradas` | `integer` | não | Planos com bolsa remunerada (PIBIC). |
| `total_voluntarias_pivic` | `integer` | não | Planos voluntários (PIVIC). |
| `total_cotistas` | `integer` | não | Planos de bolsistas que ingressaram por cota. |
| `total_cotistas_ppi` | `integer` | não | Planos de bolsistas classificados como PPI / ETNICO-RACIAL. Atenção: hoje inclui cotas "NÃO PPI" (ver silver.pibic_bolsistas.perfil_social_macro). |
| `total_baixa_renda` | `integer` | não | Planos de bolsistas que ingressaram por cota de baixa renda (até 1,5 salário mínimo per capita). |
| `valor_total_investido` | `numeric(14,2)` | não | Soma estimada das bolsas remuneradas, em R$. |
| `taxa_cotistas_pct` | `numeric(5,2)` | sim | total_cotistas / total_projetos x 100. |
| `taxa_voluntario_pct` | `numeric(5,2)` | sim | total_voluntarias_pivic / total_projetos x 100. |
| `_ordem` | `integer` | sim | Ordem de gravação: do maior para o menor número de planos. |

**Restrições:**

- Chave primária: `PRIMARY KEY (curso_pibic_norm, campus)`
- Verificação: `CHECK (((taxa_cotistas_pct >= (0)::numeric) AND (taxa_cotistas_pct <= (100)::numeric)))`
- Verificação: `CHECK (((taxa_voluntario_pct >= (0)::numeric) AND (taxa_voluntario_pct <= (100)::numeric)))`
- Verificação: `CHECK ((total_baixa_renda >= 0))`
- Verificação: `CHECK ((total_cotistas >= 0))`
- Verificação: `CHECK ((total_cotistas_ppi >= 0))`
- Verificação: `CHECK ((total_projetos >= 5))`
- Verificação: `CHECK ((total_remuneradas >= 0))`
- Verificação: `CHECK ((total_voluntarias_pivic >= 0))`
- Verificação: `CHECK ((valor_total_investido >= (0)::numeric))`

### `gold.regras_harmonizacao_canonicas`

Regras de equivalência entre o nome do curso no SIGRA e o nome da matriz curricular (entity resolution). Uma linha por nome de origem.

**Linhas na última carga:** 78

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `origem_sigra` | `text` | não | Nome normalizado do curso como aparece no SIGRA. |
| `destino_estrutura` | `text` | não | Nome da matriz em silver.estrutura_curricular para o qual a origem é mapeada. |
| `categoria` | `text` | sim | Motivo agrupado da regra (Correção de Typo no Portal, Habilitação Legada, Engenharias...). |
| `justificativa` | `text` | sim | Explicação da equivalência, em texto. |
| `discentes_impactados` | `integer` | não | Vínculos do SIGRA reclassificados por esta regra. |
| `_ordem` | `integer` | sim | Ordem de gravação: da regra que mais reclassifica vínculos para a que menos reclassifica. |

**Restrições:**

- Chave primária: `PRIMARY KEY (origem_sigra)`
- Verificação: `CHECK ((discentes_impactados >= 0))`

### `gold.relatorios`

Relatórios JSON do pipeline: métricas gerais da UnB, métricas do PIBIC e auditoria de casamento dos joins. Uma linha por arquivo.

**Linhas na última carga:** 4

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `nome` | `text` | não | Nome do arquivo de origem sem extensão (ex.: metricas_gerais_unb). |
| `conteudo` | `jsonb` | não | Conteúdo integral do JSON. |
| `_carregado_em` | `timestamp with time zone` | não | Momento em que o relatório foi carregado no banco. |

**Restrições:**

- Chave primária: `PRIMARY KEY (nome)`

### `gold.retencao_cursos_unb`

Retenção, formatura e evasão por curso. Uma linha por curso canônico de graduação; cursos com bacharelado e licenciatura sob o mesmo nome ficam numa linha só (categoria_grau = MISTO). Só entram cursos com 5 ou mais discentes.

**Linhas na última carga:** 88

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `curso` | `text` | não | Nome canônico do curso após a harmonização SIGRA -> matriz curricular (sem acento, maiúsculas). |
| `departamento` | `text` | sim | Departamento de vinculação, como registrado no SIGRA. |
| `campus` | `text` | sim | Campus de oferta. |
| `turno` | `text` | sim | DIURNO, NOTURNO ou INTEGRAL. Matutino e vespertino são unificados em DIURNO. |
| `area_conhecimento` | `text` | sim | Grande Área CNPq/MEC. |
| `grau_academico` | `text` | sim | Titulação literal conferida ao egresso, ou MISTO (BACHARELADO + LICENCIATURA). |
| `categoria_grau` | `text` | sim | BACHARELADO (inclui titulações profissionais), LICENCIATURA ou MISTO. |
| `semestre_minimo_previsto` | `numeric(4,1)` | sim | Prazo mínimo regulamentar, em semestres. |
| `semestre_ideal_previsto` | `numeric(4,1)` | sim | Duração ideal da matriz curricular, em semestres. |
| `semestre_maximo_previsto` | `numeric(4,1)` | sim | Prazo máximo antes do jubilamento, em semestres. |
| `carga_horaria_minima` | `integer` | sim | Carga horária total mínima para conclusão, em horas. |
| `total_discentes_registrados` | `integer` | não | Vínculos do curso no SIGRA. Mínimo 5 (supressão de grupos pequenos, k-anonimato). |
| `total_formados` | `integer` | não | Vínculos com saída por formatura. |
| `total_evadidos_desligados` | `integer` | não | Vínculos encerrados por abandono, jubilamento, 3 reprovações ou desligamento. |
| `taxa_formatura_pct` | `numeric(5,2)` | sim | total_formados / total_discentes_registrados x 100. |
| `taxa_evasao_pct` | `numeric(5,2)` | sim | total_evadidos_desligados / total_discentes_registrados x 100. |
| `formados_tempo_minimo_pct` | `numeric(5,2)` | sim | % dos formados que concluíram em semestres <= semestre_minimo_previsto. |
| `formados_tempo_ideal_pct` | `numeric(5,2)` | sim | % dos formados que concluíram em semestres <= semestre_ideal_previsto. |
| `formados_acima_ideal_pct` | `numeric(5,2)` | sim | % dos formados que passaram do semestre_ideal_previsto. |
| `formados_limite_maximo_pct` | `numeric(5,2)` | sim | % dos formados que concluíram em semestres >= semestre_maximo_previsto. |
| `tempo_medio_real_semestres` | `numeric(5,2)` | sim | Média de semestres entre ingresso e formatura, entre os formados. |
| `tempo_mediano_real_semestres` | `numeric(5,2)` | sim | Mediana de semestres entre ingresso e formatura, entre os formados. |
| `desvio_medio_semestres` | `numeric(5,2)` | sim | Média de (semestres cursados - semestre_ideal_previsto) entre os formados. Negativo = formou antes do ideal. |
| `indice_retencao_critica` | `numeric(4,1)` | sim | IRC, 0 a 100: (0,3 x atraso normalizado + 0,7 x evasão normalizada) x 100, com saturação nos percentis 5 e 95. |
| `classificacao_retencao` | `text` | sim | Quartil do IRC: CRÍTICA (>= p75), ALTA (>= p50), MÉDIA (>= p25), BAIXA. |
| `pibic_total_projetos` | `integer` | sim | Planos de iniciação científica de alunos do curso, em todos os anos publicados. Zero quando não há plano. |
| `pibic_bolsas_remuneradas` | `integer` | sim | Planos com bolsa remunerada (PIBIC). Nulo quando o curso não tem plano de IC. |
| `pibic_bolsas_voluntarias` | `integer` | sim | Planos voluntários (PIVIC). Nulo quando o curso não tem plano de IC. |
| `pibic_cotistas` | `integer` | sim | Planos de bolsistas que ingressaram por cota. Nulo quando o curso não tem plano de IC. |
| `pibic_investimento_total` | `numeric(14,2)` | sim | Soma estimada das bolsas remuneradas do curso, em R$. |
| `pibic_projetos_por_100_alunos` | `numeric(7,2)` | sim | pibic_total_projetos / total_discentes_registrados x 100. |
| `_ordem` | `integer` | sim | Ordem de gravação: do maior para o menor índice de retenção crítica. |

**Restrições:**

- Chave primária: `PRIMARY KEY (curso)`
- Verificação: `CHECK ((categoria_grau = ANY (ARRAY['BACHARELADO'::text, 'LICENCIATURA'::text, 'MISTO'::text])))`
- Verificação: `CHECK (((total_formados + total_evadidos_desligados) <= total_discentes_registrados))`
- Verificação: `CHECK ((classificacao_retencao = ANY (ARRAY['RETENÇÃO CRÍTICA'::text, 'RETENÇÃO ALTA'::text, 'RETENÇÃO MÉDIA'::text, 'RETENÇÃO BAIXA'::text])))`
- Verificação: `CHECK (((formados_acima_ideal_pct >= (0)::numeric) AND (formados_acima_ideal_pct <= (100)::numeric)))`
- Verificação: `CHECK (((formados_limite_maximo_pct >= (0)::numeric) AND (formados_limite_maximo_pct <= (100)::numeric)))`
- Verificação: `CHECK (((formados_tempo_ideal_pct >= (0)::numeric) AND (formados_tempo_ideal_pct <= (100)::numeric)))`
- Verificação: `CHECK (((formados_tempo_minimo_pct >= (0)::numeric) AND (formados_tempo_minimo_pct <= (100)::numeric)))`
- Verificação: `CHECK (((indice_retencao_critica >= (0)::numeric) AND (indice_retencao_critica <= (100)::numeric)))`
- Verificação: `CHECK (((taxa_evasao_pct >= (0)::numeric) AND (taxa_evasao_pct <= (100)::numeric)))`
- Verificação: `CHECK (((taxa_formatura_pct >= (0)::numeric) AND (taxa_formatura_pct <= (100)::numeric)))`
- Verificação: `CHECK ((total_discentes_registrados >= 5))`
- Verificação: `CHECK ((total_evadidos_desligados >= 0))`
- Verificação: `CHECK ((total_formados >= 0))`
- Verificação: `CHECK ((turno = ANY (ARRAY['DIURNO'::text, 'NOTURNO'::text, 'INTEGRAL'::text])))`

## Esquema `busca`

### `busca.documentos`

Um documento de texto por entidade pesquisável: cada curso da gold, cada plano de IC distinto e cada seção da documentação em docs/. Não contém nome nem matrícula.

**Linhas na última carga:** 12.849

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `id` | `bigint (identity)` | não | Chave substituta. |
| `tipo` | `text` | não | curso (gold.retencao_cursos_unb), projeto_pibic (silver.pibic_bolsistas) ou documentacao (seções dos .md em docs/). |
| `chave` | `text` | não | Chave natural do documento dentro do tipo (nome do curso, hash do plano de IC, arquivo#seção). |
| `titulo` | `text` | não | Rótulo curto exibido no resultado da busca. |
| `conteudo` | `text` | não | Texto que foi vetorizado. |
| `metadados` | `jsonb` | não | Campos estruturados para filtro e exibição (curso, campus, ano, IRC etc.). |
| `hash_conteudo` | `text` | não | SHA-256 de modelo + conteúdo. Se não mudou, a vetorização não recalcula o embedding. |
| `modelo` | `text` | não | Modelo de embedding usado. |
| `embedding` | `vector(384)` | não | Vetor normalizado de 384 dimensões. Similaridade = 1 - (embedding <=> consulta). |
| `atualizado_em` | `timestamp with time zone` | não | Última vez em que o embedding foi recalculado. |

**Restrições:**

- Chave primária: `PRIMARY KEY (id)`
- Única: `UNIQUE (tipo, chave)`
- Verificação: `CHECK ((tipo = ANY (ARRAY['curso'::text, 'projeto_pibic'::text, 'documentacao'::text])))`
