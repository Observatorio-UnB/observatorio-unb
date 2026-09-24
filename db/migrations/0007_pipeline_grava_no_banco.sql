-- O pipeline passa a gravar cada camada direto no banco (sem CSV intermediário).
--
-- 1. `_ordem` preserva a ordem em que as linhas foram gravadas. Parte da lógica da
--    silver e da gold agrega com first() e iloc[0] (ex.: o primeiro registro do catálogo
--    para cada nome de curso), então ler a camada fora de ordem mudaria o resultado.
-- 2. bronze.ingestoes guarda a procedência de cada arquivo baixado: sem o arquivo em
--    disco, é a única evidência de encoding, separador e integridade da fonte.
-- 3. Tabelas do Censo da Educação Superior (INEP), usadas no benchmark nacional.

ALTER TABLE bronze.sigra_discentes                ADD COLUMN _ordem INTEGER;
ALTER TABLE bronze.estrutura_curricular           ADD COLUMN _ordem INTEGER;
ALTER TABLE bronze.cursos_graduacao               ADD COLUMN _ordem INTEGER;
ALTER TABLE bronze.bolsistas_iniciacao_cientifica ADD COLUMN _ordem INTEGER;
ALTER TABLE silver.cursos_graduacao               ADD COLUMN _ordem INTEGER;
ALTER TABLE silver.estrutura_curricular           ADD COLUMN _ordem INTEGER;
ALTER TABLE gold.retencao_cursos_unb              ADD COLUMN _ordem INTEGER;
ALTER TABLE gold.pibic_social_unb                 ADD COLUMN _ordem INTEGER;
ALTER TABLE gold.regras_harmonizacao_canonicas    ADD COLUMN _ordem INTEGER;

COMMENT ON COLUMN bronze.sigra_discentes._ordem IS 'Posição do registro no arquivo de origem (1 = primeiro registro depois do cabeçalho).';
COMMENT ON COLUMN bronze.estrutura_curricular._ordem IS 'Posição do registro no arquivo de origem (1 = primeiro registro depois do cabeçalho).';
COMMENT ON COLUMN bronze.cursos_graduacao._ordem IS 'Posição do registro no arquivo de origem (1 = primeiro registro depois do cabeçalho).';
COMMENT ON COLUMN bronze.bolsistas_iniciacao_cientifica._ordem IS 'Posição do registro no arquivo de origem (1 = primeiro registro depois do cabeçalho).';
COMMENT ON COLUMN silver.cursos_graduacao._ordem IS 'Ordem de gravação. A gold pega o primeiro registro de cada nome de curso, então a ordem faz parte do resultado.';
COMMENT ON COLUMN silver.estrutura_curricular._ordem IS 'Ordem de gravação (alfabética por curso).';
COMMENT ON COLUMN gold.retencao_cursos_unb._ordem IS 'Ordem de gravação: do maior para o menor índice de retenção crítica.';
COMMENT ON COLUMN gold.pibic_social_unb._ordem IS 'Ordem de gravação: do maior para o menor número de planos.';
COMMENT ON COLUMN gold.regras_harmonizacao_canonicas._ordem IS 'Ordem de gravação: da regra que mais reclassifica vínculos para a que menos reclassifica.';

CREATE TABLE bronze.ingestoes (
  tabela             TEXT PRIMARY KEY,
  fonte              TEXT NOT NULL,
  pacote             TEXT,
  recurso_url        TEXT NOT NULL,
  baixado_em         TIMESTAMPTZ NOT NULL DEFAULT now(),
  tamanho_bytes      BIGINT NOT NULL CHECK (tamanho_bytes > 0),
  sha256             TEXT NOT NULL,
  encoding           TEXT NOT NULL,
  separador          TEXT NOT NULL,
  registros          INTEGER NOT NULL CHECK (registros >= 0),
  utf8_valido        BOOLEAN,
  linha_invalida     INTEGER,
  evidencia_encoding TEXT,
  metadados          JSONB
);
COMMENT ON TABLE bronze.ingestoes IS
  'Procedência do último download de cada tabela bronze: de onde veio, quando, com que encoding e separador, e o hash do arquivo. Substitui o arquivo bruto em disco como evidência da auditoria de qualidade.';
