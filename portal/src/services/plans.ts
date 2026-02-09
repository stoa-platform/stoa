/**
 * STOA Developer Portal - Plans Service
 *
 * Service for listing subscription plans.
 * Uses Control Plane API endpoints (/v1/plans).
 *
 * Reference: CAB-1121 Phase 5
 */

import { apiClient } from './api';
import type { Plan, PlanListResponse } from '../types';

export interface ListPlansParams {
  page?: number;
  pageSize?: number;
  status?: string;
}

export const plansService = {
  /**
   * List plans for a tenant
   * GET /v1/plans/{tenant_id}
   */
  list: async (tenantId: string, params?: ListPlansParams): Promise<PlanListResponse> => {
    const response = await apiClient.get<PlanListResponse>(`/v1/plans/${tenantId}`, {
      params: {
        page: params?.page || 1,
        page_size: params?.pageSize || 50,
        status: params?.status,
      },
    });
    return response.data;
  },

  /**
   * Get a plan by ID
   * GET /v1/plans/{tenant_id}/{plan_id}
   */
  get: async (tenantId: string, planId: string): Promise<Plan> => {
    const response = await apiClient.get<Plan>(`/v1/plans/${tenantId}/${planId}`);
    return response.data;
  },

  /**
   * Get a plan by slug
   * GET /v1/plans/{tenant_id}/by-slug/{slug}
   */
  getBySlug: async (tenantId: string, slug: string): Promise<Plan> => {
    const response = await apiClient.get<Plan>(`/v1/plans/${tenantId}/by-slug/${slug}`);
    return response.data;
  },
};

export default plansService;
