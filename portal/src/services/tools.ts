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
  tenant_id?: string;
  cursor?: string;
  limit?: number;
}

export interface ListToolsResponse {
  tools: MCPTool[];
  cursor?: string;
}

/**
 * MCP Tools service - calls MCP Gateway at mcp.stoa.cab-i.com
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
   * Get all available tags (categories)
   * GET /mcp/v1/tools/tags
   */
  async getTags(): Promise<string[]> {
    const response = await mcpClient.get<{ tags: string[] }>('/mcp/v1/tools/tags');
    return response.data.tags;
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
