/**
 * API Comparison Hooks (CAB-1470)
 */

import { useQuery } from '@tanstack/react-query';
import { apiComparisonService } from '../services/apiComparison';
import { useAuth } from '../contexts/AuthContext';
import type { APIComparisonResult } from '../types';

export function useAPIComparison(apiIds: string[]) {
  const { isAuthenticated, accessToken } = useAuth();

  return useQuery<APIComparisonResult>({
    queryKey: ['api-comparison', apiIds],
    queryFn: () => apiComparisonService.compareAPIs(apiIds),
    enabled: isAuthenticated && !!accessToken && apiIds.length >= 2,
    staleTime: 60 * 1000,
  });
}
