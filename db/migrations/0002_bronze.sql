-- Camada bronze: cópia fiel dos CSVs baixados pela API CKAN (src/ingestion/ckan_client.py).
-- Todas as colunas são TEXT de propósito: bronze preserva o dado como a fonte o
-- publica, inclusive os literais 'NULL' e o padding de espaços que a silver trata.

CREATE TABLE bronze.sigra_discentes (
  aluno               TEXT,
  nivel               TEXT,
  opcao               TEXT,
  curso               TEXT,
  departamento        TEXT,
  ano_ingresso        TEXT,
  forma_ingresso      TEXT,
  cota_ingresso       TEXT,
  data_nascimento     TEXT,
  sexo                TEXT,
  raca_cor            TEXT,
  forma_saida         TEXT,
  data_registro_livro TEXT,
  periodo_saida       TEXT,
  _carregado_em       TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE bronze.sigra_discentes IS
  'SIGRA (sigra.csv, pacote dados-referente-aos-alunos-de-graduacao-pos-graduacao-latu-sensu-mestrado-e-doutorado). Uma linha por vínculo de discente, todos os níveis. Separador ";", UTF-8. Contém quase-identificadores (nascimento, sexo, raça/cor).';
COMMENT ON COLUMN bronze.sigra_discentes._carregado_em IS 'Momento em que a linha foi carregada no banco (hora de ingestão, não do evento).';

CREATE TABLE bronze.estrutura_curricular (
  id_curriculo                 TEXT,
  codigo                       TEXT,
  nome_matriz                  TEXT,
  id_curso                     TEXT,
  nome_curso                   TEXT,
  semestre_conclusao_minimo    TEXT,
  semestre_conclusao_ideal     TEXT,
  semestre_conclusao_maximo    TEXT,
  meses_conclusao_minimo       TEXT,
  meses_conclusao_ideal        TEXT,
  meses_conclusao_maximo       TEXT,
  cr_total_minimo              TEXT,
  ch_total_minima              TEXT,
  ch_optativas_minima          TEXT,
  max_eletivos                 TEXT,
  ch_nao_atividade_obrigatoria TEXT,
  cr_nao_atividade_obrigatorio TEXT,
  ch_atividade_obrigatoria     TEXT,
  cr_minimo_semestre           TEXT,
  cr_maximo_semestre           TEXT,
  ch_minima_semestre           TEXT,
  ch_maxima_semestre           TEXT,
  periodo_entrada_vigor        TEXT,
  ano_entrada_vigor            TEXT,
  observacao                   TEXT,
  _carregado_em                TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE bronze.estrutura_curricular IS
  'Estruturas curriculares (estrutura-curricular.csv). Uma linha por matriz curricular. Separador ";", publicado em Latin-1.';
COMMENT ON COLUMN bronze.estrutura_curricular._carregado_em IS 'Momento em que a linha foi carregada no banco.';

CREATE TABLE bronze.cursos_graduacao (
  id_curso                TEXT,
  nome                    TEXT,
  id_coordenador          TEXT,
  coordenador             TEXT,
  situacao_curso          TEXT,
  nivel_ensino            TEXT,
  grau_academico          TEXT,
  modalidade_educacao     TEXT,
  area_conhecimento       TEXT,
  tipo_oferta             TEXT,
  turno                   TEXT,
  tipo_ciclo_formacao     TEXT,
  municipio               TEXT,
  campus                  TEXT,
  id_unidade_responsavel  TEXT,
  unidade_responsavel     TEXT,
  website                 TEXT,
  data_funcionamento      TEXT,
  codigo_inep             TEXT,
  dou                     TEXT,
  portaria_reconhecimento TEXT,
  convenio_academico      TEXT,
  _carregado_em           TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE bronze.cursos_graduacao IS
  'Catálogo de cursos de graduação (curso_graduacao.csv). Uma linha por curso/habilitação. Separador ",", UTF-8.';
COMMENT ON COLUMN bronze.cursos_graduacao._carregado_em IS 'Momento em que a linha foi carregada no banco.';

CREATE TABLE bronze.bolsistas_iniciacao_cientifica (
  id_discente         TEXT,
  matricula           TEXT,
  discente            TEXT,
  titulo              TEXT,
  codigo_projeto      TEXT,
  id_projeto_pesquisa TEXT,
  ano                 TEXT,
  id_orientador       TEXT,
  orientador          TEXT,
  categoria           TEXT,
  tipo_de_bolsa       TEXT,
  linha_pesquisa      TEXT,
  id_grupo_pesquisa   TEXT,
  grupo_pesquisa      TEXT,
  cota                TEXT,
  inicio              TEXT,
  fim                 TEXT,
  id_unidade          TEXT,
  unidade             TEXT,
  status              TEXT,
  _carregado_em       TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE bronze.bolsistas_iniciacao_cientifica IS
  'Bolsistas de iniciação científica PIBIC/PIVIC (bolsistas-de-iniciacao-cientifica.csv). Uma linha por plano de trabalho. Separador ",", Latin-1. Contém nome e matrícula do discente.';
COMMENT ON COLUMN bronze.bolsistas_iniciacao_cientifica.discente IS 'Nome completo do bolsista (dado pessoal). Descartado na silver.';
COMMENT ON COLUMN bronze.bolsistas_iniciacao_cientifica.matricula IS 'Matrícula do bolsista em claro (dado pessoal). Mascarada na silver.';
COMMENT ON COLUMN bronze.bolsistas_iniciacao_cientifica._carregado_em IS 'Momento em que a linha foi carregada no banco.';

-- Descrição das colunas da fonte. Os valores citados são os observados na carga de 2026-09.
COMMENT ON COLUMN bronze.sigra_discentes.aluno IS 'Pseudônimo do discente (ex.: Aluno201086141). Repete quando o mesmo aluno tem mais de um vínculo.';
COMMENT ON COLUMN bronze.sigra_discentes.nivel IS 'Nível do vínculo: Graduação, Mestrado ou Doutorado, com padding de espaços.';
COMMENT ON COLUMN bronze.sigra_discentes.opcao IS 'Código da opção de ingresso (curso/habilitação) no SIGRA.';
COMMENT ON COLUMN bronze.sigra_discentes.curso IS 'Nome do curso com acento e padding de até 30 espaços à direita.';
COMMENT ON COLUMN bronze.sigra_discentes.departamento IS 'Unidade acadêmica do curso.';
COMMENT ON COLUMN bronze.sigra_discentes.ano_ingresso IS 'Ano de ingresso, sem semestre.';
COMMENT ON COLUMN bronze.sigra_discentes.forma_ingresso IS 'Via de ingresso (Vestibular, Novo Vestibular, Transferência, Acordo Cultural-PEC-G, Seleção...).';
COMMENT ON COLUMN bronze.sigra_discentes.cota_ingresso IS 'Modalidade de cota no ingresso (Universal, Negro, Indígena, Escola Pública com recortes de renda, PPI e PcD).';
COMMENT ON COLUMN bronze.sigra_discentes.data_nascimento IS 'Data de nascimento, dd/mm/aaaa. Quase-identificador.';
COMMENT ON COLUMN bronze.sigra_discentes.sexo IS 'F ou M.';
COMMENT ON COLUMN bronze.sigra_discentes.raca_cor IS 'Raça/cor autodeclarada, incluindo "Não cadastrada" e "Não quero declarar". Dado sensível.';
COMMENT ON COLUMN bronze.sigra_discentes.forma_saida IS 'Motivo do encerramento do vínculo (Formatura, Desligamento Jubilamento, Repr 3 vezes na mesma disc obr, Mudança de Curso...).';
COMMENT ON COLUMN bronze.sigra_discentes.data_registro_livro IS 'Data de registro do diploma, dd/mm/aaaa. Vazia para quem não se formou.';
COMMENT ON COLUMN bronze.sigra_discentes.periodo_saida IS 'Período de saída no formato AAAAS (ex.: 20141).';

COMMENT ON COLUMN bronze.estrutura_curricular.id_curriculo IS 'Identificador da matriz curricular no SIGAA.';
COMMENT ON COLUMN bronze.estrutura_curricular.codigo IS 'Código da matriz no formato opção/versão (ex.: 6912/1).';
COMMENT ON COLUMN bronze.estrutura_curricular.nome_matriz IS 'Campo composto: curso - município - habilitação - turno - titulação (ex.: "... - BRASÍLIA -  - N - Licenciado").';
COMMENT ON COLUMN bronze.estrutura_curricular.id_curso IS 'Curso da matriz, no catálogo de cursos.';
COMMENT ON COLUMN bronze.estrutura_curricular.nome_curso IS 'Nome do curso com acento.';
COMMENT ON COLUMN bronze.estrutura_curricular.semestre_conclusao_minimo IS 'Prazo mínimo de conclusão, em semestres.';
COMMENT ON COLUMN bronze.estrutura_curricular.semestre_conclusao_ideal IS 'Duração padrão da matriz, em semestres.';
COMMENT ON COLUMN bronze.estrutura_curricular.semestre_conclusao_maximo IS 'Prazo máximo antes do jubilamento, em semestres.';
COMMENT ON COLUMN bronze.estrutura_curricular.meses_conclusao_minimo IS 'Prazo mínimo em meses. Sempre vazio na fonte.';
COMMENT ON COLUMN bronze.estrutura_curricular.meses_conclusao_ideal IS 'Prazo ideal em meses. Sempre vazio na fonte.';
COMMENT ON COLUMN bronze.estrutura_curricular.meses_conclusao_maximo IS 'Prazo máximo em meses. Sempre vazio na fonte.';
COMMENT ON COLUMN bronze.estrutura_curricular.cr_total_minimo IS 'Total mínimo de créditos.';
COMMENT ON COLUMN bronze.estrutura_curricular.ch_total_minima IS 'Carga horária total mínima, em horas.';
COMMENT ON COLUMN bronze.estrutura_curricular.ch_optativas_minima IS 'Carga horária mínima em disciplinas optativas, em horas.';
COMMENT ON COLUMN bronze.estrutura_curricular.max_eletivos IS 'Carga horária máxima em módulo livre (eletivas), em horas.';
COMMENT ON COLUMN bronze.estrutura_curricular.ch_nao_atividade_obrigatoria IS 'Carga horária obrigatória em disciplinas (exceto atividades), em horas.';
COMMENT ON COLUMN bronze.estrutura_curricular.cr_nao_atividade_obrigatorio IS 'Créditos obrigatórios em disciplinas (exceto atividades).';
COMMENT ON COLUMN bronze.estrutura_curricular.ch_atividade_obrigatoria IS 'Carga horária obrigatória em atividades (estágio, TCC...), em horas.';
COMMENT ON COLUMN bronze.estrutura_curricular.cr_minimo_semestre IS 'Mínimo de créditos por semestre.';
COMMENT ON COLUMN bronze.estrutura_curricular.cr_maximo_semestre IS 'Máximo de créditos por semestre.';
COMMENT ON COLUMN bronze.estrutura_curricular.ch_minima_semestre IS 'Carga horária mínima por semestre, em horas.';
COMMENT ON COLUMN bronze.estrutura_curricular.ch_maxima_semestre IS 'Carga horária máxima por semestre, em horas.';
COMMENT ON COLUMN bronze.estrutura_curricular.periodo_entrada_vigor IS 'Semestre (1 ou 2) em que a matriz entrou em vigor.';
COMMENT ON COLUMN bronze.estrutura_curricular.ano_entrada_vigor IS 'Ano em que a matriz entrou em vigor.';
COMMENT ON COLUMN bronze.estrutura_curricular.observacao IS 'Texto livre da coordenação sobre a matriz.';

COMMENT ON COLUMN bronze.cursos_graduacao.id_curso IS 'Identificador do curso no SIGAA.';
COMMENT ON COLUMN bronze.cursos_graduacao.nome IS 'Nome do curso com acento.';
COMMENT ON COLUMN bronze.cursos_graduacao.id_coordenador IS 'Identificador do coordenador no SIGAA ("NULL" literal quando não há).';
COMMENT ON COLUMN bronze.cursos_graduacao.coordenador IS 'Nome do coordenador do curso.';
COMMENT ON COLUMN bronze.cursos_graduacao.situacao_curso IS 'ATIVO ou INATIVO.';
COMMENT ON COLUMN bronze.cursos_graduacao.nivel_ensino IS 'Sempre vazio.';
COMMENT ON COLUMN bronze.cursos_graduacao.grau_academico IS 'Titulação conferida (Bacharel, Licenciado, Engenheiro Civil, Médico...).';
COMMENT ON COLUMN bronze.cursos_graduacao.modalidade_educacao IS 'Presencial ou A Distância.';
COMMENT ON COLUMN bronze.cursos_graduacao.area_conhecimento IS 'Grande Área CNPq/MEC; 13 cursos vêm como "Outra".';
COMMENT ON COLUMN bronze.cursos_graduacao.tipo_oferta IS 'Periodicidade da oferta (sempre Semestral).';
COMMENT ON COLUMN bronze.cursos_graduacao.turno IS 'Matutino e Vespertino, ou Noturno.';
COMMENT ON COLUMN bronze.cursos_graduacao.tipo_ciclo_formacao IS 'Sempre "Um ciclo".';
COMMENT ON COLUMN bronze.cursos_graduacao.municipio IS 'Sempre BRASÍLIA, inclusive para os campi de Gama, Ceilândia e Planaltina.';
COMMENT ON COLUMN bronze.cursos_graduacao.campus IS 'DARCY RIBEIRO, FACULDADE DO GAMA, FACULDADE DE CEILÂNDIA ou FACULDADE DE PLANALTINA.';
COMMENT ON COLUMN bronze.cursos_graduacao.id_unidade_responsavel IS 'Identificador da unidade acadêmica responsável.';
COMMENT ON COLUMN bronze.cursos_graduacao.unidade_responsavel IS 'Nome da unidade acadêmica responsável.';
COMMENT ON COLUMN bronze.cursos_graduacao.website IS 'Contato do curso; preenchido em só uma linha.';
COMMENT ON COLUMN bronze.cursos_graduacao.data_funcionamento IS 'Data de início de funcionamento, AAAA-MM-DD.';
COMMENT ON COLUMN bronze.cursos_graduacao.codigo_inep IS 'Código do curso no e-MEC/INEP.';
COMMENT ON COLUMN bronze.cursos_graduacao.dou IS 'Data de publicação do reconhecimento no Diário Oficial da União, AAAA-MM-DD.';
COMMENT ON COLUMN bronze.cursos_graduacao.portaria_reconhecimento IS 'Número da portaria de reconhecimento do curso.';
COMMENT ON COLUMN bronze.cursos_graduacao.convenio_academico IS 'Sempre vazio.';

COMMENT ON COLUMN bronze.bolsistas_iniciacao_cientifica.id_discente IS 'Sempre 0 na fonte: chave zerada, não serve para junção.';
COMMENT ON COLUMN bronze.bolsistas_iniciacao_cientifica.titulo IS 'Título do plano de trabalho.';
COMMENT ON COLUMN bronze.bolsistas_iniciacao_cientifica.codigo_projeto IS 'Sempre 0 na fonte.';
COMMENT ON COLUMN bronze.bolsistas_iniciacao_cientifica.id_projeto_pesquisa IS 'Sempre 0 na fonte.';
COMMENT ON COLUMN bronze.bolsistas_iniciacao_cientifica.ano IS 'Ano do edital.';
COMMENT ON COLUMN bronze.bolsistas_iniciacao_cientifica.id_orientador IS 'Sempre 0 na fonte.';
COMMENT ON COLUMN bronze.bolsistas_iniciacao_cientifica.orientador IS 'Nome do docente orientador.';
COMMENT ON COLUMN bronze.bolsistas_iniciacao_cientifica.categoria IS 'Sempre INICIAÇÃO CIENTÍFICA (IC).';
COMMENT ON COLUMN bronze.bolsistas_iniciacao_cientifica.tipo_de_bolsa IS 'REMUNERADA, VOLUNTÁRIA ou NÃO INFORMADO.';
COMMENT ON COLUMN bronze.bolsistas_iniciacao_cientifica.linha_pesquisa IS 'Grande linha: ARTES E HUMANIDADE, EXATAS E TECNOLÓGICAS ou SAÚDE E VIDA.';
COMMENT ON COLUMN bronze.bolsistas_iniciacao_cientifica.id_grupo_pesquisa IS 'Identificador do grupo de pesquisa. Sempre 0 ou vazio na fonte.';
COMMENT ON COLUMN bronze.bolsistas_iniciacao_cientifica.grupo_pesquisa IS 'Nome do grupo de pesquisa. Sempre vazio na fonte.';
COMMENT ON COLUMN bronze.bolsistas_iniciacao_cientifica.cota IS 'Cota de ingresso do bolsista: NÃO/NAO, NEGRO, INDÍGENA ou ESCOLA PÚB(LICA) com recortes de renda, PPI/NÃO PPI e PCD — grafia inconsistente.';
COMMENT ON COLUMN bronze.bolsistas_iniciacao_cientifica.inicio IS 'Início da vigência do plano, d/m/aaaa sem zero à esquerda.';
COMMENT ON COLUMN bronze.bolsistas_iniciacao_cientifica.fim IS 'Fim da vigência do plano, d/m/aaaa sem zero à esquerda.';
COMMENT ON COLUMN bronze.bolsistas_iniciacao_cientifica.id_unidade IS 'Sempre 0 na fonte.';
COMMENT ON COLUMN bronze.bolsistas_iniciacao_cientifica.unidade IS 'Campo composto "UNIDADE / CURSO", às vezes com sufixo de situação do aluno (- ALUNO: ATIVO, - FORMANDO).';
COMMENT ON COLUMN bronze.bolsistas_iniciacao_cientifica.status IS 'Situação da avaliação do plano: 2 - ENVIADA, 6 - AVALIADA ou 10 - RECURSO AVALIADO.';
