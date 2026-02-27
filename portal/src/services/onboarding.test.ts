import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { onboardingService } from './onboarding';

vi.mock('./api', () => ({
  apiClient: {
    get: vi.fn(),
  },
}));

import { apiClient } from './api';

const mockGet = apiClient.get as Mock;

describe('onboardingService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getFunnel', () => {
    it('fetches onboarding funnel data', async () => {
      const mockData = {
        stages: [{ stage: 'signup', count: 100, conversion_rate: 0.8 }],
        total_started: 100,
        total_completed: 60,
        avg_ttftc_seconds: 120,
        p50_ttftc_seconds: 90,
        p90_ttftc_seconds: 300,
      };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const result = await onboardingService.getFunnel();

      expect(mockGet).toHaveBeenCalledWith('/v1/admin/onboarding/funnel');
      expect(result).toEqual(mockData);
    });
  });

  describe('getStalled', () => {
    it('fetches stalled users with default hours', async () => {
      const mockData = [
        {
          user_id: 'u-1',
          tenant_id: 't-1',
          last_step: 'api_key',
          started_at: '2026-01-01',
          hours_stalled: 48,
        },
      ];
      mockGet.mockResolvedValueOnce({ data: mockData });

      const result = await onboardingService.getStalled();

      expect(mockGet).toHaveBeenCalledWith('/v1/admin/onboarding/stalled', {
        params: { hours: 24 },
      });
      expect(result).toEqual(mockData);
    });

    it('passes custom hours parameter', async () => {
      mockGet.mockResolvedValueOnce({ data: [] });

      await onboardingService.getStalled(72);

      expect(mockGet).toHaveBeenCalledWith('/v1/admin/onboarding/stalled', {
        params: { hours: 72 },
      });
    });
  });
});
