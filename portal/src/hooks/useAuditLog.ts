/**
 * Audit Log Hooks (CAB-1470)
 */

import { useQuery } from '@tanstack/react-query';
import { auditLogService } from '../services/auditLog';
import { useAuth } from '../contexts/AuthContext';
import type { AuditLogResponse, AuditLogFilters } from '../types';

export function useAuditLog(filters?: AuditLogFilters) {
  const { isAuthenticated, accessToken } = useAuth();

  return useQuery<AuditLogResponse>({
    queryKey: ['audit-log', filters],
    queryFn: () => auditLogService.getEntries(filters),
    enabled: isAuthenticated && !!accessToken,
    staleTime: 30 * 1000,
  });
}
