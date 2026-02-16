import { describe, it, expect, vi, beforeEach } from 'vitest';
import { externalMcpServersService } from './externalMcpServersApi';
import { apiService } from './api';

vi.mock('./api', () => ({
  apiService: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

const mockGet = vi.mocked(apiService.get);
const mockPost = vi.mocked(apiService.post);
const mockPut = vi.mocked(apiService.put);
const mockPatch = vi.mocked(apiService.patch);
const mockDelete = vi.mocked(apiService.delete);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ExternalMCPServersService', () => {
  describe('listServers', () => {
    it('calls with default pagination', async () => {
      mockGet.mockResolvedValue({ data: { items: [], total: 0 } } as any);
      await externalMcpServersService.listServers();
      expect(mockGet).toHaveBeenCalledWith('/v1/admin/external-mcp-servers', {
        params: { enabled_only: undefined, page: 1, page_size: 20 },
      });
    });

    it('passes all params', async () => {
      mockGet.mockResolvedValue({ data: { items: [], total: 0 } } as any);
      await externalMcpServersService.listServers({ enabled_only: true, page: 2, page_size: 50 });
      expect(mockGet).toHaveBeenCalledWith('/v1/admin/external-mcp-servers', {
        params: { enabled_only: true, page: 2, page_size: 50 },
      });
    });
  });

  describe('getServer', () => {
    it('calls correct endpoint', async () => {
      mockGet.mockResolvedValue({ data: { id: 'srv1', name: 'linear' } } as any);
      const result = await externalMcpServersService.getServer('srv1');
      expect(mockGet).toHaveBeenCalledWith('/v1/admin/external-mcp-servers/srv1');
      expect(result).toEqual({ id: 'srv1', name: 'linear' });
    });
  });

  describe('createServer', () => {
    it('posts to correct endpoint', async () => {
      const payload = {
        name: 'github',
        display_name: 'GitHub',
        base_url: 'https://mcp.github.com',
        transport: 'sse' as const,
        auth_type: 'bearer_token' as const,
      };
      mockPost.mockResolvedValue({ data: { id: 'srv2', ...payload } } as any);
      const result = await externalMcpServersService.createServer(payload as any);
      expect(mockPost).toHaveBeenCalledWith('/v1/admin/external-mcp-servers', payload);
      expect(result).toEqual({ id: 'srv2', ...payload });
    });
  });

  describe('updateServer', () => {
    it('puts to correct endpoint', async () => {
      const update = { display_name: 'GitHub Updated' };
      mockPut.mockResolvedValue({ data: { id: 'srv1', display_name: 'GitHub Updated' } } as any);
      const result = await externalMcpServersService.updateServer('srv1', update as any);
      expect(mockPut).toHaveBeenCalledWith('/v1/admin/external-mcp-servers/srv1', update);
      expect(result).toEqual({ id: 'srv1', display_name: 'GitHub Updated' });
    });
  });

  describe('deleteServer', () => {
    it('deletes correct endpoint', async () => {
      mockDelete.mockResolvedValue({ data: null } as any);
      await externalMcpServersService.deleteServer('srv1');
      expect(mockDelete).toHaveBeenCalledWith('/v1/admin/external-mcp-servers/srv1');
    });
  });

  describe('testConnection', () => {
    it('posts to correct endpoint', async () => {
      mockPost.mockResolvedValue({ data: { success: true, latency_ms: 42 } } as any);
      const result = await externalMcpServersService.testConnection('srv1');
      expect(mockPost).toHaveBeenCalledWith('/v1/admin/external-mcp-servers/srv1/test-connection');
      expect(result).toEqual({ success: true, latency_ms: 42 });
    });
  });

  describe('syncTools', () => {
    it('posts to correct endpoint', async () => {
      mockPost.mockResolvedValue({ data: { tools_added: 3, tools_removed: 1 } } as any);
      const result = await externalMcpServersService.syncTools('srv1');
      expect(mockPost).toHaveBeenCalledWith('/v1/admin/external-mcp-servers/srv1/sync-tools');
      expect(result).toEqual({ tools_added: 3, tools_removed: 1 });
    });
  });

  describe('updateTool', () => {
    it('patches correct endpoint', async () => {
      mockPatch.mockResolvedValue({ data: { id: 'tool1', enabled: false } } as any);
      const result = await externalMcpServersService.updateTool('srv1', 'tool1', {
        enabled: false,
      });
      expect(mockPatch).toHaveBeenCalledWith('/v1/admin/external-mcp-servers/srv1/tools/tool1', {
        enabled: false,
      });
      expect(result).toEqual({ id: 'tool1', enabled: false });
    });
  });
});
