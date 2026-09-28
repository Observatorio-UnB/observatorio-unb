-- Fato de iniciação científica por curso canônico e perfil social: dá uso a gold.dim_perfil_social.
--
-- O plano de IC passa a guardar a matriz do curso canônico (id_estrutura), como o vínculo: o
-- id_curso sozinho não identifica o curso (a matriz de COMUNICACAO SOCIAL aponta para o id de
-- JORNALISMO). Os planos são recriados a cada povoamento, então a coluna nasce vazia.

ALTER TABLE silver.pibic_projetos
  ADD COLUMN id_estrutura INTEGER REFERENCES silver.estruturas_curriculares (id_estrutura);
COMMENT ON COLUMN silver.pibic_projetos.id_estrutura IS
  'Matriz do curso canônico do bolsista, após a harmonização de nomes. Nula quando o curso do PIBIC não casa com nenhuma matriz.';

CREATE TABLE gold.fato_pibic_perfil (
    id_fato                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sk_curso                INTEGER NOT NULL REFERENCES gold.dim_curso (sk_curso),
    sk_perfil               INTEGER NOT NULL REFERENCES gold.dim_perfil_social (sk_perfil),
    total_projetos          INTEGER NOT NULL CHECK (total_projetos >= 5), -- k-anonimato
    total_remuneradas       INTEGER NOT NULL CHECK (total_remuneradas >= 0),
    total_voluntarias       INTEGER NOT NULL CHECK (total_voluntarias >= 0),
    valor_total_investido   NUMERIC(14,2) NOT NULL CHECK (valor_total_investido >= 0),
    atualizado_em           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uk_fato_pibic_perfil UNIQUE (sk_curso, sk_perfil),
    CHECK (total_remuneradas + total_voluntarias <= total_projetos)
);
COMMENT ON TABLE gold.fato_pibic_perfil IS
  'Planos de iniciação científica por curso canônico e perfil social do bolsista (todos os editais). Só entram grupos com 5 ou mais planos (k-anonimato).';
COMMENT ON COLUMN gold.fato_pibic_perfil.total_projetos IS 'Planos de trabalho de IC do grupo. Mínimo 5.';
COMMENT ON COLUMN gold.fato_pibic_perfil.total_remuneradas IS 'Planos com bolsa remunerada (PIBIC).';
COMMENT ON COLUMN gold.fato_pibic_perfil.total_voluntarias IS 'Planos voluntários (PIVIC).';
COMMENT ON COLUMN gold.fato_pibic_perfil.valor_total_investido IS 'Soma estimada das bolsas do grupo, em R$.';

GRANT SELECT ON gold.fato_pibic_perfil TO observatorio_leitura;

COMMENT ON TABLE gold.fato_retencao_curso IS
  'Retenção por curso canônico, calculada a partir de silver.movimentacoes_vinculos sobre as coortes maduras, com k >= 5: contagens, taxas, % no tempo ideal, atraso médio, IRC e classificação (mesmas regras de build_gold.py).';
