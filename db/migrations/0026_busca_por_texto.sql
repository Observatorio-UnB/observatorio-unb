-- ============================================================================
-- Migração 0026: Busca por texto em busca.documentos (busca híbrida)
--
-- O embedding capta o tema, mas erra sigla, número, nome exato e termo técnico ("ADR 0028", "SLA de
-- frescor", o título de um plano de IC). src/busca/buscar.py combina a busca vetorial com duas
-- buscas por texto:
--
--   - texto completo em português no título e no conteúdo (texto_busca, abaixo): acha o trecho da
--     documentação que usa os termos da pergunta;
--   - trigramas no título (pg_trgm, migração 0011): acha nome de curso, título de plano de IC e
--     número de ADR mesmo com acento ou grafia diferente.
--
-- texto_busca é gerada e gravada (STORED): calcular to_tsvector na hora, para ordenar milhares de
-- trechos que casam com uma palavra comum, levava 280 ms. A sincronização com o Supabase ignora
-- colunas geradas (sincronizar_supabase.py), e o destino calcula a sua.
-- Trigrama no conteúdo foi descartado: Seq Scan de 860 ms numa consulta comum.
-- ============================================================================

ALTER TABLE busca.documentos
    ADD COLUMN IF NOT EXISTS texto_busca tsvector
    GENERATED ALWAYS AS (to_tsvector('portuguese'::regconfig, titulo || ' ' || conteudo)) STORED;

CREATE INDEX IF NOT EXISTS documentos_texto_busca
    ON busca.documentos USING gin (texto_busca);

CREATE INDEX IF NOT EXISTS documentos_titulo_trgm
    ON busca.documentos USING gin (titulo gin_trgm_ops);

COMMENT ON COLUMN busca.documentos.texto_busca IS
  'Título e conteúdo em texto completo (português), gerado. Uma das listas da busca híbrida de src/busca/buscar.py.';
COMMENT ON INDEX busca.documentos_texto_busca IS
  'Busca em texto completo (@@) da busca híbrida.';
COMMENT ON INDEX busca.documentos_titulo_trgm IS
  'Busca por trigramas no título (<%) da busca híbrida.';
