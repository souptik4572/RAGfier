import { apiClient } from './client';

export interface PromptSummary {
  id: string;
  name: string;
  version: number;
  is_active: boolean;
  tenant_id?: string | null;
  metadata: Record<string, unknown>;
  created_at?: string | null;
  system_prompt?: string;
  user_prompt_template?: string;
}

interface PromptListResponse {
  message: string;
  prompts: PromptSummary[];
}

export interface CreatePromptPayload {
  name: string;
  system_prompt: string;
  user_prompt_template: string;
  metadata?: Record<string, unknown>;
  global?: boolean;
}

export async function listPrompts(): Promise<PromptSummary[]> {
  const res = await apiClient.get('prompts').json<PromptListResponse>();
  return res.prompts ?? [];
}

export async function createPrompt(
  payload: CreatePromptPayload
): Promise<PromptSummary> {
  return apiClient.post('prompts', { json: payload }).json<PromptSummary>();
}
