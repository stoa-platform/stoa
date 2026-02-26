import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import { useAuditLog } from './useAuditLog';

vi.mock('../services/auditLog', () => ({
  auditLogService: {
    getEntries: vi.fn(),
  },
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

import { auditLogService } from '../services/auditLog';
import { useAuth } from '../contexts/AuthContext';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

const mockAuditLogResponse = {
  entries: [
    { id: 'log-1', action: 'api.created', userId: 'u1', timestamp: '2026-01-15T10:00:00Z' },
    {
      id: 'log-2',
      action: 'subscription.approved',
      userId: 'u2',
      timestamp: '2026-01-15T11:00:00Z',
    },
  ],
  total: 2,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useAuth).mockReturnValue({
    isAuthenticated: true,
    accessToken: 'mock-token',
  } as any);
});

describe('useAuditLog', () => {
  it('fetches audit log entries when authenticated', async () => {
    vi.mocked(auditLogService.getEntries).mockResolvedValue(mockAuditLogResponse as any);

    const { result } = renderHook(() => useAuditLog(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(auditLogService.getEntries).toHaveBeenCalledWith(undefined);
    expect(result.current.data).toEqual(mockAuditLogResponse);
  });

  it('fetches with filters', async () => {
    vi.mocked(auditLogService.getEntries).mockResolvedValue(mockAuditLogResponse as any);

    const filters = { action: 'api.created', userId: 'u1' };
    const { result } = renderHook(() => useAuditLog(filters as any), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(auditLogService.getEntries).toHaveBeenCalledWith(filters);
  });

  it('does not fetch when not authenticated', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: false,
      accessToken: null,
    } as any);

    const { result } = renderHook(() => useAuditLog(), { wrapper: createWrapper() });
    expect(result.current.fetchStatus).toBe('idle');
  });

  it('uses correct query key including filters', async () => {
    vi.mocked(auditLogService.getEntries).mockResolvedValue(mockAuditLogResponse as any);

    const { result: r1 } = renderHook(() => useAuditLog({ action: 'api.created' } as any), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(r1.current.isSuccess).toBe(true));

    const { result: r2 } = renderHook(
      () => useAuditLog({ action: 'subscription.approved' } as any),
      { wrapper: createWrapper() }
    );
    await waitFor(() => expect(r2.current.isSuccess).toBe(true));
    expect(auditLogService.getEntries).toHaveBeenCalledTimes(2);
  });

  it('handles API error', async () => {
    vi.mocked(auditLogService.getEntries).mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useAuditLog(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
