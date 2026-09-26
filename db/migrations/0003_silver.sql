-- Camada silver: saída tipada de src/pipeline/transform_silver.py.
-- As restrições abaixo são o contrato da camada: se a fonte mudar e violar uma
-- delas, a carga falha em vez de propagar o erro para a gold.

CREATE TABLE silver.cursos_graduacao (
  id_curso                 INTEGER PRIMARY KEY,
  nome                     TEXT NOT NULL,
  id_coordenador           INTEGER,
  coordenador              TEXT,
  situacao_curso           TEXT,
  nivel_ensino             TEXT,
  grau_academico           TEXT,
  modalidade_educacao      TEXT,
  area_conhecimento        TEXT,
  tipo_oferta              TEXT,
  turno                    TEXT,
  tipo_ciclo_formacao      TEXT,
  municipio                TEXT,
  campus                   TEXT,
  id_unidade_responsavel   INTEGER,
  unidade_responsavel      TEXT,
  website                  TEXT,
  data_funcionamento       DATE,
  codigo_inep              INTEGER,
  dou                      DATE,
  portaria_reconhecimento  INTEGER,
  convenio_academico       TEXT,
  nome_curso_norm          TEXT NOT NULL,
  turno_norm               TEXT,
  campus_norm              TEXT,
  grau_academico_norm      TEXT,
  area_conhecimento_norm   TEXT,
  unidade_responsavel_norm TEXT
);
COMMENT ON TABLE silver.cursos_graduacao IS
  'Catálogo de cursos limpo. Uma linha por curso/habilitação (id_curso). nome_curso_norm NÃO é único: cursos com bacharelado e licenciatura aparecem duas vezes com o mesmo nome.';
COMMENT ON COLUMN silver.cursos_graduacao.id_curso IS 'Identificador do curso no SIGAA.';
COMMENT ON COLUMN silver.cursos_graduacao.coordenador IS 'Nome do coordenador do curso (servidor público, dado funcional).';
COMMENT ON COLUMN silver.cursos_graduacao.nivel_ensino IS 'Sempre vazio na fonte.';
COMMENT ON COLUMN silver.cursos_graduacao.convenio_academico IS 'Sempre vazio na fonte.';
COMMENT ON COLUMN silver.cursos_graduacao.dou IS 'Data de publicação do ato de reconhecimento no Diário Oficial da União.';
COMMENT ON COLUMN silver.cursos_graduacao.codigo_inep IS 'Código do curso no cadastro e-MEC/INEP.';
COMMENT ON COLUMN silver.cursos_graduacao.nome_curso_norm IS 'Nome sem acento, em maiúsculas e sem espaços repetidos. Chave de junção com a estrutura curricular.';
COMMENT ON COLUMN silver.cursos_graduacao.area_conhecimento_norm IS 'Grande Área CNPq/MEC. Os 13 cursos classificados como "Outra" na fonte são remapeados à mão (AREA_CONHECIMENTO_OVERRIDES).';

CREATE TABLE silver.estrutura_curricular (
  nome_curso_norm           TEXT PRIMARY KEY,
  semestre_conclusao_minimo NUMERIC(4,1) NOT NULL,
  semestre_conclusao_ideal  NUMERIC(4,1) NOT NULL,
  semestre_conclusao_maximo NUMERIC(4,1) NOT NULL,
  ch_total_minima           INTEGER,
  cr_total_minimo           INTEGER,
  id_curso                  INTEGER NOT NULL UNIQUE REFERENCES silver.cursos_graduacao (id_curso),
  CHECK (semestre_conclusao_minimo > 0),
  CHECK (semestre_conclusao_ideal >= semestre_conclusao_minimo)
);
COMMENT ON TABLE silver.estrutura_curricular IS
  'Prazos regulamentares consolidados: uma linha por curso canônico, com a mediana dos semestres entre as matrizes do curso e a maior carga horária. Não há CHECK de máximo >= ideal porque a matriz de ENGENHARIA (curso-tronco) publica máximo 3 e ideal 5 — anomalia da fonte, coberta por teste.';
