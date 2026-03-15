import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useChatService } from './useChatService';
import { createAuthMock } from '@/test/helpers';

// ── Module mocks ────────────────────────────────────────────────────────────

vi.mock('@/config', () => ({
  config: {
    api: { baseUrl: 'https://api.test.dev' },
  },
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('@/services/api', () => ({
  apiService: {
    getAuthToken: vi.fn(),
    createChatConversation: vi.fn(),
  },
}));

import { useAuth } from '@/contexts/AuthContext';
import { apiService } from '@/services/api';

const mockUseAuth = vi.mocked(useAuth);
const mockGetAuthToken = vi.mocked(apiService.getAuthToken);
const mockCreateChatConversation = vi.mocked(apiService.createChatConversation);

// ── SSE stream helpers ───────────────────────────────────────────────────────

/** Build a ReadableStream from an array of raw SSE chunks. */
function createSSEStream(events: string[]): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      for (const event of events) {
        controller.enqueue(new TextEncoder().encode(event));
      }
      controller.close();
    },
  });
}

/** Minimal fetch Response with a readable SSE body. */
function okResponse(stream: ReadableStream<Uint8Array>): Response {
  return {
    ok: true,
    body: stream,
    text: vi.fn(),
  } as unknown as Response;
}

// ── Test setup ───────────────────────────────────────────────────────────────

const mockFetch = vi.fn();
global.fetch = mockFetch;

beforeEach(() => {
  vi.clearAllMocks();

  // Default persona: cpi-admin with tenant_id 'gregarious-games'
  mockUseAuth.mockReturnValue(createAuthMock('cpi-admin'));
  mockGetAuthToken.mockReturnValue('test-token');
  mockCreateChatConversation.mockResolvedValue({ id: 'conv-42' });

  // Clear localStorage between tests
  localStorage.clear();
});

afterEach(() => {
  localStorage.clear();
});

// ── Tests ────────────────────────────────────────────────────────────────────

