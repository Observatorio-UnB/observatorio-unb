-- Usuário do chat com LLM (src/chat). Herda observatorio_leitura: lê gold, busca e dbt_marts, e não
-- enxerga bronze nem silver (ADR 0005, 0010). Somente leitura, com tempo limite.
-- O papel nasce SEM login e SEM senha: a migração não deve deixar credencial conhecida em nenhum banco.
-- Quem habilita o login é src/db/migrar.py, que lê a senha de CHAT_DATABASE_URL e só o faz se o host
-- dessa URL for o mesmo do banco que está sendo migrado (nunca o Supabase por engano).

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'observatorio_chat') THEN
    CREATE ROLE observatorio_chat NOLOGIN;
  END IF;
END
$$;

GRANT observatorio_leitura TO observatorio_chat;
ALTER ROLE observatorio_chat SET default_transaction_read_only = on;
ALTER ROLE observatorio_chat SET statement_timeout = '10s';

COMMENT ON ROLE observatorio_chat IS
  'Chat com LLM: leitura de gold, busca e dbt_marts, somente leitura, statement_timeout 10s.';
