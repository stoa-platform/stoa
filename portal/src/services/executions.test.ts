import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { executionsService } from './executions';

vi.mock('./api', () => ({
  apiClient: {
    get: vi.fn(),
  },
}));

import { apiClient } from './api';

const mockGet = apiClient.get as Mock;

describe('executionsService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('list', () => {
    it('fetches executions with default params', async () => {
      const mockData = { items: [], total: 0, page: 1, page_size: 20 };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const result = await executionsService.list();

      expect(mockGet).toHaveBeenCalledWith('/v1/usage/me/executions', {
        params: { page: 1, page_size: 20, status: undefined },
      });
      expect(result).toEqual(mockData);
    });

    it('passes custom params', async () => {
      const mockData = { items: [], total: 0, page: 2, page_size: 10 };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const result = await executionsService.list({ page: 2, page_size: 10, status: 'error' });

      expect(mockGet).toHaveBeenCalledWith('/v1/usage/me/executions', {
        params: { page: 2, page_size: 10, status: 'error' },
      });
      expect(result).toEqual(mockData);
    });
  });

  describe('getTaxonomy', () => {
    it('fetches error taxonomy', async () => {
      const mockData = {
        items: [{ category: 'timeout', count: 5, avg_duration_ms: 3000, percentage: 50 }],
        total_errors: 10,
        total_executions: 100,
        error_rate: 0.1,
      };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const result = await executionsService.getTaxonomy();

      expect(mockGet).toHaveBeenCalledWith('/v1/usage/me/executions/taxonomy');
      expect(result).toEqual(mockData);
    });
  });
});
