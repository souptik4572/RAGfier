-- migrate:up

-- Associate every integration with a prompt by name. Resolution lives in
-- app.pipeline.query_pipeline: the name is looked up in prompt_versions
-- (tenant → global), then falls back to a YAML file on disk. Storing the
-- *name* (not a prompt_versions.id) means an integration automatically
-- follows the active version when the tenant publishes a new one.
ALTER TABLE integrations
  ADD COLUMN IF NOT EXISTS prompt_name TEXT NOT NULL DEFAULT 'rag_generation_v1';

-- migrate:down

ALTER TABLE integrations
  DROP COLUMN IF EXISTS prompt_name;
