-- migrate:up

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS fts tsvector
  GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;

CREATE INDEX IF NOT EXISTS idx_documents_fts
  ON documents
  USING gin (fts);

CREATE TABLE IF NOT EXISTS prompt_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  system_prompt TEXT NOT NULL,
  user_prompt_template TEXT NOT NULL,
  metadata JSONB DEFAULT '{}'::JSONB,
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_prompt_active
  ON prompt_versions (COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::UUID), name)
  WHERE is_active = true;

ALTER TABLE prompt_versions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "tenant_isolation_prompts" ON prompt_versions;
CREATE POLICY "tenant_isolation_prompts" ON prompt_versions
  FOR SELECT
  USING (
    tenant_id IS NULL
    OR tenant_id = (auth.jwt() -> 'app_metadata' ->> 'organization_id')::UUID
  );

CREATE OR REPLACE FUNCTION match_documents_hybrid(
  query_embedding VECTOR(1536),
  query_text TEXT,
  match_count INT DEFAULT 20,
  rrf_k INT DEFAULT 60,
  dense_top_n INT DEFAULT 20,
  sparse_top_n INT DEFAULT 20,
  filter_tenant_id UUID DEFAULT NULL
)
RETURNS TABLE (
  id UUID,
  content TEXT,
  metadata JSONB,
  rrf_score FLOAT,
  dense_rank INT,
  sparse_rank INT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  WITH dense AS (
    SELECT
      d.id,
      d.content,
      d.metadata,
      ROW_NUMBER() OVER (ORDER BY d.embedding <=> query_embedding)::INT AS rank
    FROM documents d
    WHERE (filter_tenant_id IS NULL OR d.tenant_id = filter_tenant_id)
    ORDER BY d.embedding <=> query_embedding
    LIMIT dense_top_n
  ),
  sparse AS (
    SELECT
      d.id,
      d.content,
      d.metadata,
      ROW_NUMBER() OVER (
        ORDER BY ts_rank(d.fts, websearch_to_tsquery('english', query_text)) DESC
      )::INT AS rank
    FROM documents d
    WHERE
      (filter_tenant_id IS NULL OR d.tenant_id = filter_tenant_id)
      AND d.fts @@ websearch_to_tsquery('english', query_text)
    ORDER BY ts_rank(d.fts, websearch_to_tsquery('english', query_text)) DESC
    LIMIT sparse_top_n
  ),
  fused AS (
    SELECT
      COALESCE(dense.id, sparse.id) AS id,
      COALESCE(dense.content, sparse.content) AS content,
      COALESCE(dense.metadata, sparse.metadata) AS metadata,
      (COALESCE(1.0::double precision / (rrf_k + dense.rank), 0)
        + COALESCE(1.0::double precision / (rrf_k + sparse.rank), 0))::double precision AS rrf_score,
      dense.rank AS dense_rank,
      sparse.rank AS sparse_rank
    FROM dense
    FULL OUTER JOIN sparse ON dense.id = sparse.id
  )
  SELECT
    fused.id,
    fused.content,
    fused.metadata,
    fused.rrf_score,
    COALESCE(fused.dense_rank, 0),
    COALESCE(fused.sparse_rank, 0)
  FROM fused
  ORDER BY fused.rrf_score DESC
  LIMIT match_count;
END;
$$;

-- migrate:down

DROP FUNCTION IF EXISTS match_documents_hybrid(VECTOR(1536), TEXT, INT, INT, INT, INT, UUID);

DROP POLICY IF EXISTS "tenant_isolation_prompts" ON prompt_versions;
DROP TABLE IF EXISTS prompt_versions;

DROP INDEX IF EXISTS idx_documents_fts;
ALTER TABLE documents DROP COLUMN IF EXISTS fts;
