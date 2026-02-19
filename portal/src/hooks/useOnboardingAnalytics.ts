/**
 * STOA Developer Portal - Onboarding Analytics Hooks (CAB-1325 Phase 3)
 *
 * React Query hooks for admin onboarding analytics.
 */

import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../contexts/AuthContext';
import { onboardingService } from '../services/onboarding';
import type { FunnelResponse, StalledUser } from '../services/onboarding';

/**
 * Hook for onboarding funnel analytics (admin-only, 60s cache)
 */
export function useOnboardingFunnel() {
  const { isAuthenticated, accessToken } = useAuth();

  return useQuery<FunnelResponse>({
    queryKey: ['onboarding', 'funnel'],
    queryFn: () => onboardingService.getFunnel(),
    enabled: isAuthenticated && !!accessToken,
    staleTime: 60 * 1000,
  });
}

/**
 * Hook for stalled onboarding users (admin-only, 60s cache)
 */
export function useStalledUsers(hours: number = 24) {
  const { isAuthenticated, accessToken } = useAuth();

  return useQuery<StalledUser[]>({
    queryKey: ['onboarding', 'stalled', hours],
    queryFn: () => onboardingService.getStalled(hours),
    enabled: isAuthenticated && !!accessToken,
    staleTime: 60 * 1000,
  });
}
