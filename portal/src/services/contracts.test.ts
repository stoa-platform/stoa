/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * Tests for Contracts Service (UAC)
 */

import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { contractsService } from './contracts';

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

describe('contractsService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('listContracts', () => {
    it('should call GET /v1/contracts', async () => {
      const mockData = { items: [], total: 0 };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const result = await contractsService.listContracts();

      expect(mockGet).toHaveBeenCalledWith('/v1/contracts', { params: undefined });
      expect(result).toEqual(mockData);
    });

    it('should pass query params', async () => {
      mockGet.mockResolvedValueOnce({ data: { items: [], total: 0 } });

      await contractsService.listContracts({ page: 2, page_size: 10, status: 'published' });

      expect(mockGet).toHaveBeenCalledWith('/v1/contracts', {
        params: { page: 2, page_size: 10, status: 'published' },
      });
    });
  });

  describe('getContract', () => {
    it('should call GET /v1/contracts/:id', async () => {
      const mockContract = { id: 'c-1', name: 'Payments UAC' };
      mockGet.mockResolvedValueOnce({ data: mockContract });

      const result = await contractsService.getContract('c-1');

      expect(mockGet).toHaveBeenCalledWith('/v1/contracts/c-1');
      expect(result.id).toBe('c-1');
    });
  });

  describe('createContract', () => {
    it('should call POST /v1/contracts', async () => {
      const createData = { name: 'New Contract', description: 'desc' };
      const mockResponse = { id: 'c-2', ...createData };
      mockPost.mockResolvedValueOnce({ data: mockResponse });

      const result = await contractsService.createContract(createData as any);

      expect(mockPost).toHaveBeenCalledWith('/v1/contracts', createData);
      expect(result.id).toBe('c-2');
    });
  });

  describe('publishContract', () => {
    it('should call POST /v1/contracts with status published', async () => {
      const createData = { name: 'Contract', description: 'desc' };
      const mockResponse = { id: 'c-3', bindings: [] };
      mockPost.mockResolvedValueOnce({ data: mockResponse });

      const result = await contractsService.publishContract(createData as any);

      expect(mockPost).toHaveBeenCalledWith('/v1/contracts', {
        ...createData,
        status: 'published',
      });
      expect(result.id).toBe('c-3');
    });
  });

  describe('updateContract', () => {
    it('should call PATCH /v1/contracts/:id', async () => {
      const updateData = { name: 'Updated' };
      mockPatch.mockResolvedValueOnce({ data: { id: 'c-1', name: 'Updated' } });

      const result = await contractsService.updateContract('c-1', updateData as any);

      expect(mockPatch).toHaveBeenCalledWith('/v1/contracts/c-1', updateData);
      expect(result.name).toBe('Updated');
    });
  });

  describe('deleteContract', () => {
    it('should call DELETE /v1/contracts/:id', async () => {
      mockDelete.mockResolvedValueOnce({});

      await contractsService.deleteContract('c-1');

      expect(mockDelete).toHaveBeenCalledWith('/v1/contracts/c-1');
    });
  });

  describe('getBindings', () => {
    it('should call GET /v1/contracts/:id/bindings', async () => {
      const mockBindings = {
        bindings: [
          { protocol: 'rest', status: 'active' },
          { protocol: 'mcp', status: 'active' },
        ],
      };
      mockGet.mockResolvedValueOnce({ data: mockBindings });

      const result = await contractsService.getBindings('c-1');

      expect(mockGet).toHaveBeenCalledWith('/v1/contracts/c-1/bindings');
      expect(result.bindings).toHaveLength(2);
    });
  });

  describe('enableBinding', () => {
    it('should call POST /v1/contracts/:id/bindings', async () => {
      const mockResponse = { protocol: 'graphql', status: 'active' };
      mockPost.mockResolvedValueOnce({ data: mockResponse });

      const result = await contractsService.enableBinding('c-1', 'graphql' as any);

      expect(mockPost).toHaveBeenCalledWith('/v1/contracts/c-1/bindings', {
        protocol: 'graphql',
      });
      expect(result.protocol).toBe('graphql');
    });
  });

  describe('disableBinding', () => {
    it('should call DELETE /v1/contracts/:id/bindings/:protocol', async () => {
      const mockResponse = { protocol: 'kafka', status: 'disabled' };
      mockDelete.mockResolvedValueOnce({ data: mockResponse });

      const result = await contractsService.disableBinding('c-1', 'kafka' as any);

      expect(mockDelete).toHaveBeenCalledWith('/v1/contracts/c-1/bindings/kafka');
      expect(result.protocol).toBe('kafka');
    });
  });
});
