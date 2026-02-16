import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mcpGatewayService } from './mcpGatewayApi';
import { apiService } from './api';

vi.mock('./api', () => ({
  apiService: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

const mockGet = vi.mocked(apiService.get);
const mockPost = vi.mocked(apiService.post);
const mockPatch = vi.mocked(apiService.patch);
const mockDelete = vi.mocked(apiService.delete);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('MCPToolsService', () => {
  describe('getTools', () => {
    it('calls with default limit', async () => {
      mockGet.mockResolvedValue({ data: { tools: [], nextCursor: null } } as any);
      await mcpGatewayService.getTools();
      expect(mockGet).toHaveBeenCalledWith('/v1/mcp/tools', {
        params: {
          tenant_id: undefined,
          tag: undefined,
          search: undefined,
          cursor: undefined,
          limit: 20,
        },
      });
    });

    it('passes all filter params', async () => {
      mockGet.mockResolvedValue({ data: { tools: [] } } as any);
      await mcpGatewayService.getTools({
        tenant: 't1',
        tag: 'finance',
        search: 'payment',
        cursor: 'abc',
        limit: 50,
      });
      expect(mockGet).toHaveBeenCalledWith('/v1/mcp/tools', {
        params: {
          tenant_id: 't1',
          tag: 'finance',
          search: 'payment',
          cursor: 'abc',
          limit: 50,
        },
      });
    });
  });

  describe('getTool', () => {
    it('calls correct endpoint with encoded name', async () => {
      mockGet.mockResolvedValue({ data: { name: 'tool/name' } } as any);
      await mcpGatewayService.getTool('tool/name');
      expect(mockGet).toHaveBeenCalledWith('/v1/mcp/tools/tool%2Fname');
    });
  });

  describe('getToolSchema', () => {
    it('calls correct endpoint', async () => {
      mockGet.mockResolvedValue({ data: { name: 'tool1', inputSchema: {} } } as any);
      const result = await mcpGatewayService.getToolSchema('tool1');
      expect(mockGet).toHaveBeenCalledWith('/v1/mcp/tools/tool1/schema');
      expect(result).toEqual({ name: 'tool1', inputSchema: {} });
    });
  });

  describe('getToolTags', () => {
    it('returns tags array from response', async () => {
      mockGet.mockResolvedValue({ data: { tags: ['finance', 'hr'] } } as any);
      const result = await mcpGatewayService.getToolTags();
      expect(mockGet).toHaveBeenCalledWith('/v1/mcp/tools/tags');
      expect(result).toEqual(['finance', 'hr']);
    });

    it('returns empty array when tags missing', async () => {
      mockGet.mockResolvedValue({ data: {} } as any);
      const result = await mcpGatewayService.getToolTags();
      expect(result).toEqual([]);
    });
  });

  describe('getToolCategories', () => {
    it('returns categories from response', async () => {
      const categories = { categories: [{ name: 'finance', count: 5 }] };
      mockGet.mockResolvedValue({ data: categories } as any);
      const result = await mcpGatewayService.getToolCategories();
      expect(mockGet).toHaveBeenCalledWith('/v1/mcp/tools/categories');
      expect(result).toEqual(categories);
    });
  });

  describe('getMySubscriptions', () => {
    it('returns items array from response', async () => {
      mockGet.mockResolvedValue({ data: { items: [{ id: 'sub1' }] } } as any);
      const result = await mcpGatewayService.getMySubscriptions();
      expect(mockGet).toHaveBeenCalledWith('/v1/mcp/subscriptions');
      expect(result).toEqual([{ id: 'sub1' }]);
    });

    it('returns empty array when items missing', async () => {
      mockGet.mockResolvedValue({ data: {} } as any);
      const result = await mcpGatewayService.getMySubscriptions();
      expect(result).toEqual([]);
    });
  });

  describe('subscribeTool', () => {
    it('posts to correct endpoint', async () => {
      const payload = { tool_name: 'tool1' };
      mockPost.mockResolvedValue({ data: { id: 'sub1' } } as any);
      const result = await mcpGatewayService.subscribeTool(payload as any);
      expect(mockPost).toHaveBeenCalledWith('/v1/mcp/subscriptions', payload);
      expect(result).toEqual({ id: 'sub1' });
    });
  });

  describe('unsubscribeTool', () => {
    it('deletes correct endpoint', async () => {
      mockDelete.mockResolvedValue({ data: null } as any);
      await mcpGatewayService.unsubscribeTool('sub1');
      expect(mockDelete).toHaveBeenCalledWith('/v1/mcp/subscriptions/sub1');
    });
  });

  describe('updateSubscription', () => {
    it('patches correct endpoint', async () => {
      mockPatch.mockResolvedValue({ data: { id: 'sub1' } } as any);
      const result = await mcpGatewayService.updateSubscription('sub1', {
        tool_name: 'updated',
      } as any);
      expect(mockPatch).toHaveBeenCalledWith('/v1/mcp/subscriptions/sub1', {
        tool_name: 'updated',
      });
      expect(result).toEqual({ id: 'sub1' });
    });
  });

  describe('getMyUsage', () => {
    it('calls with params', async () => {
      mockGet.mockResolvedValue({ data: { total_calls: 100 } } as any);
      await mcpGatewayService.getMyUsage({ period: 'week' });
      expect(mockGet).toHaveBeenCalledWith('/v1/usage/me', { params: { period: 'week' } });
    });

    it('calls without params', async () => {
      mockGet.mockResolvedValue({ data: { total_calls: 0 } } as any);
      await mcpGatewayService.getMyUsage();
      expect(mockGet).toHaveBeenCalledWith('/v1/usage/me', { params: undefined });
    });
  });

  describe('getToolUsage', () => {
    it('calls with encoded tool name and params', async () => {
      mockGet.mockResolvedValue({ data: { total_calls: 50 } } as any);
      await mcpGatewayService.getToolUsage('tool/name', { period: 'month' });
      expect(mockGet).toHaveBeenCalledWith('/v1/usage/tools/tool%2Fname', {
        params: { period: 'month' },
      });
    });
  });

  describe('getUsageHistory', () => {
    it('calls with params', async () => {
      mockGet.mockResolvedValue({ data: { dataPoints: [] } } as any);
      await mcpGatewayService.getUsageHistory({ period: 'day', groupBy: 'hour' });
      expect(mockGet).toHaveBeenCalledWith('/v1/usage/history', {
        params: { period: 'day', groupBy: 'hour' },
      });
    });
  });

  describe('healthCheck', () => {
    it('calls correct endpoint', async () => {
      mockGet.mockResolvedValue({ data: { status: 'healthy' } } as any);
      const result = await mcpGatewayService.healthCheck();
      expect(mockGet).toHaveBeenCalledWith('/health');
      expect(result).toEqual({ status: 'healthy' });
    });
  });

  describe('legacy methods', () => {
    it('setAuthToken is a no-op', () => {
      expect(() => mcpGatewayService.setAuthToken('token')).not.toThrow();
    });

    it('clearAuthToken is a no-op', () => {
      expect(() => mcpGatewayService.clearAuthToken()).not.toThrow();
    });
  });
});
