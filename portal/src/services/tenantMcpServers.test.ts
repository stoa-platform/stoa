import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { tenantMcpServersService } from './tenantMcpServers';

vi.mock('./api', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
}));

import { apiClient } from './api';

const mockGet = apiClient.get as Mock;
const mockPost = apiClient.post as Mock;
const mockPut = apiClient.put as Mock;
const mockDelete = apiClient.delete as Mock;
const mockPatch = apiClient.patch as Mock;

const tenantId = 'tenant-1';
const serverId = 'srv-1';

describe('tenantMcpServersService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('list', () => {
    it('fetches servers with params', async () => {
      const mockData = { servers: [], total_count: 0, page: 1, page_size: 20 };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const result = await tenantMcpServersService.list(tenantId, { page: 1, enabled_only: true });

      expect(mockGet).toHaveBeenCalledWith(`/v1/tenants/${tenantId}/mcp-servers`, {
        params: { page: 1, enabled_only: true },
      });
      expect(result).toEqual(mockData);
    });
  });

  describe('get', () => {
    it('fetches a single server', async () => {
      const mockServer = { id: serverId, name: 'Test Server', tools: [] };
      mockGet.mockResolvedValueOnce({ data: mockServer });

      const result = await tenantMcpServersService.get(tenantId, serverId);

      expect(mockGet).toHaveBeenCalledWith(`/v1/tenants/${tenantId}/mcp-servers/${serverId}`);
      expect(result).toEqual(mockServer);
    });
  });

  describe('create', () => {
    it('creates a server', async () => {
      const payload = { display_name: 'New Server', base_url: 'https://mcp.example.com' };
      const mockResult = { id: 'srv-new', ...payload, tools: [] };
      mockPost.mockResolvedValueOnce({ data: mockResult });

      const result = await tenantMcpServersService.create(tenantId, payload);

      expect(mockPost).toHaveBeenCalledWith(`/v1/tenants/${tenantId}/mcp-servers`, payload);
      expect(result).toEqual(mockResult);
    });
  });

  describe('update', () => {
    it('updates a server', async () => {
      const payload = { display_name: 'Updated Server' };
      const mockResult = { id: serverId, display_name: 'Updated Server', tools: [] };
      mockPut.mockResolvedValueOnce({ data: mockResult });

      const result = await tenantMcpServersService.update(tenantId, serverId, payload);

      expect(mockPut).toHaveBeenCalledWith(
        `/v1/tenants/${tenantId}/mcp-servers/${serverId}`,
        payload
      );
      expect(result).toEqual(mockResult);
    });
  });

  describe('delete', () => {
    it('deletes a server', async () => {
      mockDelete.mockResolvedValueOnce({});

      await tenantMcpServersService.delete(tenantId, serverId);

      expect(mockDelete).toHaveBeenCalledWith(`/v1/tenants/${tenantId}/mcp-servers/${serverId}`);
    });
  });

  describe('testConnection', () => {
    it('tests connection to a server', async () => {
      const mockResult = {
        success: true,
        latency_ms: 42,
        error: null,
        server_info: {},
        tools_discovered: 5,
      };
      mockPost.mockResolvedValueOnce({ data: mockResult });

      const result = await tenantMcpServersService.testConnection(tenantId, serverId);

      expect(mockPost).toHaveBeenCalledWith(
        `/v1/tenants/${tenantId}/mcp-servers/${serverId}/test-connection`
      );
      expect(result).toEqual(mockResult);
    });
  });

  describe('syncTools', () => {
    it('syncs tools from a server', async () => {
      const mockResult = { synced_count: 3, removed_count: 1, tools: [] };
      mockPost.mockResolvedValueOnce({ data: mockResult });

      const result = await tenantMcpServersService.syncTools(tenantId, serverId);

      expect(mockPost).toHaveBeenCalledWith(
        `/v1/tenants/${tenantId}/mcp-servers/${serverId}/sync-tools`
      );
      expect(result).toEqual(mockResult);
    });
  });

  describe('toggleTool', () => {
    it('toggles a tool enabled state', async () => {
      const mockTool = { id: 'tool-1', name: 'test-tool', enabled: false };
      mockPatch.mockResolvedValueOnce({ data: mockTool });

      const result = await tenantMcpServersService.toggleTool(tenantId, serverId, 'tool-1', false);

      expect(mockPatch).toHaveBeenCalledWith(
        `/v1/tenants/${tenantId}/mcp-servers/${serverId}/tools/tool-1`,
        { enabled: false }
      );
      expect(result).toEqual(mockTool);
    });
  });
});
