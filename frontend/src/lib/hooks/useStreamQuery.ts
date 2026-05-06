import { useCallback } from 'react';
import { APIError } from '@/lib/api/client';
import { useAuthStore } from '@/lib/store/authStore';
import { useChatStore } from '@/lib/store/chatStore';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
// Global toggle (exposed to the client). Accepts '1', 'true', 'yes' (case-insensitive).
const INCLUDE_SOURCES_DEFAULT = (() => {
  const v = process.env.NEXT_PUBLIC_INCLUDE_SOURCES;
  if (v === undefined || v === null) return true;
  try {
    return ['1', 'true', 'yes'].includes(String(v).toLowerCase());
  } catch {
    return true;
  }
})();

export function useStreamQuery() {
  const { addUserMessage, startAssistantMessage, appendToken, finalizeCitation, finalizeMessage } =
    useChatStore();

  const streamQuery = useCallback(
    async (
      integrationId: string,
      query: string,
      options: { matchCount?: number; rerank?: boolean; includeSources?: boolean } = {}
    ) => {
      addUserMessage(query);
      const assistantId = startAssistantMessage();

      const token = useAuthStore.getState().accessToken;

      let response: Response;
      try {
        response = await fetch(`${BASE_URL}/query/stream`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            query,
            integration_id: integrationId,
            match_count: options.matchCount ?? 5,
            rerank: options.rerank ?? true,
            include_sources: options.includeSources ?? INCLUDE_SOURCES_DEFAULT,
          }),
        });
      } catch (err) {
        finalizeMessage(assistantId, { declined: false, retrieval_metadata: null });
        throw err;
      }

      if (!response.ok || !response.body) {
        finalizeMessage(assistantId, { declined: false, retrieval_metadata: null });
        let errorMessage = 'An unexpected error occurred';
        try {
          const body = await response.clone().json() as Record<string, unknown>;
          if (response.status === 429) {
            const detail = body.detail as Record<string, unknown> | undefined;
            const retryAfter = detail && typeof detail.retry_after_seconds === 'number'
              ? detail.retry_after_seconds
              : undefined;
            const suffix = retryAfter !== undefined
              ? ` Please try again in ${retryAfter} second${retryAfter === 1 ? '' : 's'}.`
              : '';
            throw new APIError(`Rate limit reached.${suffix}`, 429);
          }
          const detail = body.detail;
          if (typeof detail === 'string' && detail.trim()) errorMessage = detail;
          else if (typeof body.message === 'string' && body.message.trim()) errorMessage = body.message;
        } catch (inner) {
          if (inner instanceof APIError) throw inner;
        }
        throw new APIError(errorMessage, response.status);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      let buffer = '';
      let currentEvent = '';
      let currentData = '';

      const dispatchEvent = (eventType: string, data: string) => {
        if (eventType === 'sources') {
          try {
            const parsed = JSON.parse(data);
            if (parsed.citations) {
              finalizeCitation(assistantId, parsed.citations);
            }
          } catch {
            // ignore malformed JSON
          }
        } else if (eventType === 'token') {
          appendToken(assistantId, data);
        } else if (eventType === 'error') {
          try {
            const parsed = JSON.parse(data);
            const detail = typeof parsed.detail === 'string' ? parsed.detail : JSON.stringify(parsed.detail ?? parsed);
            appendToken(assistantId, `\u26a0\ufe0f ${parsed.message ?? 'Error'}: ${detail}`);
          } catch {
            appendToken(assistantId, `\u26a0\ufe0f ${data}`);
          }
        } else if (eventType === 'done') {
          try {
            const parsed = JSON.parse(data);
            finalizeMessage(assistantId, {
              declined: parsed.declined ?? false,
              retrieval_metadata: parsed.retrieval_metadata ?? null,
            });
          } catch {
            finalizeMessage(assistantId, { declined: false, retrieval_metadata: null });
          }
        }
      };

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          const rawLines = buffer.split('\n');
          // Keep the last (possibly incomplete) line in the buffer
          buffer = rawLines.pop() ?? '';
          // Strip trailing \r so CRLF line endings (per SSE spec) are handled correctly
          const lines = rawLines.map((l) => (l.endsWith('\r') ? l.slice(0, -1) : l));

          for (const line of lines) {
            if (line.startsWith('event:')) {
              currentEvent = line.slice('event:'.length).trim();
            } else if (line.startsWith('data:')) {
              const rawData = line.slice('data:'.length);
              // For token events, preserve the raw string (don't trim — spaces may be tokens)
              // For other events, trim is fine
              currentData = currentEvent === 'token' ? rawData.slice(1) : rawData.trim();
            } else if (line === '') {
              // Blank line = end of event block
              if (currentEvent && currentData !== '') {
                dispatchEvent(currentEvent, currentData);
              }
              currentEvent = '';
              currentData = '';
            }
          }
        }

        // Handle any remaining buffered content
        if (buffer) {
          const lines = buffer.split('\n').map((l) => (l.endsWith('\r') ? l.slice(0, -1) : l));
          for (const line of lines) {
            if (line.startsWith('event:')) {
              currentEvent = line.slice('event:'.length).trim();
            } else if (line.startsWith('data:')) {
              const rawData = line.slice('data:'.length);
              currentData = currentEvent === 'token' ? rawData.slice(1) : rawData.trim();
            }
          }
          if (currentEvent && currentData !== '') {
            dispatchEvent(currentEvent, currentData);
          }
        }
      } finally {
        // Ensure streaming is finalized if it wasn't already
        const currentMessages = useChatStore.getState().messages;
        const assistantMsg = currentMessages.find((m) => m.id === assistantId);
        if (assistantMsg?.isStreaming) {
          finalizeMessage(assistantId, { declined: false, retrieval_metadata: null });
        }
      }
    },
    [addUserMessage, startAssistantMessage, appendToken, finalizeCitation, finalizeMessage]
  );

  return { streamQuery };
}
