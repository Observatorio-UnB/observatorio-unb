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

Bolsistas de iniciação científica PIBIC/PIVIC (bolsistas-de-iniciacao-cientifica.csv). Uma linha por plano de trabalho. O arquivo publicado traz nome e matrícula do discente e nome do orientador, descartados em memória pela ingestão: só estas colunas são gravadas (UTF-8, separador ",").

**Linhas na última carga:** 12.793

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `titulo` | `text` | sim | Título do plano de trabalho. |
| `ano` | `text` | sim | Ano do edital. |
| `tipo_de_bolsa` | `text` | sim | REMUNERADA, VOLUNTÁRIA ou NÃO INFORMADO. |
| `linha_pesquisa` | `text` | sim | Grande linha: ARTES E HUMANIDADE, EXATAS E TECNOLÓGICAS ou SAÚDE E VIDA. |
| `cota` | `text` | sim | Cota de ingresso do bolsista: NÃO/NAO, NEGRO, INDÍGENA ou ESCOLA PÚB(LICA) com recortes de renda, PPI/NÃO PPI e PCD — grafia inconsistente. |
| `inicio` | `text` | sim | Início da vigência do plano, d/m/aaaa sem zero à esquerda. |
| `fim` | `text` | sim | Fim da vigência do plano, d/m/aaaa sem zero à esquerda. |
| `unidade` | `text` | sim | Campo composto "UNIDADE / CURSO", às vezes com sufixo de situação do aluno (- ALUNO: ATIVO, - FORMANDO). |
| `status` | `text` | sim | Situação da avaliação do plano: 2 - ENVIADA, 6 - AVALIADA ou 10 - RECURSO AVALIADO. |
| `_carregado_em` | `timestamp with time zone` | não | Momento em que a linha foi carregada no banco. |
| `_ordem` | `integer` | sim | Posição do registro no arquivo de origem (1 = primeiro registro depois do cabeçalho). |

### `bronze.cursos_graduacao`

Catálogo de cursos de graduação: todas as versões publicadas no pacote cursos-de-graduacao, empilhadas. Uma linha por curso por versão.

**Linhas na última carga:** 470

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
| `id_servidor` | `text` | sim | Identificador do coordenador como servidor. Só nas versões de 2023 em diante. |
| `arquivo_origem` | `text` | sim | Arquivo do portal de onde veio a linha (ex.: cursos-de-graduao-08-2024.csv). |
| `publicado_em` | `text` | sim | Data de publicação do arquivo no CKAN (AAAA-MM-DD). |
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

**Linhas na última carga:** 0

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

**Linhas na última carga:** 6

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
| `linhas_descartadas` | `integer` | não | Linhas malformadas descartadas durante a leitura do CSV. |

**Restrições:**

- Chave primária: `PRIMARY KEY (tabela)`
- Verificação: `CHECK ((registros >= 0))`
- Verificação: `CHECK ((tamanho_bytes > 0))`

### `bronze.sigaa_ativos`

Lista de discentes ativos do SIGAA (sigaa_ativos_AAAA_S.csv, semestre mais recente publicado), todos os níveis. O arquivo publicado traz nome, CPF parcial e nacionalidade, descartados em memória pela ingestão: só estas quatro colunas são gravadas.

**Linhas na última carga:** 53.687

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `grau` | `text` | sim | Grau do curso (Bacharelado, Licenciatura, títulos profissionais, Mestrado, Doutorado). Vazio no lato sensu. |
| `curso` | `text` | sim |  |
| `ano_ingresso` | `text` | sim |  |
| `periodo_ingresso` | `text` | sim | Semestre de ingresso: 1, 2 ou 0 (verão). |
| `_carregado_em` | `timestamp with time zone` | não |  |
| `_ordem` | `integer` | sim |  |

### `bronze.sigaa_discentes`

SIGAA (sigaa.csv, mesmo pacote do SIGRA). Uma linha por vínculo, todos os níveis, com a situação atual do vínculo. Separador ";", UTF-8. ano_ingresso vem com separador de milhar ("2,010"). Contém quase-identificadores (nascimento, sexo, raça/cor).

**Linhas na última carga:** 111.385

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `aluno` | `text` | sim | Pseudônimo do discente. Não casa com o pseudônimo do SIGRA. |
| `nivel` | `text` | sim |  |
| `curso` | `text` | sim |  |
| `unidade` | `text` | sim |  |
| `ano_ingresso` | `text` | sim |  |
| `forma_ingresso` | `text` | sim |  |
| `cota_ingresso` | `text` | sim |  |
| `data_nascimento` | `text` | sim |  |
| `sexo` | `text` | sim |  |
| `raca_cor` | `text` | sim |  |
| `status_aluno` | `text` | sim | Situação do vínculo na data do extrato: ATIVO, ATIVO - FORMANDO, TRANCADO, CONCLUÍDO, FORMADO, CANCELADO, NÃO CADASTRADO... |
| `data_registro_diploma` | `text` | sim | Data de registro do diploma, dd/mm/aaaa. Única pista do momento da conclusão. |
| `bolsa` | `text` | sim |  |
| `_carregado_em` | `timestamp with time zone` | não |  |
| `_ordem` | `integer` | sim |  |

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

### `silver.cursos`

Catálogo canônico de cursos da UnB normalizado em 3NF. Elimina repetição de campus, turno e grande área.

**Linhas na última carga:** 158

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `id_curso` | `integer` | não |  |
| `codigo_sigaa` | `text` | sim |  |
| `nome_curso_norm` | `text` | não |  |
| `campus` | `text` | não |  |
| `turno` | `text` | não |  |
| `grau_academico` | `text` | não |  |
| `categoria_grau` | `text` | não |  |
| `area_conhecimento` | `text` | não |  |
| `departamento` | `text` | sim |  |
| `is_tronco_abi` | `boolean` | não |  |
| `ativo` | `boolean` | não |  |

