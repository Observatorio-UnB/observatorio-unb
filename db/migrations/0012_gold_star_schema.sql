-- ============================================================================
-- Migração 0012: Modelagem Dimensional em Star Schema (Camada Gold)
--
-- Constrói o modelo dimensional analítico (Kimball) para o Observatório UnB:
--   1. gold.dim_curso (Dimensão Curso com atributos de classificação acadêmica)
--   2. gold.dim_campus (Dimensão Campus e Região Geográfica)
--   3. gold.dim_tempo (Dimensão Temporal para cortes por semestre e ano)
--   4. gold.dim_perfil_social (Dimensão de Perfis e Cotas)
--   5. gold.fato_retencao_curso (Fato de Integralização Curricular e IRC com k >= 5)
--   6. gold.fato_alunos_ativos (Fato de Alunos Cursando no Momento Presente)
-- ============================================================================

-- 1. Dimensão Curso
CREATE TABLE IF NOT EXISTS gold.dim_curso (
    sk_curso            INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_curso_origem     INTEGER NOT NULL UNIQUE,
    nome_curso          TEXT NOT NULL,
    grau_academico      TEXT NOT NULL,
    categoria_grau      TEXT NOT NULL CHECK (categoria_grau IN ('BACHARELADO', 'LICENCIATURA', 'MISTO')),
    area_conhecimento   TEXT NOT NULL,
    departamento        TEXT,
    is_tronco_abi       BOOLEAN NOT NULL DEFAULT false
);
COMMENT ON TABLE gold.dim_curso IS 'Dimensão conformada de cursos de graduação da UnB.';

-- 2. Dimensão Campus
CREATE TABLE IF NOT EXISTS gold.dim_campus (
    sk_campus           INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    campus              TEXT NOT NULL UNIQUE,
    regiao_admin        TEXT NOT NULL,
    municipio           TEXT NOT NULL DEFAULT 'Brasília'
);
COMMENT ON TABLE gold.dim_campus IS 'Dimensão geográfica dos campi da UnB.';

-- 3. Dimensão Tempo
CREATE TABLE IF NOT EXISTS gold.dim_tempo (
    sk_tempo            INTEGER PRIMARY KEY, -- formato numérico AAAAS (ex.: 20141)
    ano                 SMALLINT NOT NULL,
    semestre            SMALLINT NOT NULL CHECK (semestre IN (1, 2)),
    rotulo              TEXT NOT NULL,        -- '2014/1'
    decada              SMALLINT NOT NULL
);
COMMENT ON TABLE gold.dim_tempo IS 'Dimensão temporal acadêmica com granularidade semestral.';

-- 4. Dimensão Perfil Social
CREATE TABLE IF NOT EXISTS gold.dim_perfil_social (
    sk_perfil           INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    perfil_macro        TEXT NOT NULL,
    categoria_cota      TEXT NOT NULL,
    faixa_renda         TEXT,
    is_cotista          BOOLEAN NOT NULL
);
COMMENT ON TABLE gold.dim_perfil_social IS 'Dimensão social e de ações afirmativas.';

-- 5. Tabela Fato: Retenção e Formatura por Curso (k-anonimato assegurado por CHECK)
CREATE TABLE IF NOT EXISTS gold.fato_retencao_curso (
    id_fato                     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sk_curso                    INTEGER NOT NULL REFERENCES gold.dim_curso (sk_curso),
    sk_campus                   INTEGER NOT NULL REFERENCES gold.dim_campus (sk_campus),
    total_ingressantes          INTEGER NOT NULL CHECK (total_ingressantes >= 5), -- k-anonimato
    total_formados              INTEGER NOT NULL CHECK (total_formados >= 0),
    total_evadidos              INTEGER NOT NULL CHECK (total_evadidos >= 0),
    total_ainda_ativos          INTEGER NOT NULL DEFAULT 0 CHECK (total_ainda_ativos >= 0),
    taxa_formatura_pct          NUMERIC(5,2) CHECK (taxa_formatura_pct BETWEEN 0 AND 100),
    taxa_evasao_pct             NUMERIC(5,2) CHECK (taxa_evasao_pct BETWEEN 0 AND 100),
    formados_tempo_ideal_pct    NUMERIC(5,2) CHECK (formados_tempo_ideal_pct BETWEEN 0 AND 100),
    atraso_medio_semestres      NUMERIC(5,2),
    indice_retencao_critica     NUMERIC(4,1) CHECK (indice_retencao_critica BETWEEN 0 AND 100),
    classificacao_retencao      TEXT CHECK (classificacao_retencao IN ('RETENÇÃO CRÍTICA', 'RETENÇÃO ALTA', 'RETENÇÃO MÉDIA', 'RETENÇÃO BAIXA')),
    atualizado_em               TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uk_fato_curso UNIQUE (sk_curso, sk_campus)
);
COMMENT ON TABLE gold.fato_retencao_curso IS
  'Tabela Fato de Retenção Curricular por curso. Métricas consolidadas sobre coortes maduras com k >= 5.';

-- 6. Tabela Fato: Alunos Ativos Hoje (Momento Presente)
CREATE TABLE IF NOT EXISTS gold.fato_alunos_ativos (
    id_fato_ativo               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sk_curso                    INTEGER NOT NULL REFERENCES gold.dim_curso (sk_curso) UNIQUE,
    sk_tempo_referencia         INTEGER NOT NULL REFERENCES gold.dim_tempo (sk_tempo),
    total_ativos                INTEGER NOT NULL CHECK (total_ativos >= 5),
    ativos_acima_prazo_ideal    INTEGER NOT NULL CHECK (ativos_acima_prazo_ideal >= 0),
    ativos_acima_prazo_maximo   INTEGER NOT NULL CHECK (ativos_acima_prazo_maximo >= 0),
    pct_acima_prazo_ideal       NUMERIC(5,2) NOT NULL CHECK (pct_acima_prazo_ideal BETWEEN 0 AND 100),
    atualizado_em               TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE gold.fato_alunos_ativos IS
  'Tabela Fato de discentes ativos no semestre vigente, mensurando atraso e risco de jubilamento.';

-- Garantir acesso de leitura para o papel observatorio_leitura
GRANT USAGE ON SCHEMA gold TO observatorio_leitura;
GRANT SELECT ON ALL TABLES IN SCHEMA gold TO observatorio_leitura;
