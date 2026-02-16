import { describe, it, expect, vi, beforeEach } from 'vitest';
import { backendApisService } from './backendApisApi';
import { apiService } from './api';

vi.mock('./api', () => ({
  apiService: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

const mockGet = vi.mocked(apiService.get);
const mockPost = vi.mocked(apiService.post);
const mockPatch = vi.mocked(apiService.patch);
const mockDelete = vi.mocked(apiService.delete);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('BackendApisService', () => {
  describe('listBackendApis', () => {
    it('calls correct endpoint with default pagination', async () => {
      mockGet.mockResolvedValue({ data: { items: [], total: 0 } } as any);
      await backendApisService.listBackendApis('t1');
      expect(mockGet).toHaveBeenCalledWith('/v1/tenants/t1/backend-apis', {
        params: { page: 1, page_size: 50, status: undefined },
      });
    });

    it('passes custom params', async () => {
      mockGet.mockResolvedValue({ data: { items: [], total: 0 } } as any);
      await backendApisService.listBackendApis('t1', { page: 2, page_size: 10, status: 'active' });
      expect(mockGet).toHaveBeenCalledWith('/v1/tenants/t1/backend-apis', {
        params: { page: 2, page_size: 10, status: 'active' },
      });
    });

    it('returns response data', async () => {
      const response = { items: [{ id: 'b1' }], total: 1 };
      mockGet.mockResolvedValue({ data: response } as any);
      const result = await backendApisService.listBackendApis('t1');
      expect(result).toEqual(response);
    });
  });

  describe('createBackendApi', () => {
    it('posts to correct endpoint', async () => {
      const payload = {
        name: 'petstore',
        display_name: 'Petstore',
        backend_url: 'https://petstore.io',
        auth_type: 'api_key' as const,
      };
      mockPost.mockResolvedValue({ data: { id: 'b1', ...payload } } as any);
      const result = await backendApisService.createBackendApi('t1', payload as any);
      expect(mockPost).toHaveBeenCalledWith('/v1/tenants/t1/backend-apis', payload);
      expect(result).toEqual({ id: 'b1', ...payload });
    });
  });

  describe('updateBackendApi', () => {
    it('patches correct endpoint', async () => {
      const update = { display_name: 'Updated' };
      mockPatch.mockResolvedValue({ data: { id: 'b1', display_name: 'Updated' } } as any);
      const result = await backendApisService.updateBackendApi('t1', 'b1', update as any);
      expect(mockPatch).toHaveBeenCalledWith('/v1/tenants/t1/backend-apis/b1', update);
      expect(result).toEqual({ id: 'b1', display_name: 'Updated' });
    });
  });

  describe('deleteBackendApi', () => {
    it('deletes correct endpoint', async () => {
      mockDelete.mockResolvedValue({ data: null } as any);
      await backendApisService.deleteBackendApi('t1', 'b1');
      expect(mockDelete).toHaveBeenCalledWith('/v1/tenants/t1/backend-apis/b1');
    });
  });

  describe('listSaasKeys', () => {
    it('calls correct endpoint with default pagination', async () => {
      mockGet.mockResolvedValue({ data: { items: [], total: 0 } } as any);
      await backendApisService.listSaasKeys('t1');
      expect(mockGet).toHaveBeenCalledWith('/v1/tenants/t1/saas-keys', {
        params: { page: 1, page_size: 50 },
      });
    });

    it('passes custom pagination', async () => {
      mockGet.mockResolvedValue({ data: { items: [], total: 0 } } as any);
      await backendApisService.listSaasKeys('t1', { page: 3, page_size: 25 });
      expect(mockGet).toHaveBeenCalledWith('/v1/tenants/t1/saas-keys', {
        params: { page: 3, page_size: 25 },
      });
    });
  });

  describe('createSaasKey', () => {
    it('posts to correct endpoint', async () => {
      const payload = { name: 'agent-key', allowed_backend_api_ids: ['b1'] };
      mockPost.mockResolvedValue({ data: { id: 'sk1', key: 'stoa_saas_xxx' } } as any);
      const result = await backendApisService.createSaasKey('t1', payload as any);
      expect(mockPost).toHaveBeenCalledWith('/v1/tenants/t1/saas-keys', payload);
      expect(result).toEqual({ id: 'sk1', key: 'stoa_saas_xxx' });
    });
  });

  describe('revokeSaasKey', () => {
    it('deletes correct endpoint', async () => {
      mockDelete.mockResolvedValue({ data: null } as any);
      await backendApisService.revokeSaasKey('t1', 'sk1');
      expect(mockDelete).toHaveBeenCalledWith('/v1/tenants/t1/saas-keys/sk1');
    });
  });
});
