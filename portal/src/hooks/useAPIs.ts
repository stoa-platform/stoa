/**
 * STOA Developer Portal - API Hooks
 *
 * React Query hooks for API catalog operations.
 */

import { useQuery } from '@tanstack/react-query';
import { apiCatalogService, ListAPIsParams } from '../services/apiCatalog';
import type { API, PaginatedResponse } from '../types';

/**
 * Hook to list published APIs
 */
export function useAPIs(params?: ListAPIsParams) {
  return useQuery<PaginatedResponse<API>>({
    queryKey: ['apis', params],
    queryFn: () => apiCatalogService.listAPIs(params),
    staleTime: 30 * 1000, // 30 seconds
  });
}

/**
 * Hook to get a single API by ID
 */
export function useAPI(id: string | undefined) {
  return useQuery<API | null>({
    queryKey: ['api', id],
    queryFn: () => apiCatalogService.getAPI(id!),
    enabled: !!id,
    staleTime: 60 * 1000, // 1 minute
  });
}

/**
 * Hook to get OpenAPI spec for an API
 */
export function useOpenAPISpec(id: string | undefined) {
  return useQuery<object>({
    queryKey: ['api', id, 'openapi'],
    queryFn: () => apiCatalogService.getOpenAPISpec(id!),
    enabled: !!id,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Hook to get available categories
 */
export function useAPICategories() {
  return useQuery<string[]>({
    queryKey: ['api-categories'],
    queryFn: () => apiCatalogService.getCategories(),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Hook to get available tags
 */
export function useAPITags() {
  return useQuery<string[]>({
    queryKey: ['api-tags'],
    queryFn: () => apiCatalogService.getTags(),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}
