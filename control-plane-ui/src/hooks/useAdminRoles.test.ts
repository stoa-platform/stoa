import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { useAdminRoles } from './useAdminRoles';

vi.mock('../services/api', () => ({
  apiService: {
    getAdminRoles: vi.fn(),
  },
}));

import { apiService } from '../services/api';

const mockGetAdminRoles = vi.mocked(apiService.getAdminRoles);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

const mockResponse = {
  roles: [
    { id: 'role-1', name: 'admin', permissions: ['read', 'write'] },
    { id: 'role-2', name: 'viewer', permissions: ['read'] },
  ],
  total: 2,
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useAdminRoles', () => {
  it('fetches admin roles', async () => {
    mockGetAdminRoles.mockResolvedValue(mockResponse as any);

    const { result } = renderHook(() => useAdminRoles(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetAdminRoles).toHaveBeenCalled();
    expect(result.current.data).toEqual(mockResponse);
  });

  it('respects enabled option', () => {
    renderHook(() => useAdminRoles({ enabled: false }), {
      wrapper: createWrapper(),
    });
    expect(mockGetAdminRoles).not.toHaveBeenCalled();
  });

  it('defaults enabled to true', async () => {
    mockGetAdminRoles.mockResolvedValue(mockResponse as any);

    const { result } = renderHook(() => useAdminRoles(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetAdminRoles).toHaveBeenCalled();
  });

  it('handles API error', async () => {
    mockGetAdminRoles.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useAdminRoles(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(Error);
  });
});
