/**
 * STOA Developer Portal - API Catalog Service
 *
 * Service for browsing and discovering published APIs.
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

export const apiCatalogService = {
  /**
   * List all published APIs (marketplace view)
   */
  listAPIs: async (params?: ListAPIsParams): Promise<PaginatedResponse<API>> => {
    const response = await apiClient.get<PaginatedResponse<API>>('/v1/apis', {
      params: {
        page: params?.page || 1,
        page_size: params?.pageSize || 20,
        search: params?.search,
        category: params?.category,
        status: params?.status || 'published', // Default to published for portal
        tags: params?.tags?.join(','),
      },
    });
    return response.data;
  },

  /**
   * Get a single API by ID
   */
  getAPI: async (id: string): Promise<API> => {
    const response = await apiClient.get<API>(`/v1/apis/${id}`);
    return response.data;
  },

  /**
   * Get OpenAPI specification for an API
   */
  getOpenAPISpec: async (id: string): Promise<object> => {
    const response = await apiClient.get<object>(`/v1/apis/${id}/openapi`);
    return response.data;
  },

  /**
   * Get available categories
   */
  getCategories: async (): Promise<string[]> => {
    const response = await apiClient.get<{ categories: string[] }>('/v1/apis/categories');
    return response.data.categories;
  },

  /**
   * Get available tags
   */
  getTags: async (): Promise<string[]> => {
    const response = await apiClient.get<{ tags: string[] }>('/v1/apis/tags');
    return response.data.tags;
  },
};

export default apiCatalogService;
