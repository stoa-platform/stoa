import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { rateLimitsService } from './rateLimits';

vi.mock('./api', () => ({
  apiClient: {
    get: vi.fn(),
  },
}));

import { apiClient } from './api';

const mockGet = apiClient.get as Mock;

describe('rateLimitsService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getRateLimits', () => {
    it('returns rate limits from the API', async () => {
      const mockData = {
        rate_limits: [{ id: '1', name: 'default', requests_per_minute: 60 }],
        total: 1,
      };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const result = await rateLimitsService.getRateLimits();

      expect(mockGet).toHaveBeenCalledWith('/v1/portal/rate-limits');
      expect(result).toEqual(mockData);
    });

    it('returns fallback on error', async () => {
      mockGet.mockRejectedValueOnce(new Error('Network error'));

      const result = await rateLimitsService.getRateLimits();

      expect(result).toEqual({ rate_limits: [], total: 0 });
    });
  });
});
