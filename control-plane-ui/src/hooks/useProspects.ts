// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * Admin Prospects Hooks (CAB-911)
 *
 * React Query hooks for the admin prospects dashboard.
 * These hooks provide data fetching with automatic caching,
 * stale time management, and cache invalidation.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiService } from '../services/api';
import type {
  ProspectListResponse,
  ProspectsMetricsResponse,
  ProspectDetail,
  ProspectsFilters,
} from '../types';

/**
 * Hook to fetch prospects list with filters and pagination
 */
export function useProspects(
  filters: ProspectsFilters & { page?: number; limit?: number },
  options?: { enabled?: boolean }
) {
  const { enabled = true } = options || {};

  return useQuery<ProspectListResponse>({
    queryKey: ['prospects', filters],
    queryFn: () =>
      apiService.getProspects({
        company: filters.company,
        status: filters.status,
        date_from: filters.date_from,
        date_to: filters.date_to,
        page: filters.page,
        limit: filters.limit,
      }),
    enabled,
    staleTime: 5000, // 5 second stale time per requirements
  });
}

/**
 * Hook to fetch aggregated metrics for the dashboard header
 */
export function useProspectsMetrics(
  filters?: { date_from?: string; date_to?: string },
  options?: { enabled?: boolean }
) {
  const { enabled = true } = options || {};

  return useQuery<ProspectsMetricsResponse>({
    queryKey: ['prospects-metrics', filters],
    queryFn: () => apiService.getProspectsMetrics(filters),
    enabled,
    staleTime: 5000,
  });
}

/**
 * Hook to fetch detailed prospect info with timeline
 */
export function useProspectDetail(
  inviteId: string | null,
  options?: { enabled?: boolean }
) {
  const { enabled = true } = options || {};

  return useQuery<ProspectDetail>({
    queryKey: ['prospect', inviteId],
    queryFn: () => apiService.getProspect(inviteId!),
    enabled: enabled && !!inviteId,
    staleTime: 5000,
  });
}

/**
 * Hook to export prospects to CSV
 * Returns a mutation that triggers a blob download
 */
export function useExportProspectsCSV() {
  return useMutation({
    mutationFn: (filters: ProspectsFilters) =>
      apiService.exportProspectsCSV({
        company: filters.company,
        status: filters.status,
        date_from: filters.date_from,
        date_to: filters.date_to,
      }),
    onSuccess: (blob: Blob) => {
      // Trigger file download
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `prospects_${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    },
  });
}

/**
 * Hook to manually refresh prospects data
 */
export function useRefreshProspects() {
  const queryClient = useQueryClient();

  return {
    refresh: () => {
      queryClient.invalidateQueries({ queryKey: ['prospects'] });
      queryClient.invalidateQueries({ queryKey: ['prospects-metrics'] });
    },
    refreshDetail: (inviteId: string) => {
      queryClient.invalidateQueries({ queryKey: ['prospect', inviteId] });
    },
  };
}

/**
 * Derived hook for dashboard summary stats
 */
export function useProspectsSummary(
  filters?: { date_from?: string; date_to?: string }
) {
  const { data: metrics, isLoading, error } = useProspectsMetrics(filters);

  if (!metrics) {
    return {
      isLoading,
      error,
      totalInvited: 0,
      totalActive: 0,
      avgTimeToTool: null as number | null,
      avgNPS: null as number | null,
      conversionRate: 0,
      npsScore: 0,
    };
  }

  const conversionRate =
    metrics.by_status.total_invites > 0
      ? (metrics.by_status.converted / metrics.by_status.total_invites) * 100
      : 0;

  return {
    isLoading,
    error,
    totalInvited: metrics.total_invited,
    totalActive: metrics.total_active,
    avgTimeToTool: metrics.avg_time_to_tool,
    avgNPS: metrics.avg_nps,
    conversionRate,
    npsScore: metrics.nps.nps_score,
    funnel: metrics.by_status,
    npsDistribution: metrics.nps,
    topCompanies: metrics.top_companies,
  };
}
