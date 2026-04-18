-- migrate:up

-- Replace match_documents and match_documents_hybrid:
--   • Add filter_integration_id parameter
--   • Remove filter_knowledge_base_ids parameter (knowledge-base scoping is
--     now handled entirely via integration_id)

DROP FUNCTION IF EXISTS match_documents(VECTOR(1536), INT, UUID, UUID[]);
DROP FUNCTION IF EXISTS match_documents_hybrid(VECTOR(1536), TEXT, INT, INT, INT, INT, UUID, UUID[]);

CREATE OR REPLACE FUNCTION match_documents(
  query_embedding       VECTOR(1536),
  match_count           INT  DEFAULT 5,
  filter_tenant_id      UUID DEFAULT NULL,
  filter_integration_id UUID DEFAULT NULL
)
RETURNS TABLE (
  id         UUID,
  content    TEXT,
  metadata   JSONB,
  similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    d.id,
    d.content,
    d.metadata,
    1 - (d.embedding <=> query_embedding) AS similarity
  FROM documents d
  WHERE
    (filter_tenant_id      IS NULL OR d.tenant_id      = filter_tenant_id)
    AND (filter_integration_id IS NULL OR d.integration_id = filter_integration_id)
  ORDER BY d.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;


CREATE OR REPLACE FUNCTION match_documents_hybrid(
  query_embedding       VECTOR(1536),
  query_text            TEXT,
  match_count           INT  DEFAULT 20,
  rrf_k                 INT  DEFAULT 60,
  dense_top_n           INT  DEFAULT 20,
  sparse_top_n          INT  DEFAULT 20,
  filter_tenant_id      UUID DEFAULT NULL,
  filter_integration_id UUID DEFAULT NULL
)
RETURNS TABLE (
  id          UUID,
  content     TEXT,
  metadata    JSONB,
  rrf_score   FLOAT,
  dense_rank  INT,
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
    WHERE
      (filter_tenant_id      IS NULL OR d.tenant_id      = filter_tenant_id)
      AND (filter_integration_id IS NULL OR d.integration_id = filter_integration_id)
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
      (filter_tenant_id      IS NULL OR d.tenant_id      = filter_tenant_id)
      AND (filter_integration_id IS NULL OR d.integration_id = filter_integration_id)
      AND d.fts @@ websearch_to_tsquery('english', query_text)
    ORDER BY ts_rank(d.fts, websearch_to_tsquery('english', query_text)) DESC
    LIMIT sparse_top_n
  ),
  fused AS (
    SELECT
      COALESCE(dense.id,       sparse.id)      AS id,
      COALESCE(dense.content,  sparse.content) AS content,
      COALESCE(dense.metadata, sparse.metadata)AS metadata,
      (COALESCE(1.0::double precision / (rrf_k + dense.rank),  0)
       + COALESCE(1.0::double precision / (rrf_k + sparse.rank), 0))::double precision AS rrf_score,
      dense.rank  AS dense_rank,
      sparse.rank AS sparse_rank
    FROM dense
    FULL OUTER JOIN sparse ON dense.id = sparse.id
  )
  SELECT
    fused.id,
    fused.content,
    fused.metadata,
    fused.rrf_score,
    COALESCE(fused.dense_rank,  0),
    COALESCE(fused.sparse_rank, 0)
  FROM fused
  ORDER BY fused.rrf_score DESC
  LIMIT match_count;
END;
$$;


-- migrate:down

DROP FUNCTION IF EXISTS match_documents(VECTOR(1536), INT, UUID, UUID);
DROP FUNCTION IF EXISTS match_documents_hybrid(VECTOR(1536), TEXT, INT, INT, INT, INT, UUID, UUID);

CREATE OR REPLACE FUNCTION match_documents(
  query_embedding           VECTOR(1536),
  match_count               INT    DEFAULT 5,
  filter_tenant_id          UUID   DEFAULT NULL,
  filter_knowledge_base_ids UUID[] DEFAULT NULL
)
RETURNS TABLE (
  id         UUID,
  content    TEXT,
  metadata   JSONB,
  similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    d.id,
    d.content,
    d.metadata,
    1 - (d.embedding <=> query_embedding) AS similarity
  FROM documents d
  WHERE
    (filter_tenant_id          IS NULL OR d.tenant_id        = filter_tenant_id)
    AND (filter_knowledge_base_ids IS NULL OR d.knowledge_base_id = ANY(filter_knowledge_base_ids))
  ORDER BY d.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

CREATE OR REPLACE FUNCTION match_documents_hybrid(
  query_embedding           VECTOR(1536),
  query_text                TEXT,
  match_count               INT    DEFAULT 20,
  rrf_k                     INT    DEFAULT 60,
  dense_top_n               INT    DEFAULT 20,
  sparse_top_n              INT    DEFAULT 20,
  filter_tenant_id          UUID   DEFAULT NULL,
  filter_knowledge_base_ids UUID[] DEFAULT NULL
)
RETURNS TABLE (
  id          UUID,
  content     TEXT,
  metadata    JSONB,
  rrf_score   FLOAT,
  dense_rank  INT,
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
    WHERE
      (filter_tenant_id          IS NULL OR d.tenant_id        = filter_tenant_id)
      AND (filter_knowledge_base_ids IS NULL OR d.knowledge_base_id = ANY(filter_knowledge_base_ids))
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
      (filter_tenant_id          IS NULL OR d.tenant_id        = filter_tenant_id)
      AND (filter_knowledge_base_ids IS NULL OR d.knowledge_base_id = ANY(filter_knowledge_base_ids))
      AND d.fts @@ websearch_to_tsquery('english', query_text)
    ORDER BY ts_rank(d.fts, websearch_to_tsquery('english', query_text)) DESC
    LIMIT sparse_top_n
  ),
  fused AS (
    SELECT
      COALESCE(dense.id,       sparse.id)      AS id,
      COALESCE(dense.content,  sparse.content) AS content,
      COALESCE(dense.metadata, sparse.metadata)AS metadata,
      (COALESCE(1.0::double precision / (rrf_k + dense.rank),  0)
       + COALESCE(1.0::double precision / (rrf_k + sparse.rank), 0))::double precision AS rrf_score,
      dense.rank  AS dense_rank,
      sparse.rank AS sparse_rank
    FROM dense
    FULL OUTER JOIN sparse ON dense.id = sparse.id
  )
  SELECT
    fused.id,
    fused.content,
    fused.metadata,
    fused.rrf_score,
    COALESCE(fused.dense_rank,  0),
    COALESCE(fused.sparse_rank, 0)
  FROM fused
  ORDER BY fused.rrf_score DESC
  LIMIT match_count;
END;
$$;
