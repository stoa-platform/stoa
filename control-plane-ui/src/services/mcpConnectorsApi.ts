/**
 * MCP Connector Catalog API Service
 *
 * Client for the connector catalog — browse templates, authorize via OAuth,
 * and manage connected MCP servers.
 */

import { apiService } from './api';
import type { ConnectorCatalogResponse, AuthorizeResponse, CallbackResponse } from '../types';

class MCPConnectorsService {
  /**
   * List all connector templates with connection status.
   * Endpoint: GET /v1/admin/mcp-connectors
   */
  async listConnectors(tenantId?: string): Promise<ConnectorCatalogResponse> {
    const { data } = await apiService.get('/v1/admin/mcp-connectors', {
      params: tenantId ? { tenant_id: tenantId } : undefined,
    });
    return data;
  }

  /**
   * Initiate OAuth authorization for a connector.
   * Endpoint: POST /v1/admin/mcp-connectors/{slug}/authorize
   */
  async authorize(
    slug: string,
    body: {
      tenant_id?: string;
      redirect_after?: string;
      client_id?: string;
      client_secret?: string;
    }
  ): Promise<AuthorizeResponse> {
    const { data } = await apiService.post(`/v1/admin/mcp-connectors/${slug}/authorize`, body);
    return data;
  }

  /**
   * Exchange OAuth code for tokens and create the server.
   * Endpoint: POST /v1/admin/mcp-connectors/callback
   */
  async handleCallback(body: { code: string; state: string }): Promise<CallbackResponse> {
    const { data } = await apiService.post('/v1/admin/mcp-connectors/callback', body);
    return data;
  }

  /**
   * Disconnect a connector (remove the linked server).
   * Endpoint: DELETE /v1/admin/mcp-connectors/{slug}/disconnect
   */
  async disconnect(slug: string, tenantId?: string): Promise<void> {
    const params = tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : '';
    await apiService.delete(`/v1/admin/mcp-connectors/${slug}/disconnect${params}`);
  }
}

export const mcpConnectorsService = new MCPConnectorsService();