**Restrições:**

- Chave primária: `PRIMARY KEY (id_curso)`
- Verificação: `CHECK ((categoria_grau = ANY (ARRAY['BACHARELADO'::text, 'LICENCIATURA'::text, 'MISTO'::text])))`
- Verificação: `CHECK ((turno = ANY (ARRAY['DIURNO'::text, 'NOTURNO'::text, 'INTEGRAL'::text, 'DIURNO E NOTURNO'::text, 'MATUTINO'::text, 'VESPERTINO'::text, 'MATUTINO E VESPERTINO'::text])))`

### `silver.cursos_graduacao`

Catálogo de cursos de graduação consolidado: um registro por id_curso, com o valor da versão mais recente em cada campo e, se vazio nela, o da última versão que o tinha.

**Linhas na última carga:** 158

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
| `unidade_responsavel` | `text` | sim | Unidade acadêmica responsável, como na fonte. Só o catálogo de 2022 traz este campo; cursos criados depois ficam sem. |
| `website` | `text` | sim | Contato do curso; preenchido em uma linha só. |
| `data_funcionamento` | `date` | sim | Início de funcionamento do curso. |
| `codigo_inep` | `integer` | sim | Código do curso no cadastro e-MEC/INEP. |
| `dou` | `date` | sim | Data de publicação do ato de reconhecimento no Diário Oficial da União. |
| `portaria_reconhecimento` | `integer` | sim | Número da portaria de reconhecimento. |
| `convenio_academico` | `text` | sim | Sempre vazio na fonte. |
| `nome_curso_norm` | `text` | não | Nome do curso sem acento, em maiúsculas, sem o prefixo de curso guarda-chuva (Comunicação Social, Ciências Sociais). |
| `turno_norm` | `text` | sim | Turno normalizado (ex.: MATUTINO E VESPERTINO, NOTURNO). |
| `campus_norm` | `text` | sim | Campus normalizado. |
| `grau_academico_norm` | `text` | sim | Titulação normalizada (ex.: BACHAREL, LICENCIADO). |
| `area_conhecimento_norm` | `text` | sim | Grande Área CNPq/MEC. Os 13 cursos classificados como "Outra" na fonte são remapeados à mão (AREA_CONHECIMENTO_OVERRIDES). |
| `unidade_responsavel_norm` | `text` | sim | Unidade acadêmica normalizada. |
| `no_catalogo_vigente` | `boolean` | não | Falso para código de curso que não está na versão mais recente do catálogo; mantido porque pode ter alunos nas coortes analisadas. |
| `_ordem` | `integer` | sim | Ordem de gravação. A gold pega o primeiro registro de cada nome de curso, então a ordem faz parte do resultado. |

**Restrições:**

- Chave primária: `PRIMARY KEY (id_curso)`

### `silver.discentes`

Discentes únicos normalizados. Registro individual com quase-identificadores sob proteção de privilégio mínimo.

**Linhas na última carga:** 125.154

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `id_discente` | `bigint (identity)` | não | Identificador numérico sintético do discente. |
| `pseudonimo` | `text` | não | Pseudônimo original gerado pelo sistema acadêmico. |
| `data_nascimento` | `date` | sim |  |
| `sexo` | `character(1)` | sim |  |
| `raca_cor` | `text` | sim |  |
| `criado_em` | `timestamp with time zone` | não |  |

**Restrições:**

- Chave primária: `PRIMARY KEY (id_discente)`
- Única: `UNIQUE (pseudonimo)`
- Verificação: `CHECK ((sexo = ANY (ARRAY['F'::bpchar, 'M'::bpchar])))`

### `silver.discentes_graduacao`

Vínculos de graduação do SIGRA (encerrados até 2020/1) e do SIGAA (ativos na migração ou posteriores). Uma linha por vínculo; os pseudônimos das duas bases não se ligam entre si.

**Linhas na última carga:** 152.680

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `id` | `bigint (identity)` | não | Chave substituta. |
| `aluno` | `text` | não | Pseudônimo do discente publicado pelo portal (ex.: Aluno201086141). Não é único: repete entre vínculos. |
| `nivel` | `text` | sim | Nível como na fonte (sempre Graduação nesta tabela, com padding). |
| `opcao` | `integer` | sim | Código da opção de ingresso no SIGRA. Nulo no SIGAA. |
| `curso` | `text` | sim | Nome do curso como na fonte, com padding de espaços. |
| `departamento` | `text` | sim | Unidade acadêmica como na fonte (departamento no SIGRA, unidade no SIGAA). |
| `ano_ingresso` | `smallint` | não | Ano de ingresso. A fonte não informa o semestre. |
| `forma_ingresso` | `text` | sim | Via de ingresso como na fonte. |
| `cota_ingresso` | `text` | sim | Modalidade de cota no ingresso como na fonte. |
| `data_nascimento` | `date` | sim | Quase-identificador (LGPD). Combinado a curso, sexo e raça/cor, deixa 88,9% dos registros com k = 1. |
| `sexo` | `character(1)` | sim | F ou M. Quase-identificador. |
| `raca_cor` | `text` | sim | Dado pessoal sensível (LGPD, art. 5º, II). |
| `forma_saida` | `text` | sim | Motivo do encerramento do vínculo (SIGRA). Nulo no SIGAA, que não publica o motivo. |
| `data_registro_diploma` | `date` | sim | Registro do diploma (data_registro_livro no SIGRA). Nulo para quem não se formou. |
| `periodo_saida` | `integer` | sim | Período de saída AAAAS publicado pelo SIGRA. Nulo no SIGAA. |
| `nivel_norm` | `text` | não | Nível normalizado; esta tabela só guarda GRADUACAO. |
| `curso_raw` | `text` | sim | Nome do curso sem o padding, ainda com acento. |
| `curso_norm` | `text` | não | Nome do curso normalizado, antes da harmonização canônica (ver gold.regras_harmonizacao_canonicas). |
| `departamento_norm` | `text` | sim | Unidade acadêmica normalizada. |
| `forma_saida_norm` | `text` | sim | Motivo de saída normalizado, base de tipo_saida_grupo. |
| `tipo_saida_grupo` | `text` | não | FORMATURA; EVASAO (saída sem diploma, inclusive mudança de curso: o SIGAA só marca CANCELADO, sem motivo); ATIVO (ativo, formando ou trancado no SIGAA); OUTROS (anulação de registro, falecimento, não cadastrado...). |
| `ano_saida` | `smallint` | sim | Ano da saída: de periodo_saida no SIGRA; estimado pela data do diploma no SIGAA. |
| `semestre_saida` | `smallint` | sim | Semestre da saída: 1, 2 ou 0 (verão, só SIGRA). Estimado pela data do diploma no SIGAA. |
| `semestres_permanencia` | `smallint` | sim | 2 * (ano_saida - ano_ingresso) + semestre_saida. Assume ingresso no 1º semestre (incerteza de ±1 semestre). |
| `semestres_permanencia_valida` | `smallint` | sim | semestres_permanencia quando está entre 1 e 30; nulo caso contrário. |
| `fonte` | `text` | não | Sistema de origem: SIGRA (legado) ou SIGAA (atual). |
| `status_aluno` | `text` | sim | Situação do vínculo no extrato do SIGAA. Nulo no SIGRA. |
| `periodo_saida_estimado` | `boolean` | não | Verdadeiro quando ano/semestre de saída vêm da data de registro do diploma (SIGAA). A regra acerta 94,6% no SIGRA; no calendário da pandemia pode errar em 1 semestre. |
| `_ordem` | `integer` | sim |  |

