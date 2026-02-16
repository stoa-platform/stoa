import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { gatewaysService } from './gateways';

vi.mock('./api', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import { apiClient } from './api';

const mockGet = apiClient.get as Mock;
const mockPost = apiClient.post as Mock;

describe('gatewaysService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  describe('listGateways', () => {
    it('should fetch gateways with default params', async () => {
      mockGet.mockResolvedValueOnce({
        data: { items: [{ id: 'gw-1' }], total: 1, page: 1, page_size: 20 },
      });

      const result = await gatewaysService.listGateways();

      expect(mockGet).toHaveBeenCalledWith('/v1/admin/gateways', {
        params: {
          page: 1,
          page_size: 20,
          gateway_type: undefined,
          environment: undefined,
          status: undefined,
        },
      });
      expect(result.items).toHaveLength(1);
    });

    it('should pass custom params', async () => {
      mockGet.mockResolvedValueOnce({
        data: { items: [], total: 0, page: 1, page_size: 10 },
      });

      await gatewaysService.listGateways({
        page: 2,
        pageSize: 10,
        gateway_type: 'kong',
        status: 'online',
      });

      expect(mockGet).toHaveBeenCalledWith('/v1/admin/gateways', {
        params: {
          page: 2,
          page_size: 10,
          gateway_type: 'kong',
          environment: undefined,
          status: 'online',
        },
      });
    });

    it('should return fallback on error', async () => {
      mockGet.mockRejectedValueOnce(new Error('Network'));

      const result = await gatewaysService.listGateways();

      expect(result).toEqual({ items: [], total: 0, page: 1, page_size: 20 });
    });
  });

  describe('getGateway', () => {
    it('should fetch a single gateway', async () => {
      mockGet.mockResolvedValueOnce({
        data: { id: 'gw-1', name: 'kong-standalone' },
      });

      const result = await gatewaysService.getGateway('gw-1');

      expect(mockGet).toHaveBeenCalledWith('/v1/admin/gateways/gw-1');
      expect(result?.id).toBe('gw-1');
    });

    it('should return null on error', async () => {
      mockGet.mockRejectedValueOnce(new Error('Not found'));

      const result = await gatewaysService.getGateway('gw-missing');

      expect(result).toBeNull();
    });
  });

  describe('getModeStats', () => {
    it('should fetch mode stats', async () => {
      mockGet.mockResolvedValueOnce({
        data: [
          { mode: 'edge-mcp', count: 2 },
          { mode: 'sidecar', count: 1 },
        ],
      });

      const result = await gatewaysService.getModeStats();

      expect(mockGet).toHaveBeenCalledWith('/v1/admin/gateways/modes/stats');
      expect(result).toHaveLength(2);
    });

    it('should return empty array on error', async () => {
      mockGet.mockRejectedValueOnce(new Error('Server error'));

      const result = await gatewaysService.getModeStats();

      expect(result).toEqual([]);
    });
  });

  describe('triggerHealthCheck', () => {
    it('should trigger health check and return true', async () => {
      mockPost.mockResolvedValueOnce({ data: { status: 'ok' } });

      const result = await gatewaysService.triggerHealthCheck('gw-1');

      expect(mockPost).toHaveBeenCalledWith('/v1/admin/gateways/gw-1/health');
      expect(result).toBe(true);
    });

    it('should return false on error', async () => {
      mockPost.mockRejectedValueOnce(new Error('Timeout'));

      const result = await gatewaysService.triggerHealthCheck('gw-1');

      expect(result).toBe(false);
    });
  });
});
