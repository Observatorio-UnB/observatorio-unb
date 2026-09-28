-- Retrato dos discentes de graduação ativos hoje, por curso, a partir da lista de ativos do
-- SIGAA (sigaa_ativos_AAAA_S.csv). A ingestão pega o semestre mais recente publicado, então
-- o retrato avança sozinho quando a UnB publica uma lista nova. Complementa
-- gold.retencao_cursos_unb, que só olha coortes antigas (ver 0007).
-- A lista traz o semestre de ingresso, então a contagem de semestres cursados é exata; em
-- troca, não distingue formandos nem trancados. O arquivo de origem tem nome e CPF parcial:
-- a ingestão só grava as colunas abaixo.

CREATE TABLE bronze.sigaa_ativos (
  grau             TEXT,
  curso            TEXT,
  ano_ingresso     TEXT,
  periodo_ingresso TEXT,
  _carregado_em    TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE bronze.sigaa_ativos IS
  'Lista de discentes ativos do SIGAA (sigaa_ativos_AAAA_S.csv, semestre mais recente publicado), todos os níveis. O arquivo publicado traz nome, CPF parcial e nacionalidade, descartados em memória pela ingestão: só estas quatro colunas são gravadas.';
COMMENT ON COLUMN bronze.sigaa_ativos.grau IS 'Grau do curso (Bacharelado, Licenciatura, títulos profissionais, Mestrado, Doutorado). Vazio no lato sensu.';
COMMENT ON COLUMN bronze.sigaa_ativos.periodo_ingresso IS 'Semestre de ingresso: 1, 2 ou 0 (verão).';

CREATE TABLE silver.sigaa_ativos (
  id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  periodo_referencia TEXT NOT NULL CHECK (periodo_referencia ~ '^\d{4}/[12]$'),
  curso              TEXT NOT NULL,
  curso_norm         TEXT NOT NULL,
  grau               TEXT NOT NULL,
  ano_ingresso       SMALLINT NOT NULL,
  periodo_ingresso   SMALLINT NOT NULL CHECK (periodo_ingresso IN (0, 1, 2)),
  semestres_cursados SMALLINT NOT NULL CHECK (semestres_cursados >= 1)
);
COMMENT ON TABLE silver.sigaa_ativos IS
  'Discentes de graduação ativos no período de referência (lista do SIGAA), sem lato sensu nem pós stricto sensu. Um registro por discente, sem identificador.';
COMMENT ON COLUMN silver.sigaa_ativos.id IS 'Chave substituta.';
COMMENT ON COLUMN silver.sigaa_ativos.periodo_referencia IS 'Semestre da lista, tirado do nome do arquivo publicado (ex.: sigaa_ativos_2025_1.csv -> 2025/1).';
COMMENT ON COLUMN silver.sigaa_ativos.curso_norm IS 'Nome do curso sem acento, em maiúsculas, sem o prefixo de curso guarda-chuva (Comunicação Social, Ciências Sociais).';
COMMENT ON COLUMN silver.sigaa_ativos.semestres_cursados IS 'Semestres do ingresso até o de referência, contando os dois; o verão (0) conta como 1º semestre.';

CREATE TABLE gold.ativos_hoje_cursos_unb (
  curso                     TEXT PRIMARY KEY,
  periodo_referencia        TEXT NOT NULL CHECK (periodo_referencia ~ '^\d{4}/[12]$'),
  semestre_ideal_previsto   NUMERIC(4,1) NOT NULL,
  semestre_maximo_previsto  NUMERIC(4,1) NOT NULL,
  total_ativos_hoje         INTEGER NOT NULL CHECK (total_ativos_hoje >= 5),
  ativos_acima_prazo_ideal  INTEGER NOT NULL CHECK (ativos_acima_prazo_ideal >= 0),
  ativos_acima_prazo_maximo INTEGER NOT NULL CHECK (ativos_acima_prazo_maximo BETWEEN 0 AND ativos_acima_prazo_ideal),
  pct_acima_prazo_ideal     NUMERIC(5,2) NOT NULL CHECK (pct_acima_prazo_ideal BETWEEN 0 AND 100),
  CHECK (ativos_acima_prazo_ideal <= total_ativos_hoje)
);
COMMENT ON TABLE gold.ativos_hoje_cursos_unb IS
  'Discentes de graduação ativos no semestre mais recente publicado pelo SIGAA (lista de ativos), por curso canônico, todas as coortes. Cursos-tronco e cursos sem estrutura curricular publicada ficam de fora. Só entram cursos com 5 ou mais ativos (k-anonimato).';
COMMENT ON COLUMN gold.ativos_hoje_cursos_unb.curso IS 'Nome canônico do curso, o mesmo de gold.retencao_cursos_unb.';
COMMENT ON COLUMN gold.ativos_hoje_cursos_unb.periodo_referencia IS 'Semestre da lista de ativos usada (ex.: 2025/1).';
COMMENT ON COLUMN gold.ativos_hoje_cursos_unb.semestre_ideal_previsto IS 'Duração ideal da matriz curricular, em semestres.';
COMMENT ON COLUMN gold.ativos_hoje_cursos_unb.semestre_maximo_previsto IS 'Prazo máximo de integralização, em semestres.';
COMMENT ON COLUMN gold.ativos_hoje_cursos_unb.total_ativos_hoje IS 'Discentes de graduação na lista de ativos do SIGAA.';
COMMENT ON COLUMN gold.ativos_hoje_cursos_unb.ativos_acima_prazo_ideal IS 'Discentes que já cursaram mais semestres que a duração ideal (semestres contados a partir do ano e do semestre de ingresso).';
COMMENT ON COLUMN gold.ativos_hoje_cursos_unb.ativos_acima_prazo_maximo IS 'Discentes que já passaram do prazo máximo de integralização.';
COMMENT ON COLUMN gold.ativos_hoje_cursos_unb.pct_acima_prazo_ideal IS 'ativos_acima_prazo_ideal / total_ativos_hoje * 100.';