**Restrições:**

- Chave primária: `PRIMARY KEY (id)`
- Única: `UNIQUE (aluno, opcao, ano_ingresso, periodo_saida)`
- Verificação: `CHECK (((fonte = 'SIGRA'::text) = ((opcao IS NOT NULL) AND (periodo_saida IS NOT NULL))))`
- Verificação: `CHECK ((fonte = ANY (ARRAY['SIGRA'::text, 'SIGAA'::text])))`
- Verificação: `CHECK ((tipo_saida_grupo = ANY (ARRAY['FORMATURA'::text, 'EVASAO'::text, 'ATIVO'::text, 'OUTROS'::text])))`
- Verificação: `CHECK ((nivel_norm = 'GRADUACAO'::text))`
- Verificação: `CHECK ((semestre_saida = ANY (ARRAY[0, 1, 2])))`
- Verificação: `CHECK (((semestres_permanencia_valida >= 1) AND (semestres_permanencia_valida <= 30)))`
- Verificação: `CHECK ((sexo = ANY (ARRAY['F'::bpchar, 'M'::bpchar])))`

### `silver.estrutura_curricular`

Prazos regulamentares consolidados: uma linha por curso canônico, com a mediana dos semestres entre as matrizes do curso e a maior carga horária. Não há CHECK de máximo >= ideal porque a matriz de ENGENHARIA (curso-tronco) publica máximo 3 e ideal 5 — anomalia da fonte, coberta por teste.

**Linhas na última carga:** 112

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

### `silver.estruturas_curriculares`

Prazos e cargas horárias regulamentares por curso canônico (uma linha por matriz consolidada de silver.estrutura_curricular).

**Linhas na última carga:** 112

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `id_estrutura` | `integer (identity)` | não |  |
| `id_curso` | `integer` | não | Curso do catálogo dono da matriz. Pode ter outro nome (a matriz de COMUNICACAO SOCIAL aponta para JORNALISMO). |
| `semestre_minimo` | `numeric(4,1)` | não |  |
| `semestre_ideal` | `numeric(4,1)` | não |  |
| `semestre_maximo` | `numeric(4,1)` | não |  |
| `ch_total_minima` | `integer` | sim |  |
| `cr_total_minimo` | `integer` | sim |  |
| `nome_curso_canonico` | `text` | não | Nome canônico do curso, destino da harmonização SIGRA/SIGAA/PIBIC. Chave natural da gold.dim_curso. |

**Restrições:**

- Chave primária: `PRIMARY KEY (id_estrutura)`
- Única: `UNIQUE (nome_curso_canonico)`
- Única: `UNIQUE (id_curso, semestre_ideal)`
- Chave estrangeira: `FOREIGN KEY (id_curso) REFERENCES silver.cursos(id_curso) ON DELETE RESTRICT`
- Verificação: `CHECK ((ch_total_minima >= 0))`
- Verificação: `CHECK ((semestre_ideal >= semestre_minimo))`
- Verificação: `CHECK ((cr_total_minimo >= 0))`
- Verificação: `CHECK ((semestre_minimo > (0)::numeric))`

### `silver.inep_censo_superior`

Cursos presenciais das federais no Censo 2019, com as taxas por curso que permitem comparar a UnB com as demais. Uma linha por curso (CO_CURSO).

**Linhas na última carga:** 0

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

### `silver.movimentacoes_p2000_2015`

_Sem descrição._

**Linhas na última carga:** 57.982

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `id_vinculo` | `bigint (identity)` | não |  |
| `id_discente` | `bigint` | não |  |
| `id_curso` | `integer` | não |  |
| `id_estrutura` | `integer` | não |  |
| `ano_ingresso` | `smallint` | não |  |
| `semestre_ingresso` | `smallint` | sim |  |
| `forma_saida` | `text` | sim |  |
| `tipo_saida_grupo` | `text` | não |  |
| `ano_saida` | `smallint` | sim |  |
| `semestre_saida` | `smallint` | sim |  |
| `semestres_permanencia` | `smallint` | sim |  |
| `semestres_permanencia_valida` | `smallint` | sim |  |
| `periodo_saida_estimado` | `boolean` | não |  |
| `status_aluno` | `text` | sim |  |
| `fonte` | `text` | não |  |

