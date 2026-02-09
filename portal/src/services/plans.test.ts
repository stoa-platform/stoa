/**
 * Tests for Plans Service (CAB-1121 P5)
 */

import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { plansService } from './plans';

vi.mock('./api', () => ({
  apiClient: {
    get: vi.fn(),
  },
}));

import { apiClient } from './api';

const mockGet = apiClient.get as Mock;

describe('plansService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('list', () => {
    it('should call GET /v1/plans/{tenantId} with default params', async () => {
      const mockData = {
        items: [{ id: 'plan-1', name: 'Basic', slug: 'basic', status: 'active' }],
        total: 1,
        page: 1,
        page_size: 50,
        total_pages: 1,
      };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const result = await plansService.list('acme');

      expect(mockGet).toHaveBeenCalledWith('/v1/plans/acme', {
        params: { page: 1, page_size: 50, status: undefined },
      });
      expect(result.items).toHaveLength(1);
      expect(result.items[0].slug).toBe('basic');
    });

    it('should pass custom params', async () => {
      mockGet.mockResolvedValueOnce({ data: { items: [], total: 0 } });

      await plansService.list('acme', { page: 2, pageSize: 10, status: 'active' });

      expect(mockGet).toHaveBeenCalledWith('/v1/plans/acme', {
        params: { page: 2, page_size: 10, status: 'active' },
      });
    });
  });

  describe('get', () => {
    it('should call GET /v1/plans/{tenantId}/{planId}', async () => {
      const mockPlan = { id: 'plan-1', name: 'Premium', slug: 'premium' };
      mockGet.mockResolvedValueOnce({ data: mockPlan });

      const result = await plansService.get('acme', 'plan-1');

      expect(mockGet).toHaveBeenCalledWith('/v1/plans/acme/plan-1');
      expect(result.name).toBe('Premium');
    });
  });

  describe('getBySlug', () => {
    it('should call GET /v1/plans/{tenantId}/by-slug/{slug}', async () => {
      const mockPlan = { id: 'plan-1', name: 'Enterprise', slug: 'enterprise' };
      mockGet.mockResolvedValueOnce({ data: mockPlan });

      const result = await plansService.getBySlug('acme', 'enterprise');

      expect(mockGet).toHaveBeenCalledWith('/v1/plans/acme/by-slug/enterprise');
      expect(result.slug).toBe('enterprise');
    });
  });
});
