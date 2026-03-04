import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mcpConnectorsService } from './mcpConnectorsApi';

vi.mock('./api', () => ({
  apiService: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

import { apiService } from './api';

describe('mcpConnectorsService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('listConnectors', () => {
    it('calls GET without tenant_id', async () => {
      const mockResponse = { connectors: [], total: 0 };
      vi.mocked(apiService.get).mockResolvedValue({ data: mockResponse });
      const result = await mcpConnectorsService.listConnectors();
      expect(apiService.get).toHaveBeenCalledWith('/v1/admin/mcp-connectors', {
        params: undefined,
      });
      expect(result).toEqual(mockResponse);
    });

    it('calls GET with tenant_id', async () => {
      const mockResponse = { connectors: [], total: 0 };
      vi.mocked(apiService.get).mockResolvedValue({ data: mockResponse });
      const result = await mcpConnectorsService.listConnectors('tenant-1');
      expect(apiService.get).toHaveBeenCalledWith('/v1/admin/mcp-connectors', {
        params: { tenant_id: 'tenant-1' },
      });
      expect(result).toEqual(mockResponse);
    });
  });

  describe('authorize', () => {
    it('calls POST with slug and body', async () => {
      const mockResponse = { authorization_url: 'https://oauth.example.com/auth' };
      vi.mocked(apiService.post).mockResolvedValue({ data: mockResponse });
      const body = { tenant_id: 'tenant-1', redirect_after: '/connectors' };
      const result = await mcpConnectorsService.authorize('github', body);
      expect(apiService.post).toHaveBeenCalledWith(
        '/v1/admin/mcp-connectors/github/authorize',
        body
      );
      expect(result).toEqual(mockResponse);
    });
  });

  describe('handleCallback', () => {
    it('calls POST with code and state', async () => {
      const mockResponse = { server_id: 'srv-1', status: 'connected' };
      vi.mocked(apiService.post).mockResolvedValue({ data: mockResponse });
      const body = { code: 'auth-code-123', state: 'state-abc' };
      const result = await mcpConnectorsService.handleCallback(body);
      expect(apiService.post).toHaveBeenCalledWith('/v1/admin/mcp-connectors/callback', body);
      expect(result).toEqual(mockResponse);
    });
  });

  describe('disconnect', () => {
    it('calls DELETE without tenant_id', async () => {
      vi.mocked(apiService.delete).mockResolvedValue({});
      await mcpConnectorsService.disconnect('github');
      expect(apiService.delete).toHaveBeenCalledWith('/v1/admin/mcp-connectors/github/disconnect');
    });

    it('calls DELETE with tenant_id', async () => {
      vi.mocked(apiService.delete).mockResolvedValue({});
      await mcpConnectorsService.disconnect('github', 'tenant-1');
      expect(apiService.delete).toHaveBeenCalledWith(
        '/v1/admin/mcp-connectors/github/disconnect?tenant_id=tenant-1'
      );
    });
  });
});