COMMENT ON COLUMN bronze.ingestoes.tabela IS 'Tabela bronze alimentada pelo arquivo.';
COMMENT ON COLUMN bronze.ingestoes.fonte IS 'dados.unb.br (API CKAN) ou INEP.';
COMMENT ON COLUMN bronze.ingestoes.pacote IS 'Identificador do pacote no CKAN (vazio para o INEP).';
COMMENT ON COLUMN bronze.ingestoes.recurso_url IS 'URL de onde o arquivo foi baixado.';
COMMENT ON COLUMN bronze.ingestoes.baixado_em IS 'Momento do download (hora de ingestão).';
COMMENT ON COLUMN bronze.ingestoes.tamanho_bytes IS 'Tamanho do arquivo baixado, em bytes.';
COMMENT ON COLUMN bronze.ingestoes.sha256 IS 'Hash do arquivo baixado. Muda quando a fonte republica o dado.';
COMMENT ON COLUMN bronze.ingestoes.encoding IS 'Encoding usado para decodificar o arquivo (utf-8 ou latin-1).';
COMMENT ON COLUMN bronze.ingestoes.separador IS 'Separador de colunas do CSV de origem.';
COMMENT ON COLUMN bronze.ingestoes.registros IS 'Registros gravados na tabela bronze.';
COMMENT ON COLUMN bronze.ingestoes.utf8_valido IS 'Falso quando alguma das 15 primeiras linhas do arquivo não decodifica como UTF-8. Nulo quando não verificado (arquivo dentro de zip).';
COMMENT ON COLUMN bronze.ingestoes.linha_invalida IS 'Primeira linha do arquivo que não decodifica como UTF-8.';
COMMENT ON COLUMN bronze.ingestoes.evidencia_encoding IS 'O byte inválido em UTF-8 e o início da linha em que aparece.';
COMMENT ON COLUMN bronze.ingestoes.metadados IS 'Resposta de package_show da API CKAN (título, recursos, datas de atualização).';

