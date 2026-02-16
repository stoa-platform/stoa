import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import {
  usePlatformStatus,
  usePlatformComponents,
  useComponentStatus,
  useComponentDiff,
  usePlatformEvents,
  useSyncComponent,
  usePlatformHealthSummary,
} from './usePlatformStatus';

vi.mock('../services/api', () => ({
  apiService: {
    getPlatformStatus: vi.fn(),
    getPlatformComponents: vi.fn(),
    getComponentStatus: vi.fn(),
    getComponentDiff: vi.fn(),
    getPlatformEvents: vi.fn(),
    syncPlatformComponent: vi.fn(),
  },
}));

import { apiService } from '../services/api';

const mockGetPlatformStatus = vi.mocked(apiService.getPlatformStatus);
const mockGetPlatformComponents = vi.mocked(apiService.getPlatformComponents);
const mockGetComponentStatus = vi.mocked(apiService.getComponentStatus);
const mockGetComponentDiff = vi.mocked(apiService.getComponentDiff);
const mockGetPlatformEvents = vi.mocked(apiService.getPlatformEvents);
const mockSyncPlatformComponent = vi.mocked(apiService.syncPlatformComponent);

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

describe('usePlatformStatus', () => {
  it('fetches platform status', async () => {
    const status = {
      gitops: { status: 'Healthy', components: [] },
      events: [],
      external_links: [],
    };
    mockGetPlatformStatus.mockResolvedValue(status as any);

    const { result } = renderHook(() => usePlatformStatus(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(status);
    expect(mockGetPlatformStatus).toHaveBeenCalled();
  });

  it('respects enabled option', () => {
    renderHook(() => usePlatformStatus({ enabled: false }), { wrapper: createWrapper() });
    expect(mockGetPlatformStatus).not.toHaveBeenCalled();
  });
});

describe('usePlatformComponents', () => {
  it('fetches components list', async () => {
    const components = [{ name: 'stoa-gateway', sync_status: 'Synced', health_status: 'Healthy' }];
    mockGetPlatformComponents.mockResolvedValue(components as any);

    const { result } = renderHook(() => usePlatformComponents(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(components);
  });

  it('respects enabled option', () => {
    renderHook(() => usePlatformComponents({ enabled: false }), { wrapper: createWrapper() });
    expect(mockGetPlatformComponents).not.toHaveBeenCalled();
  });
});

describe('useComponentStatus', () => {
  it('fetches single component status', async () => {
    const component = { name: 'stoa-gateway', sync_status: 'Synced' };
    mockGetComponentStatus.mockResolvedValue(component as any);

    const { result } = renderHook(() => useComponentStatus('stoa-gateway'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetComponentStatus).toHaveBeenCalledWith('stoa-gateway');
  });

  it('does not fetch when name is undefined', () => {
    renderHook(() => useComponentStatus(undefined), { wrapper: createWrapper() });
    expect(mockGetComponentStatus).not.toHaveBeenCalled();
  });
});

describe('useComponentDiff', () => {
  it('fetches component diff', async () => {
    const diff = { diff: 'some-diff' };
    mockGetComponentDiff.mockResolvedValue(diff as any);

    const { result } = renderHook(() => useComponentDiff('stoa-gateway'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetComponentDiff).toHaveBeenCalledWith('stoa-gateway');
  });

  it('does not fetch when name is undefined', () => {
    renderHook(() => useComponentDiff(undefined), { wrapper: createWrapper() });
    expect(mockGetComponentDiff).not.toHaveBeenCalled();
  });
});

describe('usePlatformEvents', () => {
  it('fetches events with optional params', async () => {
    const events = [{ type: 'sync', component: 'gateway' }];
    mockGetPlatformEvents.mockResolvedValue(events as any);

    const { result } = renderHook(() => usePlatformEvents('gateway', 10), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetPlatformEvents).toHaveBeenCalledWith('gateway', 10);
  });

  it('fetches events without params', async () => {
    mockGetPlatformEvents.mockResolvedValue([] as any);

    const { result } = renderHook(() => usePlatformEvents(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetPlatformEvents).toHaveBeenCalledWith(undefined, undefined);
  });
});

describe('useSyncComponent', () => {
  it('calls sync and invalidates queries on success', async () => {
    mockSyncPlatformComponent.mockResolvedValue({ message: 'ok', operation: 'sync' });

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    const wrapper = ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: queryClient }, children);

    const { result } = renderHook(() => useSyncComponent(), { wrapper });

    result.current.mutate('stoa-gateway');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockSyncPlatformComponent).toHaveBeenCalledWith('stoa-gateway');
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['platform-status'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['platform-components'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['platform-events'] });
  });
});

describe('usePlatformHealthSummary', () => {
  it('returns defaults when no data', () => {
    mockGetPlatformStatus.mockReturnValue(new Promise(() => {}) as any);

    const { result } = renderHook(() => usePlatformHealthSummary(), {
      wrapper: createWrapper(),
    });

    expect(result.current.overallStatus).toBe('unknown');
    expect(result.current.syncedCount).toBe(0);
    expect(result.current.outOfSyncCount).toBe(0);
    expect(result.current.totalComponents).toBe(0);
  });

  it('computes derived data from platform status', async () => {
    const status = {
      gitops: {
        status: 'Healthy',
        components: [
          { name: 'gw', sync_status: 'Synced', health_status: 'Healthy' },
          { name: 'api', sync_status: 'OutOfSync', health_status: 'Degraded' },
          { name: 'ui', sync_status: 'Synced', health_status: 'Healthy' },
        ],
      },
      events: [{ type: 'sync' }],
      external_links: [{ name: 'ArgoCD', url: 'https://argocd.test' }],
      timestamp: '2026-02-16T12:00:00',
    };
    mockGetPlatformStatus.mockResolvedValue(status as any);

    const { result } = renderHook(() => usePlatformHealthSummary(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.overallStatus).toBe('Healthy');
    expect(result.current.syncedCount).toBe(2);
    expect(result.current.outOfSyncCount).toBe(1);
    expect(result.current.healthyCount).toBe(2);
    expect(result.current.degradedCount).toBe(1);
    expect(result.current.totalComponents).toBe(3);
    expect(result.current.outOfSyncComponents).toHaveLength(1);
    expect(result.current.externalLinks).toHaveLength(1);
    expect(result.current.timestamp).toBe('2026-02-16T12:00:00');
    expect(result.current.events).toHaveLength(1);
  });
});
