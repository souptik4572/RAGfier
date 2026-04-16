-- =============================================================
-- Admin reset script: truncate all application tables
-- WARNING: destructive operation for development / test environments.
-- This file is intentionally NOT part of sql/migrations/.
-- =============================================================

BEGIN;

TRUNCATE TABLE
  eval_sample_results,
  eval_runs,
  prompt_versions,
  documents,
  ingestion_jobs,
  tenants
CASCADE;

COMMIT;
