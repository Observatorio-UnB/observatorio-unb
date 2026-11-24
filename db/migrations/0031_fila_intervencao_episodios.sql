-- ============================================================================
-- Migração 0031: Episódios da fila de intervenção
--
-- Um curso pode sair da fila (deixou a RETENÇÃO CRÍTICA) e voltar num ciclo seguinte. Até aqui, na
-- volta, a linha mantinha o status, o responsável e o plano do episódio anterior: um curso de novo
-- crítico aparecia como CONCLUIDO e ficava fora do KPI "Sem andamento (NOVO)" (revisão do #82).
--
-- Agora cada passagem pela fila é um episódio:
--   - na saída, o ETL reverso copia o episódio que terminou para esta tabela (datas, andamento da
--     coordenação e as métricas com que o curso saiu);
--   - na volta, a linha da fila recomeça como NOVO, sem responsável nem plano.
-- O DEG lê aqui se um curso já teve plano antes, e com que resultado.
--
-- Idempotente (IF NOT EXISTS): o ETL reverso a aplica num destino separado (--preparar-destino).
-- ============================================================================

CREATE TABLE IF NOT EXISTS operacional.fila_intervencao_episodios (
    id                              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome_curso                      text        NOT NULL,
    entrou_na_fila_em               date        NOT NULL,
    saiu_da_fila_em                 date        NOT NULL,
    status_final                    text        NOT NULL,
    responsavel                     text,
    plano_de_acao                   text,
    atualizado_pela_coordenacao_em  timestamptz,
    indice_retencao_critica         numeric,
    taxa_evasao_pct                 numeric,
    versao_metricas                 text        NOT NULL,
    registrado_em                   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS fila_intervencao_episodios_curso
    ON operacional.fila_intervencao_episodios (nome_curso, saiu_da_fila_em);

COMMENT ON TABLE operacional.fila_intervencao_episodios IS
  'Passagens encerradas de cada curso pela fila de intervenção: datas, andamento da coordenação e métricas na saída.';
COMMENT ON COLUMN operacional.fila_intervencao_episodios.status_final IS
  'Status em que a coordenação deixou o curso quando ele saiu da fila.';

REVOKE ALL ON operacional.fila_intervencao_episodios FROM PUBLIC;
GRANT SELECT ON operacional.fila_intervencao_episodios TO coordenacao_academica;
