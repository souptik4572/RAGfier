import { apiClient } from './client';

export interface EvalRunScores {
  faithfulness_avg?: number | null;
  answer_relevancy_avg?: number | null;
  context_precision_avg?: number | null;
  context_recall_avg?: number | null;
  citation_coverage_avg?: number | null;
  decline_accuracy_avg?: number | null;
  latency_compliance_avg?: number | null;
}

export interface EvalRunSummary {
  id: string;
  dataset_version: string;
  trigger: string;
  git_sha?: string | null;
  git_branch?: string | null;
  status: string;
  passed?: boolean | null;
  scores: EvalRunScores;
  total_samples: number;
  failed_samples: number;
  created_at?: string | null;
}

export interface EvalSampleScores {
  faithfulness?: number | null;
  answer_relevancy?: number | null;
  context_precision?: number | null;
  context_recall?: number | null;
  citation_coverage?: number | null;
  decline_accuracy?: number | null;
}

export interface EvalSampleResult {
  sample_id: string;
  category?: string | null;
  user_input: string;
  response: string;
  scores: EvalSampleScores;
  passed?: boolean | null;
  failure_reasons: unknown[];
}

interface EvalRunListResponse {
  message: string;
  runs: EvalRunSummary[];
}

interface EvalSampleListResponse {
  message: string;
  run_id: string;
  samples: EvalSampleResult[];
}

export async function listEvalRuns(): Promise<EvalRunSummary[]> {
  const res = await apiClient.get('eval/runs').json<EvalRunListResponse>();
  return res.runs ?? [];
}

export async function listEvalSamples(
  runId: string
): Promise<EvalSampleResult[]> {
  const res = await apiClient
    .get(`eval/runs/${runId}/samples`)
    .json<EvalSampleListResponse>();
  return res.samples ?? [];
}

export interface StartEvalRunPayload {
  dataset_version?: string;
  trigger?: string;
}

export interface StartEvalRunResponse {
  message: string;
  eval_run_id: string;
  status: string;
}

export async function startEvalRun(
  payload: StartEvalRunPayload
): Promise<StartEvalRunResponse> {
  return apiClient
    .post('eval/run', { json: payload })
    .json<StartEvalRunResponse>();
}
