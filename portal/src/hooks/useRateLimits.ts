/**
 * Rate Limits Dashboard Hooks (CAB-1470)
 */

import { useQuery } from '@tanstack/react-query';
import { rateLimitsService } from '../services/rateLimits';
import { useAuth } from '../contexts/AuthContext';
import type { RateLimitsResponse } from '../types';

export function useRateLimits() {
  const { isAuthenticated, accessToken } = useAuth();

  return useQuery<RateLimitsResponse>({
    queryKey: ['rate-limits'],
    queryFn: () => rateLimitsService.getRateLimits(),
    enabled: isAuthenticated && !!accessToken,
    staleTime: 15 * 1000,
  });
}
