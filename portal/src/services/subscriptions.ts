// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
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
  KeyRotationRequest,
  KeyRotationResponse,
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

export interface RevealKeyResponse {
  api_key: string;
  expires_in: number; // Visibility window in seconds
}

export interface ToggleTotpResponse {
  subscription_id: string;
  totp_required: boolean;
  message: string;
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

  /**
   * Reveal API key (requires TOTP if enabled)
   * POST /mcp/v1/subscriptions/{id}/reveal-key
   *
   * ⚠️ Requires 2FA authentication if TOTP is enabled for the subscription.
   * Key is shown with a visibility timer (default 30 seconds).
   */
  revealApiKey: async (id: string, totpCode?: string): Promise<RevealKeyResponse> => {
    const response = await mcpClient.post<RevealKeyResponse>(
      `/mcp/v1/subscriptions/${id}/reveal-key`,
      totpCode ? { totp_code: totpCode } : {}
    );
    return response.data;
  },

  /**
   * Toggle TOTP requirement for key reveal
   * PATCH /mcp/v1/subscriptions/{id}/totp?enabled={true|false}
   */
  toggleTotpRequirement: async (id: string, enabled: boolean): Promise<ToggleTotpResponse> => {
    const response = await mcpClient.patch<ToggleTotpResponse>(
      `/mcp/v1/subscriptions/${id}/totp`,
      null,
      { params: { enabled } }
    );
    return response.data;
  },

  // ============ Key Rotation (CAB-314) ============

  /**
   * Rotate API key with grace period
   * POST /mcp/v1/subscriptions/{id}/rotate-key
   *
   * The old key remains valid for the grace period (default 24h).
   * After the grace period, only the new key is accepted.
   *
   * ⚠️ The new API key is returned only ONCE! Store/display immediately.
   */
  rotateApiKey: async (id: string, request?: KeyRotationRequest): Promise<KeyRotationResponse> => {
    const response = await mcpClient.post<KeyRotationResponse>(
      `/mcp/v1/subscriptions/${id}/rotate-key`,
      request || { grace_period_hours: 24 }
    );
    return response.data;
  },

  /**
   * Get subscription with rotation info
   * GET /mcp/v1/subscriptions/{id}/rotation-info
   *
   * Returns subscription details with grace period status.
   */
  getRotationInfo: async (id: string): Promise<MCPSubscription> => {
    const response = await mcpClient.get<MCPSubscription>(`/mcp/v1/subscriptions/${id}/rotation-info`);
    return response.data;
  },
};

export default subscriptionsService;
