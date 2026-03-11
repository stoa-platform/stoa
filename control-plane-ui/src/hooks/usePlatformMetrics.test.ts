import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement } from 'react';
import {
  useGatewayHealthSummary,
  useGatewayModeStats,
  useGatewayInstances,
} from './usePlatformMetrics';

vi.mock('../services/api', () => ({
  apiService: {
    getGatewayHealthSummary: vi.fn().mockResolvedValue({
      online: 3,
      offline: 1,
      degraded: 0,
      maintenance: 0,
      total: 4,
    }),
    getGatewayModeStats: vi.fn().mockResolvedValue({
      modes: [{ mode: 'edge-mcp', total: 2, online: 2, offline: 0, degraded: 0 }],
      total_gateways: 2,
    }),
    getGatewayInstances: vi.fn().mockResolvedValue({
      items: [{ id: 'gw-1', name: 'prod-edge', status: 'online' }],
      total: 1,
    }),
  },
}));

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: qc }, children);
}

describe('usePlatformMetrics', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('useGatewayHealthSummary returns health data', async () => {
    const { result } = renderHook(() => useGatewayHealthSummary(), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual({
      online: 3,
      offline: 1,
      degraded: 0,
      maintenance: 0,
      total: 4,
    });
  });

  it('useGatewayModeStats returns mode statistics', async () => {
    const { result } = renderHook(() => useGatewayModeStats(), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.total_gateways).toBe(2);
    expect(result.current.data?.modes).toHaveLength(1);
  });

  it('useGatewayInstances returns instance list', async () => {
    const { result } = renderHook(() => useGatewayInstances(), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.total).toBe(1);
    expect(result.current.data?.items[0].name).toBe('prod-edge');
  });
});
