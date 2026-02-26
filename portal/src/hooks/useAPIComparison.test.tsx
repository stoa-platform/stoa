import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import { useAPIComparison } from './useAPIComparison';

vi.mock('../services/apiComparison', () => ({
  apiComparisonService: {
    compareAPIs: vi.fn(),
  },
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

import { apiComparisonService } from '../services/apiComparison';
import { useAuth } from '../contexts/AuthContext';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

const mockComparisonResult = {
  apis: [
    { id: 'api-1', name: 'Payments API', version: 'v2', endpoints: 12 },
    { id: 'api-2', name: 'Users API', version: 'v1', endpoints: 8 },
  ],
  differences: { endpoints: 4, methods: 2 },
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useAuth).mockReturnValue({
    isAuthenticated: true,
    accessToken: 'mock-token',
  } as any);
});

describe('useAPIComparison', () => {
  it('fetches comparison when authenticated with >= 2 API IDs', async () => {
    vi.mocked(apiComparisonService.compareAPIs).mockResolvedValue(mockComparisonResult as any);

    const apiIds = ['api-1', 'api-2'];
    const { result } = renderHook(() => useAPIComparison(apiIds), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(apiComparisonService.compareAPIs).toHaveBeenCalledWith(apiIds);
    expect(result.current.data).toEqual(mockComparisonResult);
  });

  it('does not fetch when not authenticated', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: false,
      accessToken: null,
    } as any);

    const { result } = renderHook(() => useAPIComparison(['api-1', 'api-2']), {
      wrapper: createWrapper(),
    });
    expect(result.current.fetchStatus).toBe('idle');
  });

  it('does not fetch with fewer than 2 API IDs', () => {
    const { result } = renderHook(() => useAPIComparison(['api-1']), {
      wrapper: createWrapper(),
    });
    expect(result.current.fetchStatus).toBe('idle');
  });

  it('does not fetch with empty array', () => {
    const { result } = renderHook(() => useAPIComparison([]), {
      wrapper: createWrapper(),
    });
    expect(result.current.fetchStatus).toBe('idle');
  });

  it('uses correct query key including API IDs', async () => {
    vi.mocked(apiComparisonService.compareAPIs).mockResolvedValue(mockComparisonResult as any);

    const { result: r1 } = renderHook(() => useAPIComparison(['api-1', 'api-2']), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(r1.current.isSuccess).toBe(true));

    const { result: r2 } = renderHook(() => useAPIComparison(['api-3', 'api-4']), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(r2.current.isSuccess).toBe(true));
    expect(apiComparisonService.compareAPIs).toHaveBeenCalledTimes(2);
  });

  it('handles API error', async () => {
    vi.mocked(apiComparisonService.compareAPIs).mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useAPIComparison(['api-1', 'api-2']), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
