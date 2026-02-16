import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import {
  useProspects,
  useProspectsMetrics,
  useProspectDetail,
  useExportProspectsCSV,
  useRefreshProspects,
  useProspectsSummary,
} from './useProspects';

vi.mock('../services/api', () => ({
  apiService: {
    getProspects: vi.fn(),
    getProspectsMetrics: vi.fn(),
    getProspect: vi.fn(),
    exportProspectsCSV: vi.fn(),
  },
}));

import { apiService } from '../services/api';

const mockGetProspects = vi.mocked(apiService.getProspects);
const mockGetProspectsMetrics = vi.mocked(apiService.getProspectsMetrics);
const mockGetProspect = vi.mocked(apiService.getProspect);
const mockExportProspectsCSV = vi.mocked(apiService.exportProspectsCSV);

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

describe('useProspects', () => {
  it('fetches prospects with filters', async () => {
    const response = { items: [{ id: 'p1' }], total: 1 };
    mockGetProspects.mockResolvedValue(response as any);

    const filters = { company: 'Acme', status: 'active', page: 1, limit: 20 };
    const { result } = renderHook(() => useProspects(filters), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetProspects).toHaveBeenCalledWith(
      expect.objectContaining({ company: 'Acme', status: 'active', page: 1, limit: 20 })
    );
  });

  it('respects enabled option', () => {
    renderHook(() => useProspects({}, { enabled: false }), { wrapper: createWrapper() });
    expect(mockGetProspects).not.toHaveBeenCalled();
  });
});

describe('useProspectsMetrics', () => {
  it('fetches metrics with optional date filters', async () => {
    const metrics = { total_invited: 100, total_active: 50 };
    mockGetProspectsMetrics.mockResolvedValue(metrics as any);

    const filters = { date_from: '2026-01-01', date_to: '2026-02-01' };
    const { result } = renderHook(() => useProspectsMetrics(filters), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetProspectsMetrics).toHaveBeenCalledWith(filters);
  });

  it('fetches without filters', async () => {
    mockGetProspectsMetrics.mockResolvedValue({} as any);

    const { result } = renderHook(() => useProspectsMetrics(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetProspectsMetrics).toHaveBeenCalledWith(undefined);
  });
});

describe('useProspectDetail', () => {
  it('fetches prospect by inviteId', async () => {
    const prospect = { id: 'p1', name: 'John' };
    mockGetProspect.mockResolvedValue(prospect as any);

    const { result } = renderHook(() => useProspectDetail('invite-1'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetProspect).toHaveBeenCalledWith('invite-1');
  });

  it('does not fetch when inviteId is null', () => {
    renderHook(() => useProspectDetail(null), { wrapper: createWrapper() });
    expect(mockGetProspect).not.toHaveBeenCalled();
  });
});

describe('useExportProspectsCSV', () => {
  it('calls export API with filters', async () => {
    const blob = new Blob(['csv-data'], { type: 'text/csv' });
    mockExportProspectsCSV.mockResolvedValue(blob as any);

    // Mock only URL methods (don't touch document.createElement — breaks React)
    const createObjectURL = vi.fn(() => 'blob:url');
    const revokeObjectURL = vi.fn();
    global.URL.createObjectURL = createObjectURL;
    global.URL.revokeObjectURL = revokeObjectURL;

    const { result } = renderHook(() => useExportProspectsCSV(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ company: 'Acme', status: 'active' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockExportProspectsCSV).toHaveBeenCalledWith(
      expect.objectContaining({ company: 'Acme', status: 'active' })
    );
    // Verify download was triggered via URL.createObjectURL
    expect(createObjectURL).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalled();
  });
});

describe('useRefreshProspects', () => {
  it('provides refresh functions that invalidate queries', () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    const wrapper = ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: queryClient }, children);

    const { result } = renderHook(() => useRefreshProspects(), { wrapper });

    result.current.refresh();
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['prospects'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['prospects-metrics'] });

    invalidateSpy.mockClear();
    result.current.refreshDetail('invite-1');
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['prospect', 'invite-1'] });
  });
});

describe('useProspectsSummary', () => {
  it('returns defaults when no metrics', () => {
    mockGetProspectsMetrics.mockReturnValue(new Promise(() => {}) as any);

    const { result } = renderHook(() => useProspectsSummary(), { wrapper: createWrapper() });

    expect(result.current.totalInvited).toBe(0);
    expect(result.current.totalActive).toBe(0);
    expect(result.current.avgTimeToTool).toBeNull();
    expect(result.current.avgNPS).toBeNull();
    expect(result.current.conversionRate).toBe(0);
    expect(result.current.npsScore).toBe(0);
  });

  it('computes derived summary from metrics', async () => {
    const metrics = {
      total_invited: 100,
      total_active: 60,
      avg_time_to_tool: 3.5,
      avg_nps: 8.2,
      by_status: { total_invites: 100, converted: 40 },
      nps: { nps_score: 72 },
      top_companies: [{ name: 'Acme', count: 10 }],
    };
    mockGetProspectsMetrics.mockResolvedValue(metrics as any);

    const { result } = renderHook(() => useProspectsSummary(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.totalInvited).toBe(100);
    expect(result.current.totalActive).toBe(60);
    expect(result.current.avgTimeToTool).toBe(3.5);
    expect(result.current.avgNPS).toBe(8.2);
    expect(result.current.conversionRate).toBe(40);
    expect(result.current.npsScore).toBe(72);
    expect(result.current.topCompanies).toHaveLength(1);
  });

  it('handles zero invites without division error', async () => {
    const metrics = {
      total_invited: 0,
      total_active: 0,
      avg_time_to_tool: null,
      avg_nps: null,
      by_status: { total_invites: 0, converted: 0 },
      nps: { nps_score: 0 },
      top_companies: [],
    };
    mockGetProspectsMetrics.mockResolvedValue(metrics as any);

    const { result } = renderHook(() => useProspectsSummary(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.conversionRate).toBe(0);
  });
});
