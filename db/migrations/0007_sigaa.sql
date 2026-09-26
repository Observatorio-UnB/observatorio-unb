-- SIGAA como fonte principal de discentes de graduação, unido ao SIGRA.
-- O SIGRA só tem vínculos encerrados até a migração (2020/1); o SIGAA, os ativos na
-- migração e os posteriores, com a situação atual. A silver passa a guardar as duas
-- bases numa tabela só, identificadas pela coluna fonte.

CREATE TABLE bronze.sigaa_discentes (
  aluno                 TEXT,
  nivel                 TEXT,
  curso                 TEXT,
  unidade               TEXT,
  ano_ingresso          TEXT,
  forma_ingresso        TEXT,
  cota_ingresso         TEXT,
  data_nascimento       TEXT,
  sexo                  TEXT,
  raca_cor              TEXT,
  status_aluno          TEXT,
  data_registro_diploma TEXT,
  bolsa                 TEXT,
  _carregado_em         TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE bronze.sigaa_discentes IS
  'SIGAA (sigaa.csv, mesmo pacote do SIGRA). Uma linha por vínculo, todos os níveis, com a situação atual do vínculo. Separador ";", UTF-8. ano_ingresso vem com separador de milhar ("2,010"). Contém quase-identificadores (nascimento, sexo, raça/cor).';
COMMENT ON COLUMN bronze.sigaa_discentes.aluno IS 'Pseudônimo do discente. Não casa com o pseudônimo do SIGRA.';
COMMENT ON COLUMN bronze.sigaa_discentes.status_aluno IS 'Situação do vínculo na data do extrato: ATIVO, ATIVO - FORMANDO, TRANCADO, CONCLUÍDO, FORMADO, CANCELADO, NÃO CADASTRADO...';
COMMENT ON COLUMN bronze.sigaa_discentes.data_registro_diploma IS 'Data de registro do diploma, dd/mm/aaaa. Única pista do momento da conclusão.';

ALTER TABLE silver.sigra_graduacao RENAME TO discentes_graduacao;
ALTER TABLE silver.discentes_graduacao RENAME COLUMN data_registro_livro TO data_registro_diploma;
-- Linhas já carregadas são todas do SIGRA: os defaults valem para elas e saem em seguida.
-- MUDANCA_INTERNA e EVASAO_DESLIGAMENTO viram EVASAO (saída do curso sem diploma).
ALTER TABLE silver.discentes_graduacao
  DROP CONSTRAINT sigra_graduacao_tipo_saida_grupo_check,
  ADD COLUMN fonte TEXT NOT NULL DEFAULT 'SIGRA' CHECK (fonte IN ('SIGRA', 'SIGAA')),
  ADD COLUMN status_aluno TEXT,
  ADD COLUMN periodo_saida_estimado BOOLEAN NOT NULL DEFAULT false,
  ALTER COLUMN opcao DROP NOT NULL,
  ALTER COLUMN periodo_saida DROP NOT NULL;
UPDATE silver.discentes_graduacao SET tipo_saida_grupo = 'EVASAO'
  WHERE tipo_saida_grupo IN ('EVASAO_DESLIGAMENTO', 'MUDANCA_INTERNA');
ALTER TABLE silver.discentes_graduacao
  ALTER COLUMN fonte DROP DEFAULT,
  ALTER COLUMN periodo_saida_estimado DROP DEFAULT,
  ADD CONSTRAINT discentes_graduacao_tipo_saida_grupo_check
    CHECK (tipo_saida_grupo IN ('FORMATURA', 'EVASAO', 'ATIVO', 'OUTROS')),
  ADD CHECK ((fonte = 'SIGRA') = (opcao IS NOT NULL AND periodo_saida IS NOT NULL));

COMMENT ON TABLE silver.discentes_graduacao IS
  'Vínculos de graduação do SIGRA (encerrados até 2020/1) e do SIGAA (ativos na migração ou posteriores). Uma linha por vínculo; os pseudônimos das duas bases não se ligam entre si.';
COMMENT ON COLUMN silver.discentes_graduacao.id IS 'Chave substituta.';
COMMENT ON COLUMN silver.discentes_graduacao.fonte IS 'Sistema de origem: SIGRA (legado) ou SIGAA (atual).';
COMMENT ON COLUMN silver.discentes_graduacao.opcao IS 'Código da opção de ingresso no SIGRA. Nulo no SIGAA.';
COMMENT ON COLUMN silver.discentes_graduacao.departamento IS 'Unidade acadêmica como na fonte (departamento no SIGRA, unidade no SIGAA).';
COMMENT ON COLUMN silver.discentes_graduacao.forma_saida IS 'Motivo do encerramento do vínculo (SIGRA). Nulo no SIGAA, que não publica o motivo.';
COMMENT ON COLUMN silver.discentes_graduacao.status_aluno IS 'Situação do vínculo no extrato do SIGAA. Nulo no SIGRA.';
COMMENT ON COLUMN silver.discentes_graduacao.data_registro_diploma IS 'Registro do diploma (data_registro_livro no SIGRA). Nulo para quem não se formou.';
COMMENT ON COLUMN silver.discentes_graduacao.periodo_saida IS 'Período de saída AAAAS publicado pelo SIGRA. Nulo no SIGAA.';
COMMENT ON COLUMN silver.discentes_graduacao.tipo_saida_grupo IS 'FORMATURA; EVASAO (saída sem diploma, inclusive mudança de curso: o SIGAA só marca CANCELADO, sem motivo); ATIVO (ativo, formando ou trancado no SIGAA); OUTROS (anulação de registro, falecimento, não cadastrado...).';
COMMENT ON COLUMN silver.discentes_graduacao.ano_saida IS 'Ano da saída: de periodo_saida no SIGRA; estimado pela data do diploma no SIGAA.';
COMMENT ON COLUMN silver.discentes_graduacao.semestre_saida IS 'Semestre da saída: 1, 2 ou 0 (verão, só SIGRA). Estimado pela data do diploma no SIGAA.';
COMMENT ON COLUMN silver.discentes_graduacao.periodo_saida_estimado IS 'Verdadeiro quando ano/semestre de saída vêm da data de registro do diploma (SIGAA). A regra acerta 94,6% no SIGRA; no calendário da pandemia pode errar em 1 semestre.';

ALTER TABLE gold.retencao_cursos_unb
  ADD COLUMN total_ainda_ativos INTEGER NOT NULL DEFAULT 0 CHECK (total_ainda_ativos >= 0),
  ADD CHECK (total_formados + total_evadidos_desligados + total_ainda_ativos <= total_discentes_registrados);
ALTER TABLE gold.retencao_cursos_unb ALTER COLUMN total_ainda_ativos DROP DEFAULT;
COMMENT ON TABLE gold.retencao_cursos_unb IS
  'Retenção, formatura e evasão por curso, sobre as coortes de ingresso com pelo menos 8 anos de acompanhamento (ver ANOS_MATURACAO_COORTE em build_gold.py). Uma linha por curso canônico de graduação; cursos com bacharelado e licenciatura sob o mesmo nome ficam numa linha só (categoria_grau = MISTO). Só entram cursos com 5 ou mais discentes.';
COMMENT ON COLUMN gold.retencao_cursos_unb.curso IS 'Nome canônico do curso após a harmonização SIGRA/SIGAA -> matriz curricular (sem acento, maiúsculas).';
COMMENT ON COLUMN gold.retencao_cursos_unb.departamento IS 'Departamento de vinculação, como registrado no sistema acadêmico.';
COMMENT ON COLUMN gold.retencao_cursos_unb.total_discentes_registrados IS 'Vínculos do curso nas coortes analisadas (SIGRA + SIGAA). Mínimo 5 (supressão de grupos pequenos, k-anonimato).';
COMMENT ON COLUMN gold.retencao_cursos_unb.total_evadidos_desligados IS 'Vínculos encerrados sem diploma: abandono, jubilamento, desligamento, mudança de curso ou cancelamento no SIGAA.';
COMMENT ON COLUMN gold.retencao_cursos_unb.total_ainda_ativos IS 'Vínculos das coortes analisadas ainda ativos ou trancados no extrato do SIGAA.';
COMMENT ON COLUMN gold.regras_harmonizacao_canonicas.origem_sigra IS 'Nome normalizado do curso na origem (SIGRA, SIGAA ou PIBIC).';
COMMENT ON COLUMN gold.regras_harmonizacao_canonicas.discentes_impactados IS 'Vínculos de SIGRA + SIGAA reclassificados por esta regra.';
