-- ============================================================================
-- Migração 0029: FTS sem acento, pesos (título > conteúdo) e índice de metadados
--
-- Corrige duas limitações da migração 0026:
--   1. Cursos e projetos PIBIC vêm sem acento da Silver, enquanto consultas do
--      usuário vêm com acento ("ciência", "saúde", "evasão"). Normalizar com
--      unaccent() na coluna gerada texto_busca alinha ambos os lados no índice GIN.
--   2. setweight(..., 'A') no título e 'B' no conteúdo prioriza matches no título
--      no ts_rank_cd.
--   3. Índice GIN em metadados acelera filtros facetados (campus, turno, ano, etc.)
--      combinados com busca vetorial (hnsw.iterative_scan).
--
-- A função wrapper busca.sem_acento() usa search_path = public, extensions para
-- funcionar tanto no PostgreSQL local (Docker) quanto no Supabase.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE OR REPLACE FUNCTION busca.sem_acento(texto TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
SET search_path = public, extensions
AS $$
    SELECT unaccent('unaccent'::regdictionary, texto);
$$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'observatorio_leitura') THEN
        GRANT EXECUTE ON FUNCTION busca.sem_acento(TEXT) TO observatorio_leitura;
    END IF;
END
$$;

DROP INDEX IF EXISTS busca.documentos_texto_busca;

ALTER TABLE busca.documentos
    DROP COLUMN IF EXISTS texto_busca;

ALTER TABLE busca.documentos
    ADD COLUMN texto_busca tsvector
    GENERATED ALWAYS AS (
        setweight(to_tsvector('portuguese'::regconfig, busca.sem_acento(coalesce(titulo, ''))), 'A') ||
        setweight(to_tsvector('portuguese'::regconfig, busca.sem_acento(coalesce(conteudo, ''))), 'B')
    ) STORED;

CREATE INDEX documentos_texto_busca
    ON busca.documentos USING gin (texto_busca);

CREATE INDEX IF NOT EXISTS documentos_metadados_gin
    ON busca.documentos USING gin (metadados jsonb_path_ops);

COMMENT ON FUNCTION busca.sem_acento(TEXT) IS
  'Wrapper IMMUTABLE de unaccent() compatível com PostgreSQL local e Supabase para colunas geradas e consultas FTS.';
COMMENT ON COLUMN busca.documentos.texto_busca IS
  'Título (peso A) e conteúdo (peso B) sem acento em texto completo (português), gerado automaticamente.';
COMMENT ON INDEX busca.documentos_metadados_gin IS
  'Acelera filtros facetados sobre busca.documentos.metadados (campus, turno, área, classificação, ano).';
