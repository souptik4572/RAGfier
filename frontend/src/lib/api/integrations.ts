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

interface CountResponse {
  message: string;
  count: number;
}

export interface UpdateIntegrationPayload {
  name?: string;
  environment?: Integration['environment'];
  metadata?: Record<string, unknown>;
  is_default?: boolean;
}

export interface DeleteIntegrationResponse {
  message: string;
  integration_id: string;
  deleted_documents: number;
  deleted_jobs: number;
  deleted_api_keys: number;
  deleted_storage_objects: number;
}

export async function listIntegrations(): Promise<Integration[]> {
  const res = await apiClient.get('platform/integrations').json<IntegrationListResponse>();
  return res.integrations ?? [];
}

export async function countIntegrations(): Promise<number> {
  const res = await apiClient
    .get('platform/integrations/count')
    .json<CountResponse>();
  return res.count ?? 0;
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

export async function updateIntegration(
  id: string,
  payload: UpdateIntegrationPayload
): Promise<Integration> {
  return apiClient
    .patch(`platform/integrations/${id}`, { json: payload })
    .json<Integration>();
}

export async function deleteIntegration(
  id: string
): Promise<DeleteIntegrationResponse> {
  return apiClient
    .delete(`platform/integrations/${id}`)
    .json<DeleteIntegrationResponse>();
}
