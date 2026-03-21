/**
 * STOA Developer Portal - API Hooks
 *
 * React Query hooks for API catalog operations.
 */

import { useQuery } from '@tanstack/react-query';
import { apiCatalogService, ListAPIsParams, Universe } from '../services/apiCatalog';
import { usePortalEnvironment } from '../contexts/EnvironmentContext';
import type { API, PaginatedResponse } from '../types';

/**
 * Hook to list published APIs
 */
export function useAPIs(params?: ListAPIsParams) {
  const { activeEnvironment } = usePortalEnvironment();
  return useQuery<PaginatedResponse<API>>({
    queryKey: [activeEnvironment, 'apis', params],
    queryFn: () => apiCatalogService.listAPIs(params),
    staleTime: 30 * 1000, // 30 seconds
  });
}

/**
 * Hook to get a single API by ID
 */
export function useAPI(id: string | undefined) {
  const { activeEnvironment } = usePortalEnvironment();
  return useQuery<API | null>({
    queryKey: [activeEnvironment, 'api', id],
    queryFn: () => apiCatalogService.getAPI(id!),
    enabled: !!id,
    staleTime: 60 * 1000, // 1 minute
  });
}

/**
 * Hook to get OpenAPI spec for an API
 */
export function useOpenAPISpec(id: string | undefined) {
  const { activeEnvironment } = usePortalEnvironment();
  return useQuery<object>({
    queryKey: [activeEnvironment, 'api', id, 'openapi'],
    queryFn: () => apiCatalogService.getOpenAPISpec(id!),
    enabled: !!id,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Hook to get available categories
 */
export function useAPICategories() {
  const { activeEnvironment } = usePortalEnvironment();
  return useQuery<string[]>({
    queryKey: [activeEnvironment, 'api-categories'],
    queryFn: () => apiCatalogService.getCategories(),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Hook to get available universes (CAB-848)
 */
export function useUniverses() {
  const { activeEnvironment } = usePortalEnvironment();
  return useQuery<Universe[]>({
    queryKey: [activeEnvironment, 'api-universes'],
    queryFn: () => apiCatalogService.getUniverses(),
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * Hook to get available tags
 */
export function useAPITags() {
  const { activeEnvironment } = usePortalEnvironment();
  return useQuery<string[]>({
    queryKey: [activeEnvironment, 'api-tags'],
    queryFn: () => apiCatalogService.getTags(),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}
