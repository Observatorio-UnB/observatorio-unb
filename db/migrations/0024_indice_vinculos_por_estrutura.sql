-- ============================================================================
-- Migração 0024: Índice dos vínculos pela estrutura curricular
--
-- O detalhamento de um curso (ex.: distribuição de semestres até a formatura) parte do curso
-- canônico em silver.estruturas_curriculares e chega aos vínculos por id_estrutura, que não
-- tinha índice: o PostgreSQL varria as partições inteiras para devolver algumas centenas de
-- linhas (docs/explain/antes_distribuicao_formatura_por_curso.txt).
--
-- Colunas de igualdade antes da de intervalo: id_estrutura e tipo_saida_grupo, depois
-- ano_ingresso. semestres_permanencia_valida vai no INCLUDE para a consulta não ir à heap
-- (Index Only Scan quando o mapa de visibilidade está em dia, depois do autovacuum).
--
-- Criado na tabela particionada, o índice nasce em cada partição, inclusive nas que
-- silver.provisionar_particoes_movimentacoes() criar depois (0019).
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_mov_estrutura_saida_ano
    ON silver.movimentacoes_vinculos (id_estrutura, tipo_saida_grupo, ano_ingresso)
    INCLUDE (semestres_permanencia_valida);

COMMENT ON INDEX silver.idx_mov_estrutura_saida_ano IS
  'Vínculos de um curso canônico (via id_estrutura) por tipo de saída e coorte. Ver docs/explain/.';
