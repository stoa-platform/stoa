/**
 * Governance Service Tests (CAB-1525)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { governanceService, getAvailableTransitions } from '../governance';

vi.mock('../api', () => ({
  apiClient: {
    post: vi.fn(),
    get: vi.fn(),
    patch: vi.fn(),
  },
}));

vi.mock('../apiSubscriptions', () => ({
  apiSubscriptionsService: {
    listPendingForTenant: vi.fn(),
    approveSubscription: vi.fn(),
  },
}));

import { apiClient } from '../api';
import { apiSubscriptionsService } from '../apiSubscriptions';

describe('governanceService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('listPendingApprovals', () => {
    it('maps subscription responses to governance approvals', async () => {
      vi.mocked(apiSubscriptionsService.listPendingForTenant).mockResolvedValue({
        items: [
          {
            id: 'sub-1',
            application_id: 'app-1',
            application_name: 'My App',
            subscriber_id: 'user-1',
            subscriber_email: 'dev@test.com',
            api_id: 'api-1',
            api_name: 'Payment API',
            api_version: '1.0',
            tenant_id: 'tenant-1',
            plan_id: null,
            plan_name: null,
            api_key_prefix: null,
            oauth_client_id: null,
            status: 'pending' as const,
            status_reason: null,
            created_at: '2026-03-01T00:00:00Z',
            updated_at: '2026-03-01T00:00:00Z',
            approved_at: null,
            expires_at: null,
            revoked_at: null,
            approved_by: null,
            revoked_by: null,
            provisioning_status: null,
            provisioning_error: null,
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      });

      const result = await governanceService.listPendingApprovals('tenant-1');

      expect(result.items).toHaveLength(1);
      expect(result.items[0]).toMatchObject({
        id: 'sub-1',
        type: 'subscription',
        requester_name: 'My App',
        requester_email: 'dev@test.com',
        resource_name: 'Payment API',
        status: 'pending',
      });
    });
  });

  describe('rejectRequest', () => {
    it('posts rejection with reason', async () => {
      vi.mocked(apiClient.post).mockResolvedValue({ data: {} });

      await governanceService.rejectRequest('sub-1', 'Not authorized');

      expect(apiClient.post).toHaveBeenCalledWith('/v1/subscriptions/sub-1/reject', {
        reason: 'Not authorized',
      });
    });
  });

  describe('transitionAPIStatus', () => {
    it('patches API status', async () => {
      vi.mocked(apiClient.patch).mockResolvedValue({ data: {} });

      await governanceService.transitionAPIStatus('api-1', 'published', 'Ready for production');

      expect(apiClient.patch).toHaveBeenCalledWith('/v1/portal/apis/api-1/status', {
        status: 'published',
        reason: 'Ready for production',
      });
    });
  });
});

describe('getAvailableTransitions', () => {
  it('returns publish for draft', () => {
    const transitions = getAvailableTransitions('draft');
    expect(transitions).toHaveLength(1);
    expect(transitions[0].to).toBe('published');
    expect(transitions[0].requiresApproval).toBe(true);
  });

  it('returns deprecate for published', () => {
    const transitions = getAvailableTransitions('published');
    expect(transitions).toHaveLength(1);
    expect(transitions[0].to).toBe('deprecated');
  });

  it('returns restore for deprecated', () => {
    const transitions = getAvailableTransitions('deprecated');
    expect(transitions).toHaveLength(1);
    expect(transitions[0].to).toBe('published');
  });
});
