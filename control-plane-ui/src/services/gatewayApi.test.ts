import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  getGatewayHealth,
  getGatewayAPIs,
  getGatewayApplications,
  getGatewayStatus,
} from './gatewayApi';
import { apiService } from './api';

vi.mock('./api', () => ({
  apiService: {
    get: vi.fn(),
  },
}));

const mockGet = vi.mocked(apiService.get);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('gatewayApi', () => {
  describe('getGatewayHealth', () => {
    it('calls correct endpoint and returns data', async () => {
      const health = { status: 'healthy', proxy_mode: false };
      mockGet.mockResolvedValue({ data: health } as any);
      const result = await getGatewayHealth();
      expect(mockGet).toHaveBeenCalledWith('/v1/gateway/health');
      expect(result).toEqual(health);
    });
  });

  describe('getGatewayAPIs', () => {
    it('calls correct endpoint and returns data', async () => {
      const apis = [{ id: 'a1', apiName: 'test', apiVersion: '1.0', isActive: true }];
      mockGet.mockResolvedValue({ data: apis } as any);
      const result = await getGatewayAPIs();
      expect(mockGet).toHaveBeenCalledWith('/v1/gateway/apis');
      expect(result).toEqual(apis);
    });
  });

  describe('getGatewayApplications', () => {
    it('calls correct endpoint and returns data', async () => {
      const apps = [{ id: 'app1', name: 'test', contactEmails: [] }];
      mockGet.mockResolvedValue({ data: apps } as any);
      const result = await getGatewayApplications();
      expect(mockGet).toHaveBeenCalledWith('/v1/gateway/applications');
      expect(result).toEqual(apps);
    });
  });

  describe('getGatewayStatus', () => {
    it('returns aggregated status when all calls succeed', async () => {
      const health = { status: 'healthy' as const, proxy_mode: false };
      const apis = [{ id: 'a1', apiName: 'test', apiVersion: '1.0', isActive: true }];
      const apps = [{ id: 'app1', name: 'test', contactEmails: [] }];

      mockGet
        .mockResolvedValueOnce({ data: health } as any)
        .mockResolvedValueOnce({ data: apis } as any)
        .mockResolvedValueOnce({ data: apps } as any);

      const result = await getGatewayStatus();
      expect(result.health).toEqual(health);
      expect(result.apis).toEqual(apis);
      expect(result.applications).toEqual(apps);
      expect(result.fetchedAt).toBeDefined();
    });

    it('returns fallback health when health call fails', async () => {
      mockGet
        .mockRejectedValueOnce(new Error('health down'))
        .mockResolvedValueOnce({ data: [] } as any)
        .mockResolvedValueOnce({ data: [] } as any);

      const result = await getGatewayStatus();
      expect(result.health.status).toBe('unhealthy');
      expect(result.health.proxy_mode).toBe(false);
      expect(result.health.error).toContain('health down');
      expect(result.apis).toEqual([]);
      expect(result.applications).toEqual([]);
    });

    it('returns empty arrays when apis/applications calls fail', async () => {
      const health = { status: 'healthy' as const, proxy_mode: false };
      mockGet
        .mockResolvedValueOnce({ data: health } as any)
        .mockRejectedValueOnce(new Error('api error'))
        .mockRejectedValueOnce(new Error('app error'));

      const result = await getGatewayStatus();
      expect(result.health).toEqual(health);
      expect(result.apis).toEqual([]);
      expect(result.applications).toEqual([]);
    });

    it('returns complete fallback when all calls fail', async () => {
      mockGet
        .mockRejectedValueOnce(new Error('fail'))
        .mockRejectedValueOnce(new Error('fail'))
        .mockRejectedValueOnce(new Error('fail'));

      const result = await getGatewayStatus();
      expect(result.health.status).toBe('unhealthy');
      expect(result.apis).toEqual([]);
      expect(result.applications).toEqual([]);
      expect(result.fetchedAt).toBeDefined();
    });
  });
});
