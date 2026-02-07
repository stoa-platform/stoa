/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * Tests for MCP Subscriptions Service (CAB-247)
 */

import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { subscriptionsService } from './subscriptions';

vi.mock('./mcpClient', () => ({
  mcpClient: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
}));

import { mcpClient } from './mcpClient';

const mockGet = mcpClient.get as Mock;
const mockPost = mcpClient.post as Mock;
const mockDelete = mcpClient.delete as Mock;
const mockPatch = mcpClient.patch as Mock;

describe('subscriptionsService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('listSubscriptions', () => {
    it('should call GET /mcp/v1/subscriptions with default params', async () => {
      const mockData = { subscriptions: [], total: 0, page: 1, page_size: 20 };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const result = await subscriptionsService.listSubscriptions();

      expect(mockGet).toHaveBeenCalledWith('/mcp/v1/subscriptions', {
        params: { page: 1, page_size: 20, status: undefined },
      });
      expect(result).toEqual(mockData);
    });

    it('should pass custom params', async () => {
      mockGet.mockResolvedValueOnce({ data: { subscriptions: [], total: 0 } });

      await subscriptionsService.listSubscriptions({ page: 2, page_size: 10, status: 'active' });

      expect(mockGet).toHaveBeenCalledWith('/mcp/v1/subscriptions', {
        params: { page: 2, page_size: 10, status: 'active' },
      });
    });
  });

  describe('getSubscription', () => {
    it('should call GET /mcp/v1/subscriptions/:id', async () => {
      const mockSub = { id: 'sub-1', tool_id: 'tool-1', status: 'active' };
      mockGet.mockResolvedValueOnce({ data: mockSub });

      const result = await subscriptionsService.getSubscription('sub-1');

      expect(mockGet).toHaveBeenCalledWith('/mcp/v1/subscriptions/sub-1');
      expect(result.id).toBe('sub-1');
    });
  });

  describe('createSubscription', () => {
    it('should call POST /mcp/v1/subscriptions and return api_key', async () => {
      const createData = { tool_id: 'tool-1' };
      const mockResponse = {
        subscription: { id: 'sub-2', tool_id: 'tool-1' },
        api_key: 'sk-live-abc123',
      };
      mockPost.mockResolvedValueOnce({ data: mockResponse });

      const result = await subscriptionsService.createSubscription(createData as any);

      expect(mockPost).toHaveBeenCalledWith('/mcp/v1/subscriptions', createData);
      expect(result.api_key).toBe('sk-live-abc123');
    });
  });

  describe('revokeSubscription', () => {
    it('should call DELETE /mcp/v1/subscriptions/:id', async () => {
      mockDelete.mockResolvedValueOnce({});

      await subscriptionsService.revokeSubscription('sub-1');

      expect(mockDelete).toHaveBeenCalledWith('/mcp/v1/subscriptions/sub-1');
    });
  });

  describe('regenerateApiKey', () => {
    it('should call POST /mcp/v1/subscriptions/:id/regenerate', async () => {
      mockPost.mockResolvedValueOnce({ data: { api_key: 'sk-new-key' } });

      const result = await subscriptionsService.regenerateApiKey('sub-1');

      expect(mockPost).toHaveBeenCalledWith('/mcp/v1/subscriptions/sub-1/regenerate');
      expect(result.api_key).toBe('sk-new-key');
    });
  });

  describe('getConfigExport', () => {
    it('should call GET /mcp/v1/subscriptions/:id/config', async () => {
      const mockConfig = { mcpServers: { stoa: {} } };
      mockGet.mockResolvedValueOnce({ data: mockConfig });

      const result = await subscriptionsService.getConfigExport('sub-1');

      expect(mockGet).toHaveBeenCalledWith('/mcp/v1/subscriptions/sub-1/config');
      expect(result).toEqual(mockConfig);
    });
  });

  describe('getMySubscriptions', () => {
    it('should return subscriptions array from list', async () => {
      const mockData = { subscriptions: [{ id: 'sub-1' }], total: 1, page: 1, page_size: 20 };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const result = await subscriptionsService.getMySubscriptions();

      expect(result).toEqual([{ id: 'sub-1' }]);
    });
  });

  describe('revealApiKey', () => {
    it('should call POST /mcp/v1/subscriptions/:id/reveal-key without TOTP', async () => {
      const mockResponse = { api_key: 'sk-revealed', expires_in: 30 };
      mockPost.mockResolvedValueOnce({ data: mockResponse });

      const result = await subscriptionsService.revealApiKey('sub-1');

      expect(mockPost).toHaveBeenCalledWith('/mcp/v1/subscriptions/sub-1/reveal-key', {});
      expect(result.api_key).toBe('sk-revealed');
    });

    it('should include TOTP code when provided', async () => {
      mockPost.mockResolvedValueOnce({ data: { api_key: 'sk-r', expires_in: 30 } });

      await subscriptionsService.revealApiKey('sub-1', '123456');

      expect(mockPost).toHaveBeenCalledWith('/mcp/v1/subscriptions/sub-1/reveal-key', {
        totp_code: '123456',
      });
    });
  });

  describe('toggleTotpRequirement', () => {
    it('should call PATCH /mcp/v1/subscriptions/:id/totp', async () => {
      const mockResponse = { subscription_id: 'sub-1', totp_required: true, message: 'ok' };
      mockPatch.mockResolvedValueOnce({ data: mockResponse });

      const result = await subscriptionsService.toggleTotpRequirement('sub-1', true);

      expect(mockPatch).toHaveBeenCalledWith('/mcp/v1/subscriptions/sub-1/totp', null, {
        params: { enabled: true },
      });
      expect(result.totp_required).toBe(true);
    });
  });

  describe('rotateApiKey', () => {
    it('should call POST /mcp/v1/subscriptions/:id/rotate-key with default grace period', async () => {
      const mockResponse = {
        new_api_key: 'sk-rotated',
        old_key_valid_until: '2026-02-08T12:00:00Z',
        grace_period_hours: 24,
      };
      mockPost.mockResolvedValueOnce({ data: mockResponse });

      const result = await subscriptionsService.rotateApiKey('sub-1');

      expect(mockPost).toHaveBeenCalledWith('/mcp/v1/subscriptions/sub-1/rotate-key', {
        grace_period_hours: 24,
      });
      expect(result.new_api_key).toBe('sk-rotated');
    });

    it('should pass custom grace period', async () => {
      mockPost.mockResolvedValueOnce({ data: { new_api_key: 'sk-r' } });

      await subscriptionsService.rotateApiKey('sub-1', { grace_period_hours: 48 });

      expect(mockPost).toHaveBeenCalledWith('/mcp/v1/subscriptions/sub-1/rotate-key', {
        grace_period_hours: 48,
      });
    });
  });

  describe('getRotationInfo', () => {
    it('should call GET /mcp/v1/subscriptions/:id/rotation-info', async () => {
      const mockSub = { id: 'sub-1', rotation_status: 'active' };
      mockGet.mockResolvedValueOnce({ data: mockSub });

      const result = await subscriptionsService.getRotationInfo('sub-1');

      expect(mockGet).toHaveBeenCalledWith('/mcp/v1/subscriptions/sub-1/rotation-info');
      expect(result.id).toBe('sub-1');
    });
  });
});
