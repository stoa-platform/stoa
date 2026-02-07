/**
 * Tests for MCP Tools Service
 */

import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { toolsService } from './tools';

vi.mock('./mcpClient', () => ({
  mcpClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import { mcpClient } from './mcpClient';

const mockGet = mcpClient.get as Mock;
const mockPost = mcpClient.post as Mock;

describe('toolsService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('listTools', () => {
    it('should call GET /mcp/v1/tools', async () => {
      const mockData = { tools: [{ name: 'tool-1' }], total_count: 1 };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const result = await toolsService.listTools();

      expect(mockGet).toHaveBeenCalledWith('/mcp/v1/tools', { params: undefined });
      expect(result.tools).toHaveLength(1);
    });

    it('should pass filter params', async () => {
      mockGet.mockResolvedValueOnce({ data: { tools: [], total_count: 0 } });

      await toolsService.listTools({ tag: 'finance', limit: 10 });

      expect(mockGet).toHaveBeenCalledWith('/mcp/v1/tools', {
        params: { tag: 'finance', limit: 10 },
      });
    });
  });

  describe('getTool', () => {
    it('should call GET /mcp/v1/tools/:name with encoded name', async () => {
      mockGet.mockResolvedValueOnce({ data: { name: 'tenant-acme__create-order' } });

      const result = await toolsService.getTool('tenant-acme__create-order');

      expect(mockGet).toHaveBeenCalledWith('/mcp/v1/tools/tenant-acme__create-order');
      expect(result.name).toBe('tenant-acme__create-order');
    });
  });

  describe('getByTag', () => {
    it('should filter tools by tag', async () => {
      mockGet.mockResolvedValueOnce({ data: { tools: [{ name: 't1' }] } });

      const result = await toolsService.getByTag('sales');

      expect(mockGet).toHaveBeenCalledWith('/mcp/v1/tools', {
        params: { tag: 'sales', limit: 100 },
      });
      expect(result).toEqual([{ name: 't1' }]);
    });
  });

  describe('getTags', () => {
    it('should call GET /mcp/v1/tools/tags', async () => {
      const mockData = { tags: ['sales', 'finance'], tagCounts: { sales: 5, finance: 3 } };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const result = await toolsService.getTags();

      expect(mockGet).toHaveBeenCalledWith('/mcp/v1/tools/tags');
      expect(result.tags).toEqual(['sales', 'finance']);
    });
  });

  describe('getCategories', () => {
    it('should call GET /mcp/v1/tools/categories', async () => {
      mockGet.mockResolvedValueOnce({
        data: { categories: [{ name: 'Sales', count: 5 }] },
      });

      const result = await toolsService.getCategories();

      expect(result.categories).toHaveLength(1);
    });
  });

  describe('searchTools', () => {
    it('should search by query', async () => {
      mockGet.mockResolvedValueOnce({ data: { tools: [{ name: 'create-order' }] } });

      const result = await toolsService.searchTools('order');

      expect(mockGet).toHaveBeenCalledWith('/mcp/v1/tools', {
        params: { search: 'order', limit: 100 },
      });
      expect(result).toEqual([{ name: 'create-order' }]);
    });
  });

  describe('getByCategory', () => {
    it('should filter by category', async () => {
      mockGet.mockResolvedValueOnce({ data: { tools: [{ name: 't1' }] } });

      const result = await toolsService.getByCategory('Finance');

      expect(mockGet).toHaveBeenCalledWith('/mcp/v1/tools', {
        params: { category: 'Finance', limit: 100 },
      });
      expect(result).toEqual([{ name: 't1' }]);
    });
  });

  describe('invokeTool', () => {
    it('should call POST /mcp/v1/tools/:name/invoke', async () => {
      const mockResult = { toolName: 'create-order', result: { orderId: '123' } };
      mockPost.mockResolvedValueOnce({ data: mockResult });

      const result = await toolsService.invokeTool('create-order', { customerId: 'c-1' });

      expect(mockPost).toHaveBeenCalledWith('/mcp/v1/tools/create-order/invoke', {
        arguments: { customerId: 'c-1' },
      });
      expect(result.toolName).toBe('create-order');
    });
  });

  describe('getServerInfo', () => {
    it('should call GET /mcp/v1/', async () => {
      const mockInfo = { name: 'stoa-mcp', version: '1.0.0' };
      mockGet.mockResolvedValueOnce({ data: mockInfo });

      const result = await toolsService.getServerInfo();

      expect(mockGet).toHaveBeenCalledWith('/mcp/v1/');
      expect(result.name).toBe('stoa-mcp');
    });
  });

  describe('checkHealth', () => {
    it('should call GET /health', async () => {
      mockGet.mockResolvedValueOnce({ data: { status: 'ok' } });

      const result = await toolsService.checkHealth();

      expect(mockGet).toHaveBeenCalledWith('/health');
      expect(result.status).toBe('ok');
    });
  });
});