**Restrições:**

- Chave primária: `PRIMARY KEY (id_vinculo, ano_ingresso)`
- Chave estrangeira: `FOREIGN KEY (id_curso) REFERENCES silver.cursos(id_curso) ON DELETE RESTRICT`
- Chave estrangeira: `FOREIGN KEY (id_discente) REFERENCES silver.discentes(id_discente) ON DELETE RESTRICT`
- Chave estrangeira: `FOREIGN KEY (id_estrutura) REFERENCES silver.estruturas_curriculares(id_estrutura)`
- Verificação: `CHECK ((fonte = ANY (ARRAY['SIGRA'::text, 'SIGAA'::text])))`
- Verificação: `CHECK ((semestre_ingresso = ANY (ARRAY[0, 1, 2])))`
- Verificação: `CHECK ((semestre_saida = ANY (ARRAY[0, 1, 2])))`
- Verificação: `CHECK (((semestres_permanencia_valida >= 1) AND (semestres_permanencia_valida <= 35)))`
- Verificação: `CHECK ((tipo_saida_grupo = ANY (ARRAY['FORMATURA'::text, 'EVASAO'::text, 'ATIVO'::text, 'OUTROS'::text])))`

### `silver.movimentacoes_p2016_2020`

_Sem descrição._

**Linhas na última carga:** 60.105

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `id_vinculo` | `bigint (identity)` | não |  |
| `id_discente` | `bigint` | não |  |
| `id_curso` | `integer` | não |  |
| `id_estrutura` | `integer` | não |  |
| `ano_ingresso` | `smallint` | não |  |
| `semestre_ingresso` | `smallint` | sim |  |
| `forma_saida` | `text` | sim |  |
| `tipo_saida_grupo` | `text` | não |  |
| `ano_saida` | `smallint` | sim |  |
| `semestre_saida` | `smallint` | sim |  |
| `semestres_permanencia` | `smallint` | sim |  |
| `semestres_permanencia_valida` | `smallint` | sim |  |
| `periodo_saida_estimado` | `boolean` | não |  |
| `status_aluno` | `text` | sim |  |
| `fonte` | `text` | não |  |

**Restrições:**

- Chave primária: `PRIMARY KEY (id_vinculo, ano_ingresso)`
- Chave estrangeira: `FOREIGN KEY (id_curso) REFERENCES silver.cursos(id_curso) ON DELETE RESTRICT`
- Chave estrangeira: `FOREIGN KEY (id_discente) REFERENCES silver.discentes(id_discente) ON DELETE RESTRICT`
- Chave estrangeira: `FOREIGN KEY (id_estrutura) REFERENCES silver.estruturas_curriculares(id_estrutura)`
- Verificação: `CHECK ((fonte = ANY (ARRAY['SIGRA'::text, 'SIGAA'::text])))`
- Verificação: `CHECK ((semestre_ingresso = ANY (ARRAY[0, 1, 2])))`
- Verificação: `CHECK ((semestre_saida = ANY (ARRAY[0, 1, 2])))`
- Verificação: `CHECK (((semestres_permanencia_valida >= 1) AND (semestres_permanencia_valida <= 35)))`
- Verificação: `CHECK ((tipo_saida_grupo = ANY (ARRAY['FORMATURA'::text, 'EVASAO'::text, 'ATIVO'::text, 'OUTROS'::text])))`

### `silver.movimentacoes_p2021_atual`

_Sem descrição._

**Linhas na última carga:** 34.593

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `id_vinculo` | `bigint (identity)` | não |  |
| `id_discente` | `bigint` | não |  |
| `id_curso` | `integer` | não |  |
| `id_estrutura` | `integer` | não |  |
| `ano_ingresso` | `smallint` | não |  |
| `semestre_ingresso` | `smallint` | sim |  |
| `forma_saida` | `text` | sim |  |
| `tipo_saida_grupo` | `text` | não |  |
| `ano_saida` | `smallint` | sim |  |
| `semestre_saida` | `smallint` | sim |  |
| `semestres_permanencia` | `smallint` | sim |  |
| `semestres_permanencia_valida` | `smallint` | sim |  |
| `periodo_saida_estimado` | `boolean` | não |  |
| `status_aluno` | `text` | sim |  |
| `fonte` | `text` | não |  |

**Restrições:**

- Chave primária: `PRIMARY KEY (id_vinculo, ano_ingresso)`
- Chave estrangeira: `FOREIGN KEY (id_curso) REFERENCES silver.cursos(id_curso) ON DELETE RESTRICT`
- Chave estrangeira: `FOREIGN KEY (id_discente) REFERENCES silver.discentes(id_discente) ON DELETE RESTRICT`
- Chave estrangeira: `FOREIGN KEY (id_estrutura) REFERENCES silver.estruturas_curriculares(id_estrutura)`
- Verificação: `CHECK ((fonte = ANY (ARRAY['SIGRA'::text, 'SIGAA'::text])))`
- Verificação: `CHECK ((semestre_ingresso = ANY (ARRAY[0, 1, 2])))`
- Verificação: `CHECK ((semestre_saida = ANY (ARRAY[0, 1, 2])))`
- Verificação: `CHECK (((semestres_permanencia_valida >= 1) AND (semestres_permanencia_valida <= 35)))`
- Verificação: `CHECK ((tipo_saida_grupo = ANY (ARRAY['FORMATURA'::text, 'EVASAO'::text, 'ATIVO'::text, 'OUTROS'::text])))`

### `silver.movimentacoes_p_default`

_Sem descrição._

