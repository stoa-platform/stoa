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

describe('useExecutions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      accessToken: 'mock-token',
    } as any);
  });

  it('should fetch executions when authenticated', async () => {
    vi.mocked(executionsService.list).mockResolvedValueOnce({
      items: [
        {
          id: 'exec-1',
          api_name: 'Payments API',
          tool_name: 'charge',
          request_id: 'req-abc',
          method: 'POST',
          path: '/v1/charges',
          status_code: 200,
          status: 'success',
          error_category: null,
          error_message: null,
          started_at: '2026-02-24T10:00:00Z',
          completed_at: '2026-02-24T10:00:01Z',
          duration_ms: 42,
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });

    const { result } = renderHook(() => useExecutions(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items).toHaveLength(1);
    expect(result.current.data?.items[0].id).toBe('exec-1');
    expect(result.current.data?.total).toBe(1);
  });

  it('should not fetch when not authenticated', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: false,
      accessToken: null,
    } as any);

    const { result } = renderHook(() => useExecutions(), { wrapper: createWrapper() });
    expect(result.current.fetchStatus).toBe('idle');
    expect(executionsService.list).not.toHaveBeenCalled();
  });

  it('should not fetch when accessToken is missing', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      accessToken: null,
    } as any);

    const { result } = renderHook(() => useExecutions(), { wrapper: createWrapper() });
    expect(result.current.fetchStatus).toBe('idle');
    expect(executionsService.list).not.toHaveBeenCalled();
  });

  it('should pass params to the service', async () => {
    vi.mocked(executionsService.list).mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 2,
      page_size: 10,
    });

    const params = { status: 'error', page: 2, page_size: 10 };
    const { result } = renderHook(() => useExecutions(params), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(executionsService.list).toHaveBeenCalledWith(params);
  });

  it('should handle error state', async () => {
    vi.mocked(executionsService.list).mockRejectedValueOnce(new Error('Network error'));

    const { result } = renderHook(() => useExecutions(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.data).toBeUndefined();
  });

  it('should handle empty items list', async () => {
    vi.mocked(executionsService.list).mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
    });

    const { result } = renderHook(() => useExecutions(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items).toEqual([]);
    expect(result.current.data?.total).toBe(0);
  });
});

describe('useExecutionTaxonomy', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      accessToken: 'mock-token',
    } as any);
  });

  it('should fetch taxonomy when authenticated', async () => {
    vi.mocked(executionsService.getTaxonomy).mockResolvedValueOnce({
      items: [
        {
          category: 'timeout',
          count: 3,
          avg_duration_ms: 5000,
          percentage: 60,
        },
        {
          category: 'auth_error',
          count: 2,
          avg_duration_ms: null,
          percentage: 40,
        },
      ],
      total_errors: 5,
      total_executions: 50,
      error_rate: 0.1,
    });

    const { result } = renderHook(() => useExecutionTaxonomy(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items).toHaveLength(2);
    expect(result.current.data?.total_errors).toBe(5);
    expect(result.current.data?.error_rate).toBe(0.1);
  });

  it('should not fetch when not authenticated', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: false,
      accessToken: null,
    } as any);

    const { result } = renderHook(() => useExecutionTaxonomy(), { wrapper: createWrapper() });
    expect(result.current.fetchStatus).toBe('idle');
    expect(executionsService.getTaxonomy).not.toHaveBeenCalled();
  });

  it('should not fetch when accessToken is missing', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      accessToken: null,
    } as any);

    const { result } = renderHook(() => useExecutionTaxonomy(), { wrapper: createWrapper() });
    expect(result.current.fetchStatus).toBe('idle');
    expect(executionsService.getTaxonomy).not.toHaveBeenCalled();
  });

  it('should handle error state', async () => {
    vi.mocked(executionsService.getTaxonomy).mockRejectedValueOnce(new Error('API failure'));

    const { result } = renderHook(() => useExecutionTaxonomy(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.data).toBeUndefined();
  });

  it('should handle empty taxonomy', async () => {
    vi.mocked(executionsService.getTaxonomy).mockResolvedValueOnce({
      items: [],
      total_errors: 0,
      total_executions: 100,
      error_rate: 0,
    });

    const { result } = renderHook(() => useExecutionTaxonomy(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items).toEqual([]);
    expect(result.current.data?.error_rate).toBe(0);
  });
});
