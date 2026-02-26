import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import { useMarketplace, useFeaturedItems } from './useMarketplace';

vi.mock('../services/marketplace', () => ({
  marketplaceService: {
    getItems: vi.fn(),
    getFeaturedItems: vi.fn(),
  },
}));

import { marketplaceService } from '../services/marketplace';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

const mockMarketplaceResponse = {
  items: [
    { id: 'item-1', name: 'Payments API', type: 'api' },
    { id: 'item-2', name: 'Analytics Tool', type: 'tool' },
  ],
  total: 2,
  stats: { apis: 1, tools: 1 },
};

const mockFeaturedItems = [{ id: 'item-1', name: 'Payments API', type: 'api', featured: true }];

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useMarketplace', () => {
  it('fetches marketplace items without filters', async () => {
    vi.mocked(marketplaceService.getItems).mockResolvedValue(mockMarketplaceResponse as any);

    const { result } = renderHook(() => useMarketplace(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(marketplaceService.getItems).toHaveBeenCalledWith(undefined);
    expect(result.current.data).toEqual(mockMarketplaceResponse);
  });

  it('fetches marketplace items with filters', async () => {
    vi.mocked(marketplaceService.getItems).mockResolvedValue(mockMarketplaceResponse as any);

    const filters = { type: 'api', search: 'pay' };
    const { result } = renderHook(() => useMarketplace(filters as any), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(marketplaceService.getItems).toHaveBeenCalledWith(filters);
  });

  it('uses correct query key including filters', async () => {
    vi.mocked(marketplaceService.getItems).mockResolvedValue(mockMarketplaceResponse as any);

    const { result: r1 } = renderHook(() => useMarketplace({ type: 'api' } as any), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(r1.current.isSuccess).toBe(true));

    const { result: r2 } = renderHook(() => useMarketplace({ type: 'tool' } as any), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(r2.current.isSuccess).toBe(true));
    expect(marketplaceService.getItems).toHaveBeenCalledTimes(2);
  });

  it('handles API error', async () => {
    vi.mocked(marketplaceService.getItems).mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useMarketplace(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(Error);
  });
});

describe('useFeaturedItems', () => {
  it('fetches featured items', async () => {
    vi.mocked(marketplaceService.getFeaturedItems).mockResolvedValue(mockFeaturedItems as any);

    const { result } = renderHook(() => useFeaturedItems(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(mockFeaturedItems);
  });

  it('handles API error', async () => {
    vi.mocked(marketplaceService.getFeaturedItems).mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useFeaturedItems(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
