/**
 * Favorites / Bookmarks Hooks (CAB-1470)
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { favoritesService } from '../services/favorites';
import { useAuth } from '../contexts/AuthContext';
import type { FavoritesResponse, FavoriteType } from '../types';

export function useFavorites() {
  const { isAuthenticated, accessToken } = useAuth();

  return useQuery<FavoritesResponse>({
    queryKey: ['favorites'],
    queryFn: () => favoritesService.getFavorites(),
    enabled: isAuthenticated && !!accessToken,
    staleTime: 60 * 1000,
  });
}

export function useAddFavorite() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ itemType, itemId }: { itemType: FavoriteType; itemId: string }) =>
      favoritesService.addFavorite(itemType, itemId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['favorites'] });
    },
  });
}

export function useRemoveFavorite() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (favoriteId: string) => favoritesService.removeFavorite(favoriteId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['favorites'] });
    },
  });
}
