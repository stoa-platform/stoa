/**
 * Governance hooks (CAB-1525)
 *
 * React Query hooks for governance operations:
 * - Pending approvals list
 * - Governance statistics
 * - Approve/reject mutations
 * - API lifecycle transitions
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { governanceService } from '../services/governance';
import { useAuth } from '../contexts/AuthContext';
import type { APILifecycleStatus } from '../types';

const GOVERNANCE_KEYS = {
  all: ['governance'] as const,
  stats: (tenantId: string) => ['governance', 'stats', tenantId] as const,
  approvals: (tenantId: string) => ['governance', 'approvals', tenantId] as const,
};

export function useGovernanceStats() {
  const { user } = useAuth();
  const tenantId = user?.tenant_id || '';

  return useQuery({
    queryKey: GOVERNANCE_KEYS.stats(tenantId),
    queryFn: () => governanceService.getStats(tenantId),
    enabled: !!tenantId,
    staleTime: 30_000,
  });
}

export function usePendingApprovals(page = 1, pageSize = 20) {
  const { user } = useAuth();
  const tenantId = user?.tenant_id || '';

  return useQuery({
    queryKey: [...GOVERNANCE_KEYS.approvals(tenantId), page, pageSize],
    queryFn: () =>
      governanceService.listPendingApprovals(tenantId, {
        page,
        page_size: pageSize,
      }),
    enabled: !!tenantId,
    staleTime: 15_000,
  });
}

export function useApproveRequest() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, expiresAt }: { id: string; expiresAt?: string }) =>
      governanceService.approveRequest(id, expiresAt),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: GOVERNANCE_KEYS.all });
    },
  });
}

export function useRejectRequest() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) =>
      governanceService.rejectRequest(id, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: GOVERNANCE_KEYS.all });
    },
  });
}

export function useTransitionAPIStatus() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      apiId,
      newStatus,
      reason,
    }: {
      apiId: string;
      newStatus: APILifecycleStatus;
      reason?: string;
    }) => governanceService.transitionAPIStatus(apiId, newStatus, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: GOVERNANCE_KEYS.all });
    },
  });
}
