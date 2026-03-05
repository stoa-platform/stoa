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
  certificate_fingerprint?: string;
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
  api_key_prefix: string | null;
  oauth_client_id: string | null;
  status: APISubscriptionStatus;
  status_reason: string | null;
  created_at: string;
  updated_at: string;
  approved_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
  approved_by: string | null;
  revoked_by: string | null;
  provisioning_status: string | null;
  provisioning_error: string | null;
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
  application_id?: string; // Server-side filter when backend supports it
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
    apiKeyPrefix: response.api_key_prefix || undefined,
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
   * Returns the subscription (uses OAuth2, no API key generated).
   */
  createSubscription: async (
    data: CreateAPISubscriptionRequest
  ): Promise<APISubscriptionResponse> => {
    const response = await apiClient.post<APISubscriptionResponse>('/v1/subscriptions', data);
    return response.data;
  },

  /**
   * List my subscriptions
   * GET /v1/subscriptions/my
   */
  listMySubscriptions: async (
    params?: ListAPISubscriptionsParams
  ): Promise<APISubscriptionListResponse> => {
    const response = await apiClient.get<APISubscriptionListResponse>('/v1/subscriptions/my', {
      params: {
        page: params?.page || 1,
        page_size: params?.page_size || 20,
        status: params?.status,
        application_id: params?.application_id, // Server-side filter when backend supports it
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

  // ============ Tenant Admin: Approval Queue (CAB-1121) ============

  /**
   * List pending subscriptions for a tenant (tenant admin only)
   * GET /v1/subscriptions/tenant/{tenant_id}/pending
   */
  listPendingForTenant: async (
    tenantId: string,
    params?: { page?: number; page_size?: number }
  ): Promise<APISubscriptionListResponse> => {
    const response = await apiClient.get<APISubscriptionListResponse>(
      `/v1/subscriptions/tenant/${tenantId}/pending`,
      {
        params: {
          page: params?.page || 1,
          page_size: params?.page_size || 20,
        },
      }
    );
    return response.data;
  },

  /**
   * Approve a pending subscription (tenant admin only)
   * POST /v1/subscriptions/{id}/approve
   */
  approveSubscription: async (
    subscriptionId: string,
    expiresAt?: string
  ): Promise<APISubscriptionResponse> => {
    const response = await apiClient.post<APISubscriptionResponse>(
      `/v1/subscriptions/${subscriptionId}/approve`,
      { expires_at: expiresAt || null }
    );
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
