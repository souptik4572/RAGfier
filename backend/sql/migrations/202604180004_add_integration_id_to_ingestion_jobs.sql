-- migrate:up

ALTER TABLE ingestion_jobs
  ADD COLUMN IF NOT EXISTS integration_id UUID REFERENCES integrations(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_integration_id
  ON ingestion_jobs (integration_id);

-- migrate:down

DROP INDEX IF EXISTS idx_ingestion_jobs_integration_id;

ALTER TABLE ingestion_jobs
  DROP COLUMN IF EXISTS integration_id;