-- Recorte do Censo da Educação Superior 2019: cursos presenciais de universidades
-- federais. Os nomes das colunas do INEP ficam em maiúsculas, entre aspas, como no
-- dicionário de dados oficial. Diferente das tabelas bronze da UnB, esta é tipada: o
-- arquivo do INEP é filtrado na ingestão e só entram contagens e códigos.
CREATE TABLE bronze.inep_censo_superior_federais (
  "NU_ANO_CENSO"                SMALLINT NOT NULL,
  "CO_IES"                      INTEGER NOT NULL,
  "NO_CURSO"                    TEXT NOT NULL,
  "CO_CURSO"                    BIGINT NOT NULL,
  "TP_GRAU_ACADEMICO"           SMALLINT,
  "TP_MODALIDADE_ENSINO"        SMALLINT NOT NULL,
  "QT_VG_TOTAL"                 INTEGER,
  "QT_INSCRITO_TOTAL"           INTEGER,
  "QT_ING"                      INTEGER,
  "QT_MAT"                      INTEGER,
  "QT_CONC"                     INTEGER,
  "QT_SIT_TRANCADA"             INTEGER,
  "QT_SIT_DESVINCULADO"         INTEGER,
  "QT_SIT_TRANSFERIDO"          INTEGER,
  "TP_ORGANIZACAO_ACADEMICA"    SMALLINT NOT NULL,
  "TP_CATEGORIA_ADMINISTRATIVA" SMALLINT NOT NULL,
  "NO_IES"                      TEXT NOT NULL,
  _ordem                        INTEGER,
  _carregado_em                 TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE bronze.inep_censo_superior_federais IS
  'Censo da Educação Superior 2019 (INEP), recorte de cursos presenciais de universidades públicas federais. Uma linha por curso. Dado agregado por curso, sem registro individual de discente.';
COMMENT ON COLUMN bronze.inep_censo_superior_federais."NU_ANO_CENSO" IS 'Ano de referência do Censo.';
COMMENT ON COLUMN bronze.inep_censo_superior_federais."CO_IES" IS 'Código da instituição no INEP (UnB = 2).';
COMMENT ON COLUMN bronze.inep_censo_superior_federais."NO_CURSO" IS 'Nome do curso na nomenclatura do INEP.';
COMMENT ON COLUMN bronze.inep_censo_superior_federais."CO_CURSO" IS 'Código do curso no INEP.';
COMMENT ON COLUMN bronze.inep_censo_superior_federais."TP_GRAU_ACADEMICO" IS 'Grau (1 bacharelado, 2 licenciatura, 3 tecnológico...). Nulo em 175 cursos na fonte.';
COMMENT ON COLUMN bronze.inep_censo_superior_federais."TP_MODALIDADE_ENSINO" IS 'Modalidade; o recorte só tem 1 (presencial).';
COMMENT ON COLUMN bronze.inep_censo_superior_federais."QT_VG_TOTAL" IS 'Vagas totais oferecidas.';
COMMENT ON COLUMN bronze.inep_censo_superior_federais."QT_INSCRITO_TOTAL" IS 'Inscritos no processo seletivo.';
COMMENT ON COLUMN bronze.inep_censo_superior_federais."QT_ING" IS 'Ingressantes no ano.';
COMMENT ON COLUMN bronze.inep_censo_superior_federais."QT_MAT" IS 'Matrículas no ano.';
COMMENT ON COLUMN bronze.inep_censo_superior_federais."QT_CONC" IS 'Concluintes no ano.';
COMMENT ON COLUMN bronze.inep_censo_superior_federais."QT_SIT_TRANCADA" IS 'Matrículas trancadas.';
COMMENT ON COLUMN bronze.inep_censo_superior_federais."QT_SIT_DESVINCULADO" IS 'Matrículas desvinculadas do curso.';
COMMENT ON COLUMN bronze.inep_censo_superior_federais."QT_SIT_TRANSFERIDO" IS 'Matrículas transferidas para outro curso da mesma instituição.';
COMMENT ON COLUMN bronze.inep_censo_superior_federais."TP_ORGANIZACAO_ACADEMICA" IS 'Organização acadêmica; o recorte só tem 1 (universidade).';
COMMENT ON COLUMN bronze.inep_censo_superior_federais."TP_CATEGORIA_ADMINISTRATIVA" IS 'Categoria administrativa; o recorte só tem 1 (pública federal).';
COMMENT ON COLUMN bronze.inep_censo_superior_federais."NO_IES" IS 'Nome da instituição.';
COMMENT ON COLUMN bronze.inep_censo_superior_federais._ordem IS 'Posição do registro no recorte gravado.';
COMMENT ON COLUMN bronze.inep_censo_superior_federais._carregado_em IS 'Momento em que a linha foi carregada no banco.';

CREATE TABLE silver.inep_censo_superior (
  "NU_ANO_CENSO"          SMALLINT NOT NULL,
  "CO_IES"                INTEGER NOT NULL,
  "NO_IES"                TEXT NOT NULL,
  is_unb                  BOOLEAN NOT NULL,
  "CO_CURSO"              BIGINT PRIMARY KEY,
  "NO_CURSO"              TEXT NOT NULL,
  curso_inep_norm         TEXT NOT NULL,
  "QT_VG_TOTAL"           INTEGER,
  "QT_INSCRITO_TOTAL"     INTEGER,
  "QT_ING"                INTEGER,
  "QT_MAT"                INTEGER,
  "QT_CONC"               INTEGER,
  "QT_SIT_TRANCADA"       INTEGER,
  "QT_SIT_DESVINCULADO"   INTEGER,
  taxa_trancamento_pct    NUMERIC(6,2),
  taxa_desvinculacao_pct  NUMERIC(6,2),
  concorrencia_vestibular NUMERIC(8,2),
  _ordem                  INTEGER
);
COMMENT ON TABLE silver.inep_censo_superior IS
  'Cursos presenciais das federais no Censo 2019, com as taxas por curso que permitem comparar a UnB com as demais. Uma linha por curso (CO_CURSO).';
COMMENT ON COLUMN silver.inep_censo_superior."NU_ANO_CENSO" IS 'Ano de referência do Censo.';
COMMENT ON COLUMN silver.inep_censo_superior."CO_IES" IS 'Código da instituição no INEP (UnB = 2).';
COMMENT ON COLUMN silver.inep_censo_superior."NO_IES" IS 'Nome da instituição.';
COMMENT ON COLUMN silver.inep_censo_superior.is_unb IS 'Verdadeiro para cursos da UnB (CO_IES = 2).';
COMMENT ON COLUMN silver.inep_censo_superior."CO_CURSO" IS 'Código do curso no INEP.';
COMMENT ON COLUMN silver.inep_censo_superior."NO_CURSO" IS 'Nome do curso na nomenclatura do INEP. Chave de comparação entre instituições.';
COMMENT ON COLUMN silver.inep_censo_superior.curso_inep_norm IS 'Nome do curso normalizado (sem acento, maiúsculas).';
COMMENT ON COLUMN silver.inep_censo_superior."QT_VG_TOTAL" IS 'Vagas totais oferecidas.';
COMMENT ON COLUMN silver.inep_censo_superior."QT_INSCRITO_TOTAL" IS 'Inscritos no processo seletivo.';
COMMENT ON COLUMN silver.inep_censo_superior."QT_ING" IS 'Ingressantes no ano.';
COMMENT ON COLUMN silver.inep_censo_superior."QT_MAT" IS 'Matrículas no ano.';
COMMENT ON COLUMN silver.inep_censo_superior."QT_CONC" IS 'Concluintes no ano.';
COMMENT ON COLUMN silver.inep_censo_superior."QT_SIT_TRANCADA" IS 'Matrículas trancadas.';
COMMENT ON COLUMN silver.inep_censo_superior."QT_SIT_DESVINCULADO" IS 'Matrículas desvinculadas do curso.';
COMMENT ON COLUMN silver.inep_censo_superior.taxa_trancamento_pct IS 'QT_SIT_TRANCADA / QT_MAT x 100. Situação apurada no ano-censo, não por coorte.';
COMMENT ON COLUMN silver.inep_censo_superior.taxa_desvinculacao_pct IS 'QT_SIT_DESVINCULADO / QT_MAT x 100. Não é comparável com a taxa de evasão do SIGRA.';
COMMENT ON COLUMN silver.inep_censo_superior.concorrencia_vestibular IS 'QT_INSCRITO_TOTAL / QT_VG_TOTAL (inscritos por vaga).';
COMMENT ON COLUMN silver.inep_censo_superior._ordem IS 'Ordem de gravação.';

CREATE TABLE gold.inep_benchmark_cursos_unb (
  curso_inep                         TEXT PRIMARY KEY,
  qt_matriculas_unb                  INTEGER NOT NULL CHECK (qt_matriculas_unb >= 0),
  qt_ingressantes_unb                INTEGER,
  qt_concluintes_unb                 INTEGER,
  qt_trancadas_unb                   INTEGER,
  qt_desvinculados_unb               INTEGER,
  qt_vagas_unb                       INTEGER,
  qt_inscritos_unb                   INTEGER,
  taxa_trancamento_unb_pct           NUMERIC(6,2),
  taxa_desvinculacao_unb_pct         NUMERIC(6,2),
  concorrencia_vestibular_unb        NUMERIC(8,2),
  n_ies_comparadas                   INTEGER,
  mediana_trancamento_federais_pct   NUMERIC(6,2),
  mediana_desvinculacao_federais_pct NUMERIC(6,2),
  gap_trancamento_pp                 NUMERIC(6,2),
  gap_desvinculacao_pp               NUMERIC(6,2),
  razao_trancamento                  NUMERIC(8,2),
  razao_desvinculacao                NUMERIC(8,2),
  _ordem                             INTEGER
);
COMMENT ON TABLE gold.inep_benchmark_cursos_unb IS
  'Cada curso da UnB comparado com o mesmo curso nas demais universidades federais (Censo INEP 2019). Uma linha por curso da UnB com 50 ou mais matrículas.';
COMMENT ON COLUMN gold.inep_benchmark_cursos_unb.curso_inep IS 'Nome do curso na nomenclatura do INEP.';
COMMENT ON COLUMN gold.inep_benchmark_cursos_unb.qt_matriculas_unb IS 'Matrículas da UnB no curso, somando as ofertas (turnos e campi).';
COMMENT ON COLUMN gold.inep_benchmark_cursos_unb.qt_ingressantes_unb IS 'Ingressantes da UnB no curso.';
COMMENT ON COLUMN gold.inep_benchmark_cursos_unb.qt_concluintes_unb IS 'Concluintes da UnB no curso.';
COMMENT ON COLUMN gold.inep_benchmark_cursos_unb.qt_trancadas_unb IS 'Matrículas trancadas na UnB.';
COMMENT ON COLUMN gold.inep_benchmark_cursos_unb.qt_desvinculados_unb IS 'Matrículas desvinculadas na UnB.';
COMMENT ON COLUMN gold.inep_benchmark_cursos_unb.qt_vagas_unb IS 'Vagas oferecidas pela UnB.';
COMMENT ON COLUMN gold.inep_benchmark_cursos_unb.qt_inscritos_unb IS 'Inscritos no processo seletivo da UnB.';
COMMENT ON COLUMN gold.inep_benchmark_cursos_unb.taxa_trancamento_unb_pct IS 'qt_trancadas_unb / qt_matriculas_unb x 100.';
COMMENT ON COLUMN gold.inep_benchmark_cursos_unb.taxa_desvinculacao_unb_pct IS 'qt_desvinculados_unb / qt_matriculas_unb x 100.';
COMMENT ON COLUMN gold.inep_benchmark_cursos_unb.concorrencia_vestibular_unb IS 'Inscritos por vaga na UnB.';
COMMENT ON COLUMN gold.inep_benchmark_cursos_unb.n_ies_comparadas IS 'Outras federais que oferecem o curso. Nulo quando nenhuma oferece.';
COMMENT ON COLUMN gold.inep_benchmark_cursos_unb.mediana_trancamento_federais_pct IS 'Mediana da taxa de trancamento do curso nas demais federais.';
COMMENT ON COLUMN gold.inep_benchmark_cursos_unb.mediana_desvinculacao_federais_pct IS 'Mediana da taxa de desvinculação do curso nas demais federais.';
COMMENT ON COLUMN gold.inep_benchmark_cursos_unb.gap_trancamento_pp IS 'Trancamento da UnB menos a mediana das federais, em pontos percentuais.';
COMMENT ON COLUMN gold.inep_benchmark_cursos_unb.gap_desvinculacao_pp IS 'Desvinculação da UnB menos a mediana das federais, em pontos percentuais.';
COMMENT ON COLUMN gold.inep_benchmark_cursos_unb.razao_trancamento IS 'Trancamento da UnB dividido pela mediana das federais (1,9 = quase o dobro).';
COMMENT ON COLUMN gold.inep_benchmark_cursos_unb.razao_desvinculacao IS 'Desvinculação da UnB dividida pela mediana das federais.';
COMMENT ON COLUMN gold.inep_benchmark_cursos_unb._ordem IS 'Ordem de gravação: do curso com mais para o com menos matrículas.';
