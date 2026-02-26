import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import { useExecutions, useExecutionTaxonomy } from './useExecutions';

vi.mock('../services/executions', () => ({
  executionsService: {
    list: vi.fn(),
    getTaxonomy: vi.fn(),
  },
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

import { executionsService } from '../services/executions';
import { useAuth } from '../contexts/AuthContext';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

const mockExecutionsResponse = {
  items: [
    { id: 'exec-1', toolName: 'payments', status: 'success', duration: 120 },
    { id: 'exec-2', toolName: 'users', status: 'error', duration: 5000 },
  ],
  total: 2,
};

const mockTaxonomyResponse = {
  categories: [
    { name: 'timeout', count: 15 },
    { name: 'auth_failure', count: 8 },
    { name: 'rate_limited', count: 3 },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useAuth).mockReturnValue({
    isAuthenticated: true,
    accessToken: 'mock-token',
  } as any);
});

describe('useExecutions', () => {
  it('fetches executions when authenticated', async () => {
    vi.mocked(executionsService.list).mockResolvedValue(mockExecutionsResponse as any);

    const { result } = renderHook(() => useExecutions(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(executionsService.list).toHaveBeenCalledWith(undefined);
    expect(result.current.data).toEqual(mockExecutionsResponse);
  });

  it('fetches executions with params', async () => {
    vi.mocked(executionsService.list).mockResolvedValue(mockExecutionsResponse as any);

    const params = { status: 'error', page: 1 };
    const { result } = renderHook(() => useExecutions(params as any), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(executionsService.list).toHaveBeenCalledWith(params);
  });

  it('does not fetch when not authenticated', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: false,
      accessToken: null,
    } as any);

    const { result } = renderHook(() => useExecutions(), { wrapper: createWrapper() });
    expect(result.current.fetchStatus).toBe('idle');
  });

  it('handles API error', async () => {
    vi.mocked(executionsService.list).mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useExecutions(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe('useExecutionTaxonomy', () => {
  it('fetches taxonomy when authenticated', async () => {
    vi.mocked(executionsService.getTaxonomy).mockResolvedValue(mockTaxonomyResponse as any);

    const { result } = renderHook(() => useExecutionTaxonomy(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(mockTaxonomyResponse);
  });

  it('does not fetch when not authenticated', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: false,
      accessToken: null,
    } as any);

    const { result } = renderHook(() => useExecutionTaxonomy(), { wrapper: createWrapper() });
    expect(result.current.fetchStatus).toBe('idle');
  });

  it('handles API error', async () => {
    vi.mocked(executionsService.getTaxonomy).mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useExecutionTaxonomy(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
