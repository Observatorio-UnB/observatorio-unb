-- Esquemas do medalhão e extensão de busca vetorial.
-- Cada camada vive no próprio esquema, o que permite conceder acesso por camada
-- (ver 0006_controle_de_acesso.sql).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;
CREATE SCHEMA IF NOT EXISTS busca;

COMMENT ON SCHEMA bronze IS
  'Dado bruto do portal dados.unb.br, como veio da API CKAN: todas as colunas em texto, sem limpeza. Contém dado pessoal.';
COMMENT ON SCHEMA silver IS
  'Dado limpo, tipado e normalizado por src/pipeline/transform_silver.py. Nível de registro individual: contém dado pessoal.';
COMMENT ON SCHEMA gold IS
  'Tabelas analíticas agregadas por curso (k >= 5), prontas para consumo pelo painel e pelo DEG.';
COMMENT ON SCHEMA busca IS
  'Documentos vetorizados (pgvector) para busca semântica sobre cursos, projetos de IC e documentação do projeto.';
