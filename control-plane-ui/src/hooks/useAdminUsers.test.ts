import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { useAdminUsers } from './useAdminUsers';

vi.mock('../services/api', () => ({
  apiService: {
    getAdminUsers: vi.fn(),
  },
}));

import { apiService } from '../services/api';

const mockGetAdminUsers = vi.mocked(apiService.getAdminUsers);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

const mockResponse = {
  users: [
    { id: 'user-1', email: 'admin@example.com', role: 'admin', status: 'active' },
    { id: 'user-2', email: 'viewer@example.com', role: 'viewer', status: 'active' },
  ],
  total: 2,
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useAdminUsers', () => {
  it('fetches admin users with filters', async () => {
    mockGetAdminUsers.mockResolvedValue(mockResponse as any);

    const filters = { role: 'admin', status: 'active', page: 1, limit: 25 };
    const { result } = renderHook(() => useAdminUsers(filters), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetAdminUsers).toHaveBeenCalledWith({
      role: 'admin',
      status: 'active',
      search: undefined,
      page: 1,
      limit: 25,
    });
    expect(result.current.data).toEqual(mockResponse);
  });

  it('fetches without filters', async () => {
    mockGetAdminUsers.mockResolvedValue(mockResponse as any);

    const { result } = renderHook(() => useAdminUsers({}), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetAdminUsers).toHaveBeenCalledWith({
      role: undefined,
      status: undefined,
      search: undefined,
      page: undefined,
      limit: undefined,
    });
  });

  it('respects enabled option', () => {
    renderHook(() => useAdminUsers({}, { enabled: false }), {
      wrapper: createWrapper(),
    });
    expect(mockGetAdminUsers).not.toHaveBeenCalled();
  });

  it('uses correct query key including filters', async () => {
    mockGetAdminUsers.mockResolvedValue(mockResponse as any);

    const filters1 = { role: 'admin', page: 1 };
    const { result: result1 } = renderHook(() => useAdminUsers(filters1), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result1.current.isSuccess).toBe(true));

    const filters2 = { role: 'viewer', page: 2 };
    const { result: result2 } = renderHook(() => useAdminUsers(filters2), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result2.current.isSuccess).toBe(true));
    expect(mockGetAdminUsers).toHaveBeenCalledTimes(2);
  });

  it('includes search filter', async () => {
    mockGetAdminUsers.mockResolvedValue(mockResponse as any);

    const filters = { search: 'admin@example.com' };
    const { result } = renderHook(() => useAdminUsers(filters), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetAdminUsers).toHaveBeenCalledWith(
      expect.objectContaining({ search: 'admin@example.com' })
    );
  });

  it('handles API error', async () => {
    mockGetAdminUsers.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useAdminUsers({}), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(Error);
  });
});
