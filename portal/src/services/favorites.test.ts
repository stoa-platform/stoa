import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { favoritesService } from './favorites';

vi.mock('./api', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

import { apiClient } from './api';

const mockGet = apiClient.get as Mock;
const mockPost = apiClient.post as Mock;
const mockDelete = apiClient.delete as Mock;

describe('favoritesService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getFavorites', () => {
    it('returns favorites from the API', async () => {
      const mockData = {
        favorites: [{ id: 'fav-1', item_type: 'api', item_id: 'api-1' }],
        total: 1,
      };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const result = await favoritesService.getFavorites();

      expect(mockGet).toHaveBeenCalledWith('/v1/portal/favorites');
      expect(result).toEqual(mockData);
    });

    it('returns fallback on error', async () => {
      mockGet.mockRejectedValueOnce(new Error('Network error'));

      const result = await favoritesService.getFavorites();

      expect(result).toEqual({ favorites: [], total: 0 });
    });
  });

  describe('addFavorite', () => {
    it('posts a favorite to the API', async () => {
      mockPost.mockResolvedValueOnce({});

      await favoritesService.addFavorite('api', 'api-123');

      expect(mockPost).toHaveBeenCalledWith('/v1/portal/favorites', {
        item_type: 'api',
        item_id: 'api-123',
      });
    });
  });

  describe('removeFavorite', () => {
    it('deletes a favorite via the API', async () => {
      mockDelete.mockResolvedValueOnce({});

      await favoritesService.removeFavorite('fav-1');

      expect(mockDelete).toHaveBeenCalledWith('/v1/portal/favorites/fav-1');
    });
  });
});
