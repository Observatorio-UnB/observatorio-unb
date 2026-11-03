-- ============================================================================
-- Migração 0025: gold.dim_curso como dimensão de variação lenta (SCD tipo 2)
--
-- A carga sobrescrevia os atributos do curso (ON CONFLICT (nome_curso) DO UPDATE). Cada versão
-- nova do catálogo de cursos vale por cima da anterior (ADR 0021), e um curso pode mudar de
-- unidade responsável, de área, de grau (bacharelado, licenciatura ou MISTO, ADR 0004) ou virar
-- curso-tronco (ADR 0022). A sobrescrita reescrevia o passado sem deixar rastro.
-- Agora cada mudança de atributo rastreado fecha a versão vigente e abre uma nova:
--
--   - tipo 2 (nova versão): grau_academico, categoria_grau, area_conhecimento, departamento,
--     is_tronco_abi;
--   - tipo 1 (sobrescreve a versão atual): id_curso_origem, ponteiro técnico para a matriz.
--
-- A vigência é o tempo de processamento: o portal só publica os atributos atuais, sem data de
-- mudança. A primeira versão de cada curso vale desde a fundação da UnB (21/04/1962), uma data
-- fixa para o banco local e o Supabase terem a mesma chave (nome_curso, vigente_de). As versões
-- seguintes começam na carga que observou a mudança. Regras em src/db/povoar_dimensional.py e
-- no ADR 0028.
-- ============================================================================

-- O default é o início da série: as linhas que já estavam na tabela, e todo curso inserido sem
-- vigência, viram a primeira versão.
ALTER TABLE gold.dim_curso
  ADD COLUMN IF NOT EXISTS vigente_de  TIMESTAMPTZ NOT NULL DEFAULT '1962-04-21 00:00:00-03',
  ADD COLUMN IF NOT EXISTS vigente_ate TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS is_atual    BOOLEAN NOT NULL DEFAULT true;

ALTER TABLE gold.dim_curso DROP CONSTRAINT IF EXISTS dim_curso_nome_curso_key;
ALTER TABLE gold.dim_curso
  ADD CONSTRAINT uk_dim_curso_versao UNIQUE (nome_curso, vigente_de),
  ADD CONSTRAINT ck_dim_curso_vigencia CHECK (vigente_ate IS NULL OR vigente_ate > vigente_de),
  ADD CONSTRAINT ck_dim_curso_atual CHECK (is_atual = (vigente_ate IS NULL)),
  -- Uma versão atual por curso. Adiada para o fim da transação: a sincronização com o Supabase
  -- fecha a versão antiga e insere a nova no mesmo INSERT ... ON CONFLICT, em qualquer ordem.
  ADD CONSTRAINT ex_dim_curso_uma_atual EXCLUDE USING btree (nome_curso WITH =) WHERE (is_atual)
    DEFERRABLE INITIALLY DEFERRED;

CREATE INDEX IF NOT EXISTS idx_dim_curso_atual ON gold.dim_curso (nome_curso) WHERE is_atual;

COMMENT ON TABLE gold.dim_curso IS
  'Dimensão de cursos, SCD tipo 2: uma linha por versão dos atributos de classificação de um curso canônico. '
  'Chave natural: nome_curso; versão: (nome_curso, vigente_de). A versão atual tem is_atual e vigente_ate nulo. '
  'Mudança em grau, categoria, área, departamento ou tronco ABI abre versão nova; id_curso_origem é sobrescrito (tipo 1).';
COMMENT ON COLUMN gold.dim_curso.vigente_de IS
  'Início da versão: a carga que observou os atributos. A primeira versão de cada curso vale desde 21/04/1962 (fundação da UnB).';
COMMENT ON COLUMN gold.dim_curso.vigente_ate IS
  'Fim da versão: a carga que observou a mudança. Nulo na versão atual.';
COMMENT ON COLUMN gold.dim_curso.is_atual IS
  'Versão vigente hoje. Os fatos são recriados a cada carga e apontam para ela.';

-- A view do painel passa a ler só a versão atual. No Supabase nada é apagado: o fato da versão
-- fechada continua lá, e sem o filtro o curso apareceria duas vezes.
DROP MATERIALIZED VIEW IF EXISTS gold.mv_dashboard_executivo;

CREATE MATERIALIZED VIEW gold.mv_dashboard_executivo AS
SELECT
    c.sk_curso,
    c.id_curso_origem,
    c.nome_curso,
    c.area_conhecimento,
    c.categoria_grau,
    camp.campus,
    f.total_ingressantes,
    f.total_formados,
    f.total_evadidos,
    f.total_ainda_ativos,
    f.taxa_formatura_pct,
    f.taxa_evasao_pct,
    f.formados_tempo_ideal_pct,
    f.atraso_medio_semestres,
    f.indice_retencao_critica,
    f.classificacao_retencao,
    COALESCE(fa.total_ativos, 0) AS ativos_hoje_total,
    COALESCE(fa.ativos_acima_prazo_ideal, 0) AS ativos_hoje_atrasados,
    COALESCE(fa.pct_acima_prazo_ideal, 0.0) AS pct_ativos_hoje_atrasados,
    now() AS gerado_em
FROM gold.fato_retencao_curso f
JOIN gold.dim_curso c ON f.sk_curso = c.sk_curso
JOIN gold.dim_campus camp ON f.sk_campus = camp.sk_campus
LEFT JOIN gold.fato_alunos_ativos fa ON c.sk_curso = fa.sk_curso
WHERE c.is_tronco_abi = false
  AND c.is_atual;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_executivo_sk ON gold.mv_dashboard_executivo (sk_curso, campus);

COMMENT ON MATERIALIZED VIEW gold.mv_dashboard_executivo IS
  'Grão: um registro por curso canônico terminal (sem cursos-tronco), na versão atual da gold.dim_curso, o mesmo de '
  'gold.fato_retencao_curso, com os ativos do snapshot de gold.fato_alunos_ativos ao lado. Pré-computada para o painel; '
  'atualizada por gold.atualizar_mv_dashboard_executivo() (REFRESH CONCURRENTLY).';

GRANT SELECT ON gold.mv_dashboard_executivo TO observatorio_leitura;
