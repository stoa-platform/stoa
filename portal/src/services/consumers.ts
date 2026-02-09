/**
 * STOA Developer Portal - Consumers Service
 *
 * Service for managing external API consumers (CAB-1121).
 */

import { apiClient } from './api';
import type {
  Consumer,
  ConsumerCreateRequest,
  ConsumerUpdateRequest,
  ConsumerCredentials,
  PaginatedResponse,
} from '../types';

export interface ListConsumersParams {
  page?: number;
  pageSize?: number;
  status?: 'active' | 'suspended' | 'blocked';
  search?: string;
}

export const consumersService = {
  /**
   * List consumers for a tenant
   */
  listConsumers: async (
    tenantId: string,
    params?: ListConsumersParams
  ): Promise<PaginatedResponse<Consumer>> => {
    const response = await apiClient.get<PaginatedResponse<Consumer>>(`/v1/consumers/${tenantId}`, {
      params: {
        page: params?.page || 1,
        page_size: params?.pageSize || 20,
        status: params?.status,
        search: params?.search,
      },
    });
    return response.data;
  },

  /**
   * Get a single consumer by ID
   */
  getConsumer: async (tenantId: string, consumerId: string): Promise<Consumer> => {
    const response = await apiClient.get<Consumer>(`/v1/consumers/${tenantId}/${consumerId}`);
    return response.data;
  },

  /**
   * Create a new consumer
   */
  createConsumer: async (tenantId: string, data: ConsumerCreateRequest): Promise<Consumer> => {
    const response = await apiClient.post<Consumer>(`/v1/consumers/${tenantId}`, data);
    return response.data;
  },

  /**
   * Update an existing consumer
   */
  updateConsumer: async (
    tenantId: string,
    consumerId: string,
    data: ConsumerUpdateRequest
  ): Promise<Consumer> => {
    const response = await apiClient.put<Consumer>(`/v1/consumers/${tenantId}/${consumerId}`, data);
    return response.data;
  },

  /**
   * Delete a consumer
   */
  deleteConsumer: async (tenantId: string, consumerId: string): Promise<void> => {
    await apiClient.delete(`/v1/consumers/${tenantId}/${consumerId}`);
  },

  /**
   * Suspend a consumer
   */
  suspendConsumer: async (tenantId: string, consumerId: string): Promise<Consumer> => {
    const response = await apiClient.post<Consumer>(
      `/v1/consumers/${tenantId}/${consumerId}/suspend`
    );
    return response.data;
  },

  /**
   * Activate a consumer
   */
  activateConsumer: async (tenantId: string, consumerId: string): Promise<Consumer> => {
    const response = await apiClient.post<Consumer>(
      `/v1/consumers/${tenantId}/${consumerId}/activate`
    );
    return response.data;
  },

  /**
   * Block a consumer
   */
  blockConsumer: async (tenantId: string, consumerId: string): Promise<Consumer> => {
    const response = await apiClient.post<Consumer>(
      `/v1/consumers/${tenantId}/${consumerId}/block`
    );
    return response.data;
  },

  /**
   * Get consumer credentials (one-time display)
   */
  getCredentials: async (tenantId: string, consumerId: string): Promise<ConsumerCredentials> => {
    const response = await apiClient.get<ConsumerCredentials>(
      `/v1/consumers/${tenantId}/${consumerId}/credentials`
    );
    return response.data;
  },
};

export default consumersService;
