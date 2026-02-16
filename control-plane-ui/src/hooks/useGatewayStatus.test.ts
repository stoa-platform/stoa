import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { useGatewayStatus, useGatewayHealth, useGatewayPlatformInfo } from './useGatewayStatus';

vi.mock('../services/gatewayApi', () => ({
  getGatewayStatus: vi.fn(),
  getGatewayHealth: vi.fn(),
}));

vi.mock('../services/api', () => ({
  apiService: {
    getPlatformStatus: vi.fn(),
  },
}));

import { getGatewayStatus, getGatewayHealth } from '../services/gatewayApi';
import { apiService } from '../services/api';

const mockGetGatewayStatus = vi.mocked(getGatewayStatus);
const mockGetGatewayHealth = vi.mocked(getGatewayHealth);
const mockGetPlatformStatus = vi.mocked(apiService.getPlatformStatus);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useGatewayStatus', () => {
  it('fetches gateway status', async () => {
    const status = {
      health: { status: 'healthy', proxy_mode: false },
      apis: [],
      applications: [],
      fetchedAt: '2026-02-16T12:00:00',
    };
    mockGetGatewayStatus.mockResolvedValue(status as any);

    const { result } = renderHook(() => useGatewayStatus(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(status);
  });
});

describe('useGatewayHealth', () => {
  it('fetches gateway health', async () => {
    const health = { status: 'healthy' as const, proxy_mode: false };
    mockGetGatewayHealth.mockResolvedValue(health);

    const { result } = renderHook(() => useGatewayHealth(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(health);
  });
});

describe('useGatewayPlatformInfo', () => {
  it('returns defaults when no data', () => {
    mockGetPlatformStatus.mockReturnValue(new Promise(() => {}) as any);

    const { result } = renderHook(() => useGatewayPlatformInfo(), {
      wrapper: createWrapper(),
    });

    expect(result.current.gatewayComponent).toBeNull();
    expect(result.current.healthSummary).toBeNull();
    expect(result.current.externalLinks).toBeNull();
    expect(result.current.events).toEqual([]);
  });

  it('computes gateway platform info from status', async () => {
    const status = {
      gitops: {
        status: 'Healthy',
        components: [
          { name: 'stoa-gateway', sync_status: 'Synced', health_status: 'Healthy' },
          { name: 'control-plane-api', sync_status: 'Synced', health_status: 'Healthy' },
          { name: 'control-plane-ui', sync_status: 'OutOfSync', health_status: 'Degraded' },
        ],
      },
      events: [{ type: 'sync' }, { type: 'deploy' }, { type: 'error' }],
      external_links: [{ name: 'ArgoCD', url: 'https://argocd.test' }],
    };
    mockGetPlatformStatus.mockResolvedValue(status as any);

    const { result } = renderHook(() => useGatewayPlatformInfo(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.gatewayComponent).toEqual(
      expect.objectContaining({ name: 'stoa-gateway' })
    );
    expect(result.current.healthSummary).toEqual({
      total: 3,
      healthy: 2,
      degraded: 1,
      progressing: 0,
      unknown: 0,
    });
    expect(result.current.externalLinks).toHaveLength(1);
    expect(result.current.events).toHaveLength(3);
  });

  it('finds webmethods as gateway component', async () => {
    const status = {
      gitops: {
        status: 'Healthy',
        components: [{ name: 'webmethods-gw', sync_status: 'Synced', health_status: 'Healthy' }],
      },
      events: [],
      external_links: [],
    };
    mockGetPlatformStatus.mockResolvedValue(status as any);

    const { result } = renderHook(() => useGatewayPlatformInfo(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.gatewayComponent?.name).toBe('webmethods-gw');
  });

  it('returns null gatewayComponent when no match', async () => {
    const status = {
      gitops: {
        status: 'Healthy',
        components: [
          { name: 'control-plane-api', sync_status: 'Synced', health_status: 'Healthy' },
        ],
      },
      events: [],
      external_links: [],
    };
    mockGetPlatformStatus.mockResolvedValue(status as any);

    const { result } = renderHook(() => useGatewayPlatformInfo(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.gatewayComponent).toBeNull();
  });

  it('slices events to max 5', async () => {
    const status = {
      gitops: { status: 'Healthy', components: [] },
      events: Array.from({ length: 10 }, (_, i) => ({ type: `event-${i}` })),
      external_links: [],
    };
    mockGetPlatformStatus.mockResolvedValue(status as any);

    const { result } = renderHook(() => useGatewayPlatformInfo(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.events).toHaveLength(5);
  });
});