**Linhas na última carga:** 0

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `id_vinculo` | `bigint (identity)` | não |  |
| `id_discente` | `bigint` | não |  |
| `id_curso` | `integer` | não |  |
| `id_estrutura` | `integer` | não |  |
| `ano_ingresso` | `smallint` | não |  |
| `semestre_ingresso` | `smallint` | sim |  |
| `forma_saida` | `text` | sim |  |
| `tipo_saida_grupo` | `text` | não |  |
| `ano_saida` | `smallint` | sim |  |
| `semestre_saida` | `smallint` | sim |  |
| `semestres_permanencia` | `smallint` | sim |  |
| `semestres_permanencia_valida` | `smallint` | sim |  |
| `periodo_saida_estimado` | `boolean` | não |  |
| `status_aluno` | `text` | sim |  |
| `fonte` | `text` | não |  |

**Restrições:**

- Chave primária: `PRIMARY KEY (id_vinculo, ano_ingresso)`
- Chave estrangeira: `FOREIGN KEY (id_curso) REFERENCES silver.cursos(id_curso) ON DELETE RESTRICT`
- Chave estrangeira: `FOREIGN KEY (id_discente) REFERENCES silver.discentes(id_discente) ON DELETE RESTRICT`
- Chave estrangeira: `FOREIGN KEY (id_estrutura) REFERENCES silver.estruturas_curriculares(id_estrutura)`
- Verificação: `CHECK ((fonte = ANY (ARRAY['SIGRA'::text, 'SIGAA'::text])))`
- Verificação: `CHECK ((semestre_ingresso = ANY (ARRAY[0, 1, 2])))`
- Verificação: `CHECK ((semestre_saida = ANY (ARRAY[0, 1, 2])))`
- Verificação: `CHECK (((semestres_permanencia_valida >= 1) AND (semestres_permanencia_valida <= 35)))`
- Verificação: `CHECK ((tipo_saida_grupo = ANY (ARRAY['FORMATURA'::text, 'EVASAO'::text, 'ATIVO'::text, 'OUTROS'::text])))`

### `silver.pibic_bolsistas`

Planos de trabalho de iniciação científica, sem nome do bolsista e com matrícula mascarada. Uma linha por plano. Sem chave natural: a fonte traz 28 linhas idênticas.

**Linhas na última carga:** 12.793

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `id` | `bigint (identity)` | não | Chave substituta. |
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
| `valor_bolsa_anual_estimado` | `numeric(10,2)` | não | Soma, mês a mês de inicio a fim (em geral 12 meses), do valor da bolsa IC em vigor no CNPq: R$ 400 até jan/2023, R$ 700 desde fev/2023 (vigências em data/bronze/cnpq_valor_bolsa_ic.json). Zero para voluntária. |
| `titulo_norm` | `text` | sim | Título do plano de trabalho, normalizado. É o texto vetorizado na busca semântica. |
| `status_norm` | `text` | sim | Situação da avaliação do plano. |

**Restrições:**

- Chave primária: `PRIMARY KEY (id)`
- Verificação: `CHECK ((tipo_bolsa_norm = ANY (ARRAY['REMUNERADA'::text, 'VOLUNTARIA'::text, 'NAO INFORMADO'::text])))`
- Verificação: `CHECK ((valor_bolsa_anual_estimado >= (0)::numeric))`

### `silver.pibic_projetos`

Planos de trabalho de iniciação científica vinculados por chave estrangeira a discentes e cursos.

**Linhas na última carga:** 12.793

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `id_projeto` | `bigint (identity)` | não |  |
| `id_discente` | `bigint` | sim | Sempre nulo: a matrícula do bolsista não é gravada (0010_pibic.sql), então o plano não se liga ao discente. |
| `id_curso` | `integer` | sim | Curso do catálogo dono da matriz do curso canônico do bolsista. Nulo quando o curso do PIBIC não casa com nenhuma matriz. |
| `ano_edital` | `smallint` | não |  |
| `tipo_bolsa` | `text` | não |  |
| `linha_pesquisa` | `text` | sim |  |
| `is_cotista` | `boolean` | não |  |
| `cota_detalhe` | `text` | sim |  |
| `faixa_renda` | `text` | sim |  |
| `valor_bolsa_total` | `numeric(10,2)` | não |  |
| `titulo_pesquisa` | `text` | não |  |
| `status_projeto` | `text` | sim |  |
| `perfil_social_macro` | `text` | sim |  |
| `id_estrutura` | `integer` | sim | Matriz do curso canônico do bolsista, após a harmonização de nomes. Nula quando o curso do PIBIC não casa com nenhuma matriz. |

**Restrições:**

- Chave primária: `PRIMARY KEY (id_projeto)`
- Chave estrangeira: `FOREIGN KEY (id_curso) REFERENCES silver.cursos(id_curso)`
- Chave estrangeira: `FOREIGN KEY (id_discente) REFERENCES silver.discentes(id_discente)`
- Chave estrangeira: `FOREIGN KEY (id_estrutura) REFERENCES silver.estruturas_curriculares(id_estrutura)`
- Verificação: `CHECK ((tipo_bolsa = ANY (ARRAY['REMUNERADA'::text, 'VOLUNTARIA'::text, 'NAO INFORMADO'::text])))`
- Verificação: `CHECK ((valor_bolsa_total >= (0)::numeric))`

### `silver.sigaa_ativos`

Discentes de graduação ativos no período de referência (lista do SIGAA), sem lato sensu nem pós stricto sensu. Um registro por discente, sem identificador.

**Linhas na última carga:** 39.354

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `id` | `bigint (identity)` | não | Chave substituta. |
| `periodo_referencia` | `text` | não | Semestre da lista, tirado do nome do arquivo publicado (ex.: sigaa_ativos_2025_1.csv -> 2025/1). |
| `curso` | `text` | não |  |
| `curso_norm` | `text` | não | Nome do curso sem acento, em maiúsculas, sem o prefixo de curso guarda-chuva (Comunicação Social, Ciências Sociais). |
| `grau` | `text` | não |  |
| `ano_ingresso` | `smallint` | não |  |
| `periodo_ingresso` | `smallint` | não |  |
| `semestres_cursados` | `smallint` | não | Semestres do ingresso até o de referência, contando os dois; o verão (0) conta como 1º semestre. |
| `_ordem` | `integer` | sim |  |

