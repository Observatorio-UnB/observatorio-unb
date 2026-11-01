-- ============================================================================
-- Migração 0023: Granularidade declarada dos fatos da gold
--
-- O grão de cada fato fica escrito no catálogo (COMMENT ON TABLE, lido pelo dicionário de dados)
-- e imposto por uma chave única igual a ele. Análise dos níveis de grão avaliados em
-- docs/arquitetura/02_MODELAGEM_DIMENSIONAL_E_MATRIZ_KIMBALL.md, seção 4.
--
-- gold.fato_retencao_curso tinha UNIQUE (sk_curso, sk_campus), mas o grão é o curso: o campus é
-- atributo do curso canônico (MULTICAMPUS quando o nome é oferecido em mais de um campus). A
-- chave antiga aceitava o mesmo curso em dois campi, e a view do painel o mostraria duas vezes.
-- Isso acontece no Supabase: a sincronização não apaga linhas, e um curso que mudasse de campus
-- ganharia uma segunda. A chave passa a ser só sk_curso, e a sincronização (sincronizar_supabase.py)
-- passa a atualizar o campus pela mesma chave.
-- ============================================================================

-- Uma linha por curso antes de criar a chave. Localmente o fato é recriado a cada carga e não tem
-- duplicata; num banco sincronizado, fica a linha atualizada por último.
DELETE FROM gold.fato_retencao_curso f
 USING gold.fato_retencao_curso g
 WHERE f.sk_curso = g.sk_curso
   AND (f.atualizado_em, f.id_fato) < (g.atualizado_em, g.id_fato);

ALTER TABLE gold.fato_retencao_curso DROP CONSTRAINT IF EXISTS uk_fato_curso;
ALTER TABLE gold.fato_retencao_curso ADD CONSTRAINT uk_fato_retencao_grao UNIQUE (sk_curso);

COMMENT ON TABLE gold.fato_retencao_curso IS
  'Grão: um registro por curso canônico, agregando as coortes maduras (ingresso até o último ano da base menos 8). '
  'Chave do grão: UNIQUE (sk_curso). O campus (sk_campus) é atributo do curso, e não parte do grão. '
  'Contagens (total_*) são aditivas entre cursos; taxas, % no tempo ideal, atraso médio e IRC não são: '
  'para agregar, recalcular a partir das contagens. Só entram cursos com k >= 5. '
  'Mesmas regras de gold.retencao_cursos_unb.';

COMMENT ON TABLE gold.fato_alunos_ativos IS
  'Grão: snapshot periódico, um registro por curso canônico no semestre de referência da lista de ativos mais '
  'recente (sk_tempo_referencia). Chave do grão: UNIQUE (sk_curso): a carga substitui o snapshot, '
  'sem histórico. Contagens são aditivas entre cursos, mas não entre semestres (estoque). Só entram cursos com k >= 5.';

COMMENT ON TABLE gold.fato_pibic_perfil IS
  'Grão: um registro por curso canônico e perfil social do bolsista (dim_perfil_social), somando todos os editais '
  'publicados. Chave do grão: UNIQUE (sk_curso, sk_perfil). Contagens e valor investido são aditivos entre cursos e '
  'perfis. Só entram grupos com 5 ou mais planos (k-anonimato).';

COMMENT ON MATERIALIZED VIEW gold.mv_dashboard_executivo IS
  'Grão: um registro por curso canônico terminal (sem cursos-tronco), o mesmo de gold.fato_retencao_curso, '
  'com os ativos do snapshot de gold.fato_alunos_ativos ao lado. Pré-computada para o painel; atualizada por '
  'gold.atualizar_mv_dashboard_executivo() (REFRESH CONCURRENTLY).';
