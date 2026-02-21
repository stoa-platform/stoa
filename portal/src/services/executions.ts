/**
 * STOA Developer Portal — Execution Logs Service (CAB-1318)
 *
 * API client for consumer execution view endpoints.
 */

import { apiClient } from './api';

// ============ Types ============

export interface ExecutionSummary {
  id: string;
  api_name: string | null;
  tool_name: string | null;
  request_id: string;
  method: string | null;
  path: string | null;
  status_code: number | null;
  status: 'success' | 'error' | 'timeout';
  error_category: string | null;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
}

export interface ExecutionListResponse {
  items: ExecutionSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface TaxonomyItem {
  category: string;
  count: number;
  avg_duration_ms: number | null;
  percentage: number;
}

export interface TaxonomyResponse {
  items: TaxonomyItem[];
  total_errors: number;
  total_executions: number;
  error_rate: number;
}

export interface ExecutionParams {
  status?: string;
  page?: number;
  page_size?: number;
}

// ============ Service ============

export const executionsService = {
  /**
   * List my executions (consumer-scoped)
   * GET /v1/usage/me/executions
   */
  list: async (params?: ExecutionParams): Promise<ExecutionListResponse> => {
    const response = await apiClient.get<ExecutionListResponse>('/v1/usage/me/executions', {
      params: {
        page: params?.page || 1,
        page_size: params?.page_size || 20,
        status: params?.status,
      },
    });
    return response.data;
  },

  /**
   * Get my error taxonomy (consumer-scoped)
   * GET /v1/usage/me/executions/taxonomy
   */
  getTaxonomy: async (): Promise<TaxonomyResponse> => {
    const response = await apiClient.get<TaxonomyResponse>('/v1/usage/me/executions/taxonomy');
    return response.data;
  },
};

export default executionsService;
