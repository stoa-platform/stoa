/**
 * STOA Developer Portal - API Catalog Service
 *
 * Service for browsing and discovering published APIs.
 *
 * Uses /v1/portal/apis endpoint for portal-specific API browsing.
 */

import { apiClient } from './api';
import type { API, PaginatedResponse } from '../types';

export interface ListAPIsParams {
  page?: number;
  pageSize?: number;
  search?: string;
  category?: string;
  status?: 'published' | 'deprecated' | 'draft';
  tags?: string[];
}

// Portal API response format
interface PortalAPI {
  id: string;
  name: string;
  display_name: string;
  version: string;
  description: string;
  tenant_id: string;
  tenant_name?: string;
  status: string;
  backend_url?: string;
  category?: string;
  tags?: string[];
  deployments?: Record<string, boolean>;
  created_at?: string;
  updated_at?: string;
}

interface PortalAPIsResponse {
  apis: PortalAPI[];
  total: number;
  page: number;
  page_size: number;
}

/**
 * Transform Portal API format to internal API format
 */
function transformPortalAPI(portalApi: PortalAPI): API {
  return {
    id: portalApi.id,
    name: portalApi.name,
    version: portalApi.version,
    description: portalApi.description || '',
    tenantId: portalApi.tenant_id,
    tenantName: portalApi.tenant_name,
    status: portalApi.status as API['status'],
    category: portalApi.category,
    tags: portalApi.tags,
    createdAt: portalApi.created_at || new Date().toISOString(),
    updatedAt: portalApi.updated_at || new Date().toISOString(),
  };
}

export const apiCatalogService = {
  /**
   * List all published APIs (marketplace view)
   *
   * Uses /v1/portal/apis endpoint for portal-specific API browsing.
   */
  listAPIs: async (params?: ListAPIsParams): Promise<PaginatedResponse<API>> => {
    try {
      const response = await apiClient.get<PortalAPIsResponse>('/v1/portal/apis', {
        params: {
          page: params?.page || 1,
          page_size: params?.pageSize || 20,
          search: params?.search,
          category: params?.category,
          status: params?.status,
        },
      });

      const apis = (response.data.apis || []).map(transformPortalAPI);

      return {
        items: apis,
        total: response.data.total || apis.length,
        page: response.data.page || params?.page || 1,
        pageSize: response.data.page_size || params?.pageSize || 20,
        totalPages: Math.ceil((response.data.total || apis.length) / (params?.pageSize || 20)),
      };
    } catch (error) {
      console.error('Failed to fetch APIs from portal:', error);
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
   */
  getAPI: async (id: string): Promise<API | null> => {
    try {
      const response = await apiClient.get<PortalAPI>(`/v1/portal/apis/${id}`);
      return transformPortalAPI(response.data);
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
   */
  getCategories: async (): Promise<string[]> => {
    try {
      const response = await apiClient.get<string[]>('/v1/portal/api-categories');
      return response.data;
    } catch (error) {
      console.warn('Failed to fetch categories:', error);
      return [];
    }
  },

  /**
   * Get available tags
   */
  getTags: async (): Promise<string[]> => {
    try {
      const response = await apiClient.get<string[]>('/v1/portal/api-tags');
      return response.data;
    } catch (error) {
      console.warn('Failed to fetch tags:', error);
      return [];
    }
  },
};

export default apiCatalogService;
