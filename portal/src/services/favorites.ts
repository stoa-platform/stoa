/**
 * Favorites / Bookmarks Service (CAB-1470)
 */

import { apiClient } from './api';
import type { FavoritesResponse, FavoriteType } from '../types';

async function getFavorites(): Promise<FavoritesResponse> {
  try {
    const response = await apiClient.get<FavoritesResponse>('/v1/portal/favorites');
    return response.data;
  } catch {
    console.warn('Favorites endpoint not available, using fallback');
    return { favorites: [], total: 0 };
  }
}

async function addFavorite(itemType: FavoriteType, itemId: string): Promise<void> {
  await apiClient.post('/v1/portal/favorites', { item_type: itemType, item_id: itemId });
}

async function removeFavorite(favoriteId: string): Promise<void> {
  await apiClient.delete(`/v1/portal/favorites/${favoriteId}`);
}

export const favoritesService = {
  getFavorites,
  addFavorite,
  removeFavorite,
};
