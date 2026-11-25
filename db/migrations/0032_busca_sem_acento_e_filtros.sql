-- ============================================================================
-- Migração 0032: FTS sem acento, pesos (título > conteúdo) e índice de metadados
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

-- Configuração de busca textual que ignora acento (unaccent, depois o radical em português). É a do
-- ts_headline: ele normaliza o texto do documento sem alterar o que é exibido, e o realce funciona com
-- e sem acento dos dois lados ("evasao" realça "evasão", "ciência" realça "CIENCIA"). O dicionário
-- unaccent fica no esquema da extensão (public no Docker, extensions no Supabase), achado pelo catálogo.
DO $$
DECLARE
    esquema_unaccent text;
BEGIN
    SELECT n.nspname INTO esquema_unaccent
    FROM pg_ts_dict d JOIN pg_namespace n ON n.oid = d.dictnamespace
    WHERE d.dictname = 'unaccent';
    IF NOT EXISTS (SELECT 1 FROM pg_ts_config c JOIN pg_namespace n ON n.oid = c.cfgnamespace
                   WHERE n.nspname = 'busca' AND c.cfgname = 'portugues_sem_acento') THEN
        CREATE TEXT SEARCH CONFIGURATION busca.portugues_sem_acento (COPY = pg_catalog.portuguese);
    END IF;
    EXECUTE format(
        'ALTER TEXT SEARCH CONFIGURATION busca.portugues_sem_acento '
        'ALTER MAPPING FOR hword, hword_part, word WITH %I.unaccent, pg_catalog.portuguese_stem',
        esquema_unaccent);
END
$$;

COMMENT ON TEXT SEARCH CONFIGURATION busca.portugues_sem_acento IS
  'portuguese com unaccent antes do radical: usada pelo ts_headline para realçar com e sem acento.';

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
COMMENT ON INDEX busca.documentos_texto_busca IS
  'Busca em texto completo (@@) da busca híbrida, sobre título e conteúdo sem acento.';
COMMENT ON INDEX busca.documentos_metadados_gin IS
  'Acelera filtros facetados sobre busca.documentos.metadados (campus, turno, área, classificação, ano).';
