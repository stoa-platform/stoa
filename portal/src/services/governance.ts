/**
 * STOA Developer Portal - Governance Service (CAB-1525)
 *
 * Provides governance operations: approval queue, API lifecycle management,
 * and governance statistics aggregation.
 *
 * Uses existing Control-Plane API endpoints:
 * - /v1/subscriptions/tenant/{tenant_id}/pending — pending approvals
 * - /v1/subscriptions/{id}/approve — approve subscription
 * - /v1/subscriptions/{id}/reject — reject subscription
 * - /v1/portal/apis — API catalog with status filtering
 */

import { apiClient } from './api';

/** Maximum page_size accepted by the portal/apis endpoint */
const API_MAX_PAGE_SIZE = 100;
import type {
  GovernanceStats,
  GovernanceApproval,
  APILifecycleTransition,
  APILifecycleStatus,
} from '../types';
import { apiSubscriptionsService, type APISubscriptionResponse } from './apiSubscriptions';

// ============ Lifecycle Transitions ============

export const LIFECYCLE_TRANSITIONS: APILifecycleTransition[] = [
  { from: 'draft', to: 'published', label: 'Publish', requiresApproval: true },
  { from: 'published', to: 'deprecated', label: 'Deprecate', requiresApproval: false },
  { from: 'deprecated', to: 'published', label: 'Restore', requiresApproval: true },
];

export function getAvailableTransitions(
  currentStatus: APILifecycleStatus
): APILifecycleTransition[] {
  return LIFECYCLE_TRANSITIONS.filter((t) => t.from === currentStatus);
}

// ============ Helper: Map subscription to approval ============

function subscriptionToApproval(sub: APISubscriptionResponse): GovernanceApproval {
  return {
    id: sub.id,
    type: 'subscription',
    requester_name: sub.application_name,
    requester_email: sub.subscriber_email,
    resource_name: sub.api_name,
    resource_id: sub.api_id,
    details: `${sub.application_name} → ${sub.api_name} v${sub.api_version}${sub.plan_name ? ` (${sub.plan_name})` : ''}`,
    status:
      sub.status === 'pending' ? 'pending' : sub.status === 'active' ? 'approved' : 'rejected',
    created_at: sub.created_at,
    reviewed_at: sub.approved_at || sub.revoked_at || undefined,
    reviewed_by: sub.approved_by || sub.revoked_by || undefined,
  };
}

// ============ Service ============

export const governanceService = {
  /**
   * List pending approvals for a tenant
   */
  listPendingApprovals: async (
    tenantId: string,
    params?: { page?: number; page_size?: number }
  ): Promise<{ items: GovernanceApproval[]; total: number }> => {
    const response = await apiSubscriptionsService.listPendingForTenant(tenantId, params);
    return {
      items: response.items.map(subscriptionToApproval),
      total: response.total,
    };
  },

  /**
   * Approve a pending subscription request
   */
  approveRequest: async (approvalId: string, expiresAt?: string): Promise<void> => {
    await apiSubscriptionsService.approveSubscription(approvalId, expiresAt);
  },

  /**
   * Reject a pending subscription request
   * POST /v1/subscriptions/{id}/reject
   */
  rejectRequest: async (approvalId: string, reason?: string): Promise<void> => {
    await apiClient.post(`/v1/subscriptions/${approvalId}/reject`, {
      reason: reason || 'Rejected by governance admin',
    });
  },

  /**
   * Get governance statistics for a tenant
   * Aggregates data from multiple endpoints
   */
  getStats: async (tenantId: string): Promise<GovernanceStats> => {
    const pendingResponse = await apiSubscriptionsService.listPendingForTenant(tenantId, {
      page_size: 1,
    });

    // Fetch all APIs with pagination (API max page_size is 100)
    const allApis: { status: string }[] = [];
    let page = 1;
    let total = Infinity;
    while (allApis.length < total) {
      const response = await apiClient.get<{
        apis: { status: string }[];
        total: number;
        page: number;
        page_size: number;
      }>('/v1/portal/apis', {
        params: { page, page_size: API_MAX_PAGE_SIZE },
      });
      allApis.push(...response.data.apis);
      total = response.data.total;
      page++;
    }

    const apisByStatus: Record<string, number> = {};
    for (const api of allApis) {
      apisByStatus[api.status] = (apisByStatus[api.status] || 0) + 1;
    }

    return {
      pending_approvals: pendingResponse.total,
      apis_by_status: apisByStatus,
      total_subscriptions: 0,
      active_subscriptions: 0,
    };
  },

  /**
   * Transition an API to a new lifecycle status
   * PATCH /v1/portal/apis/{id}/status
   */
  transitionAPIStatus: async (
    apiId: string,
    newStatus: APILifecycleStatus,
    reason?: string
  ): Promise<void> => {
    await apiClient.patch(`/v1/portal/apis/${apiId}/status`, {
      status: newStatus,
      reason,
    });
  },
};

export default governanceService;
