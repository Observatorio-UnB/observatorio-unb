-- Publicação lida pelo Debezium (plugin pgoutput) para a captura de mudanças da Silver 3NF.
--
-- Só entram as tabelas que o lago CDC recebe (src/cdc/consumidor.py). silver.discentes fica de
-- fora, como no lago em lote: guarda nascimento, sexo e raça/cor por pessoa.
--
-- publish_via_partition_root: as mudanças das partições de movimentacoes_vinculos (inclusive as
-- criadas depois por silver.provisionar_particoes_movimentacoes) saem com o nome da tabela mãe,
-- num tópico só. truncate entra porque a recarga da Silver 3NF começa com TRUNCATE.
--
-- Criar a publicação não retém WAL nem exige wal_level = logical. Quem retém é o slot de
-- replicação, que o Debezium cria ao registrar o conector (scripts/cdc.sh).

CREATE PUBLICATION observatorio_cdc
  FOR TABLE silver.cursos, silver.estruturas_curriculares, silver.movimentacoes_vinculos
  WITH (publish = 'insert, update, delete, truncate', publish_via_partition_root = true);