**Restrições:**

- Chave primária: `PRIMARY KEY (id)`
- Verificação: `CHECK ((periodo_ingresso = ANY (ARRAY[0, 1, 2])))`
- Verificação: `CHECK ((periodo_referencia ~ '^\d{4}/[12]$'::text))`
- Verificação: `CHECK ((semestres_cursados >= 1))`

## Esquema `gold`

### `gold.ativos_hoje_cursos_unb`

Discentes de graduação ativos no semestre mais recente publicado pelo SIGAA (lista de ativos), por curso canônico, todas as coortes. Cursos-tronco e cursos sem estrutura curricular publicada ficam de fora. Só entram cursos com 5 ou mais ativos (k-anonimato).

**Linhas na última carga:** 95

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `curso` | `text` | não | Nome canônico do curso, o mesmo de gold.retencao_cursos_unb. |
| `periodo_referencia` | `text` | não | Semestre da lista de ativos usada (ex.: 2025/1). |
| `semestre_ideal_previsto` | `numeric(4,1)` | não | Duração ideal da matriz curricular, em semestres. |
| `semestre_maximo_previsto` | `numeric(4,1)` | não | Prazo máximo de integralização, em semestres. |
| `total_ativos_hoje` | `integer` | não | Discentes de graduação na lista de ativos do SIGAA. |
| `ativos_acima_prazo_ideal` | `integer` | não | Discentes que já cursaram mais semestres que a duração ideal (semestres contados a partir do ano e do semestre de ingresso). |
| `ativos_acima_prazo_maximo` | `integer` | não | Discentes que já passaram do prazo máximo de integralização. |
| `pct_acima_prazo_ideal` | `numeric(5,2)` | não | ativos_acima_prazo_ideal / total_ativos_hoje * 100. |
| `_ordem` | `integer` | sim |  |

**Restrições:**

- Chave primária: `PRIMARY KEY (curso)`
- Verificação: `CHECK ((ativos_acima_prazo_ideal >= 0))`
- Verificação: `CHECK (((ativos_acima_prazo_maximo >= 0) AND (ativos_acima_prazo_maximo <= ativos_acima_prazo_ideal)))`
- Verificação: `CHECK ((ativos_acima_prazo_ideal <= total_ativos_hoje))`
- Verificação: `CHECK (((pct_acima_prazo_ideal >= (0)::numeric) AND (pct_acima_prazo_ideal <= (100)::numeric)))`
- Verificação: `CHECK ((periodo_referencia ~ '^\d{4}/[12]$'::text))`
- Verificação: `CHECK ((total_ativos_hoje >= 5))`

### `gold.dim_campus`

Dimensão geográfica dos campi da UnB.

**Linhas na última carga:** 5

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `sk_campus` | `integer (identity)` | não |  |
| `campus` | `text` | não |  |
| `regiao_admin` | `text` | não |  |
| `municipio` | `text` | não |  |

**Restrições:**

- Chave primária: `PRIMARY KEY (sk_campus)`
- Única: `UNIQUE (campus)`

### `gold.dim_curso`

Dimensão de cursos canônicos de graduação. Chave natural nome_curso: a chave substituta sk_curso não muda quando entra curso novo.

**Linhas na última carga:** 118

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `sk_curso` | `integer (identity)` | não |  |
| `id_curso_origem` | `integer` | sim | id_curso do catálogo dono da matriz (silver.estruturas_curriculares). |
| `nome_curso` | `text` | não |  |
| `grau_academico` | `text` | não |  |
| `categoria_grau` | `text` | não |  |
| `area_conhecimento` | `text` | não |  |
| `departamento` | `text` | sim |  |
| `is_tronco_abi` | `boolean` | não |  |

**Restrições:**

- Chave primária: `PRIMARY KEY (sk_curso)`
- Única: `UNIQUE (nome_curso)`
- Verificação: `CHECK ((categoria_grau = ANY (ARRAY['BACHARELADO'::text, 'LICENCIATURA'::text, 'MISTO'::text])))`

### `gold.dim_perfil_social`

Dimensão social e de ações afirmativas: combinações distintas de perfil observadas em silver.pibic_projetos.

**Linhas na última carga:** 10

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `sk_perfil` | `integer (identity)` | não |  |
| `perfil_macro` | `text` | não |  |
| `categoria_cota` | `text` | não |  |
| `faixa_renda` | `text` | sim |  |
| `is_cotista` | `boolean` | não |  |

**Restrições:**

- Chave primária: `PRIMARY KEY (sk_perfil)`
- Única: `UNIQUE NULLS NOT DISTINCT (perfil_macro, categoria_cota, faixa_renda, is_cotista)`

### `gold.dim_tempo`

Dimensão temporal acadêmica com granularidade semestral.

**Linhas na última carga:** 34

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `sk_tempo` | `integer` | não |  |
| `ano` | `smallint` | não |  |
| `semestre` | `smallint` | não |  |
| `rotulo` | `text` | não |  |
| `decada` | `smallint` | não |  |

**Restrições:**

- Chave primária: `PRIMARY KEY (sk_tempo)`
- Verificação: `CHECK ((semestre = ANY (ARRAY[1, 2])))`

### `gold.fato_alunos_ativos`

Discentes ativos no semestre de referência por curso canônico, a partir de gold.ativos_hoje_cursos_unb (lista de ativos do SIGAA).

