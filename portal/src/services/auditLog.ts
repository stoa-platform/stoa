/**
 * Audit Log Service (CAB-1470)
 */

import { apiClient } from './api';
import type { AuditLogResponse, AuditLogFilters } from '../types';

async function getEntries(filters?: AuditLogFilters): Promise<AuditLogResponse> {
  try {
    const response = await apiClient.get<AuditLogResponse>('/v1/portal/audit-log', {
      params: filters,
    });
    return response.data;
  } catch {
    console.warn('Audit log endpoint not available, using fallback');
    return { entries: [], total: 0, page: 1, limit: 25 };
  }
}

export const auditLogService = {
  getEntries,
};
