-- ============================================================================
-- Migração 0018: API pública (somente leitura) para o painel do GitHub Pages
--
-- O painel publicado roda no navegador (stlite) e não fala com o PostgreSQL: consome o
-- Supabase pela API REST (PostgREST) com a chave pública `anon`. Em vez de expor os
-- esquemas gold e busca, a API fica em duas funções no esquema public:
--
--   observatorio_gold()    o mesmo snapshot JSON de src/db/exportar_gold.py (só gold, k >= 5);
--   observatorio_buscar()  os documentos de busca.documentos mais próximos de um vetor,
--                          sem devolver o embedding.
--
-- SECURITY DEFINER: o papel `anon` não ganha acesso a nenhuma tabela, só a estas duas
-- funções. bronze e silver (dado pessoal) continuam fora de alcance.
-- ============================================================================

CREATE OR REPLACE FUNCTION public.observatorio_gold() RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, gold
AS $$
  SELECT jsonb_build_object(
    'gerado_em', to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"+00:00"'),
    'tabelas', jsonb_build_object(
      'retencao_cursos_unb', (
        SELECT coalesce(jsonb_agg(to_jsonb(t) - '_ordem' - '_carregado_em' ORDER BY (to_jsonb(t) ->> '_ordem')::int), '[]'::jsonb)
        FROM gold.retencao_cursos_unb t),
      'ativos_hoje_cursos_unb', (
        SELECT coalesce(jsonb_agg(to_jsonb(t) - '_ordem' - '_carregado_em' ORDER BY (to_jsonb(t) ->> '_ordem')::int), '[]'::jsonb)
        FROM gold.ativos_hoje_cursos_unb t),
      'pibic_social_unb', (
        SELECT coalesce(jsonb_agg(to_jsonb(t) - '_ordem' - '_carregado_em' ORDER BY (to_jsonb(t) ->> '_ordem')::int), '[]'::jsonb)
        FROM gold.pibic_social_unb t),
      'regras_harmonizacao_canonicas', (
        SELECT coalesce(jsonb_agg(to_jsonb(t) - '_ordem' - '_carregado_em' ORDER BY (to_jsonb(t) ->> '_ordem')::int), '[]'::jsonb)
        FROM gold.regras_harmonizacao_canonicas t),
      'inep_benchmark_cursos_unb', (
        SELECT coalesce(jsonb_agg(to_jsonb(t) - '_ordem' - '_carregado_em' ORDER BY (to_jsonb(t) ->> '_ordem')::int), '[]'::jsonb)
        FROM gold.inep_benchmark_cursos_unb t)
    ),
    'relatorios', (SELECT coalesce(jsonb_object_agg(nome, conteudo), '{}'::jsonb) FROM gold.relatorios)
  )
$$;

-- Só entram documentos vetorizados com o gte-small, o modelo da Edge Function (supabase/functions/buscar):
-- vetores de outro modelo estão em outro espaço e dariam resultado sem sentido. Trocar de modelo
-- exige uma migração nova. `extensions` é onde o Supabase instala o pgvector; no banco local ele fica em public.
CREATE OR REPLACE FUNCTION public.observatorio_buscar(vetor text, tipo text DEFAULT NULL, k integer DEFAULT 8)
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public, extensions, busca
AS $$
DECLARE
  consulta vector(384) := vetor::vector(384);
BEGIN
  IF k IS NULL OR k < 1 OR k > 30 THEN
    RAISE EXCEPTION 'k deve estar entre 1 e 30';
  END IF;
  IF tipo IS NOT NULL AND tipo NOT IN ('curso', 'projeto_pibic', 'documentacao') THEN
    RAISE EXCEPTION 'tipo inválido: %', tipo;
  END IF;
  -- Com filtro por tipo, o HNSW sozinho devolveria vizinhos de todos os tipos e o WHERE
  -- descartaria a maioria; a varredura iterativa (pgvector >= 0.8) completa os k resultados.
  PERFORM set_config('hnsw.iterative_scan', 'strict_order', true);
  RETURN coalesce((
    SELECT jsonb_agg(r ORDER BY r.similaridade DESC)
    FROM (
      SELECT d.tipo, d.titulo, d.conteudo, d.metadados,
             round((1 - (d.embedding <=> consulta))::numeric, 4) AS similaridade
      FROM busca.documentos d
      WHERE d.modelo = 'Supabase/gte-small'
        AND (observatorio_buscar.tipo IS NULL OR d.tipo = observatorio_buscar.tipo)
      ORDER BY d.embedding <=> consulta
      LIMIT k
    ) r
  ), '[]'::jsonb);
END
$$;

COMMENT ON FUNCTION public.observatorio_gold() IS
  'Snapshot da gold (mesmo formato de export/gold.json) para o painel publicado. Só agregados, k >= 5.';
COMMENT ON FUNCTION public.observatorio_buscar(text, text, integer) IS
  'Busca semântica: os k documentos mais próximos de `vetor` (literal pgvector de 384 dimensões). Nunca devolve o embedding.';

REVOKE ALL ON FUNCTION public.observatorio_gold() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.observatorio_buscar(text, text, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.observatorio_gold() TO observatorio_leitura;
GRANT EXECUTE ON FUNCTION public.observatorio_buscar(text, text, integer) TO observatorio_leitura;

-- `anon` só existe no Supabase (é o papel da chave pública da API).
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    GRANT EXECUTE ON FUNCTION public.observatorio_gold() TO anon;
    GRANT EXECUTE ON FUNCTION public.observatorio_buscar(text, text, integer) TO anon;
  END IF;
END
$$;
