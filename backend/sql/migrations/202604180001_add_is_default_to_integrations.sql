-- migrate:up

-- Add is_default flag so each tenant can have one designated default integration.
-- A partial unique index enforces at most one default per tenant at the DB level.
ALTER TABLE integrations
  ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT FALSE;

CREATE UNIQUE INDEX IF NOT EXISTS uq_integrations_tenant_default
  ON integrations (tenant_id)
  WHERE is_default = TRUE;

-- migrate:down

DROP INDEX IF EXISTS uq_integrations_tenant_default;

ALTER TABLE integrations
  DROP COLUMN IF EXISTS is_default;
