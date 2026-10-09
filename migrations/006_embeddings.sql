-- pgvector stores embeddings as a native type with distance operators,
-- so similarity search happens in the database rather than by pulling
-- every vector into Python.
CREATE EXTENSION IF NOT EXISTS vector;

-- 384 dimensions: all-MiniLM-L6-v2. Changing models means a migration,
-- so the model name is recorded alongside the vector.
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS embedding vector(384);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS embedding_model TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS embedded_at TIMESTAMPTZ;
