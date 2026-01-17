/**
 * STOA Developer Portal - API Subscriptions Service
 *
 * Service for subscribing applications to APIs (REST APIs managed by Control-Plane).
 * Uses Control-Plane API endpoints (/v1/subscriptions).
 *
 * Note: This is separate from MCP subscriptions which are handled by mcpClient.
 *
 * Reference: CAB-483 - API subscription flow for Developer Portal
 */

import { apiClient } from './api';
import type { APISubscription } from '../types';

// ============ Types ============

export type APISubscriptionStatus = 'pending' | 'active' | 'suspended' | 'revoked' | 'expired';

export interface CreateAPISubscriptionRequest {
  application_id: string;
  application_name: string;
  api_id: string;
  api_name: string;
  api_version: string;
  tenant_id: string;
  plan_id?: string;
  plan_name?: string;
}

export interface APISubscriptionResponse {
  id: string;
  application_id: string;
  application_name: string;
  subscriber_id: string;
  subscriber_email: string;
  api_id: string;
  api_name: string;
  api_version: string;
  tenant_id: string;
  plan_id: string | null;
  plan_name: string | null;
  api_key_prefix: string;
  status: APISubscriptionStatus;
  status_reason: string | null;
  created_at: string;
  updated_at: string;
  approved_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
  approved_by: string | null;
  revoked_by: string | null;
}

export interface APIKeyResponse {
  subscription_id: string;
  api_key: string; // Full API key - shown only once!
  api_key_prefix: string;
  expires_at: string | null;
}

export interface APISubscriptionListResponse {
  items: APISubscriptionResponse[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ListAPISubscriptionsParams {
  page?: number;
  page_size?: number;
  status?: APISubscriptionStatus;
}

export interface KeyRotationRequest {
  grace_period_hours?: number; // Default 24, max 168
}

export interface KeyRotationResponse {
  subscription_id: string;
  new_api_key: string;
  new_api_key_prefix: string;
  old_key_expires_at: string;
  grace_period_hours: number;
  rotation_count: number;
}

// ============ Helper Functions ============

function transformToAPISubscription(response: APISubscriptionResponse): APISubscription {
  return {
    id: response.id,
    applicationId: response.application_id,
    applicationName: response.application_name,
    apiId: response.api_id,
    apiName: response.api_name,
    apiVersion: response.api_version,
    tenantId: response.tenant_id,
    planId: response.plan_id || undefined,
    planName: response.plan_name || undefined,
    status: response.status,
    apiKeyPrefix: response.api_key_prefix,
    createdAt: response.created_at,
    expiresAt: response.expires_at || undefined,
  };
}

// ============ Service ============

export const apiSubscriptionsService = {
  /**
   * Create a new API subscription
   * POST /v1/subscriptions
   *
   * Returns the API key (shown only once!)
   */
  createSubscription: async (data: CreateAPISubscriptionRequest): Promise<APIKeyResponse> => {
    const response = await apiClient.post<APIKeyResponse>('/v1/subscriptions', data);
    return response.data;
  },

  /**
   * List my subscriptions
   * GET /v1/subscriptions/my
   */
  listMySubscriptions: async (params?: ListAPISubscriptionsParams): Promise<APISubscriptionListResponse> => {
    const response = await apiClient.get<APISubscriptionListResponse>('/v1/subscriptions/my', {
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
   * GET /v1/subscriptions/{id}
   */
  getSubscription: async (id: string): Promise<APISubscriptionResponse> => {
    const response = await apiClient.get<APISubscriptionResponse>(`/v1/subscriptions/${id}`);
    return response.data;
  },

  /**
   * Cancel my subscription
   * DELETE /v1/subscriptions/{id}
   */
  cancelSubscription: async (id: string): Promise<void> => {
    await apiClient.delete(`/v1/subscriptions/${id}`);
  },

  /**
   * Rotate API key with grace period
   * POST /v1/subscriptions/{id}/rotate-key
   *
   * Returns the new API key (shown only once!)
   */
  rotateKey: async (id: string, request?: KeyRotationRequest): Promise<KeyRotationResponse> => {
    const response = await apiClient.post<KeyRotationResponse>(
      `/v1/subscriptions/${id}/rotate-key`,
      request || { grace_period_hours: 24 }
    );
    return response.data;
  },

  /**
   * Get subscription with rotation info
   * GET /v1/subscriptions/{id}/rotation-info
   */
  getRotationInfo: async (id: string): Promise<APISubscriptionResponse & {
    previous_key_expires_at: string | null;
    last_rotated_at: string | null;
    rotation_count: number;
    has_active_grace_period: boolean;
  }> => {
    const response = await apiClient.get(`/v1/subscriptions/${id}/rotation-info`);
    return response.data;
  },

  // ============ Helper Methods ============

  /**
   * Get my subscriptions as APISubscription type (for UI compatibility)
   */
  getMySubscriptionsFormatted: async (): Promise<APISubscription[]> => {
    const response = await apiSubscriptionsService.listMySubscriptions();
    return response.items.map(transformToAPISubscription);
  },
};

export default apiSubscriptionsService;
