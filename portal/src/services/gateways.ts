/**
 * STOA Developer Portal - Gateway Instances Service
 *
 * Service for browsing and monitoring gateway instances.
 * Uses /v1/admin/gateways endpoints.
 */

import { apiClient } from './api';
import type { GatewayInstance, GatewayInstancesResponse, GatewayModeStats } from '../types';

export interface ListGatewaysParams {
  page?: number;
  pageSize?: number;
  gateway_type?: string;
  environment?: string;
  status?: string;
}

export const gatewaysService = {
  listGateways: async (params?: ListGatewaysParams): Promise<GatewayInstancesResponse> => {
    try {
      const response = await apiClient.get<GatewayInstancesResponse>('/v1/admin/gateways', {
        params: {
          page: params?.page || 1,
          page_size: params?.pageSize || 20,
          gateway_type: params?.gateway_type,
          environment: params?.environment,
          status: params?.status,
        },
      });
      return response.data;
    } catch (error) {
      console.error('Failed to fetch gateways:', error);
      return { items: [], total: 0, page: 1, page_size: 20 };
    }
  },

  getGateway: async (id: string): Promise<GatewayInstance | null> => {
    try {
      const response = await apiClient.get<GatewayInstance>(`/v1/admin/gateways/${id}`);
      return response.data;
    } catch (error) {
      console.error(`Failed to fetch gateway ${id}:`, error);
      return null;
    }
  },

  getModeStats: async (): Promise<GatewayModeStats[]> => {
    try {
      const response = await apiClient.get<GatewayModeStats[]>('/v1/admin/gateways/modes/stats');
      return response.data;
    } catch (error) {
      console.error('Failed to fetch mode stats:', error);
      return [];
    }
  },

  triggerHealthCheck: async (id: string): Promise<boolean> => {
    try {
      await apiClient.post(`/v1/admin/gateways/${id}/health`);
      return true;
    } catch (error) {
      console.error(`Failed to trigger health check for gateway ${id}:`, error);
      return false;
    }
  },
};

export default gatewaysService;
