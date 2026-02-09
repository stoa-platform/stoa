/**
 * STOA Developer Portal - Plans Service
 *
 * Service for managing subscription plans (CAB-1121).
 */

import { apiClient } from './api';
import type { Plan, PaginatedResponse } from '../types';

export interface ListPlansParams {
  page?: number;
  pageSize?: number;
  status?: 'active' | 'deprecated' | 'archived';
}

export const plansService = {
  /**
   * List plans for a tenant
   */
  listPlans: async (
    tenantId: string,
    params?: ListPlansParams
  ): Promise<PaginatedResponse<Plan>> => {
    const response = await apiClient.get<PaginatedResponse<Plan>>(`/v1/plans/${tenantId}`, {
      params: {
        page: params?.page || 1,
        page_size: params?.pageSize || 20,
        status: params?.status,
      },
    });
    return response.data;
  },

  /**
   * Get a single plan by ID
   */
  getPlan: async (tenantId: string, planId: string): Promise<Plan> => {
    const response = await apiClient.get<Plan>(`/v1/plans/${tenantId}/${planId}`);
    return response.data;
  },

  /**
   * Get a plan by slug
   */
  getPlanBySlug: async (tenantId: string, slug: string): Promise<Plan> => {
    const response = await apiClient.get<Plan>(`/v1/plans/${tenantId}/by-slug/${slug}`);
    return response.data;
  },
};

export default plansService;
