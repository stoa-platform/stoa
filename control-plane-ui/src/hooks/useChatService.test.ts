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
});
