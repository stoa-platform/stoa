/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * Tests for Plan hooks (CAB-1121 P5)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import { usePlans, usePlan } from './usePlans';

vi.mock('../services/plans', () => ({
  plansService: {
    list: vi.fn(),
    get: vi.fn(),
  },
}));

import { plansService } from '../services/plans';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('usePlans', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should fetch plans list with active status by default', async () => {
    vi.mocked(plansService.list).mockResolvedValueOnce({
      items: [{ id: 'plan-1', name: 'Basic', slug: 'basic' }],
      total: 1,
      page: 1,
      page_size: 50,
      total_pages: 1,
    } as any);

    const { result } = renderHook(() => usePlans('acme'), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.items).toHaveLength(1);
    expect(plansService.list).toHaveBeenCalledWith('acme', { status: 'active' });
  });

  it('should not fetch when tenantId is undefined', () => {
    const { result } = renderHook(() => usePlans(undefined), { wrapper: createWrapper() });

    expect(result.current.fetchStatus).toBe('idle');
  });
});

describe('usePlan', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should fetch a single plan', async () => {
    vi.mocked(plansService.get).mockResolvedValueOnce({
      id: 'plan-1',
      name: 'Premium',
      slug: 'premium',
    } as any);

    const { result } = renderHook(() => usePlan('acme', 'plan-1'), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.name).toBe('Premium');
  });

  it('should not fetch when tenantId is undefined', () => {
    const { result } = renderHook(() => usePlan(undefined, 'plan-1'), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe('idle');
  });

  it('should not fetch when planId is undefined', () => {
    const { result } = renderHook(() => usePlan('acme', undefined), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe('idle');
  });
});
