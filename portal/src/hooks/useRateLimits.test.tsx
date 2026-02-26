import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import { useRateLimits } from './useRateLimits';

vi.mock('../services/rateLimits', () => ({
  rateLimitsService: {
    getRateLimits: vi.fn(),
  },
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

import { rateLimitsService } from '../services/rateLimits';
import { useAuth } from '../contexts/AuthContext';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

const mockRateLimitsResponse = {
  limits: [
    { id: 'rl-1', apiId: 'api-1', requestsPerMinute: 100, burstLimit: 200 },
    { id: 'rl-2', apiId: 'api-2', requestsPerMinute: 50, burstLimit: 100 },
  ],
  total: 2,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useAuth).mockReturnValue({
    isAuthenticated: true,
    accessToken: 'mock-token',
  } as any);
});

describe('useRateLimits', () => {
  it('fetches rate limits when authenticated', async () => {
    vi.mocked(rateLimitsService.getRateLimits).mockResolvedValue(mockRateLimitsResponse as any);

    const { result } = renderHook(() => useRateLimits(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(mockRateLimitsResponse);
  });

  it('does not fetch when not authenticated', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: false,
      accessToken: null,
    } as any);

    const { result } = renderHook(() => useRateLimits(), { wrapper: createWrapper() });
    expect(result.current.fetchStatus).toBe('idle');
  });

  it('handles API error', async () => {
    vi.mocked(rateLimitsService.getRateLimits).mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useRateLimits(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
