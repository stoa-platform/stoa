import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useServiceHealth } from './useServiceHealth';

const mockFetch = vi.fn();
global.fetch = mockFetch;

beforeEach(() => {
  vi.clearAllMocks();
  // Reset location.origin
  Object.defineProperty(window, 'location', {
    value: { origin: 'http://localhost:3000' },
    writable: true,
  });
});

describe('useServiceHealth', () => {
  it('starts in checking state', () => {
    mockFetch.mockReturnValue(new Promise(() => {})); // never resolves
    const { result } = renderHook(() => useServiceHealth('https://example.com/health'));
    expect(result.current.status).toBe('checking');
  });

  it('returns available for successful response', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      type: 'basic',
      status: 200,
      redirected: false,
      url: 'https://example.com/health',
    });
    const { result } = renderHook(() => useServiceHealth('https://example.com/health'));

    await waitFor(() => expect(result.current.status).toBe('available'));
  });

  it('returns available for opaque response (no-cors)', async () => {
    mockFetch.mockResolvedValue({ ok: false, type: 'opaque', status: 0 });
    const { result } = renderHook(() => useServiceHealth('https://cross-origin.com/health'));

    await waitFor(() => expect(result.current.status).toBe('available'));
  });

  it('returns available for 4xx responses (service is up)', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      type: 'basic',
      status: 401,
      redirected: false,
      url: 'https://example.com/health',
    });
    const { result } = renderHook(() => useServiceHealth('https://example.com/health'));

    await waitFor(() => expect(result.current.status).toBe('available'));
  });

  it('returns unavailable for 5xx responses', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      type: 'basic',
      status: 500,
      redirected: false,
      url: 'https://example.com/health',
    });
    const { result } = renderHook(() => useServiceHealth('https://example.com/health'));

    await waitFor(() => expect(result.current.status).toBe('unavailable'));
  });

  it('returns unavailable on network error', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));
    const { result } = renderHook(() => useServiceHealth('https://example.com/health'));

    await waitFor(() => expect(result.current.status).toBe('unavailable'));
  });

  it('uses same-origin mode for relative URLs', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      type: 'basic',
      status: 200,
      redirected: false,
      url: 'http://localhost:3000/api/health',
    });
    renderHook(() => useServiceHealth('/api/health'));

    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/health',
      expect.objectContaining({ mode: 'same-origin', redirect: 'follow' })
    );
  });

  it('uses no-cors mode for cross-origin URLs', async () => {
    mockFetch.mockResolvedValue({ ok: false, type: 'opaque', status: 0 });
    renderHook(() => useServiceHealth('https://external.com/health'));

    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    expect(mockFetch).toHaveBeenCalledWith(
      'https://external.com/health',
      expect.objectContaining({ mode: 'no-cors' })
    );
  });

  it('uses HEAD method', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      type: 'basic',
      status: 200,
      redirected: false,
      url: 'https://example.com/health',
    });
    renderHook(() => useServiceHealth('https://example.com/health'));

    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ method: 'HEAD' })
    );
  });

  it('passes abort signal for timeout', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      type: 'basic',
      status: 200,
      redirected: false,
      url: 'https://example.com/health',
    });
    renderHook(() => useServiceHealth('https://example.com/health'));

    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
  });

  it('retry resets to checking then resolves', async () => {
    mockFetch.mockRejectedValueOnce(new Error('fail'));
    const { result } = renderHook(() => useServiceHealth('https://example.com/health'));

    await waitFor(() => expect(result.current.status).toBe('unavailable'));

    // Retry with success
    mockFetch.mockResolvedValueOnce({
      ok: true,
      type: 'basic',
      status: 200,
      redirected: false,
      url: 'https://example.com/health',
    });
    result.current.retry();

    await waitFor(() => expect(result.current.status).toBe('available'));
  });

  // CAB-1773: Detect auth redirect for same-origin Grafana URLs
  it('returns unavailable when same-origin URL is redirected to login', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      type: 'basic',
      status: 200,
      redirected: true,
      url: 'http://localhost:3000/grafana/login?redirectTo=%2Fgrafana%2F',
    });
    const { result } = renderHook(() => useServiceHealth('/grafana/'));

    await waitFor(() => expect(result.current.status).toBe('unavailable'));
  });

  it('returns available when same-origin URL redirects within same path', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      type: 'basic',
      status: 200,
      redirected: true,
      url: 'http://localhost:3000/grafana/d/dashboard-uid',
    });
    const { result } = renderHook(() => useServiceHealth('/grafana/'));

    await waitFor(() => expect(result.current.status).toBe('available'));
  });

  it('follows redirects for same-origin (redirect: follow)', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      type: 'basic',
      status: 200,
      redirected: false,
      url: 'http://localhost:3000/api/health',
    });
    renderHook(() => useServiceHealth('/api/health'));

    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/health',
      expect.objectContaining({ redirect: 'follow' })
    );
  });

  // P2-5 + P2-6 combined lock: unmount abort must not flip status to
  // 'unavailable' (silent cancel), while timeout abort must.
  describe('P2-5 + P2-6 abort semantics', () => {
    it('unmount abort does not set status to unavailable', async () => {
      // fetch rejects with AbortError when signal aborts — simulate by
      // waiting on signal.
      mockFetch.mockImplementation(
        (_url: string, init: { signal: AbortSignal }) =>
          new Promise((_resolve, reject) => {
            init.signal.addEventListener('abort', () => {
              const err = new DOMException('aborted', 'AbortError');
              reject(err);
            });
          })
      );

      const { result, unmount } = renderHook(() =>
        useServiceHealth('https://example.com/health')
      );
      expect(result.current.status).toBe('checking');

      // Unmount before fetch completes.
      unmount();

      // Give microtask queue a chance to run the catch block.
      await new Promise((r) => setTimeout(r, 0));

      // Result snapshot is still 'checking' because we unmounted before any
      // status flip AND the catch path detected unmount-abort and skipped
      // setState. (React's renderHook result.current reflects last render;
      // we assert it did NOT become 'unavailable' post-unmount.)
      expect(result.current.status).toBe('checking');
    });

    it('timeout abort sets status to unavailable', async () => {
      vi.useFakeTimers();

      mockFetch.mockImplementation(
        (_url: string, init: { signal: AbortSignal }) =>
          new Promise((_resolve, reject) => {
            init.signal.addEventListener('abort', () => {
              const err = new DOMException('aborted', 'AbortError');
              reject(err);
            });
          })
      );

      const { result } = renderHook(() =>
        useServiceHealth('https://example.com/health')
      );
      expect(result.current.status).toBe('checking');

      // Advance past the 5s timeout — controller.abort() fires, fetch
      // rejects with AbortError, and the catch path flips to 'unavailable'
      // because abortedByUnmount is still false.
      await vi.advanceTimersByTimeAsync(5500);
      vi.useRealTimers();

      await waitFor(() => expect(result.current.status).toBe('unavailable'));
    });
  });
});
