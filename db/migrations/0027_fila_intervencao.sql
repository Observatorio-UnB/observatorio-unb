-- ============================================================================
-- Migração 0027: Fila de intervenção (destino do ETL reverso, E4)
--
-- A plataforma termina num ranking; quem age sobre ele é a coordenação do curso, acompanhada pelo
-- Decanato de Ensino de Graduação (DEG). Esta tabela é o sistema operacional onde isso acontece: uma
-- linha por curso que entrou em RETENÇÃO CRÍTICA, com as métricas que o puseram ali (escritas pelo
-- ETL reverso, src/etl_reverso/fila_intervencao.py) e o andamento da intervenção (escrito pela
-- coordenação: status, responsável, plano de ação).
--
-- As duas metades não se sobrescrevem. O ETL reverso só grava as colunas de métrica e de fila;
-- a coordenação só pode gravar as colunas de andamento (privilégio por coluna, abaixo). Um curso que
-- sai da RETENÇÃO CRÍTICA não é apagado: fica com na_fila = false e a data de saída, para o DEG ver se
-- a intervenção acompanhou a melhora.
--
-- Idempotente (IF NOT EXISTS): o ETL reverso aplica este mesmo arquivo num destino que não é o banco
-- da plataforma (--preparar-destino), como o Supabase.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS operacional;
COMMENT ON SCHEMA operacional IS
  'Sistemas onde alguém age sobre o dado tratado. Escrito pelo ETL reverso e pelos usuários do processo.';

CREATE TABLE IF NOT EXISTS operacional.fila_intervencao (
    nome_curso                      text PRIMARY KEY,
    campus                          text,
    area_conhecimento               text,

    -- Escrito pelo ETL reverso a cada ciclo, a partir de dbt_marts.painel_cursos_criticos.
    posicao                         integer,
    classificacao_retencao          text,
    indice_retencao_critica         numeric,
    taxa_evasao_pct                 numeric,
    atraso_medio_semestres          numeric,
    formados_tempo_ideal_pct        numeric,
    total_ingressantes              bigint,
    versao_metricas                 text        NOT NULL,
    ciclo_dados                     timestamptz NOT NULL,
    na_fila                         boolean     NOT NULL DEFAULT true,
    entrou_na_fila_em               date        NOT NULL DEFAULT current_date,
    saiu_da_fila_em                 date,
    sincronizado_em                 timestamptz NOT NULL DEFAULT now(),

    -- Escrito pela coordenação. O ETL reverso nunca toca nestas colunas.
    status                          text        NOT NULL DEFAULT 'NOVO'
        CHECK (status IN ('NOVO', 'EM_ANALISE', 'PLANO_EM_EXECUCAO', 'CONCLUIDO', 'DESCARTADO')),
    responsavel                     text,
    plano_de_acao                   text,
    atualizado_pela_coordenacao_em  timestamptz
);

COMMENT ON TABLE operacional.fila_intervencao IS
  'Cursos em RETENÇÃO CRÍTICA para a coordenação e o DEG agirem. Métricas pelo ETL reverso; andamento pela coordenação.';
COMMENT ON COLUMN operacional.fila_intervencao.versao_metricas IS
  'Versão da definição de cada métrica gravada (dbt_marts.metricas_definicoes), ex.: indice_retencao_critica@1.0.0.';
COMMENT ON COLUMN operacional.fila_intervencao.ciclo_dados IS
  'Carga da gold de onde vieram as métricas gravadas nesta linha. O ETL reverso recusa um ciclo mais antigo que o da última execução.';
COMMENT ON COLUMN operacional.fila_intervencao.na_fila IS
  'false quando o curso saiu da RETENÇÃO CRÍTICA. A linha fica, com o andamento que a coordenação registrou.';

-- Uma linha por execução do ETL reverso: o que mudou no destino e quando.
CREATE TABLE IF NOT EXISTS operacional.fila_intervencao_execucoes (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    executado_em     timestamptz NOT NULL DEFAULT now(),
    ciclo_dados      timestamptz NOT NULL,
    cursos_na_origem integer     NOT NULL,
    inseridos        integer     NOT NULL,
    atualizados      integer     NOT NULL,
    sairam_da_fila   integer     NOT NULL,
    duracao_ms       integer     NOT NULL
);

-- Privilégio mínimo para quem opera a fila: lê a fila e só grava o andamento (privilégio por coluna).
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'coordenacao_academica') THEN
    CREATE ROLE coordenacao_academica NOLOGIN;
  END IF;
END
$$;

COMMENT ON ROLE coordenacao_academica IS
  'Coordenações de curso e DEG: leem a fila de intervenção e gravam só status, responsável e plano de ação.';

REVOKE ALL ON SCHEMA operacional FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA operacional FROM PUBLIC;
GRANT USAGE ON SCHEMA operacional TO coordenacao_academica;
GRANT SELECT ON operacional.fila_intervencao, operacional.fila_intervencao_execucoes TO coordenacao_academica;
GRANT UPDATE (status, responsavel, plano_de_acao, atualizado_pela_coordenacao_em)
    ON operacional.fila_intervencao TO coordenacao_academica;
