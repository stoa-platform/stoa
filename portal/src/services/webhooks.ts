/**
 * STOA Developer Portal - Webhook Service (CAB-315)
 *
 * Service for managing tenant webhook configurations.
 * Uses Control-Plane API endpoints.
 */

import { apiClient } from './api';
import type {
  TenantWebhook,
  WebhookCreate,
  WebhookUpdate,
  WebhookDelivery,
  WebhookTestResponse,
} from '../types';

// ============ Types ============

export interface WebhookListResponse {
  items: TenantWebhook[];
  total: number;
}

export interface WebhookDeliveryListResponse {
  items: WebhookDelivery[];
  total: number;
}

export interface WebhookEventTypeInfo {
  event: string;
  description: string;
  payload_example: Record<string, unknown>;
}

export interface EventTypesResponse {
  events: WebhookEventTypeInfo[];
}

// ============ Service ============

export const webhooksService = {
  /**
   * Get available event types
   * GET /tenants/{tenantId}/webhooks/events
   */
  getEventTypes: async (tenantId: string): Promise<EventTypesResponse> => {
    const response = await apiClient.get<EventTypesResponse>(
      `/tenants/${tenantId}/webhooks/events`
    );
    return response.data;
  },

  /**
   * List webhooks for a tenant
   * GET /tenants/{tenantId}/webhooks
   */
  listWebhooks: async (
    tenantId: string,
    enabledOnly?: boolean
  ): Promise<WebhookListResponse> => {
    const response = await apiClient.get<WebhookListResponse>(
      `/tenants/${tenantId}/webhooks`,
      {
        params: { enabled_only: enabledOnly },
      }
    );
    return response.data;
  },

  /**
   * Get a specific webhook
   * GET /tenants/{tenantId}/webhooks/{webhookId}
   */
  getWebhook: async (
    tenantId: string,
    webhookId: string
  ): Promise<TenantWebhook> => {
    const response = await apiClient.get<TenantWebhook>(
      `/tenants/${tenantId}/webhooks/${webhookId}`
    );
    return response.data;
  },

  /**
   * Create a new webhook
   * POST /tenants/{tenantId}/webhooks
   */
  createWebhook: async (
    tenantId: string,
    data: WebhookCreate
  ): Promise<TenantWebhook> => {
    const response = await apiClient.post<TenantWebhook>(
      `/tenants/${tenantId}/webhooks`,
      data
    );
    return response.data;
  },

  /**
   * Update a webhook
   * PATCH /tenants/{tenantId}/webhooks/{webhookId}
   */
  updateWebhook: async (
    tenantId: string,
    webhookId: string,
    data: WebhookUpdate
  ): Promise<TenantWebhook> => {
    const response = await apiClient.patch<TenantWebhook>(
      `/tenants/${tenantId}/webhooks/${webhookId}`,
      data
    );
    return response.data;
  },

  /**
   * Delete a webhook
   * DELETE /tenants/{tenantId}/webhooks/{webhookId}
   */
  deleteWebhook: async (
    tenantId: string,
    webhookId: string
  ): Promise<void> => {
    await apiClient.delete(`/tenants/${tenantId}/webhooks/${webhookId}`);
  },

  /**
   * Test a webhook
   * POST /tenants/{tenantId}/webhooks/{webhookId}/test
   */
  testWebhook: async (
    tenantId: string,
    webhookId: string,
    eventType?: string
  ): Promise<WebhookTestResponse> => {
    const response = await apiClient.post<WebhookTestResponse>(
      `/tenants/${tenantId}/webhooks/${webhookId}/test`,
      { event_type: eventType || 'subscription.created' }
    );
    return response.data;
  },

  /**
   * Get delivery history for a webhook
   * GET /tenants/{tenantId}/webhooks/{webhookId}/deliveries
   */
  getDeliveries: async (
    tenantId: string,
    webhookId: string,
    limit?: number
  ): Promise<WebhookDeliveryListResponse> => {
    const response = await apiClient.get<WebhookDeliveryListResponse>(
      `/tenants/${tenantId}/webhooks/${webhookId}/deliveries`,
      {
        params: { limit: limit || 50 },
      }
    );
    return response.data;
  },

  /**
   * Retry a failed delivery
   * POST /tenants/{tenantId}/webhooks/{webhookId}/deliveries/{deliveryId}/retry
   */
  retryDelivery: async (
    tenantId: string,
    webhookId: string,
    deliveryId: string
  ): Promise<WebhookDelivery> => {
    const response = await apiClient.post<WebhookDelivery>(
      `/tenants/${tenantId}/webhooks/${webhookId}/deliveries/${deliveryId}/retry`
    );
    return response.data;
  },
};

export default webhooksService;
