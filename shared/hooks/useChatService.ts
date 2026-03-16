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
 * CAB-1816 Phase 2: Mutation tool confirmation + token budget.
 * CAB-1836: Extracted to shared/ for Console + Portal reuse.
 */
import { useCallback, useRef, useState } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ChatToolCall {
  tool_use_id: string;
  tool_name: string;
  result?: string;
}

export interface PendingConfirmation {
  tool_use_id: string;
  tool_name: string;
  tool_input: Record<string, unknown>;
  description: string;
}

export interface StreamCallbacks {
  /** Called for each text chunk as it arrives */
  onDelta?: (text: string) => void;
  /** Called when a tool call starts */
  onToolStart?: (toolUseId: string, toolName: string) => void;
  /** Called when a tool call result arrives */
  onToolResult?: (toolUseId: string, toolName: string, result: string) => void;
  /** Called when a mutation tool requires user confirmation */
  onConfirmationRequired?: (confirmation: PendingConfirmation) => void;
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

export interface TokenBudgetStatus {
  user_tokens_today: number;
  tenant_tokens_today: number;
  daily_budget: number;
  remaining: number;
  budget_exceeded: boolean;
  usage_percent: number;
}

/**
 * App-specific dependencies injected by the consumer (Console or Portal).
 * Using dependency injection keeps this hook app-agnostic.
 */
export interface ChatServiceOptions {
  /** Base URL for the Control Plane API (e.g. https://api.gostoa.dev) */
  apiBaseUrl: string;
  /** Returns the current bearer token, or null if not authenticated */
  getToken: () => string | null;
  /** Returns the active tenant ID, or throws if none is available */
  getTenantId: () => string;
  /** Creates a new chat conversation and returns its ID */
  createConversation: (tenantId: string) => Promise<{ id: string }>;
  /** Identifies which app is using the chat — sent as X-Chat-Source header (CAB-1852) */
  source?: 'console' | 'portal';
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useChatService(options: ChatServiceOptions) {
  // Store options in a ref so callbacks stay stable across renders
  // while always using the latest values.
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const conversationId = useRef<string | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  /** Resolve the active tenant via the injected getTenantId. */
  const getTenantId = useCallback((): string => {
    return optionsRef.current.getTenantId();
  }, []);

  /** Ensure we have a valid auth token via the injected getToken. */
  const getToken = useCallback((): string => {
    const token = optionsRef.current.getToken();
    if (!token) throw new Error('Not authenticated');
    return token;
  }, []);

  /** Build base headers including optional X-Chat-Source (CAB-1852). */
  const buildHeaders = useCallback(
    (token: string, extra: Record<string, string> = {}): Record<string, string> => {
      const headers: Record<string, string> = { Authorization: `Bearer ${token}`, ...extra };
      const src = optionsRef.current.source;
      if (src) headers['X-Chat-Source'] = src;
      return headers;
    },
    []
  );

  // -------------------------------------------------------------------------
  // Conversation management
  // -------------------------------------------------------------------------

  const loadConversations = useCallback(async (): Promise<ConversationSummary[]> => {
    const tenantId = getTenantId();
    const token = getToken();
    const res = await fetch(
      `${optionsRef.current.apiBaseUrl}/v1/tenants/${tenantId}/chat/conversations?limit=20&status=active`,
      { headers: buildHeaders(token) }
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
  }, [getTenantId, getToken, buildHeaders]);

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
        `${optionsRef.current.apiBaseUrl}/v1/tenants/${tenantId}/chat/conversations/${id}`,
        { method: 'DELETE', headers: buildHeaders(token) }
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
    [getTenantId, getToken, newConversation, buildHeaders]
  );

  // -------------------------------------------------------------------------
  // Abort support
  // -------------------------------------------------------------------------

  const abort = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  // -------------------------------------------------------------------------
  // SSE stream parser (shared between sendMessageStream and confirmTool)
  // -------------------------------------------------------------------------

  const parseSSEStream = useCallback(
    async (res: Response, callbacks: StreamCallbacks): Promise<void> => {
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
                case 'confirmation_required':
                  callbacks.onConfirmationRequired?.({
                    tool_use_id: payload.tool_use_id,
                    tool_name: payload.tool_name,
                    tool_input: payload.tool_input,
                    description: payload.description,
                  });
                  break;
                case 'error':
                  callbacks.onError?.(payload.error || 'Unknown error');
                  break;
                case 'message_end':
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
    []
  );

  // -------------------------------------------------------------------------
  // Streaming message send
  // -------------------------------------------------------------------------

  const sendMessageStream = useCallback(
    async (message: string, callbacks: StreamCallbacks = {}): Promise<void> => {
      const tenantId = getTenantId();
      const token = getToken();

      // Lazy-create conversation on first message
      if (!conversationId.current) {
        const conv = await optionsRef.current.createConversation(tenantId);
        conversationId.current = conv.id;
        setActiveConversationId(conv.id);
      }

      const url = `${optionsRef.current.apiBaseUrl}/v1/tenants/${tenantId}/chat/conversations/${conversationId.current}/messages`;

      // Abort any previous in-flight request
      abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const res = await fetch(url, {
        method: 'POST',
        headers: buildHeaders(token, { 'Content-Type': 'application/json' }),
        body: JSON.stringify({ content: message }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const detail = await res.text();
        const errMsg = `Chat request failed (${res.status}): ${detail}`;
        callbacks.onError?.(errMsg);
        throw new Error(errMsg);
      }

      await parseSSEStream(res, callbacks);
    },
    [getTenantId, getToken, abort, parseSSEStream, buildHeaders]
  );

  // -------------------------------------------------------------------------
  // Tool confirmation (CAB-1816 Phase 2)
  // -------------------------------------------------------------------------

  const confirmTool = useCallback(
    async (
      confirmation: PendingConfirmation,
      approved: boolean,
      callbacks: StreamCallbacks = {}
    ): Promise<void> => {
      const tenantId = getTenantId();
      const token = getToken();

      if (!conversationId.current) {
        callbacks.onError?.('No active conversation');
        return;
      }

      const url = `${optionsRef.current.apiBaseUrl}/v1/tenants/${tenantId}/chat/conversations/${conversationId.current}/messages`;

      abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const res = await fetch(url, {
        method: 'POST',
        headers: buildHeaders(token, { 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          content: approved
            ? `Confirmed: ${confirmation.tool_name}`
            : `Cancelled: ${confirmation.tool_name}`,
          tool_confirmation: {
            tool_use_id: confirmation.tool_use_id,
            tool_name: confirmation.tool_name,
            tool_input: confirmation.tool_input,
            approved,
          },
        }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const detail = await res.text();
        callbacks.onError?.(`Confirmation failed (${res.status}): ${detail}`);
        return;
      }

      await parseSSEStream(res, callbacks);
    },
    [getTenantId, getToken, abort, parseSSEStream, buildHeaders]
  );

  // -------------------------------------------------------------------------
  // Token budget status (CAB-1816 Phase 2)
  // -------------------------------------------------------------------------

  const fetchBudgetStatus = useCallback(async (): Promise<TokenBudgetStatus | null> => {
    const tenantId = getTenantId();
    const token = getToken();
    const res = await fetch(
      `${optionsRef.current.apiBaseUrl}/v1/tenants/${tenantId}/chat/usage/budget`,
      { headers: buildHeaders(token) }
    );
    if (!res.ok) return null;
    return res.json();
  }, [getTenantId, getToken, buildHeaders]);

  // -------------------------------------------------------------------------
  // Load conversation messages (for history switching)
  // -------------------------------------------------------------------------

  const loadConversationMessages = useCallback(
    async (convId: string): Promise<{ role: string; content: string; created_at: string }[]> => {
      const tenantId = getTenantId();
      const token = getToken();
      const res = await fetch(
        `${optionsRef.current.apiBaseUrl}/v1/tenants/${tenantId}/chat/conversations/${convId}`,
        { headers: buildHeaders(token) }
      );
      if (!res.ok) return [];
      const data = await res.json();
      return (data.messages || []).map(
        (m: { role: string; content: string; created_at: string }) => ({
          role: m.role,
          content: m.content,
          created_at: m.created_at,
        })
      );
    },
    [getTenantId, getToken, buildHeaders]
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
    /** Confirm or reject a pending mutation tool */
    confirmTool,
    /** Fetch token budget status */
    fetchBudgetStatus,
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
    /** Load messages for a specific conversation */
    loadConversationMessages,
    /** List of loaded conversations */
    conversations,
    /** Currently active conversation ID */
    activeConversationId,
  };
}
