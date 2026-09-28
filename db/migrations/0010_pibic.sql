-- PIBIC: valor da bolsa pela tabela de vigências do CNPq e minimização dos dados pessoais.
--
-- 1. O valor da bolsa deixa de ser 400/700 fixo por ano de edital: passa a somar, mês a mês
--    da vigência, o valor da bolsa IC em vigor no CNPq (vigências lidas da página oficial,
--    ADR 0023). O ciclo 2022 atravessa o reajuste de fev/2023.
-- 2. A ingestão grava só as colunas usadas pela análise (LGPD, art. 6º, III, ADR 0020): nome
--    e matrícula do discente e nome do orientador não chegam mais ao disco nem ao banco. Os
--    ids, sempre zerados na fonte, também saem. Na silver, a matrícula mascarada e o
--    orientador, que nenhuma análise usava, deixam de existir.

ALTER TABLE bronze.bolsistas_iniciacao_cientifica
  DROP COLUMN IF EXISTS id_discente,
  DROP COLUMN IF EXISTS matricula,
  DROP COLUMN IF EXISTS discente,
  DROP COLUMN IF EXISTS codigo_projeto,
  DROP COLUMN IF EXISTS id_projeto_pesquisa,
  DROP COLUMN IF EXISTS id_orientador,
  DROP COLUMN IF EXISTS orientador,
  DROP COLUMN IF EXISTS categoria,
  DROP COLUMN IF EXISTS id_grupo_pesquisa,
  DROP COLUMN IF EXISTS grupo_pesquisa,
  DROP COLUMN IF EXISTS id_unidade;
COMMENT ON TABLE bronze.bolsistas_iniciacao_cientifica IS
  'Bolsistas de iniciação científica PIBIC/PIVIC (bolsistas-de-iniciacao-cientifica.csv). Uma linha por plano de trabalho. O arquivo publicado traz nome e matrícula do discente e nome do orientador, descartados em memória pela ingestão: só estas colunas são gravadas (UTF-8, separador ",").';

ALTER TABLE silver.pibic_bolsistas
  DROP COLUMN IF EXISTS matricula_mascarada,
  DROP COLUMN IF EXISTS orientador_norm;
COMMENT ON COLUMN silver.pibic_bolsistas.valor_bolsa_anual_estimado IS
  'Soma, mês a mês de inicio a fim (em geral 12 meses), do valor da bolsa IC em vigor no CNPq: R$ 400 até jan/2023, R$ 700 desde fev/2023 (vigências em data/bronze/cnpq_valor_bolsa_ic.json). Zero para voluntária.';
