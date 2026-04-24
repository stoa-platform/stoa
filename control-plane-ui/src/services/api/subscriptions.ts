import { httpClient, path } from '../http';
import type { Schemas } from '@stoa/shared/api-types';
import type { Subscription, SubscriptionListResponse, SubscriptionStats } from '../../types';

export const subscriptionsClient = {
  async list(
    tenantId: string,
    status?: string,
    page = 1,
    pageSize = 20,
    environment?: string
  ): Promise<SubscriptionListResponse> {
    const { data } = await httpClient.get(path('v1', 'subscriptions', 'tenant', tenantId), {
      params: { status, page, page_size: pageSize, environment },
    });
    return data;
  },

  async listPending(tenantId: string, page = 1, pageSize = 20): Promise<SubscriptionListResponse> {
    const { data } = await httpClient.get(
      path('v1', 'subscriptions', 'tenant', tenantId, 'pending'),
      {
        params: { page, page_size: pageSize },
      }
    );
    return data;
  },

  async getStats(tenantId: string): Promise<SubscriptionStats> {
    const { data } = await httpClient.get(path('v1', 'subscriptions', 'tenant', tenantId, 'stats'));
    return data;
  },

  async approve(id: string, expiresAt?: string): Promise<Subscription> {
    const { data } = await httpClient.post(path('v1', 'subscriptions', id, 'approve'), {
      expires_at: expiresAt || null,
    });
    return data;
  },

  async reject(id: string, reason: string): Promise<Subscription> {
    const { data } = await httpClient.post(path('v1', 'subscriptions', id, 'reject'), { reason });
    return data;
  },

  async bulkAction(
    payload: Schemas['BulkSubscriptionAction']
  ): Promise<Schemas['BulkActionResult']> {
    const { data } = await httpClient.post('/v1/subscriptions/bulk', payload);
    return data;
  },
};
