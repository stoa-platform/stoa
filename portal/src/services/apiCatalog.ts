/**
 * STOA Developer Portal - API Catalog Service
 *
 * Service for browsing and discovering published APIs.
 *
 * NOTE: This is a temporary implementation using /v1/gateway/apis endpoint.
 * Once Control-Plane API adds /v1/portal/* endpoints, this should be updated
 * to use those instead for a better portal-specific experience.
 */

import { apiClient } from './api';
import type { API, PaginatedResponse } from '../types';

export interface ListAPIsParams {
  page?: number;
  pageSize?: number;
  search?: string;
  category?: string;
  status?: 'published' | 'deprecated';
  tags?: string[];
}

// Gateway API response format (different from portal format)
interface GatewayAPI {
  id: string;
  name: string;
  version: string;
  description?: string;
  tenant_id: string;
  tenant_name?: string;
  status: string;
  gateway_url?: string;
  openapi_spec_url?: string;
  created_at?: string;
  updated_at?: string;
}

interface GatewayAPIsResponse {
  apis: GatewayAPI[];
  total?: number;
  page?: number;
  page_size?: number;
}

/**
 * Transform Gateway API format to Portal API format
 */
function transformGatewayAPI(gatewayApi: GatewayAPI): API {
  return {
    id: gatewayApi.id,
    name: gatewayApi.name,
    version: gatewayApi.version,
    description: gatewayApi.description || '',
    tenantId: gatewayApi.tenant_id,
    tenantName: gatewayApi.tenant_name,
    status: gatewayApi.status as API['status'],
    createdAt: gatewayApi.created_at || new Date().toISOString(),
    updatedAt: gatewayApi.updated_at || new Date().toISOString(),
  };
}

export const apiCatalogService = {
  /**
   * List all published APIs (marketplace view)
   *
   * Uses /v1/gateway/apis endpoint (workaround until /v1/portal/apis is implemented)
   */
  listAPIs: async (params?: ListAPIsParams): Promise<PaginatedResponse<API>> => {
    try {
      const response = await apiClient.get<GatewayAPIsResponse>('/v1/gateway/apis', {
        params: {
          page: params?.page || 1,
          page_size: params?.pageSize || 20,
          search: params?.search,
        },
      });

      const apis = (response.data.apis || []).map(transformGatewayAPI);

      return {
        items: apis,
        total: response.data.total || apis.length,
        page: response.data.page || params?.page || 1,
        pageSize: response.data.page_size || params?.pageSize || 20,
        totalPages: Math.ceil((response.data.total || apis.length) / (params?.pageSize || 20)),
      };
    } catch (error) {
      console.error('Failed to fetch APIs from gateway:', error);
      // Return empty response on error
      return {
        items: [],
        total: 0,
        page: params?.page || 1,
        pageSize: params?.pageSize || 20,
        totalPages: 0,
      };
    }
  },

  /**
   * Get a single API by ID
   *
   * NOTE: This endpoint may not exist in gateway - returns null if not found
   */
  getAPI: async (id: string): Promise<API | null> => {
    try {
      // Try to fetch from gateway APIs and find by ID
      const response = await apiClient.get<GatewayAPIsResponse>('/v1/gateway/apis');
      const gatewayApi = response.data.apis?.find(api => api.id === id);

      if (gatewayApi) {
        return transformGatewayAPI(gatewayApi);
      }
      return null;
    } catch (error) {
      console.error(`Failed to fetch API ${id}:`, error);
      return null;
    }
  },

  /**
   * Get OpenAPI specification for an API
   *
   * NOTE: May need to be updated when /v1/portal/apis/{id}/openapi is available
   */
  getOpenAPISpec: async (id: string): Promise<object | null> => {
    try {
      const response = await apiClient.get<object>(`/v1/gateway/apis/${id}/openapi`);
      return response.data;
    } catch (error) {
      console.warn(`OpenAPI spec not available for API ${id}:`, error);
      return null;
    }
  },

  /**
   * Get available categories
   *
   * NOTE: Not implemented in gateway API - returns empty array
   */
  getCategories: async (): Promise<string[]> => {
    // Categories endpoint not available in gateway API
    // Will be implemented when /v1/portal/apis/categories is added
    console.warn('Categories endpoint not yet implemented');
    return [];
  },

  /**
   * Get available tags
   *
   * NOTE: Not implemented in gateway API - returns empty array
   */
  getTags: async (): Promise<string[]> => {
    // Tags endpoint not available in gateway API
    // Will be implemented when /v1/portal/apis/tags is added
    console.warn('Tags endpoint not yet implemented');
    return [];
  },
};

export default apiCatalogService;
