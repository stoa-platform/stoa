import { useQuery } from '@tanstack/react-query';
import { getGatewayStatus, getGatewayHealth, GatewayStatusResponse, GatewayHealthResponse } from '../services/gatewayApi';

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
