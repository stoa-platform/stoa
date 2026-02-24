/**
 * Admin Access Requests Hook (CAB-1468)
 *
 * React Query hook for the admin access requests table.
 */
import { useQuery } from '@tanstack/react-query';
import { apiService } from '../services/api';
import type { AccessRequestListResponse } from '../types';

export function useAccessRequests(
  filters: { status?: string; page?: number; limit?: number },
  options?: { enabled?: boolean }
) {
  const { enabled = true } = options || {};

  return useQuery<AccessRequestListResponse>({
    queryKey: ['access-requests', filters],
    queryFn: () =>
      apiService.getAccessRequests({
        status: filters.status,
        page: filters.page,
        limit: filters.limit,
      }),
    enabled,
    staleTime: 5000,
  });
}
