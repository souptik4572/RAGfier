import ky, { type BeforeRequestHook, type AfterResponseHook } from 'ky';
import { useAuthStore } from '@/lib/store/authStore';

function extractMessageFromBody(body: unknown): string | undefined {
  if (typeof body === 'string') {
    return body.trim() || undefined;
  }

  if (!body || typeof body !== 'object') {
    return undefined;
  }

  const record = body as Record<string, unknown>;

  const detail = record.detail;
  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }

  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0];
    if (typeof first === 'string' && first.trim()) {
      return first;
    }
    if (first && typeof first === 'object') {
      const firstRecord = first as Record<string, unknown>;
      if (typeof firstRecord.msg === 'string' && firstRecord.msg.trim()) {
        return firstRecord.msg;
      }
      if (typeof firstRecord.message === 'string' && firstRecord.message.trim()) {
        return firstRecord.message;
      }
    }
  }

  if (detail && typeof detail === 'object') {
    const nested = extractMessageFromBody(detail);
    if (nested) {
      return nested;
    }
  }

  if (typeof record.message === 'string' && record.message.trim()) {
    return record.message;
  }

  if (typeof record.error === 'string' && record.error.trim()) {
    return record.error;
  }

  return undefined;
}

export class APIError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'APIError';
    this.status = status;
  }
}

const beforeRequest: BeforeRequestHook = (request) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    request.headers.set('Authorization', `Bearer ${token}`);
  }
};

const afterResponse: AfterResponseHook = async (_request, _options, response) => {
  if (response.status === 401) {
    useAuthStore.getState().clearAuth();
    document.cookie = 'ragfier-token=; Max-Age=0; path=/';
    if (typeof window !== 'undefined') {
      window.location.href = '/login';
    }
    return;
  }

  if (!response.ok) {
    let message = response.statusText || 'An unexpected error occurred';
    try {
      const body = await response.clone().json();
      const extracted = extractMessageFromBody(body);
      if (extracted) {
        message = extracted;
      }
    } catch {
      try {
        const text = await response.clone().text();
        if (text.trim()) {
          message = text;
        }
      } catch {
        // ignore parse errors and keep fallback message
      }
    }
    throw new APIError(message, response.status);
  }
};

export const apiClient = ky.create({
  prefixUrl: process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000',
  hooks: {
    beforeRequest: [beforeRequest],
    afterResponse: [afterResponse],
  },
  timeout: 30000,
});
