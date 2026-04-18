import { apiClient } from './client';
import type { CreateIntegrationFormValues } from '@/lib/schemas/integration.schema';

export interface Integration {
  id: string;
  name: string;
  environment: 'production' | 'staging' | 'development';
  metadata?: Record<string, unknown>;
  is_default?: boolean;
  created_at: string;
  updated_at: string;
}

interface IntegrationListResponse {
  integrations: Integration[];
}

export async function listIntegrations(): Promise<Integration[]> {
  const res = await apiClient.get('platform/integrations').json<IntegrationListResponse>();
  return res.integrations ?? [];
}

export async function getIntegration(id: string): Promise<Integration> {
  return apiClient.get(`platform/integrations/${id}`).json<Integration>();
}

export async function createIntegration(
  payload: CreateIntegrationFormValues
): Promise<Integration> {
  return apiClient
    .post('platform/integrations', { json: payload })
    .json<Integration>();
}

export async function deleteIntegration(id: string): Promise<void> {
  await apiClient.delete(`platform/integrations/${id}`);
}
