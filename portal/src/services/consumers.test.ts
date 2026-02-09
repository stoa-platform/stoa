/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * Tests for Consumer Service (CAB-1121 P5)
 */

import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { consumersService } from './consumers';

vi.mock('./api', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
  },
}));

import { apiClient } from './api';

const mockGet = apiClient.get as Mock;
const mockPost = apiClient.post as Mock;
const mockPut = apiClient.put as Mock;

describe('consumersService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('register', () => {
    it('should call POST /v1/consumers/{tenantId}', async () => {
      const data = { name: 'My App', external_id: 'my-app', contact_email: 'dev@acme.com' };
      const mockResponse = { id: 'consumer-1', ...data, status: 'active' };
      mockPost.mockResolvedValueOnce({ data: mockResponse });

      const result = await consumersService.register('acme', data as any);

      expect(mockPost).toHaveBeenCalledWith('/v1/consumers/acme', data);
      expect(result.id).toBe('consumer-1');
    });
  });

  describe('list', () => {
    it('should call GET /v1/consumers/{tenantId} with default params', async () => {
      const mockData = { items: [], total: 0, page: 1, page_size: 20, total_pages: 0 };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const result = await consumersService.list('acme');

      expect(mockGet).toHaveBeenCalledWith('/v1/consumers/acme', {
        params: { page: 1, page_size: 20, status: undefined },
      });
      expect(result).toEqual(mockData);
    });

    it('should pass custom params', async () => {
      mockGet.mockResolvedValueOnce({ data: { items: [], total: 0 } });

      await consumersService.list('acme', { page: 2, pageSize: 10, status: 'active' });

      expect(mockGet).toHaveBeenCalledWith('/v1/consumers/acme', {
        params: { page: 2, page_size: 10, status: 'active' },
      });
    });
  });

  describe('get', () => {
    it('should call GET /v1/consumers/{tenantId}/{consumerId}', async () => {
      const mockConsumer = { id: 'consumer-1', name: 'My App' };
      mockGet.mockResolvedValueOnce({ data: mockConsumer });

      const result = await consumersService.get('acme', 'consumer-1');

      expect(mockGet).toHaveBeenCalledWith('/v1/consumers/acme/consumer-1');
      expect(result.id).toBe('consumer-1');
    });
  });

  describe('update', () => {
    it('should call PUT /v1/consumers/{tenantId}/{consumerId}', async () => {
      const updateData = { name: 'Updated App' };
      const mockResponse = { id: 'consumer-1', name: 'Updated App' };
      mockPut.mockResolvedValueOnce({ data: mockResponse });

      const result = await consumersService.update('acme', 'consumer-1', updateData as any);

      expect(mockPut).toHaveBeenCalledWith('/v1/consumers/acme/consumer-1', updateData);
      expect(result.name).toBe('Updated App');
    });
  });

  describe('getCredentials', () => {
    it('should call GET /v1/consumers/{tenantId}/{consumerId}/credentials', async () => {
      const mockCreds = {
        client_id: 'client-123',
        client_secret: 'secret-xyz',
        token_endpoint: 'https://auth.gostoa.dev/realms/stoa/protocol/openid-connect/token',
        grant_type: 'client_credentials',
      };
      mockGet.mockResolvedValueOnce({ data: mockCreds });

      const result = await consumersService.getCredentials('acme', 'consumer-1');

      expect(mockGet).toHaveBeenCalledWith('/v1/consumers/acme/consumer-1/credentials');
      expect(result.client_id).toBe('client-123');
      expect(result.client_secret).toBe('secret-xyz');
    });
  });

  describe('suspend', () => {
    it('should call POST /v1/consumers/{tenantId}/{consumerId}/suspend', async () => {
      const mockResponse = { id: 'consumer-1', status: 'suspended' };
      mockPost.mockResolvedValueOnce({ data: mockResponse });

      const result = await consumersService.suspend('acme', 'consumer-1');

      expect(mockPost).toHaveBeenCalledWith('/v1/consumers/acme/consumer-1/suspend');
      expect(result.status).toBe('suspended');
    });
  });

  describe('activate', () => {
    it('should call POST /v1/consumers/{tenantId}/{consumerId}/activate', async () => {
      const mockResponse = { id: 'consumer-1', status: 'active' };
      mockPost.mockResolvedValueOnce({ data: mockResponse });

      const result = await consumersService.activate('acme', 'consumer-1');

      expect(mockPost).toHaveBeenCalledWith('/v1/consumers/acme/consumer-1/activate');
      expect(result.status).toBe('active');
    });
  });
});
