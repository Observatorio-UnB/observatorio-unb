-- ============================================================================
-- Migração 0021: Registro das cargas da Silver 3NF e do dado que chega atrasado
--
-- Cada carga de silver.movimentacoes_vinculos (src/db/povoar_silver_3nf.py) grava a marca
-- d'água em silver.cargas_vinculos e o retrato das janelas (vínculos por ano de ingresso,
-- desfecho e período de saída) em silver.cargas_vinculos_retrato. A view
-- silver.chegadas_por_carga compara o retrato de cada carga com o da anterior e classifica o
-- que mudou: chegou no prazo, atrasado ou sem período de saída. Regras em
-- src/db/dado_atrasado.py e no ADR 0026.
--
-- O retrato é agregado, mas fica na silver: o papel observatorio_leitura não o lê (0006).
-- ============================================================================

CREATE TABLE IF NOT EXISTS silver.cargas_vinculos (
    id_carga              INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    carregada_em          TIMESTAMPTZ NOT NULL DEFAULT now(),
    publicada_em          DATE NOT NULL,
    marca_dagua           INTEGER NOT NULL CHECK (marca_dagua % 10 IN (0, 1, 2)),
    ultima_coorte_madura  SMALLINT,
    total_vinculos        INTEGER NOT NULL CHECK (total_vinculos >= 0)
);

COMMENT ON TABLE silver.cargas_vinculos IS
  'Uma linha por carga de silver.movimentacoes_vinculos, com a marca d''água usada para classificar o que chegou.';
COMMENT ON COLUMN silver.cargas_vinculos.publicada_em IS
  'Publicação no portal do arquivo de vínculos mais recente da carga (SIGRA ou SIGAA, por bronze.ingestoes). É o tempo de processamento.';
COMMENT ON COLUMN silver.cargas_vinculos.marca_dagua IS
  'Último período de saída (AAAAS, semestre 0 = verão) dado como fechado: o fim do período mais a tolerância não passa de publicada_em.';
COMMENT ON COLUMN silver.cargas_vinculos.ultima_coorte_madura IS
  'Último ano de ingresso que entra na gold nesta carga (ADR 0014). Mudança em coorte até aqui revisa número já publicado.';

CREATE TABLE IF NOT EXISTS silver.cargas_vinculos_retrato (
    id_carga          INTEGER NOT NULL REFERENCES silver.cargas_vinculos (id_carga) ON DELETE CASCADE,
    ano_ingresso      SMALLINT NOT NULL,
    tipo_saida_grupo  TEXT NOT NULL,
    periodo_saida     INTEGER,
    total             INTEGER NOT NULL CHECK (total > 0),
    CONSTRAINT uk_cargas_vinculos_retrato
      UNIQUE NULLS NOT DISTINCT (id_carga, ano_ingresso, tipo_saida_grupo, periodo_saida)
);

COMMENT ON TABLE silver.cargas_vinculos_retrato IS
  'Vínculos de cada carga por ano de ingresso, desfecho e período de saída. Só contagens: nenhuma linha identifica um discente.';
COMMENT ON COLUMN silver.cargas_vinculos_retrato.periodo_saida IS
  'Período de saída (AAAAS). Nulo quando o vínculo não tem período: ativo, cancelado no SIGAA ou formado sem diploma registrado.';

-- Diferenças entre o retrato de cada carga e o da anterior. A comparação é pela contagem, e não
-- vínculo a vínculo: o id de silver.movimentacoes_vinculos é refeito a cada recarga, e nada
-- garante que a fonte mantenha o pseudônimo do discente entre duas publicações.
CREATE OR REPLACE VIEW silver.chegadas_por_carga AS
WITH pares AS (
    SELECT id_carga,
           lag(id_carga) OVER w AS id_anterior,
           lag(marca_dagua) OVER w AS marca_anterior,
           lag(ultima_coorte_madura) OVER w AS coorte_madura_anterior
    FROM silver.cargas_vinculos
    WINDOW w AS (ORDER BY id_carga)
), lados AS (
    SELECT p.id_carga, r.ano_ingresso, r.tipo_saida_grupo, r.periodo_saida, r.total AS antes, 0 AS depois
    FROM pares p
    JOIN silver.cargas_vinculos_retrato r ON r.id_carga = p.id_anterior
    UNION ALL
    SELECT p.id_carga, r.ano_ingresso, r.tipo_saida_grupo, r.periodo_saida, 0, r.total
    FROM pares p
    JOIN silver.cargas_vinculos_retrato r ON r.id_carga = p.id_carga
    WHERE p.id_anterior IS NOT NULL
)
SELECT l.id_carga,
       l.ano_ingresso,
       (l.ano_ingresso - l.ano_ingresso % 5)::smallint AS quinquenio_ingresso,
       l.tipo_saida_grupo,
       l.periodo_saida,
       sum(l.antes)::int AS total_antes,
       sum(l.depois)::int AS total_depois,
       (sum(l.depois) - sum(l.antes))::int AS diferenca,
       CASE WHEN l.periodo_saida IS NULL THEN 'SEM_PERIODO'
            WHEN l.periodo_saida <= p.marca_anterior THEN 'ATRASADA'
            ELSE 'NO_PRAZO' END AS chegada,
       coalesce(l.ano_ingresso <= p.coorte_madura_anterior, false) AS coorte_publicada
FROM lados l
JOIN pares p USING (id_carga)
GROUP BY l.id_carga, l.ano_ingresso, l.tipo_saida_grupo, l.periodo_saida, p.marca_anterior, p.coorte_madura_anterior
HAVING sum(l.antes) <> sum(l.depois);

COMMENT ON VIEW silver.chegadas_por_carga IS
  'O que mudou de uma carga para a anterior, por janela. chegada: ATRASADA (período até a marca d''água da carga '
  'anterior, que já o dava como fechado), NO_PRAZO (período ainda aberto) ou SEM_PERIODO.';
COMMENT ON COLUMN silver.chegadas_por_carga.diferenca IS
  'Vínculos a mais (positivo) ou a menos (negativo) na janela em relação à carga anterior.';
COMMENT ON COLUMN silver.chegadas_por_carga.coorte_publicada IS
  'A coorte já estava na gold da carga anterior: a mudança revisa número publicado.';
