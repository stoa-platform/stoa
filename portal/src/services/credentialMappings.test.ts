import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { credentialMappingsService } from './credentialMappings';

vi.mock('./api', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

import { apiClient } from './api';

const mockGet = apiClient.get as Mock;
const mockPost = apiClient.post as Mock;
const mockPut = apiClient.put as Mock;
const mockDelete = apiClient.delete as Mock;

const tenantId = 'tenant-1';

describe('credentialMappingsService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('list', () => {
    it('fetches credential mappings with params', async () => {
      const mockData = { items: [], total: 0, page: 1, page_size: 20 };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const result = await credentialMappingsService.list(tenantId, {
        consumer_id: 'c-1',
        page: 1,
      });

      expect(mockGet).toHaveBeenCalledWith(`/v1/tenants/${tenantId}/credential-mappings`, {
        params: { consumer_id: 'c-1', page: 1 },
      });
      expect(result).toEqual(mockData);
    });

    it('fetches without params', async () => {
      const mockData = { items: [], total: 0, page: 1, page_size: 20 };
      mockGet.mockResolvedValueOnce({ data: mockData });

      await credentialMappingsService.list(tenantId);

      expect(mockGet).toHaveBeenCalledWith(`/v1/tenants/${tenantId}/credential-mappings`, {
        params: undefined,
      });
    });
  });

  describe('get', () => {
    it('fetches a single credential mapping', async () => {
      const mockMapping = { id: 'cm-1', consumer_id: 'c-1', api_id: 'a-1' };
      mockGet.mockResolvedValueOnce({ data: mockMapping });

      const result = await credentialMappingsService.get(tenantId, 'cm-1');

      expect(mockGet).toHaveBeenCalledWith(`/v1/tenants/${tenantId}/credential-mappings/cm-1`);
      expect(result).toEqual(mockMapping);
    });
  });

  describe('create', () => {
    it('creates a credential mapping', async () => {
      const payload = {
        consumer_id: 'c-1',
        api_id: 'a-1',
        auth_type: 'api_key' as const,
        header_name: 'X-Api-Key',
        credential_value: 'secret',
      };
      const mockResult = { id: 'cm-new', ...payload };
      mockPost.mockResolvedValueOnce({ data: mockResult });

      const result = await credentialMappingsService.create(tenantId, payload);

      expect(mockPost).toHaveBeenCalledWith(`/v1/tenants/${tenantId}/credential-mappings`, payload);
      expect(result).toEqual(mockResult);
    });
  });

  describe('update', () => {
    it('updates a credential mapping', async () => {
      const payload = { auth_type: 'bearer' as const };
      const mockResult = { id: 'cm-1', auth_type: 'bearer' };
      mockPut.mockResolvedValueOnce({ data: mockResult });

      const result = await credentialMappingsService.update(tenantId, 'cm-1', payload);

      expect(mockPut).toHaveBeenCalledWith(
        `/v1/tenants/${tenantId}/credential-mappings/cm-1`,
        payload
      );
      expect(result).toEqual(mockResult);
    });
  });

  describe('delete', () => {
    it('deletes a credential mapping', async () => {
      mockDelete.mockResolvedValueOnce({});

      await credentialMappingsService.delete(tenantId, 'cm-1');

      expect(mockDelete).toHaveBeenCalledWith(`/v1/tenants/${tenantId}/credential-mappings/cm-1`);
    });
  });

  describe('listByConsumer', () => {
    it('fetches mappings for a specific consumer', async () => {
      const mockData = [{ id: 'cm-1', consumer_id: 'c-1' }];
      mockGet.mockResolvedValueOnce({ data: mockData });

      const result = await credentialMappingsService.listByConsumer(tenantId, 'c-1');

      expect(mockGet).toHaveBeenCalledWith(
        `/v1/tenants/${tenantId}/credential-mappings/consumer/c-1`
      );
      expect(result).toEqual(mockData);
    });
  });
});
