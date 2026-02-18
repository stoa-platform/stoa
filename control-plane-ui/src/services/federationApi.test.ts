import { describe, it, expect, vi, beforeEach } from 'vitest';
import { federationService } from './federationApi';
import { apiService } from './api';

vi.mock('./api', () => ({
  apiService: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

const mockGet = vi.mocked(apiService.get);
const mockPost = vi.mocked(apiService.post);
const mockPut = vi.mocked(apiService.put);
const mockPatch = vi.mocked(apiService.patch);
const mockDelete = vi.mocked(apiService.delete);

beforeEach(() => {
  vi.clearAllMocks();
});

const T = 'tenant-1';
const M = 'master-1';
const S = 'sub-1';

describe('FederationService', () => {
  describe('listMasterAccounts', () => {
    it('calls correct endpoint', async () => {
      mockGet.mockResolvedValue({ data: { items: [], total: 0 } } as any);
      const result = await federationService.listMasterAccounts(T);
      expect(mockGet).toHaveBeenCalledWith(`/v1/tenants/${T}/federation/accounts`);
      expect(result).toEqual({ items: [], total: 0 });
    });
  });

  describe('getMasterAccount', () => {
    it('calls correct endpoint', async () => {
      mockGet.mockResolvedValue({ data: { id: M, name: 'Test' } } as any);
      const result = await federationService.getMasterAccount(T, M);
      expect(mockGet).toHaveBeenCalledWith(`/v1/tenants/${T}/federation/accounts/${M}`);
      expect(result).toEqual({ id: M, name: 'Test' });
    });
  });

  describe('createMasterAccount', () => {
    it('posts to correct endpoint', async () => {
      const payload = { name: 'Partner', max_sub_accounts: 10 };
      mockPost.mockResolvedValue({ data: { id: M, ...payload } } as any);
      const result = await federationService.createMasterAccount(T, payload);
      expect(mockPost).toHaveBeenCalledWith(`/v1/tenants/${T}/federation/accounts`, payload);
      expect(result).toEqual({ id: M, ...payload });
    });
  });

  describe('updateMasterAccount', () => {
    it('patches correct endpoint', async () => {
      const update = { status: 'suspended' as const };
      mockPatch.mockResolvedValue({ data: { id: M, status: 'suspended' } } as any);
      const result = await federationService.updateMasterAccount(T, M, update);
      expect(mockPatch).toHaveBeenCalledWith(`/v1/tenants/${T}/federation/accounts/${M}`, update);
      expect(result).toEqual({ id: M, status: 'suspended' });
    });
  });

  describe('deleteMasterAccount', () => {
    it('deletes correct endpoint', async () => {
      mockDelete.mockResolvedValue({ data: null } as any);
      await federationService.deleteMasterAccount(T, M);
      expect(mockDelete).toHaveBeenCalledWith(`/v1/tenants/${T}/federation/accounts/${M}`);
    });
  });

  describe('listSubAccounts', () => {
    it('calls correct endpoint', async () => {
      mockGet.mockResolvedValue({ data: { items: [], total: 0 } } as any);
      const result = await federationService.listSubAccounts(T, M);
      expect(mockGet).toHaveBeenCalledWith(
        `/v1/tenants/${T}/federation/accounts/${M}/sub-accounts`
      );
      expect(result).toEqual({ items: [], total: 0 });
    });
  });

  describe('createSubAccount', () => {
    it('posts to correct endpoint', async () => {
      const payload = { name: 'Agent' };
      mockPost.mockResolvedValue({ data: { id: S, api_key: 'key-123', ...payload } } as any);
      const result = await federationService.createSubAccount(T, M, payload);
      expect(mockPost).toHaveBeenCalledWith(
        `/v1/tenants/${T}/federation/accounts/${M}/sub-accounts`,
        payload
      );
      expect(result).toEqual({ id: S, api_key: 'key-123', ...payload });
    });
  });

  describe('revokeSubAccount', () => {
    it('posts to correct endpoint', async () => {
      mockPost.mockResolvedValue({ data: { id: S, status: 'revoked' } } as any);
      const result = await federationService.revokeSubAccount(T, M, S);
      expect(mockPost).toHaveBeenCalledWith(
        `/v1/tenants/${T}/federation/accounts/${M}/sub-accounts/${S}/revoke`
      );
      expect(result).toEqual({ id: S, status: 'revoked' });
    });
  });

  describe('getToolAllowList', () => {
    it('calls correct endpoint', async () => {
      mockGet.mockResolvedValue({ data: { allowed_tools: ['tool-1'] } } as any);
      const result = await federationService.getToolAllowList(T, M, S);
      expect(mockGet).toHaveBeenCalledWith(
        `/v1/tenants/${T}/federation/accounts/${M}/sub-accounts/${S}/tools`
      );
      expect(result).toEqual({ allowed_tools: ['tool-1'] });
    });
  });

  describe('updateToolAllowList', () => {
    it('puts to correct endpoint', async () => {
      mockPut.mockResolvedValue({ data: { allowed_tools: ['tool-1', 'tool-2'] } } as any);
      const result = await federationService.updateToolAllowList(T, M, S, ['tool-1', 'tool-2']);
      expect(mockPut).toHaveBeenCalledWith(
        `/v1/tenants/${T}/federation/accounts/${M}/sub-accounts/${S}/tools`,
        { allowed_tools: ['tool-1', 'tool-2'] }
      );
      expect(result).toEqual({ allowed_tools: ['tool-1', 'tool-2'] });
    });
  });
});
