-- Ajustes de esquema para a carga Silver 3NF -> Star Schema (src/db/povoar_silver_3nf.py e
-- src/db/povoar_dimensional.py).
--
-- 1. O curso canônico (o mesmo nome de gold.retencao_cursos_unb) é o da matriz curricular, não o
--    do catálogo: a matriz de COMUNICACAO SOCIAL aponta para o id_curso de JORNALISMO. A matriz
--    passa a guardar o nome canônico, e todo vínculo aponta para uma matriz.
-- 2. Nenhuma fonte publica o semestre de ingresso (SIGRA e extrato do SIGAA só têm o ano).
-- 3. pibic_projetos guarda o perfil social macro, origem de gold.dim_perfil_social.
-- 4. dim_perfil_social tem faixa_renda nula; sem NULLS NOT DISTINCT a recarga duplicaria linhas.
--
-- As tabelas 3NF são derivadas das tabelas silver da carga e recriadas por inteiro a cada
-- execução do povoamento: esvaziá-las aqui não perde dado.

TRUNCATE silver.pibic_projetos, silver.movimentacoes_vinculos, silver.estruturas_curriculares,
         silver.discentes, silver.cursos RESTART IDENTITY;

ALTER TABLE silver.estruturas_curriculares
  ADD COLUMN nome_curso_canonico TEXT NOT NULL UNIQUE;
COMMENT ON TABLE silver.estruturas_curriculares IS
  'Prazos e cargas horárias regulamentares por curso canônico (uma linha por matriz consolidada de silver.estrutura_curricular).';
COMMENT ON COLUMN silver.estruturas_curriculares.nome_curso_canonico IS
  'Nome canônico do curso, destino da harmonização SIGRA/SIGAA/PIBIC. Chave natural da gold.dim_curso.';
COMMENT ON COLUMN silver.estruturas_curriculares.id_curso IS
  'Curso do catálogo dono da matriz. Pode ter outro nome (a matriz de COMUNICACAO SOCIAL aponta para JORNALISMO).';

ALTER TABLE silver.movimentacoes_vinculos
  ALTER COLUMN semestre_ingresso DROP NOT NULL,
  ALTER COLUMN id_estrutura SET NOT NULL;
COMMENT ON COLUMN silver.movimentacoes_vinculos.semestre_ingresso IS
  'Sempre nulo hoje: SIGRA e o extrato do SIGAA só publicam o ano de ingresso.';
COMMENT ON COLUMN silver.movimentacoes_vinculos.id_estrutura IS
  'Matriz do curso canônico do vínculo, após a harmonização de nomes (gold.regras_harmonizacao_canonicas).';

ALTER TABLE silver.pibic_projetos
  ADD COLUMN perfil_social_macro TEXT;
COMMENT ON COLUMN silver.pibic_projetos.id_discente IS
  'Sempre nulo: a matrícula do bolsista não é gravada (0010_pibic.sql), então o plano não se liga ao discente.';
COMMENT ON COLUMN silver.pibic_projetos.id_curso IS
  'Curso do catálogo dono da matriz do curso canônico do bolsista. Nulo quando o curso do PIBIC não casa com nenhuma matriz.';

ALTER TABLE gold.dim_perfil_social
  DROP CONSTRAINT uk_dim_perfil_social,
  ADD CONSTRAINT uk_dim_perfil_social
    UNIQUE NULLS NOT DISTINCT (perfil_macro, categoria_cota, faixa_renda, is_cotista);
COMMENT ON TABLE gold.dim_perfil_social IS
  'Dimensão social e de ações afirmativas: combinações distintas de perfil observadas em silver.pibic_projetos.';

COMMENT ON TABLE gold.dim_curso IS
  'Dimensão de cursos canônicos de graduação. Chave natural nome_curso: a chave substituta sk_curso não muda quando entra curso novo.';
COMMENT ON COLUMN gold.dim_curso.id_curso_origem IS 'id_curso do catálogo dono da matriz (silver.estruturas_curriculares).';
COMMENT ON TABLE gold.fato_retencao_curso IS
  'Retenção por curso canônico, recalculada a partir de silver.movimentacoes_vinculos sobre as coortes maduras, com k >= 5. IRC, classificação, % no tempo ideal e atraso médio vêm de gold.retencao_cursos_unb (percentis calculados em build_gold.py).';
COMMENT ON TABLE gold.fato_alunos_ativos IS
  'Discentes ativos no semestre de referência por curso canônico, a partir de gold.ativos_hoje_cursos_unb (lista de ativos do SIGAA).';
