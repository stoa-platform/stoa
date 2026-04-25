/**
 * MCP Connector Catalog API Service
 *
 * Client for the connector catalog — browse templates, authorize via OAuth,
 * and manage connected MCP servers.
 */

import { apiService } from './api';
import { path } from './http';
import type { ConnectorCatalogResponse } from '../types';
import type { Schemas } from '@stoa/shared/api-types';

class MCPConnectorsService {
  /**
   * List all connector templates with connection status.
   * Endpoint: GET /v1/admin/mcp-connectors
   */
  async listConnectors(tenantId?: string, environment?: string): Promise<ConnectorCatalogResponse> {
    const params: Record<string, string> = {};
    // P1-14: != null preserves empty-string / 0 legitimate values
    if (tenantId != null) params.tenant_id = tenantId;
    if (environment != null) params.environment = environment;
    const { data } = await apiService.get('/v1/admin/mcp-connectors', {
      params: Object.keys(params).length > 0 ? params : undefined,
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
  ): Promise<Schemas['AuthorizeResponse']> {
    const { data } = await apiService.post(
      path('v1', 'admin', 'mcp-connectors', slug, 'authorize'),
      body
    );
    return data;
  }

  /**
   * Exchange OAuth code for tokens and create the server.
   * Endpoint: POST /v1/admin/mcp-connectors/callback
   */
  async handleCallback(body: {
    code: string;
    state: string;
  }): Promise<Schemas['CallbackResponse']> {
    const { data } = await apiService.post('/v1/admin/mcp-connectors/callback', body);
    return data;
  }

  /**
   * Disconnect a connector (remove the linked server).
   * Endpoint: DELETE /v1/admin/mcp-connectors/{slug}/disconnect
   */
  async disconnect(slug: string, tenantId?: string): Promise<void> {
    const params = tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : '';
    await apiService.delete(path('v1', 'admin', 'mcp-connectors', slug, 'disconnect') + params);
  }

  /**
   * Promote a connector to a target environment.
   * Endpoint: POST /v1/admin/mcp-connectors/{slug}/promote
   */
  async promote(
    slug: string,
    body: {
      target_environment: string;
      tenant_id?: string;
      confirm?: boolean;
    }
  ): Promise<Schemas['PromoteResponse']> {
    const { data } = await apiService.post(
      path('v1', 'admin', 'mcp-connectors', slug, 'promote'),
      body
    );
    return data;
  }
}

export const mcpConnectorsService = new MCPConnectorsService();
