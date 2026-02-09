/**
 * STOA Developer Portal - Consumer Service
 *
 * Service for consumer registration and management.
 * Uses Control Plane API endpoints (/v1/consumers).
 *
 * Reference: CAB-1121 Phase 5
 */

import { apiClient } from './api';
import type {
  Consumer,
  ConsumerCreate,
  ConsumerUpdate,
  ConsumerCredentials,
  ConsumerListResponse,
} from '../types';

export interface ListConsumersParams {
  page?: number;
  pageSize?: number;
  status?: string;
}

export const consumersService = {
  /**
   * Register a new consumer
   * POST /v1/consumers/{tenant_id}
   */
  register: async (tenantId: string, data: ConsumerCreate): Promise<Consumer> => {
    const response = await apiClient.post<Consumer>(`/v1/consumers/${tenantId}`, data);
    return response.data;
  },

  /**
   * List consumers for a tenant
   * GET /v1/consumers/{tenant_id}
   */
  list: async (tenantId: string, params?: ListConsumersParams): Promise<ConsumerListResponse> => {
    const response = await apiClient.get<ConsumerListResponse>(`/v1/consumers/${tenantId}`, {
      params: {
        page: params?.page || 1,
        page_size: params?.pageSize || 20,
        status: params?.status,
      },
    });
    return response.data;
  },

  /**
   * Get a consumer by ID
   * GET /v1/consumers/{tenant_id}/{consumer_id}
   */
  get: async (tenantId: string, consumerId: string): Promise<Consumer> => {
    const response = await apiClient.get<Consumer>(`/v1/consumers/${tenantId}/${consumerId}`);
    return response.data;
  },

  /**
   * Update a consumer
   * PUT /v1/consumers/{tenant_id}/{consumer_id}
   */
  update: async (tenantId: string, consumerId: string, data: ConsumerUpdate): Promise<Consumer> => {
    const response = await apiClient.put<Consumer>(`/v1/consumers/${tenantId}/${consumerId}`, data);
    return response.data;
  },

  /**
   * Get consumer OAuth2 credentials (regenerates secret on each call)
   * GET /v1/consumers/{tenant_id}/{consumer_id}/credentials
   */
  getCredentials: async (tenantId: string, consumerId: string): Promise<ConsumerCredentials> => {
    const response = await apiClient.get<ConsumerCredentials>(
      `/v1/consumers/${tenantId}/${consumerId}/credentials`
    );
    return response.data;
  },

  /**
   * Suspend a consumer
   * POST /v1/consumers/{tenant_id}/{consumer_id}/suspend
   */
  suspend: async (tenantId: string, consumerId: string): Promise<Consumer> => {
    const response = await apiClient.post<Consumer>(
      `/v1/consumers/${tenantId}/${consumerId}/suspend`
    );
    return response.data;
  },

  /**
   * Activate a consumer
   * POST /v1/consumers/{tenant_id}/{consumer_id}/activate
   */
  activate: async (tenantId: string, consumerId: string): Promise<Consumer> => {
    const response = await apiClient.post<Consumer>(
      `/v1/consumers/${tenantId}/${consumerId}/activate`
    );
    return response.data;
  },
};

export default consumersService;
