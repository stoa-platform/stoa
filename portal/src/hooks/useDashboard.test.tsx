import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import {
  useDashboardStats,
  useDashboardActivity,
  useFeaturedAPIs,
  useFeaturedAITools,
} from './useDashboard';

vi.mock('../services/dashboard', () => ({
  dashboardService: {
    getStats: vi.fn(),
    getRecentActivity: vi.fn(),
  },
}));

vi.mock('../services/api', () => ({
  apiClient: {
    get: vi.fn(),
  },
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

import { dashboardService } from '../services/dashboard';
import { apiClient } from '../services/api';
import { useAuth } from '../contexts/AuthContext';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('useDashboardStats', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      accessToken: 'mock-token',
    } as any);
  });

  it('should fetch dashboard stats when authenticated', async () => {
    vi.mocked(dashboardService.getStats).mockResolvedValueOnce({
      tools_available: 10,
      active_subscriptions: 5,
      api_calls_this_week: 1234,
    });

    const { result } = renderHook(() => useDashboardStats(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.tools_available).toBe(10);
  });

  it('should not fetch when not authenticated', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: false,
      accessToken: null,
    } as any);

    const { result } = renderHook(() => useDashboardStats(), { wrapper: createWrapper() });
    expect(result.current.fetchStatus).toBe('idle');
  });
});

describe('useDashboardActivity', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      accessToken: 'mock-token',
    } as any);
  });

  it('should fetch recent activity', async () => {
    vi.mocked(dashboardService.getRecentActivity).mockResolvedValueOnce([
      { id: 'a1', type: 'api.call', title: 'Call', timestamp: '2026-02-10' },
    ] as any);

    const { result } = renderHook(() => useDashboardActivity(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
  });

  it('should not fetch when not authenticated', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: false,
      accessToken: null,
    } as any);

    const { result } = renderHook(() => useDashboardActivity(), { wrapper: createWrapper() });
    expect(result.current.fetchStatus).toBe('idle');
  });
});

describe('useFeaturedAPIs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      accessToken: 'mock-token',
    } as any);
  });

  it('should fetch featured APIs', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { apis: [{ id: 'api-1', name: 'Payments' }] },
    } as any);

    const { result } = renderHook(() => useFeaturedAPIs(4), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
    expect(apiClient.get).toHaveBeenCalledWith('/v1/portal/apis', { params: { limit: 4 } });
  });

  it('should handle empty response', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { apis: undefined },
    } as any);

    const { result } = renderHook(() => useFeaturedAPIs(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([]);
  });
});

describe('useFeaturedAITools', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      accessToken: 'mock-token',
    } as any);
  });

  it('should fetch featured AI tools', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { servers: [{ id: 'srv-1', name: 'stoa-platform' }] },
    } as any);

    const { result } = renderHook(() => useFeaturedAITools(4), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
    expect(apiClient.get).toHaveBeenCalledWith('/v1/portal/mcp-servers', { params: { limit: 4 } });
  });

  it('should handle empty response', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { servers: undefined },
    } as any);

    const { result } = renderHook(() => useFeaturedAITools(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([]);
  });
});
