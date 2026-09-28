-- O catálogo de cursos passa a juntar todas as versões publicadas, com a mais recente
-- valendo; uma versão nova entra sem mudança de esquema. As versões a partir de 2023 deixam
-- de listar alguns códigos (ex.: 414162, um dos dois cadastros de Jornalismo em 2022) e de
-- trazer unidade_responsavel. Nomes de curso perdem o prefixo do antigo curso guarda-chuva
-- (Comunicação Social, Ciências Sociais): "COMUNICAÇÃO SOCIAL - JORNALISMO" vira JORNALISMO.

ALTER TABLE bronze.cursos_graduacao
  ADD COLUMN id_servidor    TEXT,
  ADD COLUMN arquivo_origem TEXT,
  ADD COLUMN publicado_em   TEXT;
COMMENT ON TABLE bronze.cursos_graduacao IS
  'Catálogo de cursos de graduação: todas as versões publicadas no pacote cursos-de-graduacao, empilhadas. Uma linha por curso por versão.';
COMMENT ON COLUMN bronze.cursos_graduacao.id_servidor IS 'Identificador do coordenador como servidor. Só nas versões de 2023 em diante.';
COMMENT ON COLUMN bronze.cursos_graduacao.arquivo_origem IS 'Arquivo do portal de onde veio a linha (ex.: cursos-de-graduao-08-2024.csv).';
COMMENT ON COLUMN bronze.cursos_graduacao.publicado_em IS 'Data de publicação do arquivo no CKAN (AAAA-MM-DD).';

-- Linhas já carregadas vêm do catálogo de 2022, que era o vigente: o default vale para elas.
ALTER TABLE silver.cursos_graduacao
  ADD COLUMN no_catalogo_vigente BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE silver.cursos_graduacao ALTER COLUMN no_catalogo_vigente DROP DEFAULT;
COMMENT ON TABLE silver.cursos_graduacao IS
  'Catálogo de cursos de graduação consolidado: um registro por id_curso, com o valor da versão mais recente em cada campo e, se vazio nela, o da última versão que o tinha.';
COMMENT ON COLUMN silver.cursos_graduacao.no_catalogo_vigente IS 'Falso para código de curso que não está na versão mais recente do catálogo; mantido porque pode ter alunos nas coortes analisadas.';
COMMENT ON COLUMN silver.cursos_graduacao.nome_curso_norm IS 'Nome do curso sem acento, em maiúsculas, sem o prefixo de curso guarda-chuva (Comunicação Social, Ciências Sociais).';
COMMENT ON COLUMN silver.cursos_graduacao.unidade_responsavel IS 'Unidade acadêmica responsável, como na fonte. Só o catálogo de 2022 traz este campo; cursos criados depois ficam sem.';

-- Nome com oferta diurna e noturna deixa de receber um turno escolhido pela ordem das linhas.
ALTER TABLE gold.retencao_cursos_unb
  DROP CONSTRAINT retencao_cursos_unb_turno_check,
  ADD CONSTRAINT retencao_cursos_unb_turno_check
    CHECK (turno IN ('DIURNO', 'NOTURNO', 'INTEGRAL', 'DIURNO E NOTURNO'));
COMMENT ON COLUMN gold.retencao_cursos_unb.turno IS 'DIURNO, NOTURNO, INTEGRAL ou DIURNO E NOTURNO (nome com as duas ofertas; nenhuma fonte liga o discente à oferta). Matutino e vespertino são unificados em DIURNO.';
COMMENT ON COLUMN gold.retencao_cursos_unb.campus IS 'Campus de oferta; MULTICAMPUS quando o mesmo nome é oferecido em mais de um campus.';
