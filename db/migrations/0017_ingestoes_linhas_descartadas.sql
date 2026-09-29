-- ============================================================================
-- Migração 0017: Rastreamento de Linhas Descartadas na Ingestão Bronze
--
-- Registra quantas linhas malformadas foram descartadas pelo leitor de CSV (on_bad_lines),
-- garantindo rastreabilidade e integridade para auditoria.
-- ============================================================================

ALTER TABLE bronze.ingestoes ADD COLUMN IF NOT EXISTS linhas_descartadas INTEGER NOT NULL DEFAULT 0;

COMMENT ON COLUMN bronze.ingestoes.linhas_descartadas IS
  'Linhas malformadas descartadas durante a leitura do CSV.';
