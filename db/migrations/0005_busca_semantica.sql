-- Busca semântica: documentos de texto com o embedding correspondente (pgvector).
-- Preenchida por src/busca/vetorizar.py a partir das tabelas do próprio banco.
--
-- A dimensão 384 é a do modelo sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2.
-- Trocar de modelo exige uma migração nova que altere a coluna e reindexe.

CREATE TABLE busca.documentos (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tipo          TEXT NOT NULL CHECK (tipo IN ('curso', 'projeto_pibic', 'documentacao')),
  chave         TEXT NOT NULL,
  titulo        TEXT NOT NULL,
  conteudo      TEXT NOT NULL,
  metadados     JSONB NOT NULL DEFAULT '{}'::jsonb,
  hash_conteudo TEXT NOT NULL,
  modelo        TEXT NOT NULL,
  embedding     vector(384) NOT NULL,
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tipo, chave)
);

-- HNSW com distância de cosseno (operador <=>). Com poucos milhares de linhas uma
-- varredura sequencial também serve; o índice mantém a latência estável se o
-- volume crescer.
CREATE INDEX documentos_embedding_hnsw ON busca.documentos USING hnsw (embedding vector_cosine_ops);
CREATE INDEX documentos_tipo_idx ON busca.documentos (tipo);

COMMENT ON TABLE busca.documentos IS
  'Um documento de texto por entidade pesquisável: cada curso da gold, cada plano de IC distinto e cada seção da documentação em docs/. Não contém nome nem matrícula.';
COMMENT ON COLUMN busca.documentos.tipo IS 'curso (gold.retencao_cursos_unb), projeto_pibic (silver.pibic_bolsistas) ou documentacao (seções dos .md em docs/).';
COMMENT ON COLUMN busca.documentos.chave IS 'Chave natural do documento dentro do tipo (nome do curso, hash do plano de IC, arquivo#seção).';
COMMENT ON COLUMN busca.documentos.titulo IS 'Rótulo curto exibido no resultado da busca.';
COMMENT ON COLUMN busca.documentos.conteudo IS 'Texto que foi vetorizado.';
COMMENT ON COLUMN busca.documentos.metadados IS 'Campos estruturados para filtro e exibição (curso, campus, ano, IRC etc.).';
COMMENT ON COLUMN busca.documentos.hash_conteudo IS 'SHA-256 de modelo + conteúdo. Se não mudou, a vetorização não recalcula o embedding.';
COMMENT ON COLUMN busca.documentos.modelo IS 'Modelo de embedding usado.';
COMMENT ON COLUMN busca.documentos.embedding IS 'Vetor normalizado de 384 dimensões. Similaridade = 1 - (embedding <=> consulta).';
COMMENT ON COLUMN busca.documentos.id IS 'Chave substituta.';
COMMENT ON COLUMN busca.documentos.atualizado_em IS 'Última vez em que o embedding foi recalculado.';
