/**
 * Admin Users Hook (CAB-1454)
 *
 * React Query hook for the admin user management table.
 */
import { useQuery } from '@tanstack/react-query';
import { apiService } from '../services/api';
import type { AdminUserListResponse } from '../types';

export function useAdminUsers(
  filters: {
    role?: string;
    status?: string;
    search?: string;
    page?: number;
    limit?: number;
  },
  options?: { enabled?: boolean }
) {
  const { enabled = true } = options || {};

  return useQuery<AdminUserListResponse>({
    queryKey: ['admin-users', filters],
    queryFn: () =>
      apiService.getAdminUsers({
        role: filters.role,
        status: filters.status,
        search: filters.search,
        page: filters.page,
        limit: filters.limit,
      }),
    enabled,
    staleTime: 5000,
  });
}
