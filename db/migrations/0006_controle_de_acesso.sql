-- Privilégio mínimo: quem só consome o painel ou a busca lê gold e busca, e não
-- enxerga bronze nem silver, que guardam registro individual de discente.
-- Para um usuário de login herdar esse acesso: GRANT observatorio_leitura TO <usuario>;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'observatorio_leitura') THEN
    CREATE ROLE observatorio_leitura NOLOGIN;
  END IF;
END
$$;

COMMENT ON ROLE observatorio_leitura IS
  'Leitura das camadas publicáveis (gold e busca). Sem acesso a bronze e silver.';

REVOKE ALL ON SCHEMA bronze, silver FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA bronze, silver FROM PUBLIC;

GRANT USAGE ON SCHEMA gold, busca TO observatorio_leitura;
GRANT SELECT ON ALL TABLES IN SCHEMA gold, busca TO observatorio_leitura;
ALTER DEFAULT PRIVILEGES IN SCHEMA gold, busca GRANT SELECT ON TABLES TO observatorio_leitura;
