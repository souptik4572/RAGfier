import { apiClient } from './client';

export type ApiKeyScope =
  | 'query:read'
  | 'documents:read'
  | 'documents:write'
  | 'analytics:read';

export type ApiKeyStatus = 'active' | 'revoked' | 'expired';

export interface ApiKey {
  id: string;
  tenant_id: string;
  integration_id: string;
  name: string;
  prefix: string;
  scopes: ApiKeyScope[];
  status: ApiKeyStatus;
  expires_at?: string | null;
  last_used_at?: string | null;
  created_at?: string | null;
}

export interface ApiKeyWithSecret extends ApiKey {
  secret: string;
}

interface ApiKeyListResponse {
  message: string;
  api_keys: ApiKey[];
}

export interface CreateApiKeyPayload {
  name: string;
  integration_id: string;
  scopes: ApiKeyScope[];
  expires_at?: string | null;
}

export async function listApiKeys(): Promise<ApiKey[]> {
  const res = await apiClient.get('platform/api-keys').json<ApiKeyListResponse>();
  return res.api_keys ?? [];
}

export async function createApiKey(
  payload: CreateApiKeyPayload
): Promise<ApiKeyWithSecret> {
  return apiClient
    .post('platform/api-keys', { json: payload })
    .json<ApiKeyWithSecret>();
}

export async function revokeApiKey(id: string): Promise<ApiKey> {
  return apiClient.post(`platform/api-keys/${id}/revoke`).json<ApiKey>();
}
