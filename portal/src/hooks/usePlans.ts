/**
 * STOA Developer Portal - Plan Hooks
 *
 * React Query hooks for subscription plans.
 *
 * Reference: CAB-1121 Phase 5
 */

import { useQuery } from '@tanstack/react-query';
import { plansService, ListPlansParams } from '../services/plans';
import type { Plan, PlanListResponse } from '../types';

/**
 * Hook to list plans for a tenant (only active by default)
 */
export function usePlans(tenantId: string | undefined, params?: ListPlansParams) {
  return useQuery<PlanListResponse>({
    queryKey: ['plans', tenantId, params],
    queryFn: () => plansService.list(tenantId!, { status: 'active', ...params }),
    enabled: !!tenantId,
    staleTime: 60 * 1000,
  });
}

/**
 * Hook to get a single plan by ID
 */
export function usePlan(tenantId: string | undefined, planId: string | undefined) {
  return useQuery<Plan>({
    queryKey: ['plan', tenantId, planId],
    queryFn: () => plansService.get(tenantId!, planId!),
    enabled: !!tenantId && !!planId,
    staleTime: 60 * 1000,
  });
}
