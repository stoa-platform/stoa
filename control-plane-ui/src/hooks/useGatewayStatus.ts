import { useQuery } from '@tanstack/react-query';
import { getGatewayStatus, getGatewayHealth, GatewayStatusResponse, GatewayHealthResponse } from '../services/gatewayApi';
import { usePlatformStatus } from './usePlatformStatus';

export function useGatewayStatus() {
  return useQuery<GatewayStatusResponse>({
    queryKey: ['gateway', 'status'],
    queryFn: getGatewayStatus,
    refetchInterval: 30000,
    staleTime: 10000,
  });
}

export function useGatewayHealth() {
  return useQuery<GatewayHealthResponse>({
    queryKey: ['gateway', 'health'],
    queryFn: getGatewayHealth,
    refetchInterval: 30000,
    staleTime: 10000,
  });
}

/**
 * Hook to get ArgoCD sync status and platform health for gateway extensions (CAB-1023).
 * Reuses usePlatformStatus — no additional API calls.
 */
export function useGatewayPlatformInfo() {
  const { data, isLoading, error } = usePlatformStatus();

  if (!data) {
    return { isLoading, error, gatewayComponent: null, healthSummary: null, externalLinks: null, events: [] };
  }

  const components = data.gitops.components;
  const gatewayComponent = components.find(
    (c) => c.name.includes('gateway') || c.name.includes('webmethods')
  ) || null;

  const healthyCount = components.filter((c) => c.health_status === 'Healthy').length;
  const degradedCount = components.filter(
    (c) => c.health_status === 'Degraded' || c.health_status === 'Missing'
  ).length;
  const progressingCount = components.filter((c) => c.health_status === 'Progressing').length;
  const unknownCount = components.length - healthyCount - degradedCount - progressingCount;

  return {
    isLoading,
    error,
    gatewayComponent,
    healthSummary: {
      total: components.length,
      healthy: healthyCount,
      degraded: degradedCount,
      progressing: progressingCount,
      unknown: unknownCount,
    },
    externalLinks: data.external_links,
    events: data.events.slice(0, 5),
  };
}
