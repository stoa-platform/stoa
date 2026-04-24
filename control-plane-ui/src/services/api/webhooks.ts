import { httpClient, path } from '../http';
import type { Schemas } from '@stoa/shared/api-types';
import type { TenantWebhook, WebhookListResponse, WebhookDeliveryListResponse } from '../../types';

export const webhooksClient = {
  async list(tenantId: string): Promise<WebhookListResponse> {
    const { data } = await httpClient.get(path('v1', 'tenants', tenantId, 'webhooks'));
    return data;
  },

  async get(tenantId: string, webhookId: string): Promise<TenantWebhook> {
    const { data } = await httpClient.get(path('v1', 'tenants', tenantId, 'webhooks', webhookId));
    return data;
  },

  async create(tenantId: string, payload: Schemas['WebhookCreate']): Promise<TenantWebhook> {
    const { data } = await httpClient.post(path('v1', 'tenants', tenantId, 'webhooks'), payload);
    return data;
  },

  async update(
    tenantId: string,
    webhookId: string,
    payload: Schemas['WebhookUpdate']
  ): Promise<TenantWebhook> {
    const { data } = await httpClient.patch(
      path('v1', 'tenants', tenantId, 'webhooks', webhookId),
      payload
    );
    return data;
  },

  async remove(tenantId: string, webhookId: string): Promise<void> {
    await httpClient.delete(path('v1', 'tenants', tenantId, 'webhooks', webhookId));
  },

  async test(tenantId: string, webhookId: string): Promise<Schemas['WebhookTestResponse']> {
    const { data } = await httpClient.post(
      path('v1', 'tenants', tenantId, 'webhooks', webhookId, 'test'),
      {
        event_type: 'subscription.created',
      }
    );
    return data;
  },

  async listDeliveries(
    tenantId: string,
    webhookId: string,
    limit = 50
  ): Promise<WebhookDeliveryListResponse> {
    const { data } = await httpClient.get(
      path('v1', 'tenants', tenantId, 'webhooks', webhookId, 'deliveries'),
      { params: { limit } }
    );
    return data;
  },

  async retryDelivery(tenantId: string, webhookId: string, deliveryId: string): Promise<void> {
    await httpClient.post(
      path('v1', 'tenants', tenantId, 'webhooks', webhookId, 'deliveries', deliveryId, 'retry')
    );
  },
};
