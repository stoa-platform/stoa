/**
 * STOA Developer Portal - Subscriptions Service
 *
 * Service for managing API subscriptions.
 */

import { apiClient } from './api';
import type { APISubscription, PaginatedResponse } from '../types';

export interface ListSubscriptionsParams {
  page?: number;
  pageSize?: number;
  applicationId?: string;
  apiId?: string;
  status?: 'pending' | 'active' | 'suspended' | 'cancelled';
}

export interface SubscribeToAPIRequest {
  applicationId: string;
  apiId: string;
  plan: 'free' | 'basic' | 'premium' | 'enterprise';
}

export const subscriptionsService = {
  /**
   * List user's API subscriptions
   */
  listSubscriptions: async (params?: ListSubscriptionsParams): Promise<PaginatedResponse<APISubscription>> => {
    const response = await apiClient.get<PaginatedResponse<APISubscription>>('/v1/subscriptions', {
      params: {
        page: params?.page || 1,
        page_size: params?.pageSize || 20,
        application_id: params?.applicationId,
        api_id: params?.apiId,
        status: params?.status,
      },
    });
    return response.data;
  },

  /**
   * Get a single subscription by ID
   */
  getSubscription: async (id: string): Promise<APISubscription> => {
    const response = await apiClient.get<APISubscription>(`/v1/subscriptions/${id}`);
    return response.data;
  },

  /**
   * Subscribe an application to an API
   */
  subscribe: async (data: SubscribeToAPIRequest): Promise<APISubscription> => {
    const response = await apiClient.post<APISubscription>('/v1/subscriptions', data);
    return response.data;
  },

  /**
   * Cancel a subscription
   */
  cancelSubscription: async (id: string): Promise<void> => {
    await apiClient.delete(`/v1/subscriptions/${id}`);
  },

  /**
   * Get subscription usage statistics
   */
  getUsage: async (id: string): Promise<APISubscription['usage']> => {
    const response = await apiClient.get<APISubscription['usage']>(`/v1/subscriptions/${id}/usage`);
    return response.data;
  },

  /**
   * Get subscriptions for a specific application
   */
  getByApplication: async (applicationId: string): Promise<APISubscription[]> => {
    const response = await apiClient.get<{ items: APISubscription[] }>('/v1/subscriptions', {
      params: { application_id: applicationId },
    });
    return response.data.items;
  },
};

export default subscriptionsService;
