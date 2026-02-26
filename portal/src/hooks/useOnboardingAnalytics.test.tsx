import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import { useOnboardingFunnel, useStalledUsers } from './useOnboardingAnalytics';

vi.mock('../services/onboarding', () => ({
  onboardingService: {
    getFunnel: vi.fn(),
    getStalled: vi.fn(),
  },
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

import { onboardingService } from '../services/onboarding';
import { useAuth } from '../contexts/AuthContext';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

const mockFunnelResponse = {
  stages: [
    { name: 'signup', count: 100, conversionRate: 1.0 },
    { name: 'first_api_key', count: 65, conversionRate: 0.65 },
    { name: 'first_call', count: 40, conversionRate: 0.4 },
  ],
};

const mockStalledUsers = [
  { id: 'u1', email: 'dev@example.com', stalledAt: 'first_api_key', hoursSinceActivity: 48 },
  { id: 'u2', email: 'test@example.com', stalledAt: 'signup', hoursSinceActivity: 72 },
];

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useAuth).mockReturnValue({
    isAuthenticated: true,
    accessToken: 'mock-token',
  } as any);
});

describe('useOnboardingFunnel', () => {
  it('fetches funnel data when authenticated', async () => {
    vi.mocked(onboardingService.getFunnel).mockResolvedValue(mockFunnelResponse as any);

    const { result } = renderHook(() => useOnboardingFunnel(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(mockFunnelResponse);
  });

  it('does not fetch when not authenticated', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: false,
      accessToken: null,
    } as any);

    const { result } = renderHook(() => useOnboardingFunnel(), { wrapper: createWrapper() });
    expect(result.current.fetchStatus).toBe('idle');
  });

  it('handles API error', async () => {
    vi.mocked(onboardingService.getFunnel).mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useOnboardingFunnel(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe('useStalledUsers', () => {
  it('fetches stalled users with default hours', async () => {
    vi.mocked(onboardingService.getStalled).mockResolvedValue(mockStalledUsers as any);

    const { result } = renderHook(() => useStalledUsers(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(onboardingService.getStalled).toHaveBeenCalledWith(24);
    expect(result.current.data).toEqual(mockStalledUsers);
  });

  it('fetches stalled users with custom hours', async () => {
    vi.mocked(onboardingService.getStalled).mockResolvedValue(mockStalledUsers as any);

    const { result } = renderHook(() => useStalledUsers(48), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(onboardingService.getStalled).toHaveBeenCalledWith(48);
  });

  it('does not fetch when not authenticated', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: false,
      accessToken: null,
    } as any);

    const { result } = renderHook(() => useStalledUsers(), { wrapper: createWrapper() });
    expect(result.current.fetchStatus).toBe('idle');
  });

  it('handles API error', async () => {
    vi.mocked(onboardingService.getStalled).mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useStalledUsers(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
