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
    mockFetch.mockResolvedValue({ ok: true, type: 'basic', status: 200 });
    const { result } = renderHook(() => useServiceHealth('https://example.com/health'));

    await waitFor(() => expect(result.current.status).toBe('available'));
  });

  it('returns available for opaque response (no-cors)', async () => {
    mockFetch.mockResolvedValue({ ok: false, type: 'opaque', status: 0 });
    const { result } = renderHook(() => useServiceHealth('https://cross-origin.com/health'));

    await waitFor(() => expect(result.current.status).toBe('available'));
  });

  it('returns available for 4xx responses (service is up)', async () => {
    mockFetch.mockResolvedValue({ ok: false, type: 'basic', status: 401 });
    const { result } = renderHook(() => useServiceHealth('https://example.com/health'));

    await waitFor(() => expect(result.current.status).toBe('available'));
  });

  it('returns unavailable for 5xx responses', async () => {
    mockFetch.mockResolvedValue({ ok: false, type: 'basic', status: 500 });
    const { result } = renderHook(() => useServiceHealth('https://example.com/health'));

    await waitFor(() => expect(result.current.status).toBe('unavailable'));
  });

  it('returns unavailable on network error', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));
    const { result } = renderHook(() => useServiceHealth('https://example.com/health'));

    await waitFor(() => expect(result.current.status).toBe('unavailable'));
  });

  it('uses same-origin mode for relative URLs', async () => {
    mockFetch.mockResolvedValue({ ok: true, type: 'basic', status: 200 });
    renderHook(() => useServiceHealth('/api/health'));

    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/health',
      expect.objectContaining({ mode: 'same-origin' })
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
    mockFetch.mockResolvedValue({ ok: true, type: 'basic', status: 200 });
    renderHook(() => useServiceHealth('https://example.com/health'));

    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ method: 'HEAD' })
    );
  });

  it('passes abort signal for timeout', async () => {
    mockFetch.mockResolvedValue({ ok: true, type: 'basic', status: 200 });
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
    mockFetch.mockResolvedValueOnce({ ok: true, type: 'basic', status: 200 });
    result.current.retry();

    await waitFor(() => expect(result.current.status).toBe('available'));
  });
});
