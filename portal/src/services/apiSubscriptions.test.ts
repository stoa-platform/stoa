/**
 * Tests for API Subscriptions Service (CAB-483)
 */

import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { apiSubscriptionsService } from './apiSubscriptions';

vi.mock('./api', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

import { apiClient } from './api';

const mockGet = apiClient.get as Mock;
const mockPost = apiClient.post as Mock;
const mockDelete = apiClient.delete as Mock;

describe('apiSubscriptionsService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('createSubscription', () => {
    it('should call POST /v1/subscriptions and return API key', async () => {
      const createData = {
        application_id: 'app-1',
        application_name: 'My App',
        api_id: 'api-1',
        api_name: 'Payments',
        api_version: '2.0',
        tenant_id: 'acme',
      };
      const mockResponse = {
        subscription_id: 'sub-1',
        api_key: 'sk-live-xyz',
        api_key_prefix: 'sk-live',
        expires_at: null,
      };
      mockPost.mockResolvedValueOnce({ data: mockResponse });

      const result = await apiSubscriptionsService.createSubscription(createData);

      expect(mockPost).toHaveBeenCalledWith('/v1/subscriptions', createData);
      expect(result.api_key).toBe('sk-live-xyz');
    });
  });

  describe('listMySubscriptions', () => {
    it('should call GET /v1/subscriptions/my with default params', async () => {
      const mockData = { items: [], total: 0, page: 1, page_size: 20, total_pages: 0 };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const result = await apiSubscriptionsService.listMySubscriptions();

      expect(mockGet).toHaveBeenCalledWith('/v1/subscriptions/my', {
        params: { page: 1, page_size: 20, status: undefined, application_id: undefined },
      });
      expect(result).toEqual(mockData);
    });

    it('should pass custom params', async () => {
      mockGet.mockResolvedValueOnce({ data: { items: [], total: 0 } });

      await apiSubscriptionsService.listMySubscriptions({
        page: 2,
        page_size: 10,
        status: 'active',
        application_id: 'app-1',
      });

      expect(mockGet).toHaveBeenCalledWith('/v1/subscriptions/my', {
        params: { page: 2, page_size: 10, status: 'active', application_id: 'app-1' },
      });
    });
  });

  describe('getSubscription', () => {
    it('should call GET /v1/subscriptions/:id', async () => {
      const mockSub = { id: 'sub-1', status: 'active' };
      mockGet.mockResolvedValueOnce({ data: mockSub });

      const result = await apiSubscriptionsService.getSubscription('sub-1');

      expect(mockGet).toHaveBeenCalledWith('/v1/subscriptions/sub-1');
      expect(result.id).toBe('sub-1');
    });
  });

  describe('cancelSubscription', () => {
    it('should call DELETE /v1/subscriptions/:id', async () => {
      mockDelete.mockResolvedValueOnce({});

      await apiSubscriptionsService.cancelSubscription('sub-1');

      expect(mockDelete).toHaveBeenCalledWith('/v1/subscriptions/sub-1');
    });
  });

  describe('rotateKey', () => {
    it('should call POST /v1/subscriptions/:id/rotate-key with default grace', async () => {
      const mockResponse = {
        subscription_id: 'sub-1',
        new_api_key: 'sk-new',
        new_api_key_prefix: 'sk-ne',
        old_key_expires_at: '2026-02-08T12:00:00Z',
        grace_period_hours: 24,
        rotation_count: 1,
      };
      mockPost.mockResolvedValueOnce({ data: mockResponse });

      const result = await apiSubscriptionsService.rotateKey('sub-1');

      expect(mockPost).toHaveBeenCalledWith('/v1/subscriptions/sub-1/rotate-key', {
        grace_period_hours: 24,
      });
      expect(result.new_api_key).toBe('sk-new');
    });

    it('should pass custom grace period', async () => {
      mockPost.mockResolvedValueOnce({ data: { new_api_key: 'sk-r' } });

      await apiSubscriptionsService.rotateKey('sub-1', { grace_period_hours: 48 });

      expect(mockPost).toHaveBeenCalledWith('/v1/subscriptions/sub-1/rotate-key', {
        grace_period_hours: 48,
      });
    });
  });

  describe('getRotationInfo', () => {
    it('should call GET /v1/subscriptions/:id/rotation-info', async () => {
      const mockInfo = { id: 'sub-1', rotation_count: 3, has_active_grace_period: true };
      mockGet.mockResolvedValueOnce({ data: mockInfo });

      const result = await apiSubscriptionsService.getRotationInfo('sub-1');

      expect(mockGet).toHaveBeenCalledWith('/v1/subscriptions/sub-1/rotation-info');
      expect(result.rotation_count).toBe(3);
    });
  });

  describe('listPendingForTenant', () => {
    it('should call GET /v1/subscriptions/tenant/{tenantId}/pending with default params', async () => {
      const mockData = { items: [], total: 0, page: 1, page_size: 20, total_pages: 0 };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const result = await apiSubscriptionsService.listPendingForTenant('acme');

      expect(mockGet).toHaveBeenCalledWith('/v1/subscriptions/tenant/acme/pending', {
        params: { page: 1, page_size: 20 },
      });
      expect(result).toEqual(mockData);
    });

    it('should pass custom params', async () => {
      mockGet.mockResolvedValueOnce({ data: { items: [], total: 0 } });

      await apiSubscriptionsService.listPendingForTenant('acme', { page: 2, page_size: 10 });

      expect(mockGet).toHaveBeenCalledWith('/v1/subscriptions/tenant/acme/pending', {
        params: { page: 2, page_size: 10 },
      });
    });
  });

  describe('approveSubscription', () => {
    it('should call POST /v1/subscriptions/{id}/approve', async () => {
      const mockResponse = { id: 'sub-1', status: 'active' };
      mockPost.mockResolvedValueOnce({ data: mockResponse });

      const result = await apiSubscriptionsService.approveSubscription('sub-1');

      expect(mockPost).toHaveBeenCalledWith('/v1/subscriptions/sub-1/approve', {
        expires_at: null,
      });
      expect(result.status).toBe('active');
    });

    it('should pass expires_at when provided', async () => {
      mockPost.mockResolvedValueOnce({ data: { id: 'sub-1', status: 'active' } });

      await apiSubscriptionsService.approveSubscription('sub-1', '2026-12-31T23:59:59Z');

      expect(mockPost).toHaveBeenCalledWith('/v1/subscriptions/sub-1/approve', {
        expires_at: '2026-12-31T23:59:59Z',
      });
    });
  });

  describe('getMySubscriptionsFormatted', () => {
    it('should return formatted subscriptions', async () => {
      const mockItems = [
        {
          id: 'sub-1',
          application_id: 'app-1',
          application_name: 'My App',
          subscriber_id: 'user-1',
          subscriber_email: 'test@acme.com',
          api_id: 'api-1',
          api_name: 'Payments',
          api_version: '2.0',
          tenant_id: 'acme',
          plan_id: null,
          plan_name: null,
          api_key_prefix: 'sk-live',
          status: 'active',
          status_reason: null,
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
          approved_at: null,
          expires_at: null,
          revoked_at: null,
          approved_by: null,
          revoked_by: null,
        },
      ];
      mockGet.mockResolvedValueOnce({
        data: { items: mockItems, total: 1, page: 1, page_size: 20, total_pages: 1 },
      });

      const result = await apiSubscriptionsService.getMySubscriptionsFormatted();

      expect(result).toHaveLength(1);
      expect(result[0].applicationId).toBe('app-1');
      expect(result[0].apiName).toBe('Payments');
    });
  });
});
