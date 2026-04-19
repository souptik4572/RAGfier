import { apiClient } from './client';

export interface UsageBucket {
  window_start?: string | null;
  request_count: number;
  success_count: number;
  error_count: number;
  total_input_tokens: number;
  total_output_tokens: number;
  avg_latency_ms: number;
}

interface UsageResponse {
  message: string;
  buckets: UsageBucket[];
}

export interface ListUsageParams {
  days?: number;
}

export async function listUsage(
  params: ListUsageParams = {}
): Promise<UsageBucket[]> {
  const searchParams: Record<string, string | number> = {};
  if (params.days) searchParams.days = params.days;
  const res = await apiClient
    .get('platform/usage', { searchParams })
    .json<UsageResponse>();
  return res.buckets ?? [];
}