COMMENT ON COLUMN silver.estrutura_curricular.semestre_conclusao_minimo IS 'Mediana do prazo mínimo de conclusão, em semestres, entre as matrizes do curso.';
COMMENT ON COLUMN silver.estrutura_curricular.semestre_conclusao_ideal IS 'Mediana do prazo ideal (duração padrão) de conclusão, em semestres.';
COMMENT ON COLUMN silver.estrutura_curricular.semestre_conclusao_maximo IS 'Mediana do prazo máximo antes do jubilamento, em semestres.';
COMMENT ON COLUMN silver.estrutura_curricular.ch_total_minima IS 'Maior carga horária total mínima entre as matrizes do curso, em horas.';
COMMENT ON COLUMN silver.estrutura_curricular.cr_total_minimo IS 'Maior total mínimo de créditos entre as matrizes do curso.';
COMMENT ON COLUMN silver.estrutura_curricular.id_curso IS 'Curso da primeira matriz do grupo, no catálogo de cursos.';

CREATE TABLE silver.sigra_graduacao (
  id                           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  aluno                        TEXT NOT NULL,
  nivel                        TEXT,
  opcao                        INTEGER NOT NULL,
  curso                        TEXT,
  departamento                 TEXT,
  ano_ingresso                 SMALLINT NOT NULL,
  forma_ingresso               TEXT,
  cota_ingresso                TEXT,
  data_nascimento              DATE,
  sexo                         CHAR(1) CHECK (sexo IN ('F', 'M')),
  raca_cor                     TEXT,
  forma_saida                  TEXT,
  data_registro_livro          DATE,
  periodo_saida                INTEGER NOT NULL,
  nivel_norm                   TEXT NOT NULL CHECK (nivel_norm = 'GRADUACAO'),
  curso_raw                    TEXT,
  curso_norm                   TEXT NOT NULL,
  departamento_norm            TEXT,
  forma_saida_norm             TEXT,
  tipo_saida_grupo             TEXT NOT NULL
    CHECK (tipo_saida_grupo IN ('FORMATURA', 'EVASAO_DESLIGAMENTO', 'MUDANCA_INTERNA', 'OUTROS')),
  ano_saida                    SMALLINT,
  semestre_saida               SMALLINT CHECK (semestre_saida IN (0, 1, 2)),
  semestres_permanencia        SMALLINT,
  semestres_permanencia_valida SMALLINT CHECK (semestres_permanencia_valida BETWEEN 1 AND 30),
  UNIQUE (aluno, opcao, ano_ingresso, periodo_saida)
);
COMMENT ON TABLE silver.sigra_graduacao IS
  'Vínculos de graduação do SIGRA. Uma linha por vínculo (aluno + opção + ingresso + saída): o mesmo aluno aparece mais de uma vez quando muda de curso. Registro individual com quase-identificadores — nunca expor fora do banco.';
COMMENT ON COLUMN silver.sigra_graduacao.id IS 'Chave substituta. A chave natural é (aluno, opcao, ano_ingresso, periodo_saida).';
COMMENT ON COLUMN silver.sigra_graduacao.aluno IS 'Pseudônimo do discente publicado pelo portal (ex.: Aluno201086141). Não é único: repete entre vínculos.';
COMMENT ON COLUMN silver.sigra_graduacao.opcao IS 'Código da opção de ingresso no SIGRA. Não há tabela pública que ligue opção a grau (bacharelado/licenciatura).';
COMMENT ON COLUMN silver.sigra_graduacao.data_nascimento IS 'Quase-identificador (LGPD). Combinado a curso, sexo e raça/cor, deixa 88,9% dos registros com k = 1.';
COMMENT ON COLUMN silver.sigra_graduacao.raca_cor IS 'Dado pessoal sensível (LGPD, art. 5º, II).';
COMMENT ON COLUMN silver.sigra_graduacao.periodo_saida IS 'Ano e semestre da saída no formato AAAAS (ex.: 20141). Semestre 0 indica período de verão.';
COMMENT ON COLUMN silver.sigra_graduacao.curso_norm IS 'Nome do curso normalizado, antes da harmonização canônica (ver gold.regras_harmonizacao_canonicas).';
COMMENT ON COLUMN silver.sigra_graduacao.tipo_saida_grupo IS 'forma_saida agrupada: FORMATURA, EVASAO_DESLIGAMENTO (abandono, jubilamento, 3 reprovações, desligamento), MUDANCA_INTERNA ou OUTROS.';
COMMENT ON COLUMN silver.sigra_graduacao.semestres_permanencia IS '2 * (ano_saida - ano_ingresso) + semestre_saida. Assume ingresso no 1º semestre (incerteza de ±1 semestre).';
COMMENT ON COLUMN silver.sigra_graduacao.semestres_permanencia_valida IS 'semestres_permanencia quando está entre 1 e 30; nulo caso contrário.';

