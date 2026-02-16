import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { useApiConnectivity } from './useApiConnectivity';

vi.mock('../config', () => ({
  config: {
    api: { baseUrl: 'https://api.test.dev' },
  },
}));

const mockFetch = vi.fn();
global.fetch = mockFetch;

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.clearAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('useApiConnectivity', () => {
  it('returns isChecking=true initially', () => {
    mockFetch.mockReturnValue(new Promise(() => {})); // never resolves
    const { result } = renderHook(() => useApiConnectivity(), { wrapper: createWrapper() });
    expect(result.current.isChecking).toBe(true);
    expect(result.current.isConnected).toBe(false);
  });

  it('returns isConnected=true when health check succeeds', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ status: 'healthy' }),
    });

    const { result } = renderHook(() => useApiConnectivity(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isConnected).toBe(true));
    expect(result.current.isChecking).toBe(false);
  });

  it('returns isConnected=false when health check fails', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useApiConnectivity(), { wrapper: createWrapper() });

    // Advance past retry delay (hook has retry: 1, retryDelay: 5000)
    await vi.advanceTimersByTimeAsync(6000);

    await waitFor(() => expect(result.current.isConnected).toBe(false));
  });

  it('calls correct health endpoint', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ status: 'healthy' }),
    });

    renderHook(() => useApiConnectivity(), { wrapper: createWrapper() });

    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    expect(mockFetch).toHaveBeenCalledWith(
      'https://api.test.dev/health',
      expect.objectContaining({ method: 'GET' })
    );
  });

  it('returns isConnected=false when API returns error status', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
    });

    const { result } = renderHook(() => useApiConnectivity(), { wrapper: createWrapper() });

    // Advance past retry delay
    await vi.advanceTimersByTimeAsync(6000);

    await waitFor(() => expect(result.current.isConnected).toBe(false));
  });
});
