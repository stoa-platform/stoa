import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import { useFavorites, useAddFavorite, useRemoveFavorite } from './useFavorites';

vi.mock('../services/favorites', () => ({
  favoritesService: {
    getFavorites: vi.fn(),
    addFavorite: vi.fn(),
    removeFavorite: vi.fn(),
  },
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

import { favoritesService } from '../services/favorites';
import { useAuth } from '../contexts/AuthContext';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

const mockFavorites = {
  items: [
    { id: 'fav-1', itemType: 'api', itemId: 'api-1', name: 'Payments API' },
    { id: 'fav-2', itemType: 'tool', itemId: 'tool-1', name: 'Analytics Tool' },
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

describe('useFavorites', () => {
  it('fetches favorites when authenticated', async () => {
    vi.mocked(favoritesService.getFavorites).mockResolvedValue(mockFavorites as any);

    const { result } = renderHook(() => useFavorites(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(mockFavorites);
  });

  it('does not fetch when not authenticated', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: false,
      accessToken: null,
    } as any);

    const { result } = renderHook(() => useFavorites(), { wrapper: createWrapper() });
    expect(result.current.fetchStatus).toBe('idle');
  });

  it('handles API error', async () => {
    vi.mocked(favoritesService.getFavorites).mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useFavorites(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe('useAddFavorite', () => {
  it('adds a favorite successfully', async () => {
    vi.mocked(favoritesService.addFavorite).mockResolvedValue({ id: 'fav-3' } as any);

    const { result } = renderHook(() => useAddFavorite(), { wrapper: createWrapper() });

    await act(async () => {
      result.current.mutate({ itemType: 'api' as any, itemId: 'api-2' });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(favoritesService.addFavorite).toHaveBeenCalledWith('api', 'api-2');
  });

  it('handles mutation error', async () => {
    vi.mocked(favoritesService.addFavorite).mockRejectedValue(new Error('Failed'));

    const { result } = renderHook(() => useAddFavorite(), { wrapper: createWrapper() });

    await act(async () => {
      result.current.mutate({ itemType: 'api' as any, itemId: 'api-2' });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe('useRemoveFavorite', () => {
  it('removes a favorite successfully', async () => {
    vi.mocked(favoritesService.removeFavorite).mockResolvedValue(undefined as any);

    const { result } = renderHook(() => useRemoveFavorite(), { wrapper: createWrapper() });

    await act(async () => {
      result.current.mutate('fav-1');
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(favoritesService.removeFavorite).toHaveBeenCalledWith('fav-1');
  });

  it('handles mutation error', async () => {
    vi.mocked(favoritesService.removeFavorite).mockRejectedValue(new Error('Failed'));

    const { result } = renderHook(() => useRemoveFavorite(), { wrapper: createWrapper() });

    await act(async () => {
      result.current.mutate('fav-1');
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
