/**
 * External MCP Servers API Service
 *
 * Client for managing external MCP servers (Linear, GitHub, Slack, etc.)
 * via the Control-Plane-API.
 */

import { apiService } from './api';
import type {
  ExternalMCPServer,
  ExternalMCPServerDetail,
  ExternalMCPServerCreate,
  ExternalMCPServerUpdate,
  ExternalMCPServerListResponse,
  ExternalMCPServerTool,
  TestConnectionResponse,
  SyncToolsResponse,
} from '../types';

/**
 * External MCP Servers Service
 *
 * Provides CRUD operations for external MCP servers and their tools.
 */
class ExternalMCPServersService {
  // ==========================================================================
  // Server CRUD Operations
  // ==========================================================================

  /**
   * List all external MCP servers.
   * Endpoint: GET /v1/admin/external-mcp-servers
   */
  async listServers(params?: {
    enabled_only?: boolean;
    page?: number;
    page_size?: number;
  }): Promise<ExternalMCPServerListResponse> {
    const { data } = await apiService.get('/v1/admin/external-mcp-servers', {
      params: {
        enabled_only: params?.enabled_only,
        page: params?.page || 1,
        page_size: params?.page_size || 20,
      },
    });
    return data;
  }

  /**
   * Get a specific external MCP server with tools.
   * Endpoint: GET /v1/admin/external-mcp-servers/{id}
   */
  async getServer(serverId: string): Promise<ExternalMCPServerDetail> {
    const { data } = await apiService.get(`/v1/admin/external-mcp-servers/${serverId}`);
    return data;
  }

  /**
   * Create a new external MCP server.
   * Endpoint: POST /v1/admin/external-mcp-servers
   */
  async createServer(server: ExternalMCPServerCreate): Promise<ExternalMCPServer> {
    const { data } = await apiService.post('/v1/admin/external-mcp-servers', server);
    return data;
  }

  /**
   * Update an external MCP server.
   * Endpoint: PUT /v1/admin/external-mcp-servers/{id}
   */
  async updateServer(serverId: string, update: ExternalMCPServerUpdate): Promise<ExternalMCPServer> {
    const { data } = await apiService.put(`/v1/admin/external-mcp-servers/${serverId}`, update);
    return data;
  }

  /**
   * Delete an external MCP server.
   * Endpoint: DELETE /v1/admin/external-mcp-servers/{id}
   */
  async deleteServer(serverId: string): Promise<void> {
    await apiService.delete(`/v1/admin/external-mcp-servers/${serverId}`);
  }

  // ==========================================================================
  // Server Actions
  // ==========================================================================

  /**
   * Test connection to an external MCP server.
   * Endpoint: POST /v1/admin/external-mcp-servers/{id}/test-connection
   */
  async testConnection(serverId: string): Promise<TestConnectionResponse> {
    const { data } = await apiService.post(`/v1/admin/external-mcp-servers/${serverId}/test-connection`);
    return data;
  }

  /**
   * Sync tools from an external MCP server.
   * Endpoint: POST /v1/admin/external-mcp-servers/{id}/sync-tools
   */
  async syncTools(serverId: string): Promise<SyncToolsResponse> {
    const { data } = await apiService.post(`/v1/admin/external-mcp-servers/${serverId}/sync-tools`);
    return data;
  }

  // ==========================================================================
  // Tool Operations
  // ==========================================================================

  /**
   * Enable or disable a tool.
   * Endpoint: PATCH /v1/admin/external-mcp-servers/{serverId}/tools/{toolId}
   */
  async updateTool(
    serverId: string,
    toolId: string,
    update: { enabled: boolean }
  ): Promise<ExternalMCPServerTool> {
    const { data } = await apiService.patch(
      `/v1/admin/external-mcp-servers/${serverId}/tools/${toolId}`,
      update
    );
    return data;
  }
}

// Export singleton instance
export const externalMcpServersService = new ExternalMCPServersService();
