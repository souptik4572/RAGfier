-- migrate:up

CREATE TABLE IF NOT EXISTS knowledge_bases (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  slug TEXT NOT NULL,
  description TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  settings JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (tenant_id, slug)
);

CREATE TABLE IF NOT EXISTS integrations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  environment TEXT NOT NULL DEFAULT 'production',
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS api_keys (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  integration_id UUID NOT NULL REFERENCES integrations(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  prefix TEXT NOT NULL UNIQUE,
  secret_hash TEXT NOT NULL,
  scopes JSONB NOT NULL DEFAULT '[]'::JSONB,
  status TEXT NOT NULL DEFAULT 'active',
  expires_at TIMESTAMPTZ,
  last_used_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS connector_sources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  knowledge_base_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  type TEXT NOT NULL,
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  sync_mode TEXT NOT NULL DEFAULT 'manual',
  encrypted_config TEXT NOT NULL,
  config_summary JSONB NOT NULL DEFAULT '{}'::JSONB,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  last_synced_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS connector_sync_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  connector_source_id UUID NOT NULL REFERENCES connector_sources(id) ON DELETE CASCADE,
  knowledge_base_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'pending',
  trigger TEXT NOT NULL DEFAULT 'manual',
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  error_message TEXT,
  started_at TIMESTAMPTZ DEFAULT now(),
  finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS audit_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  actor_type TEXT NOT NULL,
  actor_id TEXT,
  action TEXT NOT NULL,
  resource_type TEXT,
  resource_id TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS request_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  integration_id UUID REFERENCES integrations(id) ON DELETE SET NULL,
  api_key_id UUID REFERENCES api_keys(id) ON DELETE SET NULL,
  actor_type TEXT NOT NULL DEFAULT 'api_key',
  endpoint TEXT NOT NULL,
  method TEXT NOT NULL,
  status_code INTEGER NOT NULL,
  latency_ms INTEGER NOT NULL DEFAULT 0,
  input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  error_code TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS usage_rollups (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  integration_id UUID REFERENCES integrations(id) ON DELETE SET NULL,
  bucket_start TIMESTAMPTZ NOT NULL,
  granularity TEXT NOT NULL DEFAULT 'day',
  request_count INTEGER NOT NULL DEFAULT 0,
  success_count INTEGER NOT NULL DEFAULT 0,
  error_count INTEGER NOT NULL DEFAULT 0,
  total_input_tokens INTEGER NOT NULL DEFAULT 0,
  total_output_tokens INTEGER NOT NULL DEFAULT 0,
  avg_latency_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (tenant_id, integration_id, bucket_start, granularity)
);

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS knowledge_base_id UUID REFERENCES knowledge_bases(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS source_type TEXT,
  ADD COLUMN IF NOT EXISTS source_id UUID,
  ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';

ALTER TABLE ingestion_jobs
  ADD COLUMN IF NOT EXISTS knowledge_base_id UUID REFERENCES knowledge_bases(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS source_id UUID,
  ADD COLUMN IF NOT EXISTS source_type TEXT;

CREATE INDEX IF NOT EXISTS idx_knowledge_bases_tenant
  ON knowledge_bases (tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_integrations_tenant
  ON integrations (tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_api_keys_integration
  ON api_keys (tenant_id, integration_id, status);

CREATE INDEX IF NOT EXISTS idx_documents_kb
  ON documents (tenant_id, knowledge_base_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_jobs_kb
  ON ingestion_jobs (tenant_id, knowledge_base_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_connector_sources_tenant
  ON connector_sources (tenant_id, knowledge_base_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_connector_sync_jobs_connector
  ON connector_sync_jobs (tenant_id, connector_source_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_request_logs_tenant
  ON request_logs (tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_logs_tenant
  ON audit_logs (tenant_id, created_at DESC);

ALTER TABLE knowledge_bases ENABLE ROW LEVEL SECURITY;
ALTER TABLE integrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE connector_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE connector_sync_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE request_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_rollups ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "tenant_isolation_knowledge_bases" ON knowledge_bases;
CREATE POLICY "tenant_isolation_knowledge_bases" ON knowledge_bases
  FOR SELECT
  USING (
    tenant_id = (auth.jwt() -> 'app_metadata' ->> 'organization_id')::UUID
  );

DROP POLICY IF EXISTS "tenant_isolation_integrations" ON integrations;
CREATE POLICY "tenant_isolation_integrations" ON integrations
  FOR SELECT
  USING (
    tenant_id = (auth.jwt() -> 'app_metadata' ->> 'organization_id')::UUID
  );

DROP POLICY IF EXISTS "tenant_isolation_api_keys" ON api_keys;
CREATE POLICY "tenant_isolation_api_keys" ON api_keys
  FOR SELECT
  USING (
    tenant_id = (auth.jwt() -> 'app_metadata' ->> 'organization_id')::UUID
  );

DROP POLICY IF EXISTS "tenant_isolation_connector_sources" ON connector_sources;
CREATE POLICY "tenant_isolation_connector_sources" ON connector_sources
  FOR SELECT
  USING (
    tenant_id = (auth.jwt() -> 'app_metadata' ->> 'organization_id')::UUID
  );

DROP POLICY IF EXISTS "tenant_isolation_connector_sync_jobs" ON connector_sync_jobs;
CREATE POLICY "tenant_isolation_connector_sync_jobs" ON connector_sync_jobs
  FOR SELECT
  USING (
    tenant_id = (auth.jwt() -> 'app_metadata' ->> 'organization_id')::UUID
  );

DROP POLICY IF EXISTS "tenant_isolation_audit_logs" ON audit_logs;
CREATE POLICY "tenant_isolation_audit_logs" ON audit_logs
  FOR SELECT
  USING (
    tenant_id = (auth.jwt() -> 'app_metadata' ->> 'organization_id')::UUID
  );

DROP POLICY IF EXISTS "tenant_isolation_request_logs" ON request_logs;
CREATE POLICY "tenant_isolation_request_logs" ON request_logs
  FOR SELECT
  USING (
    tenant_id = (auth.jwt() -> 'app_metadata' ->> 'organization_id')::UUID
  );

DROP POLICY IF EXISTS "tenant_isolation_usage_rollups" ON usage_rollups;
CREATE POLICY "tenant_isolation_usage_rollups" ON usage_rollups
  FOR SELECT
  USING (
    tenant_id = (auth.jwt() -> 'app_metadata' ->> 'organization_id')::UUID
  );

CREATE OR REPLACE FUNCTION match_documents(
  query_embedding VECTOR(1536),
  match_count INT DEFAULT 5,
  filter_tenant_id UUID DEFAULT NULL,
  filter_knowledge_base_ids UUID[] DEFAULT NULL
)
RETURNS TABLE (
  id UUID,
  content TEXT,
  metadata JSONB,
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
    (filter_tenant_id IS NULL OR d.tenant_id = filter_tenant_id)
    AND (
      filter_knowledge_base_ids IS NULL
      OR d.knowledge_base_id = ANY(filter_knowledge_base_ids)
    )
  ORDER BY d.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

CREATE OR REPLACE FUNCTION match_documents_hybrid(
  query_embedding VECTOR(1536),
  query_text TEXT,
  match_count INT DEFAULT 20,
  rrf_k INT DEFAULT 60,
  dense_top_n INT DEFAULT 20,
  sparse_top_n INT DEFAULT 20,
  filter_tenant_id UUID DEFAULT NULL,
  filter_knowledge_base_ids UUID[] DEFAULT NULL
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
    WHERE
      (filter_tenant_id IS NULL OR d.tenant_id = filter_tenant_id)
      AND (
        filter_knowledge_base_ids IS NULL
        OR d.knowledge_base_id = ANY(filter_knowledge_base_ids)
      )
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
      AND (
        filter_knowledge_base_ids IS NULL
        OR d.knowledge_base_id = ANY(filter_knowledge_base_ids)
      )
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

DROP FUNCTION IF EXISTS match_documents_hybrid(VECTOR(1536), TEXT, INT, INT, INT, INT, UUID, UUID[]);
DROP FUNCTION IF EXISTS match_documents(VECTOR(1536), INT, UUID, UUID[]);

DROP POLICY IF EXISTS "tenant_isolation_usage_rollups" ON usage_rollups;
DROP POLICY IF EXISTS "tenant_isolation_request_logs" ON request_logs;
DROP POLICY IF EXISTS "tenant_isolation_audit_logs" ON audit_logs;
DROP POLICY IF EXISTS "tenant_isolation_connector_sync_jobs" ON connector_sync_jobs;
DROP POLICY IF EXISTS "tenant_isolation_connector_sources" ON connector_sources;
DROP POLICY IF EXISTS "tenant_isolation_api_keys" ON api_keys;
DROP POLICY IF EXISTS "tenant_isolation_integrations" ON integrations;
DROP POLICY IF EXISTS "tenant_isolation_knowledge_bases" ON knowledge_bases;

DROP TABLE IF EXISTS usage_rollups;
DROP TABLE IF EXISTS request_logs;
DROP TABLE IF EXISTS audit_logs;
DROP TABLE IF EXISTS connector_sync_jobs;
DROP TABLE IF EXISTS connector_sources;
DROP TABLE IF EXISTS api_keys;
DROP TABLE IF EXISTS integrations;
DROP TABLE IF EXISTS knowledge_bases;

ALTER TABLE ingestion_jobs
  DROP COLUMN IF EXISTS source_type,
  DROP COLUMN IF EXISTS source_id,
  DROP COLUMN IF EXISTS knowledge_base_id;

ALTER TABLE documents
  DROP COLUMN IF EXISTS status,
  DROP COLUMN IF EXISTS source_id,
  DROP COLUMN IF EXISTS source_type,
  DROP COLUMN IF EXISTS knowledge_base_id;