CREATE TABLE silver.pibic_bolsistas (
  id                         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  matricula_mascarada        TEXT NOT NULL,
  ano                        SMALLINT NOT NULL,
  tipo_bolsa_norm            TEXT NOT NULL CHECK (tipo_bolsa_norm IN ('REMUNERADA', 'VOLUNTARIA', 'NAO INFORMADO')),
  linha_pesquisa_norm        TEXT,
  campus                     TEXT NOT NULL,
  departamento_pibic_norm    TEXT,
  curso_pibic_norm           TEXT,
  perfil_social_macro        TEXT,
  cota_detalhe               TEXT,
  faixa_renda                TEXT,
  is_cotista                 BOOLEAN NOT NULL,
  valor_bolsa_anual_estimado NUMERIC(10,2) NOT NULL CHECK (valor_bolsa_anual_estimado >= 0),
  orientador_norm            TEXT,
  titulo_norm                TEXT,
  status_norm                TEXT
);
COMMENT ON TABLE silver.pibic_bolsistas IS
  'Planos de trabalho de iniciação científica, sem nome do bolsista e com matrícula mascarada. Uma linha por plano. Sem chave natural: a fonte traz 28 linhas idênticas.';
COMMENT ON COLUMN silver.pibic_bolsistas.matricula_mascarada IS '3 primeiros + *** + 2 últimos dígitos da matrícula. Mascarar não é anonimizar: combinada a curso e ano ainda pode identificar.';
COMMENT ON COLUMN silver.pibic_bolsistas.valor_bolsa_anual_estimado IS 'Estimativa: 12 x R$ 700 a partir de 2023, 12 x R$ 400 antes; zero para voluntária.';
COMMENT ON COLUMN silver.pibic_bolsistas.curso_pibic_norm IS 'Curso extraído do campo "unidade" (texto após a barra), sem prefixos como BACHARELADO EM.';
COMMENT ON COLUMN silver.pibic_bolsistas.titulo_norm IS 'Título do plano de trabalho, normalizado. É o texto vetorizado na busca semântica.';

COMMENT ON COLUMN silver.cursos_graduacao.nome IS 'Nome do curso com acento, como na fonte.';
COMMENT ON COLUMN silver.cursos_graduacao.id_coordenador IS 'Identificador do coordenador no SIGAA.';
COMMENT ON COLUMN silver.cursos_graduacao.situacao_curso IS 'ATIVO ou INATIVO.';
COMMENT ON COLUMN silver.cursos_graduacao.grau_academico IS 'Titulação conferida, como na fonte.';
COMMENT ON COLUMN silver.cursos_graduacao.modalidade_educacao IS 'Presencial ou A Distância.';
COMMENT ON COLUMN silver.cursos_graduacao.area_conhecimento IS 'Grande Área como na fonte (inclui "Outra"). Use area_conhecimento_norm.';
COMMENT ON COLUMN silver.cursos_graduacao.tipo_oferta IS 'Periodicidade da oferta (sempre Semestral).';
COMMENT ON COLUMN silver.cursos_graduacao.turno IS 'Turno como na fonte.';
COMMENT ON COLUMN silver.cursos_graduacao.tipo_ciclo_formacao IS 'Sempre "Um ciclo".';
COMMENT ON COLUMN silver.cursos_graduacao.municipio IS 'Sempre BRASÍLIA na fonte, mesmo fora do Plano Piloto.';
COMMENT ON COLUMN silver.cursos_graduacao.campus IS 'Campus como na fonte.';
COMMENT ON COLUMN silver.cursos_graduacao.id_unidade_responsavel IS 'Identificador da unidade acadêmica responsável.';
COMMENT ON COLUMN silver.cursos_graduacao.unidade_responsavel IS 'Unidade acadêmica responsável, como na fonte.';
COMMENT ON COLUMN silver.cursos_graduacao.website IS 'Contato do curso; preenchido em uma linha só.';
COMMENT ON COLUMN silver.cursos_graduacao.data_funcionamento IS 'Início de funcionamento do curso.';
COMMENT ON COLUMN silver.cursos_graduacao.portaria_reconhecimento IS 'Número da portaria de reconhecimento.';
COMMENT ON COLUMN silver.cursos_graduacao.turno_norm IS 'Turno normalizado (ex.: MATUTINO E VESPERTINO, NOTURNO).';
COMMENT ON COLUMN silver.cursos_graduacao.campus_norm IS 'Campus normalizado.';
COMMENT ON COLUMN silver.cursos_graduacao.grau_academico_norm IS 'Titulação normalizada (ex.: BACHAREL, LICENCIADO).';
COMMENT ON COLUMN silver.cursos_graduacao.unidade_responsavel_norm IS 'Unidade acadêmica normalizada.';

