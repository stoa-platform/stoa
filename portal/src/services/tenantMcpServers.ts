/**
 * Tenant MCP Servers API Service
 *
 * API client for tenant-scoped MCP server self-service (CAB-1319).
 * Endpoints: /v1/tenants/{tenant_id}/mcp-servers
 */

import { apiClient } from './api';

// ============ Types ============

export interface TenantMCPServerTool {
  id: string;
  name: string;
  namespaced_name: string;
  display_name: string | null;
  description: string | null;
  input_schema: Record<string, unknown> | null;
  enabled: boolean;
  synced_at: string;
}

export interface TenantMCPServer {
  id: string;
  name: string;
  display_name: string;
  description: string | null;
  icon: string | null;
  base_url: string;
  transport: 'sse' | 'http' | 'websocket';
  auth_type: 'none' | 'api_key' | 'bearer_token' | 'oauth2';
  has_credentials: boolean;
  tool_prefix: string | null;
  enabled: boolean;
  health_status: 'unknown' | 'healthy' | 'degraded' | 'unhealthy';
  last_health_check: string | null;
  last_sync_at: string | null;
  sync_error: string | null;
  tools_count: number;
  created_at: string;
  updated_at: string;
}

export interface TenantMCPServerDetail extends TenantMCPServer {
  tools: TenantMCPServerTool[];
}

export interface TenantMCPServerListResponse {
  servers: TenantMCPServer[];
  total_count: number;
  page: number;
  page_size: number;
}

export interface TenantMCPServerCreatePayload {
  display_name: string;
  description?: string;
  icon?: string;
  base_url: string;
  transport?: 'sse' | 'http' | 'websocket';
  auth_type?: 'none' | 'api_key' | 'bearer_token' | 'oauth2';
  credentials?: {
    api_key?: string;
    bearer_token?: string;
    oauth2?: {
      client_id: string;
      client_secret: string;
      token_url: string;
      scope?: string;
    };
  };
  tool_prefix?: string;
}

export interface TenantMCPServerUpdatePayload {
  display_name?: string;
  description?: string;
  icon?: string;
  base_url?: string;
  transport?: 'sse' | 'http' | 'websocket';
  auth_type?: 'none' | 'api_key' | 'bearer_token' | 'oauth2';
  credentials?: {
    api_key?: string;
    bearer_token?: string;
    oauth2?: {
      client_id: string;
      client_secret: string;
      token_url: string;
      scope?: string;
    };
  };
  tool_prefix?: string;
  enabled?: boolean;
}

export interface TestConnectionResponse {
  success: boolean;
  latency_ms: number | null;
  error: string | null;
  server_info: Record<string, unknown> | null;
  tools_discovered: number | null;
}

export interface SyncToolsResponse {
  synced_count: number;
  removed_count: number;
  tools: TenantMCPServerTool[];
}

// ============ Service ============

function basePath(tenantId: string) {
  return `/v1/tenants/${tenantId}/mcp-servers`;
}

export const tenantMcpServersService = {
  async list(
    tenantId: string,
    params?: { page?: number; page_size?: number; enabled_only?: boolean }
  ): Promise<TenantMCPServerListResponse> {
    const response = await apiClient.get<TenantMCPServerListResponse>(basePath(tenantId), {
      params,
    });
    return response.data;
  },

  async get(tenantId: string, serverId: string): Promise<TenantMCPServerDetail> {
    const response = await apiClient.get<TenantMCPServerDetail>(
      `${basePath(tenantId)}/${serverId}`
    );
    return response.data;
  },

  async create(
    tenantId: string,
    data: TenantMCPServerCreatePayload
  ): Promise<TenantMCPServerDetail> {
    const response = await apiClient.post<TenantMCPServerDetail>(basePath(tenantId), data);
    return response.data;
  },

  async update(
    tenantId: string,
    serverId: string,
    data: TenantMCPServerUpdatePayload
  ): Promise<TenantMCPServerDetail> {
    const response = await apiClient.put<TenantMCPServerDetail>(
      `${basePath(tenantId)}/${serverId}`,
      data
    );
    return response.data;
  },

  async delete(tenantId: string, serverId: string): Promise<void> {
    await apiClient.delete(`${basePath(tenantId)}/${serverId}`);
  },

  async testConnection(tenantId: string, serverId: string): Promise<TestConnectionResponse> {
    const response = await apiClient.post<TestConnectionResponse>(
      `${basePath(tenantId)}/${serverId}/test-connection`
    );
    return response.data;
  },

  async syncTools(tenantId: string, serverId: string): Promise<SyncToolsResponse> {
    const response = await apiClient.post<SyncToolsResponse>(
      `${basePath(tenantId)}/${serverId}/sync-tools`
    );
    return response.data;
  },

  async toggleTool(
    tenantId: string,
    serverId: string,
    toolId: string,
    enabled: boolean
  ): Promise<TenantMCPServerTool> {
    const response = await apiClient.patch<TenantMCPServerTool>(
      `${basePath(tenantId)}/${serverId}/tools/${toolId}`,
      { enabled }
    );
    return response.data;
  },
};

export default tenantMcpServersService;
