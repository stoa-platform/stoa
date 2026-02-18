/**
 * Tests for Webhooks Service (CAB-315)
 */

import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { webhooksService } from './webhooks';

vi.mock('./api', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

import { apiClient } from './api';

const mockGet = apiClient.get as Mock;
const mockPost = apiClient.post as Mock;
const mockPatch = apiClient.patch as Mock;
const mockDelete = apiClient.delete as Mock;

const TENANT = 'acme';

describe('webhooksService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getEventTypes', () => {
    it('should call GET /tenants/:id/webhooks/events', async () => {
      const mockData = { events: [{ event: 'subscription.created', description: 'desc' }] };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const result = await webhooksService.getEventTypes(TENANT);

      expect(mockGet).toHaveBeenCalledWith(`/tenants/${TENANT}/webhooks/events`);
      expect(result.events).toHaveLength(1);
    });
  });

  describe('listWebhooks', () => {
    it('should call GET /tenants/:id/webhooks', async () => {
      const mockData = { items: [{ id: 'wh-1' }], total: 1 };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const result = await webhooksService.listWebhooks(TENANT);

      expect(mockGet).toHaveBeenCalledWith(`/tenants/${TENANT}/webhooks`, {
        params: { enabled_only: undefined },
      });
      expect(result.items).toHaveLength(1);
    });

    it('should filter enabled only', async () => {
      mockGet.mockResolvedValueOnce({ data: { items: [], total: 0 } });

      await webhooksService.listWebhooks(TENANT, true);

      expect(mockGet).toHaveBeenCalledWith(`/tenants/${TENANT}/webhooks`, {
        params: { enabled_only: true },
      });
    });
  });

  describe('getWebhook', () => {
    it('should call GET /tenants/:id/webhooks/:webhookId', async () => {
      const mockData = { id: 'wh-1', url: 'https://example.com/hook' };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const result = await webhooksService.getWebhook(TENANT, 'wh-1');

      expect(mockGet).toHaveBeenCalledWith(`/tenants/${TENANT}/webhooks/wh-1`);
      expect(result.id).toBe('wh-1');
    });
  });

  describe('createWebhook', () => {
    it('should call POST /tenants/:id/webhooks', async () => {
      const createData = { url: 'https://example.com/hook', events: ['subscription.created'] };
      mockPost.mockResolvedValueOnce({ data: { id: 'wh-2', ...createData } });

      const result = await webhooksService.createWebhook(TENANT, createData as any);

      expect(mockPost).toHaveBeenCalledWith(`/tenants/${TENANT}/webhooks`, createData);
      expect(result.id).toBe('wh-2');
    });
  });

  describe('updateWebhook', () => {
    it('should call PATCH /tenants/:id/webhooks/:webhookId', async () => {
      const updateData = { url: 'https://new-url.com/hook' };
      mockPatch.mockResolvedValueOnce({ data: { id: 'wh-1', ...updateData } });

      const result = await webhooksService.updateWebhook(TENANT, 'wh-1', updateData as any);

      expect(mockPatch).toHaveBeenCalledWith(`/tenants/${TENANT}/webhooks/wh-1`, updateData);
      expect(result.url).toBe('https://new-url.com/hook');
    });
  });

  describe('deleteWebhook', () => {
    it('should call DELETE /tenants/:id/webhooks/:webhookId', async () => {
      mockDelete.mockResolvedValueOnce({});

      await webhooksService.deleteWebhook(TENANT, 'wh-1');

      expect(mockDelete).toHaveBeenCalledWith(`/tenants/${TENANT}/webhooks/wh-1`);
    });
  });

  describe('testWebhook', () => {
    it('should call POST /tenants/:id/webhooks/:webhookId/test', async () => {
      const mockResponse = { success: true, status_code: 200 };
      mockPost.mockResolvedValueOnce({ data: mockResponse });

      const result = await webhooksService.testWebhook(TENANT, 'wh-1');

      expect(mockPost).toHaveBeenCalledWith(`/tenants/${TENANT}/webhooks/wh-1/test`, {
        event_type: 'subscription.created',
      });
      expect(result.success).toBe(true);
    });

    it('should use custom event type', async () => {
      mockPost.mockResolvedValueOnce({ data: { success: true } });

      await webhooksService.testWebhook(TENANT, 'wh-1', 'api.deployed');

      expect(mockPost).toHaveBeenCalledWith(`/tenants/${TENANT}/webhooks/wh-1/test`, {
        event_type: 'api.deployed',
      });
    });
  });

  describe('getDeliveries', () => {
    it('should call GET /tenants/:id/webhooks/:webhookId/deliveries', async () => {
      const mockData = { items: [{ id: 'd-1' }], total: 1 };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const result = await webhooksService.getDeliveries(TENANT, 'wh-1');

      expect(mockGet).toHaveBeenCalledWith(`/tenants/${TENANT}/webhooks/wh-1/deliveries`, {
        params: { limit: 50 },
      });
      expect(result.items).toHaveLength(1);
    });

    it('should pass custom limit', async () => {
      mockGet.mockResolvedValueOnce({ data: { items: [], total: 0 } });

      await webhooksService.getDeliveries(TENANT, 'wh-1', 10);

      expect(mockGet).toHaveBeenCalledWith(`/tenants/${TENANT}/webhooks/wh-1/deliveries`, {
        params: { limit: 10 },
      });
    });
  });

  describe('retryDelivery', () => {
    it('should call POST /tenants/:id/webhooks/:webhookId/deliveries/:deliveryId/retry', async () => {
      mockPost.mockResolvedValueOnce({ data: { id: 'd-1', status: 'pending' } });

      const result = await webhooksService.retryDelivery(TENANT, 'wh-1', 'd-1');

      expect(mockPost).toHaveBeenCalledWith(
        `/tenants/${TENANT}/webhooks/wh-1/deliveries/d-1/retry`
      );
      expect(result.id).toBe('d-1');
    });
  });
});
