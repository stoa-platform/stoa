import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { useDeployEvents } from './useDeployEvents';
import type { Event } from '../types';

// Capture the onEvent callback passed to useEvents
let capturedOnEvent: ((event: Event) => void) | undefined;

vi.mock('./useEvents', () => ({
  useEvents: vi.fn((opts: { onEvent?: (event: Event) => void }) => {
    capturedOnEvent = opts.onEvent;
  }),
}));

vi.mock('../services/api', () => ({
  apiService: {
    getDeploymentLogs: vi.fn(),
  },
}));

import { useEvents } from './useEvents';
import { apiService } from '../services/api';

const mockGetDeploymentLogs = vi.mocked(apiService.getDeploymentLogs);
const mockUseEvents = vi.mocked(useEvents);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

function makeEvent(type: string, deploymentId: string, extra: Record<string, unknown> = {}): Event {
  return {
    id: `evt-${Date.now()}`,
    type,
    tenant_id: 'tenant-1',
    timestamp: new Date().toISOString(),
    payload: { deployment_id: deploymentId, ...extra },
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  capturedOnEvent = undefined;
});

describe('useDeployEvents', () => {
  it('initializes with empty deploy states', () => {
    const { result } = renderHook(() => useDeployEvents({ tenantId: 'tenant-1' }), {
      wrapper: createWrapper(),
    });

    expect(result.current.deployStates).toEqual({});
  });

  it('passes correct options to useEvents', () => {
    renderHook(() => useDeployEvents({ tenantId: 'tenant-1', enabled: false }), {
      wrapper: createWrapper(),
    });

    expect(mockUseEvents).toHaveBeenCalledWith(
      expect.objectContaining({
        tenantId: 'tenant-1',
        eventTypes: ['deploy-started', 'deploy-progress', 'deploy-success', 'deploy-failed'],
        enabled: false,
      })
    );
  });

  it('handles deploy-started event', () => {
    const { result } = renderHook(() => useDeployEvents({ tenantId: 'tenant-1' }), {
      wrapper: createWrapper(),
    });

    act(() => {
      capturedOnEvent?.(makeEvent('deploy-started', 'deploy-1'));
    });

    expect(result.current.deployStates['deploy-1']).toEqual({
      logs: [],
      currentStep: 'init',
      status: 'in_progress',
    });
  });

  it('handles deploy-progress event and accumulates logs', () => {
    const { result } = renderHook(() => useDeployEvents({ tenantId: 'tenant-1' }), {
      wrapper: createWrapper(),
    });

    act(() => {
      capturedOnEvent?.(makeEvent('deploy-started', 'deploy-1'));
    });

    act(() => {
      capturedOnEvent?.(
        makeEvent('deploy-progress', 'deploy-1', {
          seq: 1,
          level: 'info',
          step: 'build',
          message: 'Building image...',
        })
      );
    });

    const state = result.current.deployStates['deploy-1'];
    expect(state.logs).toHaveLength(1);
    expect(state.logs[0].message).toBe('Building image...');
    expect(state.logs[0].step).toBe('build');
    expect(state.currentStep).toBe('build');
    expect(state.status).toBe('in_progress');
  });

  it('handles deploy-success event and calls onStatusChange', () => {
    const onStatusChange = vi.fn();
    const { result } = renderHook(() => useDeployEvents({ tenantId: 'tenant-1', onStatusChange }), {
      wrapper: createWrapper(),
    });

    act(() => {
      capturedOnEvent?.(makeEvent('deploy-started', 'deploy-1'));
    });

    act(() => {
      capturedOnEvent?.(makeEvent('deploy-success', 'deploy-1'));
    });

    expect(result.current.deployStates['deploy-1'].status).toBe('success');
    expect(result.current.deployStates['deploy-1'].currentStep).toBe('complete');
    expect(onStatusChange).toHaveBeenCalledWith('deploy-1', 'success');
  });

  it('handles deploy-failed event and calls onStatusChange', () => {
    const onStatusChange = vi.fn();
    const { result } = renderHook(() => useDeployEvents({ tenantId: 'tenant-1', onStatusChange }), {
      wrapper: createWrapper(),
    });

    act(() => {
      capturedOnEvent?.(makeEvent('deploy-started', 'deploy-1'));
    });

    act(() => {
      capturedOnEvent?.(makeEvent('deploy-failed', 'deploy-1'));
    });

    expect(result.current.deployStates['deploy-1'].status).toBe('failed');
    expect(result.current.deployStates['deploy-1'].currentStep).toBeNull();
    expect(onStatusChange).toHaveBeenCalledWith('deploy-1', 'failed');
  });

  it('ignores events without deployment_id', () => {
    const { result } = renderHook(() => useDeployEvents({ tenantId: 'tenant-1' }), {
      wrapper: createWrapper(),
    });

    act(() => {
      capturedOnEvent?.({
        id: 'evt-1',
        type: 'deploy-started',
        tenant_id: 'tenant-1',
        timestamp: new Date().toISOString(),
        payload: {},
      });
    });

    expect(result.current.deployStates).toEqual({});
  });

  it('tracks multiple deployments independently', () => {
    const { result } = renderHook(() => useDeployEvents({ tenantId: 'tenant-1' }), {
      wrapper: createWrapper(),
    });

    act(() => {
      capturedOnEvent?.(makeEvent('deploy-started', 'deploy-1'));
      capturedOnEvent?.(makeEvent('deploy-started', 'deploy-2'));
    });

    act(() => {
      capturedOnEvent?.(makeEvent('deploy-success', 'deploy-1'));
    });

    expect(result.current.deployStates['deploy-1'].status).toBe('success');
    expect(result.current.deployStates['deploy-2'].status).toBe('in_progress');
  });

  it('loadHistoricalLogs fetches and updates state', async () => {
    const historicalLogs = {
      items: [
        {
          id: 'log-1',
          deployment_id: 'deploy-1',
          tenant_id: 'tenant-1',
          seq: 0,
          level: 'info' as const,
          step: 'init',
          message: 'Starting deployment',
          created_at: '2026-02-20T10:00:00Z',
        },
        {
          id: 'log-2',
          deployment_id: 'deploy-1',
          tenant_id: 'tenant-1',
          seq: 1,
          level: 'info' as const,
          step: 'build',
          message: 'Building image',
          created_at: '2026-02-20T10:01:00Z',
        },
      ],
      total: 2,
    };
    mockGetDeploymentLogs.mockResolvedValue(historicalLogs as any);

    const { result } = renderHook(() => useDeployEvents({ tenantId: 'tenant-1' }), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.loadHistoricalLogs('deploy-1');
    });

    expect(mockGetDeploymentLogs).toHaveBeenCalledWith('tenant-1', 'deploy-1');
    expect(result.current.deployStates['deploy-1'].logs).toHaveLength(2);
    expect(result.current.deployStates['deploy-1'].currentStep).toBe('build');
  });

  it('ignores unknown event types', () => {
    const { result } = renderHook(() => useDeployEvents({ tenantId: 'tenant-1' }), {
      wrapper: createWrapper(),
    });

    act(() => {
      capturedOnEvent?.(makeEvent('deploy-unknown', 'deploy-1'));
    });

    expect(result.current.deployStates['deploy-1']).toBeUndefined();
  });

  it('defaults log seq when not provided', () => {
    const { result } = renderHook(() => useDeployEvents({ tenantId: 'tenant-1' }), {
      wrapper: createWrapper(),
    });

    act(() => {
      capturedOnEvent?.(makeEvent('deploy-started', 'deploy-1'));
    });

    act(() => {
      capturedOnEvent?.(
        makeEvent('deploy-progress', 'deploy-1', {
          message: 'step without seq',
        })
      );
    });

    const state = result.current.deployStates['deploy-1'];
    expect(state.logs).toHaveLength(1);
    expect(state.logs[0].seq).toBe(0); // defaults to existing logs length (0)
  });
});
