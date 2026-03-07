import { describe, it, expect, vi, beforeEach } from 'vitest';
import { proxyBackendService } from './proxyBackendService';
import { apiService } from './api';

vi.mock('./api', () => ({
  apiService: {
    get: vi.fn(),
  },
}));

const mockGet = vi.mocked(apiService.get);

const mockBackend = {
  id: 'backend-1',
  name: 'openai',
  display_name: 'OpenAI API',
  description: 'OpenAI proxy backend',
  base_url: 'https://api.openai.com',
  health_endpoint: '/health',
  auth_type: 'bearer' as const,
  credential_ref: 'cred-openai',
  rate_limit_rpm: 60,
  circuit_breaker_enabled: true,
  fallback_direct: false,
  timeout_secs: 30,
  status: 'active' as const,
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const mockHealthStatus = {
  backend_name: 'openai',
  healthy: true,
  status_code: 200,
  latency_ms: 42,
  error: null,
  checked_at: '2026-01-01T00:00:00Z',
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('proxyBackendService', () => {
  describe('list()', () => {
    it('calls correct endpoint with default params (activeOnly = false)', async () => {
      mockGet.mockResolvedValue({ data: { items: [], total: 0 } } as any);
      await proxyBackendService.list();
      expect(mockGet).toHaveBeenCalledWith('/v1/proxy-backends', {
        params: { active_only: false },
      });
    });

    it('passes active_only: true when activeOnly is true', async () => {
      mockGet.mockResolvedValue({ data: { items: [], total: 0 } } as any);
      await proxyBackendService.list(true);
      expect(mockGet).toHaveBeenCalledWith('/v1/proxy-backends', {
        params: { active_only: true },
      });
    });

    it('normalizes array response to {items, total}', async () => {
      mockGet.mockResolvedValue({ data: [mockBackend] } as any);
      const result = await proxyBackendService.list();
      expect(result).toEqual({ items: [mockBackend], total: 1 });
    });

    it('handles empty array response', async () => {
      mockGet.mockResolvedValue({ data: [] } as any);
      const result = await proxyBackendService.list();
      expect(result).toEqual({ items: [], total: 0 });
    });

    it('returns wrapped {items, total} response as-is', async () => {
      mockGet.mockResolvedValue({ data: { items: [mockBackend], total: 1 } } as any);
      const result = await proxyBackendService.list();
      expect(result).toEqual({ items: [mockBackend], total: 1 });
    });

    it('infers total from items.length when total field is absent in wrapped response', async () => {
      mockGet.mockResolvedValue({ data: { items: [mockBackend] } } as any);
      const result = await proxyBackendService.list();
      expect(result).toEqual({ items: [mockBackend], total: 1 });
    });

    it('returns empty items when wrapped response has no items field', async () => {
      mockGet.mockResolvedValue({ data: {} } as any);
      const result = await proxyBackendService.list();
      expect(result).toEqual({ items: [], total: 0 });
    });
  });

  describe('healthCheck()', () => {
    it('calls correct endpoint with backendId', async () => {
      mockGet.mockResolvedValue({ data: mockHealthStatus } as any);
      await proxyBackendService.healthCheck('backend-1');
      expect(mockGet).toHaveBeenCalledWith('/v1/proxy-backends/backend-1/health');
    });

    it('returns health status data', async () => {
      mockGet.mockResolvedValue({ data: mockHealthStatus } as any);
      const result = await proxyBackendService.healthCheck('backend-1');
      expect(result).toEqual(mockHealthStatus);
    });
  });
});
