/**
 * STOA Developer Portal - MCP Subscriptions Service
 *
 * ⚠️ IMPORTANT: MCP Subscriptions are on MCP Gateway, NOT Control-Plane API!
 *
 * Reference: Linear CAB-247
 */

import { mcpClient } from './mcpClient';
import type {
  MCPSubscription,
  MCPSubscriptionCreate,
  MCPSubscriptionConfig,
} from '../types';

// ============ Types ============

export interface ListSubscriptionsParams {
  page?: number;
  page_size?: number;
  status?: 'active' | 'expired' | 'revoked';
}

export interface SubscriptionsListResponse {
  subscriptions: MCPSubscription[];
  total: number;
  page: number;
  page_size: number;
}

export interface CreateSubscriptionResponse {
  subscription: MCPSubscription;
  api_key: string; // ⚠️ Shown only ONCE!
}

// ============ Service ============

export const subscriptionsService = {
  /**
   * List my MCP subscriptions
   * GET /mcp/v1/subscriptions
   */
  listSubscriptions: async (params?: ListSubscriptionsParams): Promise<SubscriptionsListResponse> => {
    const response = await mcpClient.get<SubscriptionsListResponse>('/mcp/v1/subscriptions', {
      params: {
        page: params?.page || 1,
        page_size: params?.page_size || 20,
        status: params?.status,
      },
    });
    return response.data;
  },

  /**
   * Get subscription details
   * GET /mcp/v1/subscriptions/{id}
   */
  getSubscription: async (id: string): Promise<MCPSubscription> => {
    const response = await mcpClient.get<MCPSubscription>(`/mcp/v1/subscriptions/${id}`);
    return response.data;
  },

  /**
   * Create a new subscription
   * POST /mcp/v1/subscriptions
   *
   * ⚠️ The API key is returned only ONCE! Store/display immediately.
   */
  createSubscription: async (data: MCPSubscriptionCreate): Promise<CreateSubscriptionResponse> => {
    const response = await mcpClient.post<CreateSubscriptionResponse>('/mcp/v1/subscriptions', data);
    return response.data;
  },

  /**
   * Revoke a subscription
   * DELETE /mcp/v1/subscriptions/{id}
   */
  revokeSubscription: async (id: string): Promise<void> => {
    await mcpClient.delete(`/mcp/v1/subscriptions/${id}`);
  },

  /**
   * Regenerate API key for a subscription
   * POST /mcp/v1/subscriptions/{id}/regenerate
   *
   * ⚠️ Old key is immediately invalidated!
   */
  regenerateApiKey: async (id: string): Promise<{ api_key: string }> => {
    const response = await mcpClient.post<{ api_key: string }>(`/mcp/v1/subscriptions/${id}/regenerate`);
    return response.data;
  },

  /**
   * Get claude_desktop_config.json export
   * GET /mcp/v1/subscriptions/{id}/config
   */
  getConfigExport: async (id: string): Promise<MCPSubscriptionConfig> => {
    const response = await mcpClient.get<MCPSubscriptionConfig>(`/mcp/v1/subscriptions/${id}/config`);
    return response.data;
  },

  /**
   * Get subscriptions for current user (convenience wrapper)
   */
  getMySubscriptions: async (): Promise<MCPSubscription[]> => {
    const response = await subscriptionsService.listSubscriptions();
    return response.subscriptions;
  },
};

export default subscriptionsService;
