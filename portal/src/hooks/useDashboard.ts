/**
 * STOA Developer Portal - Dashboard Hooks (CAB-691)
 *
 * React Query hooks for dashboard data with staleTime caching.
 */

import { useQuery } from '@tanstack/react-query';
import { dashboardService } from '../services/dashboard';
import { apiClient } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import type { DashboardStats, RecentActivityItem } from '../types';

/**
 * Hook for dashboard stats with 30s cache
 */
export function useDashboardStats() {
  const { isAuthenticated, accessToken } = useAuth();

  return useQuery<DashboardStats>({
    queryKey: ['dashboard-stats'],
    queryFn: () => dashboardService.getStats(),
    enabled: isAuthenticated && !!accessToken,
    staleTime: 30 * 1000,
  });
}

/**
 * Hook for dashboard recent activity with 30s cache
 */
export function useDashboardActivity() {
  const { isAuthenticated, accessToken } = useAuth();

  return useQuery<RecentActivityItem[]>({
    queryKey: ['dashboard-activity'],
    queryFn: () => dashboardService.getRecentActivity(),
    enabled: isAuthenticated && !!accessToken,
    staleTime: 30 * 1000,
  });
}

export interface APIPreview {
  id: string;
  name: string;
  displayName: string;
  description: string;
  version: string;
  status: string;
  category: string;
  tags: string[];
  visibility?: 'public' | 'internal';
}

/**
 * Hook for featured APIs with 60s cache
 */
export function useFeaturedAPIs(limit: number = 4) {
  const { isAuthenticated, accessToken } = useAuth();

  return useQuery<APIPreview[]>({
    queryKey: ['featured-apis', limit],
    queryFn: async () => {
      const response = await apiClient.get('/v1/portal/apis', { params: { limit } });
      return response.data.apis || [];
    },
    enabled: isAuthenticated && !!accessToken,
    staleTime: 60 * 1000,
  });
}

export interface AIToolPreview {
  id: string;
  name: string;
  displayName: string;
  description: string;
  category: 'platform' | 'tenant' | 'public';
  status: string;
  tools: { id: string; displayName: string }[];
}

/**
 * Hook for featured AI tools with 60s cache
 */
export function useFeaturedAITools(limit: number = 4) {
  const { isAuthenticated, accessToken } = useAuth();

  return useQuery<AIToolPreview[]>({
    queryKey: ['featured-tools', limit],
    queryFn: async () => {
      const response = await apiClient.get('/v1/portal/mcp-servers', { params: { limit } });
      return response.data.servers || [];
    },
    enabled: isAuthenticated && !!accessToken,
    staleTime: 60 * 1000,
  });
}