**Linhas na última carga:** 95

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `id_fato_ativo` | `bigint (identity)` | não |  |
| `sk_curso` | `integer` | não |  |
| `sk_tempo_referencia` | `integer` | não |  |
| `total_ativos` | `integer` | não |  |
| `ativos_acima_prazo_ideal` | `integer` | não |  |
| `ativos_acima_prazo_maximo` | `integer` | não |  |
| `pct_acima_prazo_ideal` | `numeric(5,2)` | não |  |
| `atualizado_em` | `timestamp with time zone` | não |  |

**Restrições:**

- Chave primária: `PRIMARY KEY (id_fato_ativo)`
- Única: `UNIQUE (sk_curso)`
- Chave estrangeira: `FOREIGN KEY (sk_curso) REFERENCES gold.dim_curso(sk_curso)`
- Chave estrangeira: `FOREIGN KEY (sk_tempo_referencia) REFERENCES gold.dim_tempo(sk_tempo)`
- Verificação: `CHECK ((ativos_acima_prazo_ideal >= 0))`
- Verificação: `CHECK ((ativos_acima_prazo_maximo >= 0))`
- Verificação: `CHECK (((pct_acima_prazo_ideal >= (0)::numeric) AND (pct_acima_prazo_ideal <= (100)::numeric)))`
- Verificação: `CHECK ((total_ativos >= 5))`

### `gold.fato_pibic_perfil`

Planos de iniciação científica por curso canônico e perfil social do bolsista (todos os editais). Só entram grupos com 5 ou mais planos (k-anonimato).

**Linhas na última carga:** 286

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `id_fato` | `bigint (identity)` | não |  |
| `sk_curso` | `integer` | não |  |
| `sk_perfil` | `integer` | não |  |
| `total_projetos` | `integer` | não | Planos de trabalho de IC do grupo. Mínimo 5. |
| `total_remuneradas` | `integer` | não | Planos com bolsa remunerada (PIBIC). |
| `total_voluntarias` | `integer` | não | Planos voluntários (PIVIC). |
| `valor_total_investido` | `numeric(14,2)` | não | Soma estimada das bolsas do grupo, em R$. |
| `atualizado_em` | `timestamp with time zone` | não |  |

**Restrições:**

- Chave primária: `PRIMARY KEY (id_fato)`
- Única: `UNIQUE (sk_curso, sk_perfil)`
- Chave estrangeira: `FOREIGN KEY (sk_curso) REFERENCES gold.dim_curso(sk_curso)`
- Chave estrangeira: `FOREIGN KEY (sk_perfil) REFERENCES gold.dim_perfil_social(sk_perfil)`
- Verificação: `CHECK (((total_remuneradas + total_voluntarias) <= total_projetos))`
- Verificação: `CHECK ((total_projetos >= 5))`
- Verificação: `CHECK ((total_remuneradas >= 0))`
- Verificação: `CHECK ((total_voluntarias >= 0))`
- Verificação: `CHECK ((valor_total_investido >= (0)::numeric))`

### `gold.fato_retencao_curso`

Retenção por curso canônico, calculada a partir de silver.movimentacoes_vinculos sobre as coortes maduras, com k >= 5: contagens, taxas, % no tempo ideal, atraso médio, IRC e classificação (mesmas regras de build_gold.py).

**Linhas na última carga:** 95

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `id_fato` | `bigint (identity)` | não |  |
| `sk_curso` | `integer` | não |  |
| `sk_campus` | `integer` | não |  |
| `total_ingressantes` | `integer` | não |  |
| `total_formados` | `integer` | não |  |
| `total_evadidos` | `integer` | não |  |
| `total_ainda_ativos` | `integer` | não |  |
| `taxa_formatura_pct` | `numeric(5,2)` | sim |  |
| `taxa_evasao_pct` | `numeric(5,2)` | sim |  |
| `formados_tempo_ideal_pct` | `numeric(5,2)` | sim |  |
| `atraso_medio_semestres` | `numeric(5,2)` | sim |  |
| `indice_retencao_critica` | `numeric(4,1)` | sim |  |
| `classificacao_retencao` | `text` | sim |  |
| `atualizado_em` | `timestamp with time zone` | não |  |

**Restrições:**

- Chave primária: `PRIMARY KEY (id_fato)`
- Única: `UNIQUE (sk_curso, sk_campus)`
- Chave estrangeira: `FOREIGN KEY (sk_campus) REFERENCES gold.dim_campus(sk_campus)`
- Chave estrangeira: `FOREIGN KEY (sk_curso) REFERENCES gold.dim_curso(sk_curso)`
- Verificação: `CHECK ((classificacao_retencao = ANY (ARRAY['RETENÇÃO CRÍTICA'::text, 'RETENÇÃO ALTA'::text, 'RETENÇÃO MÉDIA'::text, 'RETENÇÃO BAIXA'::text])))`
- Verificação: `CHECK (((formados_tempo_ideal_pct >= (0)::numeric) AND (formados_tempo_ideal_pct <= (100)::numeric)))`
- Verificação: `CHECK (((indice_retencao_critica >= (0)::numeric) AND (indice_retencao_critica <= (100)::numeric)))`
- Verificação: `CHECK (((taxa_evasao_pct >= (0)::numeric) AND (taxa_evasao_pct <= (100)::numeric)))`
- Verificação: `CHECK (((taxa_formatura_pct >= (0)::numeric) AND (taxa_formatura_pct <= (100)::numeric)))`
- Verificação: `CHECK ((total_ainda_ativos >= 0))`
- Verificação: `CHECK ((total_evadidos >= 0))`
- Verificação: `CHECK ((total_formados >= 0))`
- Verificação: `CHECK ((total_ingressantes >= 5))`

### `gold.inep_benchmark_cursos_unb`

Cada curso da UnB comparado com o mesmo curso nas demais universidades federais (Censo INEP 2019). Uma linha por curso da UnB com 50 ou mais matrículas.

**Linhas na última carga:** 0

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

