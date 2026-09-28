-- ============================================================================
-- Migração 0011: Modelo Relacional Normalizado em 3ª Forma Normal (Camada Silver)
--
-- Decompõe os dados brutos e vínculos de discentes em relações 3NF:
--   1. silver.discentes (Pessoas físicas únicas, encapsulando dados sensíveis e LGPD)
--   2. silver.cursos (Catálogo canônico de cursos, eliminando redundâncias)
--   3. silver.estruturas_curriculares (Matrizes e prazos regulamentares por curso)
--   4. silver.movimentacoes_vinculos (Fato operacional com particionamento por ano)
--   5. silver.pibic_projetos (Planos de pesquisa vinculados a aluno e curso)
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 1. Entidade Discente
CREATE TABLE IF NOT EXISTS silver.discentes (
    id_discente         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pseudonimo          TEXT NOT NULL UNIQUE,
    data_nascimento     DATE,
    sexo                CHAR(1) CHECK (sexo IN ('F', 'M')),
    raca_cor            TEXT,
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE silver.discentes IS
  'Discentes únicos normalizados. Registro individual com quase-identificadores sob proteção de privilégio mínimo.';
COMMENT ON COLUMN silver.discentes.id_discente IS 'Identificador numérico sintético do discente.';
COMMENT ON COLUMN silver.discentes.pseudonimo IS 'Pseudônimo original gerado pelo sistema acadêmico.';

-- 2. Catálogo Canônico de Cursos
CREATE TABLE IF NOT EXISTS silver.cursos (
    id_curso            INTEGER PRIMARY KEY,
    codigo_sigaa        TEXT,
    nome_curso_norm     TEXT NOT NULL,
    campus              TEXT NOT NULL,
    turno               TEXT NOT NULL CHECK (turno IN ('DIURNO', 'NOTURNO', 'INTEGRAL', 'DIURNO E NOTURNO', 'MATUTINO', 'VESPERTINO', 'MATUTINO E VESPERTINO')),
    grau_academico      TEXT NOT NULL,
    categoria_grau      TEXT NOT NULL CHECK (categoria_grau IN ('BACHARELADO', 'LICENCIATURA', 'MISTO')),
    area_conhecimento   TEXT NOT NULL,
    departamento        TEXT,
    is_tronco_abi       BOOLEAN NOT NULL DEFAULT false,
    ativo               BOOLEAN NOT NULL DEFAULT true
);
CREATE INDEX IF NOT EXISTS idx_cursos_nome_trgm ON silver.cursos USING gin (nome_curso_norm gin_trgm_ops);

COMMENT ON TABLE silver.cursos IS
  'Catálogo canônico de cursos da UnB normalizado em 3NF. Elimina repetição de campus, turno e grande área.';

-- 3. Estruturas Curriculares e Matrizes
CREATE TABLE IF NOT EXISTS silver.estruturas_curriculares (
    id_estrutura        INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_curso            INTEGER NOT NULL REFERENCES silver.cursos (id_curso) ON DELETE RESTRICT,
    semestre_minimo     NUMERIC(4,1) NOT NULL CHECK (semestre_minimo > 0),
    semestre_ideal      NUMERIC(4,1) NOT NULL CHECK (semestre_ideal >= semestre_minimo),
    semestre_maximo     NUMERIC(4,1) NOT NULL,
    ch_total_minima     INTEGER CHECK (ch_total_minima > 0),
    cr_total_minimo     INTEGER CHECK (cr_total_minimo > 0),
    CONSTRAINT uk_curso_estrutura UNIQUE (id_curso, semestre_ideal)
);
COMMENT ON TABLE silver.estruturas_curriculares IS
  'Prazos e cargas horárias regulamentares de cada matriz curricular.';

-- 4. Movimentações e Vínculos Discentes (Particionada por Ano de Ingresso)
CREATE TABLE IF NOT EXISTS silver.movimentacoes_vinculos (
    id_vinculo                   BIGINT GENERATED ALWAYS AS IDENTITY,
    id_discente                  BIGINT NOT NULL REFERENCES silver.discentes (id_discente) ON DELETE RESTRICT,
    id_curso                     INTEGER NOT NULL REFERENCES silver.cursos (id_curso) ON DELETE RESTRICT,
    id_estrutura                 INTEGER REFERENCES silver.estruturas_curriculares (id_estrutura),
    ano_ingresso                 SMALLINT NOT NULL,
    semestre_ingresso            SMALLINT NOT NULL CHECK (semestre_ingresso IN (1, 2)),
    forma_saida                  TEXT,
    tipo_saida_grupo             TEXT NOT NULL CHECK (tipo_saida_grupo IN ('FORMATURA', 'EVASAO', 'ATIVO', 'OUTROS')),
    ano_saida                    SMALLINT,
    semestre_saida               SMALLINT CHECK (semestre_saida IN (0, 1, 2)),
    semestres_permanencia        SMALLINT,
    semestres_permanencia_valida SMALLINT CHECK (semestres_permanencia_valida BETWEEN 1 AND 35),
    periodo_saida_estimado       BOOLEAN NOT NULL DEFAULT false,
    status_aluno                 TEXT,
    fonte                        TEXT NOT NULL CHECK (fonte IN ('SIGRA', 'SIGAA')),
    PRIMARY KEY (id_vinculo, ano_ingresso)
) PARTITION BY RANGE (ano_ingresso);

COMMENT ON TABLE silver.movimentacoes_vinculos IS
  'Vínculos de matrícula e movimentação de discentes normalizados em 3NF com particionamento temporal.';

-- Partições declarativas por intervalo de anos
CREATE TABLE IF NOT EXISTS silver.movimentacoes_p2000_2015 
    PARTITION OF silver.movimentacoes_vinculos FOR VALUES FROM (2000) TO (2016);
CREATE TABLE IF NOT EXISTS silver.movimentacoes_p2016_2020 
    PARTITION OF silver.movimentacoes_vinculos FOR VALUES FROM (2016) TO (2021);
CREATE TABLE IF NOT EXISTS silver.movimentacoes_p2021_atual 
    PARTITION OF silver.movimentacoes_vinculos FOR VALUES FROM (2021) TO (2035);
CREATE TABLE IF NOT EXISTS silver.movimentacoes_p_default 
    PARTITION OF silver.movimentacoes_vinculos DEFAULT;

-- Índices B-Tree especializados para filtros frequentes
CREATE INDEX IF NOT EXISTS idx_mov_curso_ano ON silver.movimentacoes_vinculos (id_curso, ano_ingresso);
CREATE INDEX IF NOT EXISTS idx_mov_evasao ON silver.movimentacoes_vinculos (id_curso) 
    WHERE tipo_saida_grupo = 'EVASAO';

-- 5. Projetos PIBIC e Iniciação Científica
CREATE TABLE IF NOT EXISTS silver.pibic_projetos (
    id_projeto                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_discente                 BIGINT REFERENCES silver.discentes (id_discente),
    id_curso                    INTEGER REFERENCES silver.cursos (id_curso),
    ano_edital                  SMALLINT NOT NULL,
    tipo_bolsa                  TEXT NOT NULL CHECK (tipo_bolsa IN ('REMUNERADA', 'VOLUNTARIA', 'NAO INFORMADO')),
    linha_pesquisa              TEXT,
    is_cotista                  BOOLEAN NOT NULL,
    cota_detalhe                TEXT,
    faixa_renda                 TEXT,
    valor_bolsa_total           NUMERIC(10,2) NOT NULL DEFAULT 0.00 CHECK (valor_bolsa_total >= 0),
    titulo_pesquisa             TEXT NOT NULL,
    status_projeto              TEXT
);
COMMENT ON TABLE silver.pibic_projetos IS
  'Planos de trabalho de iniciação científica vinculados por chave estrangeira a discentes e cursos.';