describe('useChatService', () => {
  describe('sendMessage — guard clauses', () => {
    it('throws "No tenant selected" when localStorage empty and user has no tenant_id', async () => {
      mockUseAuth.mockReturnValue({
        ...createAuthMock('cpi-admin'),
        user: { ...createAuthMock('cpi-admin').user, tenant_id: undefined as unknown as string },
      });

      const { result } = renderHook(() => useChatService());

      await expect(act(() => result.current.sendMessage('hello'))).rejects.toThrow(
        'No tenant selected'
      );
    });

    it('throws "Not authenticated" when getAuthToken returns null', async () => {
      mockGetAuthToken.mockReturnValue(null);

      const { result } = renderHook(() => useChatService());

      await expect(act(() => result.current.sendMessage('hello'))).rejects.toThrow(
        'Not authenticated'
      );
    });
  });

  describe('sendMessage — conversation lifecycle', () => {
    it('lazy-creates a conversation on the first message', async () => {
      const stream = createSSEStream(['data: {"delta":"hi"}\n\n']);
      mockFetch.mockResolvedValue(okResponse(stream));

      const { result } = renderHook(() => useChatService());
      await act(() => result.current.sendMessage('first'));

      expect(mockCreateChatConversation).toHaveBeenCalledTimes(1);
      expect(mockCreateChatConversation).toHaveBeenCalledWith('gregarious-games');
    });

    it('reuses the conversation ID on subsequent messages', async () => {
      // Each fetch call must return a FRESH Response with its own ReadableStream —
      // a single ReadableStream can only be read once; a second getReader() throws "locked".
      mockFetch.mockImplementation(() =>
        Promise.resolve(okResponse(createSSEStream(['data: {"delta":"ok"}\n\n'])))
      );

      const { result } = renderHook(() => useChatService());

      await act(() => result.current.sendMessage('first'));
      await act(() => result.current.sendMessage('second'));

      // createChatConversation should only be called once across two messages
      expect(mockCreateChatConversation).toHaveBeenCalledTimes(1);

      // Both fetch calls should use the same conversation ID
      expect(mockFetch).toHaveBeenCalledTimes(2);
      const [url1] = mockFetch.mock.calls[0];
      const [url2] = mockFetch.mock.calls[1];
      expect(url1).toContain('conv-42');
      expect(url2).toContain('conv-42');
    });
  });

  describe('sendMessage — HTTP request', () => {
    it('posts to the correct URL with Authorization header', async () => {
      const stream = createSSEStream(['data: {"delta":"ok"}\n\n']);
      mockFetch.mockResolvedValue(okResponse(stream));

      const { result } = renderHook(() => useChatService());
      await act(() => result.current.sendMessage('test message'));

      expect(mockFetch).toHaveBeenCalledWith(
        'https://api.test.dev/v1/tenants/gregarious-games/chat/conversations/conv-42/messages',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            Authorization: 'Bearer test-token',
            'Content-Type': 'application/json',
          }),
          body: JSON.stringify({ content: 'test message' }),
        })
      );
    });

    it('prefers localStorage tenant over user.tenant_id', async () => {
      localStorage.setItem('stoa-active-tenant', 'local-tenant');
      const stream = createSSEStream(['data: {"delta":"ok"}\n\n']);
      mockFetch.mockResolvedValue(okResponse(stream));

      const { result } = renderHook(() => useChatService());
      await act(() => result.current.sendMessage('hello'));

      expect(mockCreateChatConversation).toHaveBeenCalledWith('local-tenant');
      const [url] = mockFetch.mock.calls[0];
      expect(url).toContain('/tenants/local-tenant/');
    });
  });

  describe('sendMessage — error handling', () => {
    it('throws with status and detail on non-ok response', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 429,
        text: vi.fn().mockResolvedValue('rate limit exceeded'),
      } as unknown as Response);

      const { result } = renderHook(() => useChatService());

      await expect(act(() => result.current.sendMessage('hello'))).rejects.toThrow(
        'Chat request failed (429): rate limit exceeded'
      );
    });

    it('throws "No response body" when res.body is null', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        body: null,
        text: vi.fn(),
      } as unknown as Response);

      const { result } = renderHook(() => useChatService());

      await expect(act(() => result.current.sendMessage('hello'))).rejects.toThrow(
        'No response body'
      );
    });
  });

  describe('sendMessage — SSE stream parsing', () => {
    it('accumulates content_delta events into the final result', async () => {
      const stream = createSSEStream([
        'data: {"delta":"Hello"}\n\n',
        'data: {"delta":", "}\n\n',
        'data: {"delta":"world"}\n\n',
      ]);
      mockFetch.mockResolvedValue(okResponse(stream));

      const { result } = renderHook(() => useChatService());
      let response!: string;
      await act(async () => {
        response = await result.current.sendMessage('hi');
      });

      expect(response).toBe('Hello, world');
    });

    it('returns "(no response)" when stream contains no delta events', async () => {
      const stream = createSSEStream(['event: status\ndata: {"type":"thinking"}\n\n']);
      mockFetch.mockResolvedValue(okResponse(stream));

      const { result } = renderHook(() => useChatService());
      let response!: string;
      await act(async () => {
        response = await result.current.sendMessage('hi');
      });

      expect(response).toBe('(no response)');
    });

    it('handles CRLF line endings in SSE stream', async () => {
      const stream = createSSEStream([
        'data: {"delta":"CR"}\r\n\r\n',
        'data: {"delta":"LF"}\r\n\r\n',
      ]);
      mockFetch.mockResolvedValue(okResponse(stream));

      const { result } = renderHook(() => useChatService());
      let response!: string;
      await act(async () => {
        response = await result.current.sendMessage('hi');
      });

      expect(response).toBe('CRLF');
    });

    it('skips malformed SSE frames gracefully', async () => {
      const stream = createSSEStream([
        'data: not-valid-json\n\n',
        'data: {"delta":"valid"}\n\n',
        'data: {broken\n\n',
      ]);
      mockFetch.mockResolvedValue(okResponse(stream));

      const { result } = renderHook(() => useChatService());
      let response!: string;
      await act(async () => {
        response = await result.current.sendMessage('hi');
      });

      // Only the valid delta should accumulate; malformed frames are silently skipped
      expect(response).toBe('valid');
    });

    it('skips frames that have no data: line', async () => {
      const stream = createSSEStream(['event: ping\n\n', 'data: {"delta":"pong"}\n\n']);
      mockFetch.mockResolvedValue(okResponse(stream));

      const { result } = renderHook(() => useChatService());
      let response!: string;
      await act(async () => {
        response = await result.current.sendMessage('hi');
      });

      expect(response).toBe('pong');
    });

    it('handles multi-chunk frames split across read() calls', async () => {
      // Simulate the stream delivering parts of a single SSE frame across chunks
      const encoder = new TextEncoder();
      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(encoder.encode('data: {"delta":"spl'));
          controller.enqueue(encoder.encode('it"}\n\n'));
          controller.close();
        },
      });
      mockFetch.mockResolvedValue(okResponse(stream));

      const { result } = renderHook(() => useChatService());
      let response!: string;
      await act(async () => {
        response = await result.current.sendMessage('hi');
      });

      expect(response).toBe('split');
    });
  });

  describe('sendMessageStream — confirmation_required event', () => {
    it('fires onConfirmationRequired callback for confirmation events', async () => {
      const stream = createSSEStream([
        'event: content_delta\ndata: {"delta":"I will subscribe you."}\n\n',
        'event: confirmation_required\ndata: {"tool_use_id":"tc-1","tool_name":"subscribe_api","tool_input":{"api_id":"a1"},"description":"Subscribe to Weather API"}\n\n',
        'event: message_end\ndata: {}\n\n',
      ]);
      mockFetch.mockResolvedValue(okResponse(stream));

      const { result } = renderHook(() => useChatService());
      const onConfirmationRequired = vi.fn();
      const onDelta = vi.fn();

      await act(async () => {
        await result.current.sendMessageStream('subscribe me', {
          onDelta,
          onConfirmationRequired,
          onComplete: vi.fn(),
        });
      });

      expect(onDelta).toHaveBeenCalledWith('I will subscribe you.');
      expect(onConfirmationRequired).toHaveBeenCalledWith({
        tool_use_id: 'tc-1',
        tool_name: 'subscribe_api',
        tool_input: { api_id: 'a1' },
        description: 'Subscribe to Weather API',
      });
    });

    it('fires onError callback for error events', async () => {
      const stream = createSSEStream(['event: error\ndata: {"error":"Budget exceeded"}\n\n']);
      mockFetch.mockResolvedValue(okResponse(stream));

      const { result } = renderHook(() => useChatService());
      const onError = vi.fn();

      await act(async () => {
        await result.current.sendMessageStream('hello', { onError });
      });

      expect(onError).toHaveBeenCalledWith('Budget exceeded');
    });

    it('fires tool_use_start and tool_use_result callbacks', async () => {
      const stream = createSSEStream([
        'event: tool_use_start\ndata: {"tool_use_id":"tu-1","tool_name":"list_apis"}\n\n',
        'event: tool_use_result\ndata: {"tool_use_id":"tu-1","tool_name":"list_apis","result":"[{\\"name\\":\\"API1\\"}]"}\n\n',
      ]);
      mockFetch.mockResolvedValue(okResponse(stream));

      const { result } = renderHook(() => useChatService());
      const onToolStart = vi.fn();
      const onToolResult = vi.fn();

      await act(async () => {
        await result.current.sendMessageStream('list', { onToolStart, onToolResult });
      });

      expect(onToolStart).toHaveBeenCalledWith('tu-1', 'list_apis');
      expect(onToolResult).toHaveBeenCalledWith('tu-1', 'list_apis', '[{"name":"API1"}]');
    });
  });

  describe('confirmTool', () => {
    it('sends tool_confirmation payload and parses response stream', async () => {
      // First call: sendMessage to establish conversation
      const initStream = createSSEStream(['data: {"delta":"init"}\n\n']);
      mockFetch.mockResolvedValueOnce(okResponse(initStream));

      const { result } = renderHook(() => useChatService());
      await act(() => result.current.sendMessage('hello'));

      // Second call: confirmTool
      const confirmStream = createSSEStream([
        'event: content_delta\ndata: {"delta":"Subscription created!"}\n\n',
      ]);
      mockFetch.mockResolvedValueOnce(okResponse(confirmStream));

      const onDelta = vi.fn();
      const onComplete = vi.fn();

      await act(async () => {
        await result.current.confirmTool(
          {
            tool_use_id: 'tc-1',
            tool_name: 'subscribe_api',
            tool_input: { api_id: 'a1' },
            description: 'Subscribe',
          },
          true,
          { onDelta, onComplete }
        );
      });

      // Verify the request body includes tool_confirmation
      const [, opts] = mockFetch.mock.calls[1];
      const body = JSON.parse(opts.body as string);
      expect(body.tool_confirmation).toEqual({
        tool_use_id: 'tc-1',
        tool_name: 'subscribe_api',
        tool_input: { api_id: 'a1' },
        approved: true,
      });
      expect(onDelta).toHaveBeenCalledWith('Subscription created!');
    });

    it('does nothing when no active conversation', async () => {
      const { result } = renderHook(() => useChatService());
      const onError = vi.fn();

      await act(async () => {
        await result.current.confirmTool(
          {
            tool_use_id: 'tc-1',
            tool_name: 'subscribe_api',
            tool_input: {},
            description: 'Test',
          },
          true,
          { onError }
        );
      });

      expect(onError).toHaveBeenCalledWith('No active conversation');
      expect(mockFetch).not.toHaveBeenCalled();
    });
  });

  describe('fetchBudgetStatus', () => {
    it('fetches and returns budget data', async () => {
      const budgetData = {
        user_tokens_today: 5000,
        tenant_tokens_today: 12000,
        daily_budget: 50000,
        remaining: 38000,
        budget_exceeded: false,
        usage_percent: 24,
      };
      mockFetch.mockResolvedValue({
        ok: true,
        json: vi.fn().mockResolvedValue(budgetData),
      } as unknown as Response);

      const { result } = renderHook(() => useChatService());
      let budget: unknown;
      await act(async () => {
        budget = await result.current.fetchBudgetStatus();
      });

      expect(budget).toEqual(budgetData);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/chat/usage/budget'),
        expect.objectContaining({
          headers: { Authorization: 'Bearer test-token' },
        })
      );
    });

    it('returns null on error', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
      } as unknown as Response);

      const { result } = renderHook(() => useChatService());
      let budget: unknown;
      await act(async () => {
        budget = await result.current.fetchBudgetStatus();
      });

      expect(budget).toBeNull();
    });
  });

  describe('conversation management', () => {
    it('loadConversations fetches and returns conversation list', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: vi.fn().mockResolvedValue({
          items: [{ id: 'c1', title: 'Chat 1', status: 'active', updated_at: '2026-03-14' }],
        }),
      } as unknown as Response);

      const { result } = renderHook(() => useChatService());
      let convos: unknown;
      await act(async () => {
        convos = await result.current.loadConversations();
      });

      expect(convos).toEqual([
        { id: 'c1', title: 'Chat 1', status: 'active', updated_at: '2026-03-14' },
      ]);
    });

    it('switchConversation updates activeConversationId', () => {
      const { result } = renderHook(() => useChatService());

      act(() => {
        result.current.switchConversation('conv-99');
      });

      expect(result.current.activeConversationId).toBe('conv-99');
    });

    it('newConversation clears activeConversationId', () => {
      const { result } = renderHook(() => useChatService());

      act(() => {
        result.current.switchConversation('conv-99');
      });
      act(() => {
        result.current.newConversation();
      });

      expect(result.current.activeConversationId).toBeNull();
    });

    it('deleteConversation removes from list and clears active if matching', async () => {
      // Setup: load conversations first
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: vi.fn().mockResolvedValue({
          items: [
            { id: 'c1', title: 'Chat 1', status: 'active', updated_at: '2026-03-14' },
            { id: 'c2', title: 'Chat 2', status: 'active', updated_at: '2026-03-14' },
          ],
        }),
      } as unknown as Response);

      const { result } = renderHook(() => useChatService());
      await act(async () => {
        await result.current.loadConversations();
      });

      // Delete c1
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
      } as unknown as Response);

      let deleted!: boolean;
      await act(async () => {
        deleted = await result.current.deleteConversation('c1');
      });

      expect(deleted).toBe(true);
    });
  });
});
