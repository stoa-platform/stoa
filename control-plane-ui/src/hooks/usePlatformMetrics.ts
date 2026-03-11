/**
 * Platform Metrics Hooks (CAB-1775)
 *
 * React Query hooks for platform-wide KPIs: gateway health summary,
 * mode stats, and aggregated metrics. Used by the Dashboard.
 */
import { useQuery } from '@tanstack/react-query';
import { apiService } from '../services/api';

const REFRESH_INTERVAL = 30_000;

export interface GatewayHealthSummary {
  online: number;
  offline: number;
  degraded: number;
  maintenance: number;
  total: number;
}

export interface GatewayModeStats {
  modes: Array<{
    mode: string;
    total: number;
    online: number;
    offline: number;
    degraded: number;
  }>;
  total_gateways: number;
}

/**
 * Fetch gateway health summary (online/offline/degraded counts).
 */
export function useGatewayHealthSummary() {
  return useQuery<GatewayHealthSummary>({
    queryKey: ['gateway-health-summary'],
    queryFn: () => apiService.getGatewayHealthSummary(),
    refetchInterval: REFRESH_INTERVAL,
    staleTime: 10_000,
  });
}

/**
 * Fetch gateway mode statistics (edge-mcp, sidecar, proxy, shadow).
 */
export function useGatewayModeStats() {
  return useQuery<GatewayModeStats>({
    queryKey: ['gateway-mode-stats'],
    queryFn: () => apiService.getGatewayModeStats(),
    refetchInterval: REFRESH_INTERVAL,
    staleTime: 10_000,
  });
}

/**
 * Fetch gateway instances list for the health cards.
 */
export function useGatewayInstances() {
  return useQuery<{ items: any[]; total: number }>({
    queryKey: ['gateway-instances-dashboard'],
    queryFn: () => apiService.getGatewayInstances({ page_size: 20 }),
    refetchInterval: REFRESH_INTERVAL,
    staleTime: 10_000,
  });
}
