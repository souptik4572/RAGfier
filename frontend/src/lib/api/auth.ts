import { apiClient } from './client';
import type { LoginFormValues, SignupFormValues } from '@/lib/schemas/auth.schema';

export interface AuthResponse {
  access_token: string;
  tenant_id: string;
  user_id: string;
  email: string;
}

export async function login(payload: LoginFormValues): Promise<AuthResponse> {
  return apiClient.post('auth/login', { json: payload }).json<AuthResponse>();
}

export async function signup(payload: SignupFormValues): Promise<AuthResponse> {
  return apiClient.post('auth/signup', { json: payload }).json<AuthResponse>();
}
