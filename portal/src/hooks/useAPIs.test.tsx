/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * Tests for API catalog hooks
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import { useAPIs, useAPI, useAPICategories, useUniverses, useAPITags } from './useAPIs';

vi.mock('../services/apiCatalog', () => ({
  apiCatalogService: {
    listAPIs: vi.fn(),
    getAPI: vi.fn(),
    getCategories: vi.fn(),
    getUniverses: vi.fn(),
    getTags: vi.fn(),
  },
}));

import { apiCatalogService } from '../services/apiCatalog';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('useAPIs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should fetch APIs list', async () => {
    vi.mocked(apiCatalogService.listAPIs).mockResolvedValueOnce({
      items: [{ id: 'api-1', name: 'Payments' }],
      total: 1,
      page: 1,
      pageSize: 20,
      totalPages: 1,
    } as any);

    const { result } = renderHook(() => useAPIs(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.items).toHaveLength(1);
  });
});

describe('useAPI', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should fetch a single API', async () => {
    vi.mocked(apiCatalogService.getAPI).mockResolvedValueOnce({
      id: 'api-1',
      name: 'Payments',
    } as any);

    const { result } = renderHook(() => useAPI('api-1'), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.id).toBe('api-1');
  });

  it('should not fetch when id is undefined', () => {
    const { result } = renderHook(() => useAPI(undefined), { wrapper: createWrapper() });

    expect(result.current.fetchStatus).toBe('idle');
  });
});

describe('useAPICategories', () => {
  it('should fetch categories', async () => {
    vi.mocked(apiCatalogService.getCategories).mockResolvedValueOnce(['finance', 'crm']);

    const { result } = renderHook(() => useAPICategories(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual(['finance', 'crm']);
  });
});

describe('useUniverses', () => {
  it('should fetch universes', async () => {
    vi.mocked(apiCatalogService.getUniverses).mockResolvedValueOnce([
      { id: 'u1', label: 'Finance' },
    ]);

    const { result } = renderHook(() => useUniverses(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toHaveLength(1);
  });
});

describe('useAPITags', () => {
  it('should fetch tags', async () => {
    vi.mocked(apiCatalogService.getTags).mockResolvedValueOnce(['payments', 'crm']);

    const { result } = renderHook(() => useAPITags(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual(['payments', 'crm']);
  });
});
