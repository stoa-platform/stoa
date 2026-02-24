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

describe('useOnboardingFunnel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      accessToken: 'mock-token',
    } as any);
  });

  it('should fetch funnel data when authenticated', async () => {
    vi.mocked(onboardingService.getFunnel).mockResolvedValueOnce({
      stages: [
        { stage: 'register', count: 100, conversion_rate: null },
        { stage: 'first_api', count: 60, conversion_rate: 0.6 },
        { stage: 'first_call', count: 40, conversion_rate: 0.67 },
      ],
      total_started: 100,
      total_completed: 40,
      avg_ttftc_seconds: 300,
      p50_ttftc_seconds: 240,
      p90_ttftc_seconds: 600,
    });

    const { result } = renderHook(() => useOnboardingFunnel(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.stages).toHaveLength(3);
    expect(result.current.data?.total_started).toBe(100);
    expect(result.current.data?.total_completed).toBe(40);
  });

  it('should not fetch when not authenticated', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: false,
      accessToken: null,
    } as any);

    const { result } = renderHook(() => useOnboardingFunnel(), { wrapper: createWrapper() });
    expect(result.current.fetchStatus).toBe('idle');
    expect(onboardingService.getFunnel).not.toHaveBeenCalled();
  });

  it('should not fetch when accessToken is missing', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      accessToken: null,
    } as any);

    const { result } = renderHook(() => useOnboardingFunnel(), { wrapper: createWrapper() });
    expect(result.current.fetchStatus).toBe('idle');
    expect(onboardingService.getFunnel).not.toHaveBeenCalled();
  });

  it('should handle error state', async () => {
    vi.mocked(onboardingService.getFunnel).mockRejectedValueOnce(new Error('Forbidden'));

    const { result } = renderHook(() => useOnboardingFunnel(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.data).toBeUndefined();
  });

  it('should handle null TTFTC values', async () => {
    vi.mocked(onboardingService.getFunnel).mockResolvedValueOnce({
      stages: [],
      total_started: 5,
      total_completed: 0,
      avg_ttftc_seconds: null,
      p50_ttftc_seconds: null,
      p90_ttftc_seconds: null,
    });

    const { result } = renderHook(() => useOnboardingFunnel(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.avg_ttftc_seconds).toBeNull();
    expect(result.current.data?.stages).toEqual([]);
  });
});

describe('useStalledUsers', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      accessToken: 'mock-token',
    } as any);
  });

  it('should fetch stalled users with default hours (24)', async () => {
    vi.mocked(onboardingService.getStalled).mockResolvedValueOnce([
      {
        user_id: 'user-1',
        tenant_id: 'tenant-abc',
        last_step: 'first_api',
        started_at: '2026-02-23T10:00:00Z',
        hours_stalled: 26,
      },
      {
        user_id: 'user-2',
        tenant_id: 'tenant-def',
        last_step: null,
        started_at: '2026-02-22T08:00:00Z',
        hours_stalled: 50,
      },
    ]);

    const { result } = renderHook(() => useStalledUsers(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(2);
    expect(result.current.data?.[0].user_id).toBe('user-1');
    expect(onboardingService.getStalled).toHaveBeenCalledWith(24);
  });

  it('should pass custom hours to the service', async () => {
    vi.mocked(onboardingService.getStalled).mockResolvedValueOnce([]);

    const { result } = renderHook(() => useStalledUsers(48), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(onboardingService.getStalled).toHaveBeenCalledWith(48);
  });

  it('should not fetch when not authenticated', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: false,
      accessToken: null,
    } as any);

    const { result } = renderHook(() => useStalledUsers(), { wrapper: createWrapper() });
    expect(result.current.fetchStatus).toBe('idle');
    expect(onboardingService.getStalled).not.toHaveBeenCalled();
  });

  it('should not fetch when accessToken is missing', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      accessToken: null,
    } as any);

    const { result } = renderHook(() => useStalledUsers(), { wrapper: createWrapper() });
    expect(result.current.fetchStatus).toBe('idle');
    expect(onboardingService.getStalled).not.toHaveBeenCalled();
  });

  it('should handle error state', async () => {
    vi.mocked(onboardingService.getStalled).mockRejectedValueOnce(new Error('Forbidden'));

    const { result } = renderHook(() => useStalledUsers(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.data).toBeUndefined();
  });

  it('should handle empty list when no stalled users', async () => {
    vi.mocked(onboardingService.getStalled).mockResolvedValueOnce([]);

    const { result } = renderHook(() => useStalledUsers(24), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([]);
  });

  it('should handle user with null last_step', async () => {
    vi.mocked(onboardingService.getStalled).mockResolvedValueOnce([
      {
        user_id: 'user-3',
        tenant_id: 'tenant-xyz',
        last_step: null,
        started_at: '2026-02-20T12:00:00Z',
        hours_stalled: 96,
      },
    ]);

    const { result } = renderHook(() => useStalledUsers(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.[0].last_step).toBeNull();
    expect(result.current.data?.[0].hours_stalled).toBe(96);
  });
});
