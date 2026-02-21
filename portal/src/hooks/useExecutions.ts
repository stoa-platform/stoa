/**
 * STOA Developer Portal — Execution Hooks (CAB-1318)
 *
 * React Query hooks for execution logs and error taxonomy.
 */

import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../contexts/AuthContext';
import {
  executionsService,
  type ExecutionListResponse,
  type ExecutionParams,
  type TaxonomyResponse,
} from '../services/executions';

/**
 * Hook for consumer execution logs with 30s cache
 */
export function useExecutions(params?: ExecutionParams) {
  const { isAuthenticated, accessToken } = useAuth();

  return useQuery<ExecutionListResponse>({
    queryKey: ['executions', params],
    queryFn: () => executionsService.list(params),
    enabled: isAuthenticated && !!accessToken,
    staleTime: 30 * 1000,
  });
}

/**
 * Hook for consumer error taxonomy with 30s cache
 */
export function useExecutionTaxonomy() {
  const { isAuthenticated, accessToken } = useAuth();

  return useQuery<TaxonomyResponse>({
    queryKey: ['execution-taxonomy'],
    queryFn: () => executionsService.getTaxonomy(),
    enabled: isAuthenticated && !!accessToken,
    staleTime: 30 * 1000,
  });
}
