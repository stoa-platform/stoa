/**
 * useChatService — manages chat conversation lifecycle and SSE message streaming.
 *
 * Lazy-creates a conversation on first message, then sends messages via
 * fetch() + ReadableStream (not EventSource — we need the Authorization header).
 * Accumulates content_delta events and returns the full assembled response (V1).
 */
import { useCallback, useRef } from 'react';

import { config } from '@/config';
import { useAuth } from '@/contexts/AuthContext';
import { apiService } from '@/services/api';

export function useChatService() {
  const { user } = useAuth();
  const conversationId = useRef<string | null>(null);

  const sendMessage = useCallback(
    async (message: string): Promise<string> => {
      // Prefer the UI-selected tenant (Layout stores it in localStorage),
      // fall back to the Keycloak token claim for non-admin users.
      const tenantId = localStorage.getItem('stoa-active-tenant') || user?.tenant_id;
      if (!tenantId) throw new Error('No tenant selected');

      const token = apiService.getAuthToken();
      if (!token) throw new Error('Not authenticated');

      // Lazy-create conversation on first message
      if (!conversationId.current) {
        const conv = await apiService.createChatConversation(tenantId);
        conversationId.current = conv.id;
      }

      const url = `${config.api.baseUrl}/v1/tenants/${tenantId}/chat/conversations/${conversationId.current}/messages`;

      const res = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ content: message }),
      });

      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`Chat request failed (${res.status}): ${detail}`);
      }

      // Read SSE stream and accumulate content_delta text
      const reader = res.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let buffer = '';
      let result = '';

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Parse SSE frames: "event: <type>\ndata: <json>\n\n"
        const frames = buffer.split('\n\n');
        buffer = frames.pop() ?? '';

        for (const frame of frames) {
          const dataLine = frame.split('\n').find((l) => l.startsWith('data:'));
          if (!dataLine) continue;

          try {
            const payload = JSON.parse(dataLine.slice(5).trim());
            if (payload.delta !== undefined) {
              result += payload.delta;
            }
          } catch {
            // skip malformed frames
          }
        }
      }

      return result || '(no response)';
    },
    [user]
  );

  return { sendMessage };
}
