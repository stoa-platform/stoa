import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { useAccessRequests } from './useAccessRequests';

vi.mock('../services/api', () => ({
  apiService: {
    getAccessRequests: vi.fn(),
  },
}));

import { apiService } from '../services/api';

const mockGetAccessRequests = vi.mocked(apiService.getAccessRequests);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

const mockResponse = {
  items: [
    { id: 'req-1', email: 'alice@example.com', status: 'pending' },
    { id: 'req-2', email: 'bob@example.com', status: 'contacted' },
  ],
  total: 2,
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useAccessRequests', () => {
  it('fetches access requests with filters', async () => {
    mockGetAccessRequests.mockResolvedValue(mockResponse as any);

    const filters = { status: 'pending', page: 1, limit: 25 };
    const { result } = renderHook(() => useAccessRequests(filters), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetAccessRequests).toHaveBeenCalledWith({
      status: 'pending',
      page: 1,
      limit: 25,
    });
    expect(result.current.data).toEqual(mockResponse);
  });

  it('fetches without filters', async () => {
    mockGetAccessRequests.mockResolvedValue(mockResponse as any);

    const { result } = renderHook(() => useAccessRequests({}), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetAccessRequests).toHaveBeenCalledWith({
      status: undefined,
      page: undefined,
      limit: undefined,
    });
  });

  it('respects enabled option', () => {
    renderHook(() => useAccessRequests({}, { enabled: false }), {
      wrapper: createWrapper(),
    });
    expect(mockGetAccessRequests).not.toHaveBeenCalled();
  });

  it('defaults enabled to true', async () => {
    mockGetAccessRequests.mockResolvedValue(mockResponse as any);

    const { result } = renderHook(() => useAccessRequests({ status: 'pending' }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetAccessRequests).toHaveBeenCalled();
  });

  it('uses correct query key including filters', async () => {
    mockGetAccessRequests.mockResolvedValue(mockResponse as any);

    const filters1 = { status: 'pending', page: 1 };
    const { result: result1 } = renderHook(() => useAccessRequests(filters1), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result1.current.isSuccess).toBe(true));

    // Different filters = different cache key = new API call
    const filters2 = { status: 'contacted', page: 2 };
    const { result: result2 } = renderHook(() => useAccessRequests(filters2), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result2.current.isSuccess).toBe(true));
    expect(mockGetAccessRequests).toHaveBeenCalledTimes(2);
  });

  it('handles API error', async () => {
    mockGetAccessRequests.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useAccessRequests({}), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(Error);
  });
});
