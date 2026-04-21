import { apiClient } from './client';

export interface HealthResponse {
  status: 'ok' | 'degraded' | 'down';
  version?: string;
  services?: Record<string, 'up' | 'down' | 'unknown'>;
}

export async function getHealth(): Promise<HealthResponse> {
  return apiClient.get('health').json<HealthResponse>();
}
