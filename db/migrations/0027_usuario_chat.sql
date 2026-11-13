-- Usuário de login do chat com LLM (src/chat). Herda observatorio_leitura: lê gold, busca e
-- dbt_marts, e não enxerga bronze nem silver (ADR 0005, 0010). Somente leitura, com tempo limite.
-- A senha abaixo é a de desenvolvimento (docker-compose); fora dele, troque com
--   ALTER ROLE observatorio_chat PASSWORD '...';
-- e aponte CHAT_DATABASE_URL para o banco local, nunca para o Supabase.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'observatorio_chat') THEN
    CREATE ROLE observatorio_chat LOGIN PASSWORD 'observatorio_chat';
  END IF;
END
$$;

GRANT observatorio_leitura TO observatorio_chat;
ALTER ROLE observatorio_chat SET default_transaction_read_only = on;
ALTER ROLE observatorio_chat SET statement_timeout = '10s';

COMMENT ON ROLE observatorio_chat IS
  'Chat com LLM: leitura de gold, busca e dbt_marts, somente leitura, statement_timeout 10s.';
