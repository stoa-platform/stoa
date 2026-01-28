// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * Platform Status Hooks (CAB-654)
 *
 * React Query hooks for platform status and GitOps sync operations.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiService } from '../services/api';
import type {
  PlatformStatusResponse,
  ComponentStatus,
  ApplicationDiffResponse,
  PlatformEvent,
} from '../services/api';

/**
 * Hook to fetch platform status with auto-refresh
 */
export function usePlatformStatus(options?: { enabled?: boolean; refetchInterval?: number }) {
  const { enabled = true, refetchInterval = 30000 } = options || {};

  return useQuery<PlatformStatusResponse>({
    queryKey: ['platform-status'],
    queryFn: () => apiService.getPlatformStatus(),
    enabled,
    refetchInterval, // Refresh every 30 seconds by default
    staleTime: 10000, // Consider data stale after 10 seconds
  });
}

/**
 * Hook to fetch all platform components
 */
export function usePlatformComponents(options?: { enabled?: boolean }) {
  const { enabled = true } = options || {};

  return useQuery<ComponentStatus[]>({
    queryKey: ['platform-components'],
    queryFn: () => apiService.getPlatformComponents(),
    enabled,
    staleTime: 30000,
  });
}

/**
 * Hook to fetch a single component status
 */
export function useComponentStatus(name: string | undefined, options?: { enabled?: boolean }) {
  const { enabled = true } = options || {};

  return useQuery<ComponentStatus>({
    queryKey: ['platform-component', name],
    queryFn: () => apiService.getComponentStatus(name!),
    enabled: enabled && !!name,
    staleTime: 10000,
  });
}

/**
 * Hook to fetch component diff for OutOfSync applications
 */
export function useComponentDiff(name: string | undefined, options?: { enabled?: boolean }) {
  const { enabled = true } = options || {};

  return useQuery<ApplicationDiffResponse>({
    queryKey: ['platform-component-diff', name],
    queryFn: () => apiService.getComponentDiff(name!),
    enabled: enabled && !!name,
    staleTime: 30000,
  });
}

/**
 * Hook to fetch platform events
 */
export function usePlatformEvents(
  component?: string,
  limit?: number,
  options?: { enabled?: boolean }
) {
  const { enabled = true } = options || {};

  return useQuery<PlatformEvent[]>({
    queryKey: ['platform-events', component, limit],
    queryFn: () => apiService.getPlatformEvents(component, limit),
    enabled,
    staleTime: 30000,
  });
}

/**
 * Hook to trigger component sync
 */
export function useSyncComponent() {
  const queryClient = useQueryClient();

  return useMutation<
    { message: string; operation: string },
    Error,
    string
  >({
    mutationFn: (name: string) => apiService.syncPlatformComponent(name),
    onSuccess: () => {
      // Invalidate platform status and components to refresh data
      queryClient.invalidateQueries({ queryKey: ['platform-status'] });
      queryClient.invalidateQueries({ queryKey: ['platform-components'] });
      queryClient.invalidateQueries({ queryKey: ['platform-events'] });
    },
  });
}

/**
 * Hook to get derived data from platform status
 */
export function usePlatformHealthSummary() {
  const { data, isLoading, error } = usePlatformStatus();

  if (!data) {
    return {
      isLoading,
      error,
      overallStatus: 'unknown' as const,
      syncedCount: 0,
      outOfSyncCount: 0,
      healthyCount: 0,
      degradedCount: 0,
      totalComponents: 0,
      outOfSyncComponents: [] as ComponentStatus[],
    };
  }

  const components = data.gitops.components;
  const syncedCount = components.filter((c) => c.sync_status === 'Synced').length;
  const outOfSyncCount = components.filter((c) => c.sync_status === 'OutOfSync').length;
  const healthyCount = components.filter((c) => c.health_status === 'Healthy').length;
  const degradedCount = components.filter(
    (c) => c.health_status === 'Degraded' || c.health_status === 'Missing'
  ).length;
  const outOfSyncComponents = components.filter((c) => c.sync_status === 'OutOfSync');

  return {
    isLoading,
    error,
    overallStatus: data.gitops.status,
    syncedCount,
    outOfSyncCount,
    healthyCount,
    degradedCount,
    totalComponents: components.length,
    outOfSyncComponents,
    externalLinks: data.external_links,
    timestamp: data.timestamp,
    events: data.events,
  };
}
