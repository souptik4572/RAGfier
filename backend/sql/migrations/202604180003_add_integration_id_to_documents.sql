-- migrate:up

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS integration_id UUID REFERENCES integrations(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_documents_integration_id
  ON documents (integration_id);

-- migrate:down

DROP INDEX IF EXISTS idx_documents_integration_id;

ALTER TABLE documents
  DROP COLUMN IF EXISTS integration_id;
