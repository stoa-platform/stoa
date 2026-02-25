/**
 * Tests for Application hooks
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import {
  useApplications,
  useApplication,
  useCreateApplication,
  useUpdateApplication,
  useDeleteApplication,
  useRegenerateSecret,
} from './useApplications';

// Mock the service
vi.mock('../services/applications', () => ({
  applicationsService: {
    listApplications: vi.fn(),
    getApplication: vi.fn(),
    createApplication: vi.fn(),
    updateApplication: vi.fn(),
    deleteApplication: vi.fn(),
    regenerateSecret: vi.fn(),
  },
}));

import { applicationsService } from '../services/applications';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('useApplications', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should fetch applications list', async () => {
    vi.mocked(applicationsService.listApplications).mockResolvedValueOnce({
      items: [{ id: 'app-1', name: 'My App' }],
      total: 1,
      page: 1,
      pageSize: 20,
      totalPages: 1,
    } as any);

    const { result } = renderHook(() => useApplications(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.items).toHaveLength(1);
    expect(applicationsService.listApplications).toHaveBeenCalledWith(undefined);
  });

  it('should pass params to listApplications', async () => {
    vi.mocked(applicationsService.listApplications).mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      pageSize: 20,
      totalPages: 0,
    } as any);

    const params = { page: 2, status: 'active' as const };
    const { result } = renderHook(() => useApplications(params), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(applicationsService.listApplications).toHaveBeenCalledWith(params);
  });
});

describe('useApplication', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should fetch a single application', async () => {
    vi.mocked(applicationsService.getApplication).mockResolvedValueOnce({
      id: 'app-1',
      name: 'My App',
    } as any);

    const { result } = renderHook(() => useApplication('app-1'), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.id).toBe('app-1');
  });

  it('should not fetch when id is undefined', () => {
    const { result } = renderHook(() => useApplication(undefined), { wrapper: createWrapper() });

    expect(result.current.fetchStatus).toBe('idle');
  });
});

describe('useCreateApplication', () => {
  it('should create an application', async () => {
    vi.mocked(applicationsService.createApplication).mockResolvedValueOnce({
      id: 'app-2',
      name: 'New App',
    } as any);

    const { result } = renderHook(() => useCreateApplication(), { wrapper: createWrapper() });

    result.current.mutate({ name: 'New App', description: 'desc' } as any);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.id).toBe('app-2');
  });
});

describe('useUpdateApplication', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should update an application', async () => {
    vi.mocked(applicationsService.updateApplication).mockResolvedValueOnce({
      id: 'app-1',
      name: 'Updated App',
    } as any);

    const { result } = renderHook(() => useUpdateApplication('app-1'), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ name: 'Updated App' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(applicationsService.updateApplication).toHaveBeenCalledWith('app-1', {
      name: 'Updated App',
    });
    expect(result.current.data?.name).toBe('Updated App');
  });
});

describe('useDeleteApplication', () => {
  it('should delete an application', async () => {
    vi.mocked(applicationsService.deleteApplication).mockResolvedValueOnce(undefined);

    const { result } = renderHook(() => useDeleteApplication(), { wrapper: createWrapper() });

    result.current.mutate('app-1');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

describe('useRegenerateSecret', () => {
  it('should regenerate client secret', async () => {
    vi.mocked(applicationsService.regenerateSecret).mockResolvedValueOnce({
      clientSecret: 'new-secret',
    });

    const { result } = renderHook(() => useRegenerateSecret('app-1'), {
      wrapper: createWrapper(),
    });

    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.clientSecret).toBe('new-secret');
  });
});
