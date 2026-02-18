/**
 * Tests for useOnboarding hooks (CAB-1325)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import { useOnboardingProgress, useMarkStep, useCompleteOnboarding } from '../useOnboarding';
import * as onboardingService from '../../services/onboarding';

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: vi.fn().mockReturnValue({
    isAuthenticated: true,
    accessToken: 'mock-token',
    user: { tenant_id: 'test-tenant' },
  }),
}));

vi.mock('../../services/onboarding');

const mockGetProgress = vi.mocked(onboardingService.getProgress);
const mockMarkStep = vi.mocked(onboardingService.markStep);
const mockComplete = vi.mocked(onboardingService.complete);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

const mockProgress: onboardingService.OnboardingProgressResponse = {
  tenant_id: 'test-tenant',
  user_id: 'test-user',
  steps_completed: { choose_use_case: '2026-02-20T14:00:00Z' },
  started_at: '2026-02-20T14:00:00Z',
  completed_at: null,
  ttftc_seconds: null,
  is_complete: false,
};

describe('useOnboardingProgress', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetProgress.mockResolvedValue(mockProgress);
  });

  it('fetches progress when authenticated with tenant', async () => {
    const { result } = renderHook(() => useOnboardingProgress(), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.tenant_id).toBe('test-tenant');
  });

  it('skips when no tenant_id', async () => {
    const { useAuth } = await import('../../contexts/AuthContext');
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      accessToken: 'mock-token',
      user: { tenant_id: undefined },
    } as ReturnType<typeof useAuth>);

    const { result } = renderHook(() => useOnboardingProgress(), {
      wrapper: createWrapper(),
    });
    // Should not fetch — enabled=false
    expect(result.current.isFetching).toBe(false);
  });
});

describe('useMarkStep', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockMarkStep.mockResolvedValue({
      ...mockProgress,
      steps_completed: {
        choose_use_case: '2026-02-20T14:00:00Z',
        create_app: '2026-02-20T14:05:00Z',
      },
    });
  });

  it('calls markStep service', async () => {
    const { result } = renderHook(() => useMarkStep(), {
      wrapper: createWrapper(),
    });
    result.current.mutate('create_app');
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockMarkStep).toHaveBeenCalledWith('create_app');
  });

  it('handles error gracefully', async () => {
    mockMarkStep.mockRejectedValue(new Error('Network error'));
    const { result } = renderHook(() => useMarkStep(), {
      wrapper: createWrapper(),
    });
    result.current.mutate('create_app');
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe('useCompleteOnboarding', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockComplete.mockResolvedValue({ completed: true, ttftc_seconds: 45 });
  });

  it('calls complete service', async () => {
    const { result } = renderHook(() => useCompleteOnboarding(), {
      wrapper: createWrapper(),
    });
    result.current.mutate();
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.completed).toBe(true);
  });

  it('handles error gracefully', async () => {
    mockComplete.mockRejectedValue(new Error('Server error'));
    const { result } = renderHook(() => useCompleteOnboarding(), {
      wrapper: createWrapper(),
    });
    result.current.mutate();
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
