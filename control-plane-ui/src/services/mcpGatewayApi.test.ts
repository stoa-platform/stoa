import { describe, it, expect, vi, beforeEach } from 'vitest';
import axios from 'axios';
import { mcpGatewayService } from './mcpGatewayApi';
import { mockTools, mockSubscription, mockUsageSummary } from '../test/mocks';

// Mock axios
vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => ({
      get: vi.fn(),
      post: vi.fn(),
      patch: vi.fn(),
      delete: vi.fn(),
      defaults: {
        headers: {
          common: {},
        },
      },
      interceptors: {
        request: {
          use: vi.fn(),
        },
        response: {
          use: vi.fn(),
        },
      },
    })),
  },
}));

describe('mcpGatewayService', () => {
  let mockClient: ReturnType<typeof axios.create>;

  beforeEach(() => {
    vi.clearAllMocks();
    mockClient = axios.create();
  });

  describe('authentication', () => {
    it('setAuthToken sets bearer token', () => {
      const token = 'test-token';
      mcpGatewayService.setAuthToken(token);

      expect(mockClient.defaults.headers.common['Authorization']).toBe(`Bearer ${token}`);
    });

    it('clearAuthToken removes authorization header', () => {
      mcpGatewayService.setAuthToken('test-token');
      mcpGatewayService.clearAuthToken();

      expect(mockClient.defaults.headers.common['Authorization']).toBeUndefined();
    });
  });

  describe('getTools', () => {
    it('fetches tools with default params', async () => {
      const mockResponse = { data: { tools: mockTools, totalCount: mockTools.length } };
      (mockClient.get as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);

      const result = await mcpGatewayService.getTools();

      expect(mockClient.get).toHaveBeenCalledWith('/mcp/tools', {
        params: {
          tenant: undefined,
          tag: undefined,
          search: undefined,
          cursor: undefined,
          limit: 20,
        },
      });
      expect(result.tools).toHaveLength(mockTools.length);
    });

    it('fetches tools with filters', async () => {
      const mockResponse = { data: { tools: [mockTools[0]], totalCount: 1 } };
      (mockClient.get as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);

      await mcpGatewayService.getTools({
        tenant: 'acme-corp',
        tag: 'apis',
        search: 'list',
        limit: 10,
      });

      expect(mockClient.get).toHaveBeenCalledWith('/mcp/tools', {
        params: {
          tenant: 'acme-corp',
          tag: 'apis',
          search: 'list',
          cursor: undefined,
          limit: 10,
        },
      });
    });
  });

  describe('getTool', () => {
    it('fetches a specific tool by name', async () => {
      const mockResponse = { data: mockTools[0] };
      (mockClient.get as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);

      const result = await mcpGatewayService.getTool('stoa_list_apis');

      expect(mockClient.get).toHaveBeenCalledWith('/mcp/tools/stoa_list_apis');
      expect(result.name).toBe('stoa_list_apis');
    });
  });

  describe('getToolTags', () => {
    it('fetches all unique tags', async () => {
      const mockResponse = { data: { tags: ['platform', 'apis', 'payments'] } };
      (mockClient.get as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);

      const result = await mcpGatewayService.getToolTags();

      expect(mockClient.get).toHaveBeenCalledWith('/mcp/tools/tags');
      expect(result).toContain('platform');
    });
  });

  describe('subscriptions', () => {
    it('getMySubscriptions fetches user subscriptions', async () => {
      const mockResponse = { data: { subscriptions: [mockSubscription] } };
      (mockClient.get as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);

      const result = await mcpGatewayService.getMySubscriptions();

      expect(mockClient.get).toHaveBeenCalledWith('/mcp/subscriptions');
      expect(result).toHaveLength(1);
    });

    it('subscribeTool creates a new subscription', async () => {
      const mockResponse = { data: mockSubscription };
      (mockClient.post as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);

      const result = await mcpGatewayService.subscribeTool({ toolName: 'stoa_list_apis' });

      expect(mockClient.post).toHaveBeenCalledWith('/mcp/subscriptions', { toolName: 'stoa_list_apis' });
      expect(result.toolName).toBe('stoa_list_apis');
    });

    it('unsubscribeTool removes a subscription', async () => {
      (mockClient.delete as ReturnType<typeof vi.fn>).mockResolvedValue({});

      await mcpGatewayService.unsubscribeTool('sub-123');

      expect(mockClient.delete).toHaveBeenCalledWith('/mcp/subscriptions/sub-123');
    });
  });

  describe('usage', () => {
    it('getMyUsage fetches user usage summary', async () => {
      const mockResponse = { data: mockUsageSummary };
      (mockClient.get as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);

      const result = await mcpGatewayService.getMyUsage({ period: 'week' });

      expect(mockClient.get).toHaveBeenCalledWith('/mcp/usage/me', { params: { period: 'week' } });
      expect(result.totalCalls).toBe(156);
    });

    it('getToolUsage fetches usage for a specific tool', async () => {
      const mockResponse = { data: mockUsageSummary };
      (mockClient.get as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);

      const result = await mcpGatewayService.getToolUsage('stoa_list_apis', { period: 'month' });

      expect(mockClient.get).toHaveBeenCalledWith('/mcp/usage/tools/stoa_list_apis', { params: { period: 'month' } });
      expect(result.period).toBe('week');
    });
  });

  describe('server info', () => {
    it('getServerInfo fetches MCP server info', async () => {
      const mockResponse = {
        data: {
          name: 'STOA MCP Gateway',
          version: '1.0.0',
          protocolVersion: '1.0',
          capabilities: { tools: true, resources: true, prompts: true },
        },
      };
      (mockClient.get as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);

      const result = await mcpGatewayService.getServerInfo();

      expect(mockClient.get).toHaveBeenCalledWith('/mcp/server-info');
      expect(result.name).toBe('STOA MCP Gateway');
    });

    it('healthCheck returns health status', async () => {
      const mockResponse = { data: { status: 'healthy' } };
      (mockClient.get as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);

      const result = await mcpGatewayService.healthCheck();

      expect(mockClient.get).toHaveBeenCalledWith('/health');
      expect(result.status).toBe('healthy');
    });
  });
});
