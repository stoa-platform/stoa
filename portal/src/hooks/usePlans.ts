/**
 * STOA Developer Portal - Plan Hooks
 *
 * React Query hooks for subscription plan operations (CAB-1121).
 */

import { useQuery } from '@tanstack/react-query';
import { plansService, ListPlansParams } from '../services/plans';
import type { Plan, PaginatedResponse } from '../types';

/**
 * Hook to list plans for a tenant
 */
export function usePlans(tenantId: string | undefined, params?: ListPlansParams) {
  return useQuery<PaginatedResponse<Plan>>({
    queryKey: ['plans', tenantId, params],
    queryFn: () => plansService.listPlans(tenantId!, params),
    enabled: !!tenantId,
    staleTime: 60 * 1000, // 1 minute - plans don't change often
  });
}

/**
 * Hook to get a single plan by ID
 */
export function usePlan(tenantId: string | undefined, planId: string | undefined) {
  return useQuery<Plan>({
    queryKey: ['plan', tenantId, planId],
    queryFn: () => plansService.getPlan(tenantId!, planId!),
    enabled: !!tenantId && !!planId,
    staleTime: 60 * 1000, // 1 minute
  });
}

/**
 * Hook to get a plan by slug
 */
export function usePlanBySlug(tenantId: string | undefined, slug: string | undefined) {
  return useQuery<Plan>({
    queryKey: ['plan', tenantId, 'slug', slug],
    queryFn: () => plansService.getPlanBySlug(tenantId!, slug!),
    enabled: !!tenantId && !!slug,
    staleTime: 60 * 1000, // 1 minute
  });
}