COMMENT ON COLUMN silver.estrutura_curricular.nome_curso_norm IS 'Nome do curso normalizado. Destino da harmonização canônica do SIGRA.';

COMMENT ON COLUMN silver.sigra_graduacao.nivel IS 'Nível como na fonte (sempre Graduação nesta tabela, com padding).';
COMMENT ON COLUMN silver.sigra_graduacao.curso IS 'Nome do curso como na fonte, com padding de espaços.';
COMMENT ON COLUMN silver.sigra_graduacao.departamento IS 'Unidade acadêmica como na fonte.';
COMMENT ON COLUMN silver.sigra_graduacao.ano_ingresso IS 'Ano de ingresso. A fonte não informa o semestre.';
COMMENT ON COLUMN silver.sigra_graduacao.forma_ingresso IS 'Via de ingresso como na fonte.';
COMMENT ON COLUMN silver.sigra_graduacao.cota_ingresso IS 'Modalidade de cota no ingresso como na fonte.';
COMMENT ON COLUMN silver.sigra_graduacao.sexo IS 'F ou M. Quase-identificador.';
COMMENT ON COLUMN silver.sigra_graduacao.forma_saida IS 'Motivo do encerramento do vínculo como na fonte.';
COMMENT ON COLUMN silver.sigra_graduacao.data_registro_livro IS 'Registro do diploma. Nulo para quem não se formou.';
COMMENT ON COLUMN silver.sigra_graduacao.nivel_norm IS 'Nível normalizado; esta tabela só guarda GRADUACAO.';
COMMENT ON COLUMN silver.sigra_graduacao.curso_raw IS 'Nome do curso sem o padding, ainda com acento.';
COMMENT ON COLUMN silver.sigra_graduacao.departamento_norm IS 'Unidade acadêmica normalizada.';
COMMENT ON COLUMN silver.sigra_graduacao.forma_saida_norm IS 'Motivo de saída normalizado, base de tipo_saida_grupo.';
COMMENT ON COLUMN silver.sigra_graduacao.ano_saida IS 'Ano extraído de periodo_saida.';
COMMENT ON COLUMN silver.sigra_graduacao.semestre_saida IS 'Semestre extraído de periodo_saida: 1, 2 ou 0 (verão).';

COMMENT ON COLUMN silver.pibic_bolsistas.id IS 'Chave substituta.';
COMMENT ON COLUMN silver.pibic_bolsistas.ano IS 'Ano do edital.';
COMMENT ON COLUMN silver.pibic_bolsistas.tipo_bolsa_norm IS 'REMUNERADA (PIBIC), VOLUNTARIA (PIVIC) ou NAO INFORMADO.';
COMMENT ON COLUMN silver.pibic_bolsistas.linha_pesquisa_norm IS 'Grande linha de pesquisa normalizada.';
COMMENT ON COLUMN silver.pibic_bolsistas.campus IS 'Campus inferido do nome da unidade: DARCY RIBEIRO, FGA - GAMA, FCE - CEILANDIA ou FUP - PLANALTINA.';
COMMENT ON COLUMN silver.pibic_bolsistas.departamento_pibic_norm IS 'Unidade extraída do campo "unidade" (texto antes da barra).';
COMMENT ON COLUMN silver.pibic_bolsistas.perfil_social_macro IS 'AMPLA CONCORRENCIA, PPI / ETNICO-RACIAL, ESCOLA PUBLICA ou OUTRAS COTAS. Atenção: a regra atual classifica cotas "NÃO PPI" como PPI.';
COMMENT ON COLUMN silver.pibic_bolsistas.cota_detalhe IS 'Grupo de cota detalhado (ex.: ESCOLA PUBLICA - PPI, COTAS RACIAIS (NEGRO/INDIGENA)).';
COMMENT ON COLUMN silver.pibic_bolsistas.faixa_renda IS 'BAIXA RENDA (<= 1.5 SM), INDEPENDENTE DE RENDA, NAO ESPECIFICADO ou NAO APLICAVEL (ampla concorrência).';
COMMENT ON COLUMN silver.pibic_bolsistas.is_cotista IS 'Verdadeiro se o bolsista ingressou por qualquer cota.';
COMMENT ON COLUMN silver.pibic_bolsistas.orientador_norm IS 'Nome do docente orientador, normalizado.';
COMMENT ON COLUMN silver.pibic_bolsistas.status_norm IS 'Situação da avaliação do plano.';
