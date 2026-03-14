/**
 * useChatService — manages chat conversation lifecycle and SSE message streaming.
 *
 * Supports two modes:
 *   1. Streaming (default) — calls onDelta/onToolUse/onComplete callbacks as SSE events arrive
 *   2. Await mode — accumulates full response and returns it (backward-compatible)
 *
 * Lazy-creates a conversation on first message, then sends messages via
 * fetch() + ReadableStream (not EventSource — we need the Authorization header).
 *
 * CAB-1816: Progressive streaming + tool rendering + conversation management.
 */
import { useCallback, useRef, useState } from 'react';

import { config } from '@/config';
import { useAuth } from '@/contexts/AuthContext';
import { apiService } from '@/services/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ChatToolCall {
  tool_use_id: string;
  tool_name: string;
  result?: string;
}

export interface StreamCallbacks {
  /** Called for each text chunk as it arrives */
  onDelta?: (text: string) => void;
  /** Called when a tool call starts */
  onToolStart?: (toolUseId: string, toolName: string) => void;
  /** Called when a tool call result arrives */
  onToolResult?: (toolUseId: string, toolName: string, result: string) => void;
  /** Called when an error occurs during streaming */
  onError?: (error: string) => void;
  /** Called when the full response is complete */
  onComplete?: (fullText: string, toolCalls: ChatToolCall[]) => void;
}

export interface ConversationSummary {
  id: string;
  title: string;
  status: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useChatService() {
  const { user } = useAuth();
  const conversationId = useRef<string | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  /** Resolve the active tenant from localStorage or user token. */
  const getTenantId = useCallback((): string => {
    const tenantId = localStorage.getItem('stoa-active-tenant') || user?.tenant_id;
    if (!tenantId) throw new Error('No tenant selected');
    return tenantId;
  }, [user]);

  /** Ensure we have a valid auth token. */
  const getToken = useCallback((): string => {
    const token = apiService.getAuthToken();
    if (!token) throw new Error('Not authenticated');
    return token;
  }, []);

  // -------------------------------------------------------------------------
  // Conversation management
  // -------------------------------------------------------------------------

  const loadConversations = useCallback(async (): Promise<ConversationSummary[]> => {
    const tenantId = getTenantId();
    const token = getToken();
    const res = await fetch(
      `${config.api.baseUrl}/v1/tenants/${tenantId}/chat/conversations?limit=20&status=active`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    if (!res.ok) return [];
    const data = await res.json();
    const items: ConversationSummary[] = (data.items || []).map(
      (c: { id: string; title: string; status: string; updated_at: string }) => ({
        id: c.id,
        title: c.title,
        status: c.status,
        updated_at: c.updated_at,
      })
    );
    setConversations(items);
    return items;
  }, [getTenantId, getToken]);

  const switchConversation = useCallback((id: string | null) => {
    conversationId.current = id;
    setActiveConversationId(id);
  }, []);

  const newConversation = useCallback(() => {
    conversationId.current = null;
    setActiveConversationId(null);
  }, []);

  const deleteConversation = useCallback(
    async (id: string): Promise<boolean> => {
      const tenantId = getTenantId();
      const token = getToken();
      const res = await fetch(
        `${config.api.baseUrl}/v1/tenants/${tenantId}/chat/conversations/${id}`,
        { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } }
      );
      if (res.ok || res.status === 204) {
        setConversations((prev) => prev.filter((c) => c.id !== id));
        if (conversationId.current === id) {
          newConversation();
        }
        return true;
      }
      return false;
    },
    [getTenantId, getToken, newConversation]
  );

  // -------------------------------------------------------------------------
  // Abort support
  // -------------------------------------------------------------------------

  const abort = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  // -------------------------------------------------------------------------
  // Streaming message send
  // -------------------------------------------------------------------------

  const sendMessageStream = useCallback(
    async (message: string, callbacks: StreamCallbacks = {}): Promise<void> => {
      const tenantId = getTenantId();
      const token = getToken();

      // Lazy-create conversation on first message
      if (!conversationId.current) {
        const conv = await apiService.createChatConversation(tenantId);
        conversationId.current = conv.id;
        setActiveConversationId(conv.id);
      }

      const url = `${config.api.baseUrl}/v1/tenants/${tenantId}/chat/conversations/${conversationId.current}/messages`;

      // Abort any previous in-flight request
      abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const res = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ content: message }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const detail = await res.text();
        const errMsg = `Chat request failed (${res.status}): ${detail}`;
        callbacks.onError?.(errMsg);
        throw new Error(errMsg);
      }

      const reader = res.body?.getReader();
      if (!reader) {
        callbacks.onError?.('No response body');
        throw new Error('No response body');
      }

      const decoder = new TextDecoder();
      let buffer = '';
      let fullText = '';
      const toolCalls: ChatToolCall[] = [];

      try {
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
          const frames = buffer.split('\n\n');
          buffer = frames.pop() ?? '';

          for (const frame of frames) {
            const eventLine = frame.split('\n').find((l) => l.startsWith('event:'));
            const dataLine = frame.split('\n').find((l) => l.startsWith('data:'));
            if (!dataLine) continue;

            const eventType = eventLine?.slice(6).trim() ?? 'message';

            try {
              const payload = JSON.parse(dataLine.slice(5).trim());

              switch (eventType) {
                case 'content_delta':
                case 'message': {
                  const delta = payload.delta ?? payload.content ?? '';
                  if (delta) {
                    fullText += delta;
                    callbacks.onDelta?.(delta);
                  }
                  break;
                }
                case 'tool_use_start':
                  callbacks.onToolStart?.(payload.tool_use_id, payload.tool_name);
                  break;
                case 'tool_use_result': {
                  const tc: ChatToolCall = {
                    tool_use_id: payload.tool_use_id,
                    tool_name: payload.tool_name,
                    result: payload.result,
                  };
                  toolCalls.push(tc);
                  callbacks.onToolResult?.(payload.tool_use_id, payload.tool_name, payload.result);
                  break;
                }
                case 'error':
                  callbacks.onError?.(payload.error || 'Unknown error');
                  break;
                case 'message_end':
                  // Final event — streaming complete
                  break;
                default:
                  break;
              }
            } catch {
              // skip malformed frames
            }
          }
        }
      } finally {
        abortRef.current = null;
      }

      callbacks.onComplete?.(fullText, toolCalls);
    },
    [getTenantId, getToken, abort]
  );

  // -------------------------------------------------------------------------
  // Backward-compatible: accumulate full response (used by simple callers)
  // -------------------------------------------------------------------------

  const sendMessage = useCallback(
    async (message: string): Promise<string> => {
      let result = '';
      await sendMessageStream(message, {
        onDelta: (delta) => {
          result += delta;
        },
      });
      return result || '(no response)';
    },
    [sendMessageStream]
  );

  return {
    /** Send a message and get the full response (backward-compatible) */
    sendMessage,
    /** Send a message with streaming callbacks */
    sendMessageStream,
    /** Abort the current streaming request */
    abort,
    /** Load conversation list */
    loadConversations,
    /** Switch to an existing conversation */
    switchConversation,
    /** Start a new conversation */
    newConversation,
    /** Delete a conversation */
    deleteConversation,
    /** List of loaded conversations */
    conversations,
    /** Currently active conversation ID */
    activeConversationId,
  };
}
