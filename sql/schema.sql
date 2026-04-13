-- =============================================================
-- Phase 1: Domain-Specific RAG Ingestion — Database Schema
-- Apply via the Supabase SQL Editor.
-- =============================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================
-- Table: tenants
-- =============================================================
CREATE TABLE IF NOT EXISTS tenants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  slug TEXT UNIQUE NOT NULL,
  plan TEXT DEFAULT 'free',
  settings JSONB DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- =============================================================
-- Table: ingestion_jobs
-- =============================================================
CREATE TABLE IF NOT EXISTS ingestion_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  file_name TEXT NOT NULL,
  file_path TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
    -- Valid statuses: pending | parsing | chunking | embedding | completed | failed
  total_chunks INTEGER DEFAULT 0,
  processed_chunks INTEGER DEFAULT 0,
  error_message TEXT,
  metadata JSONB DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- =============================================================
-- Table: documents
-- =============================================================
CREATE TABLE IF NOT EXISTS documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  job_id UUID REFERENCES ingestion_jobs(id) ON DELETE SET NULL,
  content TEXT NOT NULL,
  embedding VECTOR(1536),
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- =============================================================
-- Indexes
-- =============================================================
CREATE INDEX IF NOT EXISTS idx_documents_embedding
  ON documents
  USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_documents_tenant_id
  ON documents (tenant_id);

CREATE INDEX IF NOT EXISTS idx_documents_job_id
  ON documents (job_id);

CREATE INDEX IF NOT EXISTS idx_documents_metadata
  ON documents
  USING gin (metadata);

CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_tenant_status
  ON ingestion_jobs (tenant_id, status);

-- =============================================================
-- Row-Level Security
-- =============================================================
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_jobs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "tenant_isolation_select" ON documents;
CREATE POLICY "tenant_isolation_select" ON documents
  FOR SELECT
  USING (
    tenant_id = (auth.jwt() -> 'app_metadata' ->> 'organization_id')::UUID
  );

DROP POLICY IF EXISTS "service_role_insert" ON documents;
CREATE POLICY "service_role_insert" ON documents
  FOR INSERT
  WITH CHECK (true);

DROP POLICY IF EXISTS "tenant_isolation_jobs" ON ingestion_jobs;
CREATE POLICY "tenant_isolation_jobs" ON ingestion_jobs
  FOR SELECT
  USING (
    tenant_id = (auth.jwt() -> 'app_metadata' ->> 'organization_id')::UUID
  );

-- =============================================================
-- RPC: match_documents
-- =============================================================
CREATE OR REPLACE FUNCTION match_documents(
  query_embedding VECTOR(1536),
  match_count INT DEFAULT 5,
  filter_tenant_id UUID DEFAULT NULL
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
  ORDER BY d.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
