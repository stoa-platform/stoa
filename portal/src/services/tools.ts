/**
 * STOA Developer Portal - MCP Tools Service
 *
 * Service for MCP Tool discovery and invocation via MCP Gateway.
 * This enables AI agents to discover and use platform capabilities.
 *
 * The MCP Gateway exposes platform operations as Model Context Protocol tools,
 * enabling AI agents to manage the STOA platform programmatically.
 */

import { mcpClient } from './mcpClient';
import type { MCPTool, MCPToolInvocation, MCPServerInfo } from '../types';

export interface ListToolsParams {
  tag?: string;
  tags?: string;  // Comma-separated list of tags
  category?: string;  // Filter by category (Sales, Finance, Operations, Communications)
  search?: string;  // Search in name and description
  tenant_id?: string;
  cursor?: string;
  limit?: number;
}

export interface ListToolsResponse {
  tools: MCPTool[];
  cursor?: string;
  total_count?: number;
}

export interface ToolCategory {
  name: string;
  count: number;
}

export interface ListCategoriesResponse {
  categories: ToolCategory[];
}

export interface ListTagsResponse {
  tags: string[];
  tagCounts: Record<string, number>;
}

/**
 * MCP Tools service - calls MCP Gateway at mcp.gostoa.dev
 */
export const toolsService = {
  /**
   * List all available MCP tools
   * GET /mcp/v1/tools
   *
   * @param params - Optional filters (tag, tenant_id) and pagination (cursor, limit)
   */
  async listTools(params?: ListToolsParams): Promise<ListToolsResponse> {
    const response = await mcpClient.get<ListToolsResponse>('/mcp/v1/tools', { params });
    return response.data;
  },

  /**
   * Get a single tool by name
   * GET /mcp/v1/tools/{name}
   *
   * @param name - Tool name (e.g., "tenant-acme__create-order")
   */
  async getTool(name: string): Promise<MCPTool> {
    const response = await mcpClient.get<MCPTool>(`/mcp/v1/tools/${encodeURIComponent(name)}`);
    return response.data;
  },

  /**
   * Get tools filtered by tag (category)
   * GET /mcp/v1/tools?tag={tag}
   *
   * @param tag - Tag to filter by
   */
  async getByTag(tag: string): Promise<MCPTool[]> {
    const response = await mcpClient.get<ListToolsResponse>('/mcp/v1/tools', {
      params: { tag, limit: 100 },
    });
    return response.data.tools;
  },

  /**
   * Get all available tags with counts
   * GET /mcp/v1/tools/tags
   */
  async getTags(): Promise<ListTagsResponse> {
    const response = await mcpClient.get<ListTagsResponse>('/mcp/v1/tools/tags');
    return response.data;
  },

  /**
   * Get all available categories with tool counts
   * GET /mcp/v1/tools/categories
   */
  async getCategories(): Promise<ListCategoriesResponse> {
    const response = await mcpClient.get<ListCategoriesResponse>('/mcp/v1/tools/categories');
    return response.data;
  },

  /**
   * Search tools by name and description
   * GET /mcp/v1/tools?search={query}
   *
   * @param query - Search query string
   */
  async searchTools(query: string): Promise<MCPTool[]> {
    const response = await mcpClient.get<ListToolsResponse>('/mcp/v1/tools', {
      params: { search: query, limit: 100 },
    });
    return response.data.tools;
  },

  /**
   * Get tools by category
   * GET /mcp/v1/tools?category={category}
   *
   * @param category - Category name (Sales, Finance, Operations, Communications)
   */
  async getByCategory(category: string): Promise<MCPTool[]> {
    const response = await mcpClient.get<ListToolsResponse>('/mcp/v1/tools', {
      params: { category, limit: 100 },
    });
    return response.data.tools;
  },

  /**
   * Invoke a tool (requires authentication)
   * POST /mcp/v1/tools/{name}/invoke
   *
   * This is used by AI agents to execute platform operations.
   *
   * @param name - Tool name to invoke
   * @param args - Arguments matching the tool's inputSchema
   */
  async invokeTool(name: string, args: Record<string, unknown>): Promise<MCPToolInvocation> {
    const response = await mcpClient.post<MCPToolInvocation>(
      `/mcp/v1/tools/${encodeURIComponent(name)}/invoke`,
      { arguments: args }
    );
    return response.data;
  },

  /**
   * Get MCP server info
   * GET /mcp/v1/
   *
   * Returns server name, version, and capabilities.
   */
  async getServerInfo(): Promise<MCPServerInfo> {
    const response = await mcpClient.get<MCPServerInfo>('/mcp/v1/');
    return response.data;
  },

  /**
   * Check MCP Gateway health
   * GET /health
   */
  async checkHealth(): Promise<{ status: string }> {
    const response = await mcpClient.get<{ status: string }>('/health');
    return response.data;
  },
};

export default toolsService;
