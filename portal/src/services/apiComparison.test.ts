import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { apiComparisonService } from './apiComparison';

vi.mock('./api', () => ({
  apiClient: {
    post: vi.fn(),
  },
}));

import { apiClient } from './api';

const mockPost = apiClient.post as Mock;

describe('apiComparisonService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('compareAPIs', () => {
    it('posts API IDs and returns comparison result', async () => {
      const mockData = {
        api_ids: ['api-1', 'api-2'],
        api_names: { 'api-1': 'Payment API', 'api-2': 'Auth API' },
        fields: [{ name: 'auth', values: { 'api-1': 'OAuth2', 'api-2': 'API Key' } }],
      };
      mockPost.mockResolvedValueOnce({ data: mockData });

      const result = await apiComparisonService.compareAPIs(['api-1', 'api-2']);

      expect(mockPost).toHaveBeenCalledWith('/v1/portal/apis/compare', {
        api_ids: ['api-1', 'api-2'],
      });
      expect(result).toEqual(mockData);
    });

    it('returns fallback on error', async () => {
      mockPost.mockRejectedValueOnce(new Error('Network error'));

      const result = await apiComparisonService.compareAPIs(['api-1', 'api-2']);

      expect(result).toEqual({
        api_ids: ['api-1', 'api-2'],
        api_names: {},
        fields: [],
      });
    });
  });
});
