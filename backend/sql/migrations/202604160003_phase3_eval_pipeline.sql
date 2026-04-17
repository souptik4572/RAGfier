-- migrate:up

CREATE TABLE IF NOT EXISTS eval_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  dataset_version TEXT NOT NULL,
  trigger TEXT NOT NULL,
  git_sha TEXT,
  git_branch TEXT,
  status TEXT NOT NULL DEFAULT 'running',
  faithfulness_avg DOUBLE PRECISION,
  answer_relevancy_avg DOUBLE PRECISION,
  context_precision_avg DOUBLE PRECISION,
  context_recall_avg DOUBLE PRECISION,
  citation_coverage_avg DOUBLE PRECISION,
  decline_accuracy_avg DOUBLE PRECISION,
  latency_compliance_avg DOUBLE PRECISION,
  thresholds JSONB NOT NULL DEFAULT '{}'::JSONB,
  passed BOOLEAN,
  failure_reasons JSONB DEFAULT '[]'::JSONB,
  total_samples INTEGER DEFAULT 0,
  failed_samples INTEGER DEFAULT 0,
  eval_model TEXT,
  total_eval_cost_usd DOUBLE PRECISION,
  duration_seconds DOUBLE PRECISION,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS eval_sample_results (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  eval_run_id UUID NOT NULL REFERENCES eval_runs(id) ON DELETE CASCADE,
  sample_id TEXT NOT NULL,
  category TEXT,
  user_input TEXT NOT NULL,
  response TEXT NOT NULL,
  retrieved_contexts JSONB NOT NULL DEFAULT '[]'::JSONB,
  reference TEXT,
  faithfulness DOUBLE PRECISION,
  answer_relevancy DOUBLE PRECISION,
  context_precision DOUBLE PRECISION,
  context_recall DOUBLE PRECISION,
  citation_coverage DOUBLE PRECISION,
  decline_accuracy DOUBLE PRECISION,
  latency_ms DOUBLE PRECISION,
  passed BOOLEAN,
  failure_reasons JSONB DEFAULT '[]'::JSONB,
  num_chunks_retrieved INTEGER,
  top_rerank_score DOUBLE PRECISION,
  model_used TEXT,
  prompt_version TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_eval_runs_tenant
  ON eval_runs (tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_eval_runs_git
  ON eval_runs (git_sha);

CREATE INDEX IF NOT EXISTS idx_eval_sample_results_run
  ON eval_sample_results (eval_run_id);

CREATE INDEX IF NOT EXISTS idx_eval_sample_results_category
  ON eval_sample_results (eval_run_id, category);

ALTER TABLE eval_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE eval_sample_results ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "tenant_isolation_eval_runs" ON eval_runs;
CREATE POLICY "tenant_isolation_eval_runs" ON eval_runs
  FOR SELECT
  USING (
    tenant_id = (auth.jwt() -> 'app_metadata' ->> 'organization_id')::UUID
  );

DROP POLICY IF EXISTS "tenant_isolation_eval_samples" ON eval_sample_results;
CREATE POLICY "tenant_isolation_eval_samples" ON eval_sample_results
  FOR SELECT
  USING (
    eval_run_id IN (
      SELECT id FROM eval_runs
      WHERE tenant_id = (auth.jwt() -> 'app_metadata' ->> 'organization_id')::UUID
    )
  );

-- migrate:down

DROP POLICY IF EXISTS "tenant_isolation_eval_samples" ON eval_sample_results;
DROP POLICY IF EXISTS "tenant_isolation_eval_runs" ON eval_runs;

DROP TABLE IF EXISTS eval_sample_results;
DROP TABLE IF EXISTS eval_runs;
