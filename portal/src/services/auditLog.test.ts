import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { auditLogService } from './auditLog';

vi.mock('./api', () => ({
  apiClient: {
    get: vi.fn(),
  },
}));

import { apiClient } from './api';

const mockGet = apiClient.get as Mock;

describe('auditLogService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getEntries', () => {
    it('returns audit log entries from the API', async () => {
      const mockData = {
        entries: [{ id: '1', action: 'api.created', timestamp: '2026-01-01' }],
        total: 1,
        page: 1,
        limit: 25,
      };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const result = await auditLogService.getEntries();

      expect(mockGet).toHaveBeenCalledWith('/v1/portal/audit-log', { params: undefined });
      expect(result).toEqual(mockData);
    });

    it('passes filters as query params', async () => {
      const filters = { page: 2, limit: 10, action: 'api.created' };
      mockGet.mockResolvedValueOnce({ data: { entries: [], total: 0, page: 2, limit: 10 } });

      await auditLogService.getEntries(filters);

      expect(mockGet).toHaveBeenCalledWith('/v1/portal/audit-log', { params: filters });
    });

    it('returns fallback on error', async () => {
      mockGet.mockRejectedValueOnce(new Error('Network error'));

      const result = await auditLogService.getEntries();

      expect(result).toEqual({ entries: [], total: 0, page: 1, limit: 25 });
    });
  });
});
