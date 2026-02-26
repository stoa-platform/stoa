/**
 * Admin Roles Hook (CAB-1454)
 *
 * React Query hook for the RBAC role management view.
 */
import { useQuery } from '@tanstack/react-query';
import { apiService } from '../services/api';
import type { RoleListResponse } from '../types';

export function useAdminRoles(options?: { enabled?: boolean }) {
  const { enabled = true } = options || {};

  return useQuery<RoleListResponse>({
    queryKey: ['admin-roles'],
    queryFn: () => apiService.getAdminRoles(),
    enabled,
    staleTime: 30000,
  });
}