**Linhas na última carga:** 72

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `origem_sigra` | `text` | não | Nome normalizado do curso na origem (SIGRA, SIGAA ou PIBIC). |
| `destino_estrutura` | `text` | não | Nome da matriz em silver.estrutura_curricular para o qual a origem é mapeada. |
| `categoria` | `text` | sim | Motivo agrupado da regra (Correção de Typo no Portal, Habilitação Legada, Engenharias...). |
| `justificativa` | `text` | sim | Explicação da equivalência, em texto. |
| `discentes_impactados` | `integer` | não | Vínculos de SIGRA + SIGAA reclassificados por esta regra. |
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

Retenção, formatura e evasão por curso, sobre as coortes de ingresso com pelo menos 8 anos de acompanhamento (ver ANOS_MATURACAO_COORTE em build_gold.py). Uma linha por curso canônico de graduação; cursos com bacharelado e licenciatura sob o mesmo nome ficam numa linha só (categoria_grau = MISTO). Só entram cursos com 5 ou mais discentes.

**Linhas na última carga:** 95

| Coluna | Tipo | Nulo | Descrição |
| :--- | :--- | :---: | :--- |
| `curso` | `text` | não | Nome canônico do curso após a harmonização SIGRA/SIGAA -> matriz curricular (sem acento, maiúsculas). |
| `departamento` | `text` | sim | Departamento de vinculação, como registrado no sistema acadêmico. |
| `campus` | `text` | sim | Campus de oferta; MULTICAMPUS quando o mesmo nome é oferecido em mais de um campus. |
| `turno` | `text` | sim | DIURNO, NOTURNO, INTEGRAL ou DIURNO E NOTURNO (nome com as duas ofertas; nenhuma fonte liga o discente à oferta). Matutino e vespertino são unificados em DIURNO. |
| `area_conhecimento` | `text` | sim | Grande Área CNPq/MEC. |
| `grau_academico` | `text` | sim | Titulação literal conferida ao egresso, ou MISTO (BACHARELADO + LICENCIATURA). |
| `categoria_grau` | `text` | sim | BACHARELADO (inclui titulações profissionais), LICENCIATURA ou MISTO. |
| `semestre_minimo_previsto` | `numeric(4,1)` | sim | Prazo mínimo regulamentar, em semestres. |
| `semestre_ideal_previsto` | `numeric(4,1)` | sim | Duração ideal da matriz curricular, em semestres. |
| `semestre_maximo_previsto` | `numeric(4,1)` | sim | Prazo máximo antes do jubilamento, em semestres. |
| `carga_horaria_minima` | `integer` | sim | Carga horária total mínima para conclusão, em horas. |
| `total_discentes_registrados` | `integer` | não | Vínculos do curso nas coortes analisadas (SIGRA + SIGAA). Mínimo 5 (supressão de grupos pequenos, k-anonimato). |
| `total_formados` | `integer` | não | Vínculos com saída por formatura. |
| `total_evadidos_desligados` | `integer` | não | Vínculos encerrados sem diploma: abandono, jubilamento, desligamento, mudança de curso ou cancelamento no SIGAA. |
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
| `total_ainda_ativos` | `integer` | não | Vínculos das coortes analisadas ainda ativos ou trancados no extrato do SIGAA. |
| `_ordem` | `integer` | sim | Ordem de gravação: do maior para o menor índice de retenção crítica. |

**Restrições:**

- Chave primária: `PRIMARY KEY (curso)`
- Verificação: `CHECK ((categoria_grau = ANY (ARRAY['BACHARELADO'::text, 'LICENCIATURA'::text, 'MISTO'::text])))`
- Verificação: `CHECK (((total_formados + total_evadidos_desligados) <= total_discentes_registrados))`
- Verificação: `CHECK ((((total_formados + total_evadidos_desligados) + total_ainda_ativos) <= total_discentes_registrados))`
- Verificação: `CHECK ((classificacao_retencao = ANY (ARRAY['RETENÇÃO CRÍTICA'::text, 'RETENÇÃO ALTA'::text, 'RETENÇÃO MÉDIA'::text, 'RETENÇÃO BAIXA'::text])))`
- Verificação: `CHECK (((formados_acima_ideal_pct >= (0)::numeric) AND (formados_acima_ideal_pct <= (100)::numeric)))`
- Verificação: `CHECK (((formados_limite_maximo_pct >= (0)::numeric) AND (formados_limite_maximo_pct <= (100)::numeric)))`
- Verificação: `CHECK (((formados_tempo_ideal_pct >= (0)::numeric) AND (formados_tempo_ideal_pct <= (100)::numeric)))`
- Verificação: `CHECK (((formados_tempo_minimo_pct >= (0)::numeric) AND (formados_tempo_minimo_pct <= (100)::numeric)))`
- Verificação: `CHECK (((indice_retencao_critica >= (0)::numeric) AND (indice_retencao_critica <= (100)::numeric)))`
- Verificação: `CHECK (((taxa_evasao_pct >= (0)::numeric) AND (taxa_evasao_pct <= (100)::numeric)))`
- Verificação: `CHECK (((taxa_formatura_pct >= (0)::numeric) AND (taxa_formatura_pct <= (100)::numeric)))`
- Verificação: `CHECK ((total_ainda_ativos >= 0))`
- Verificação: `CHECK ((total_discentes_registrados >= 5))`
- Verificação: `CHECK ((total_evadidos_desligados >= 0))`
- Verificação: `CHECK ((total_formados >= 0))`
- Verificação: `CHECK ((turno = ANY (ARRAY['DIURNO'::text, 'NOTURNO'::text, 'INTEGRAL'::text, 'DIURNO E NOTURNO'::text])))`

## Esquema `busca`

### `busca.documentos`

Um documento de texto por entidade pesquisável: cada curso da gold, cada plano de IC distinto e cada seção da documentação em docs/. Não contém nome nem matrícula.

**Linhas na última carga:** variável (depende de `VETORIZAR_TIPOS`)

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
