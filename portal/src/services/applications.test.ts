/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * Tests for Applications Service
 */

import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { applicationsService } from './applications';

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

describe('applicationsService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('listApplications', () => {
    it('should call GET /v1/applications with default params', async () => {
      const mockData = { items: [], total: 0 };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const result = await applicationsService.listApplications();

      expect(mockGet).toHaveBeenCalledWith('/v1/applications', {
        params: { page: 1, page_size: 20, status: undefined },
      });
      expect(result).toEqual(mockData);
    });

    it('should pass custom params', async () => {
      const mockData = { items: [], total: 0 };
      mockGet.mockResolvedValueOnce({ data: mockData });

      await applicationsService.listApplications({ page: 2, pageSize: 10, status: 'active' });

      expect(mockGet).toHaveBeenCalledWith('/v1/applications', {
        params: { page: 2, page_size: 10, status: 'active' },
      });
    });
  });

  describe('getApplication', () => {
    it('should call GET /v1/applications/:id', async () => {
      const mockApp = { id: 'app-1', name: 'My App' };
      mockGet.mockResolvedValueOnce({ data: mockApp });

      const result = await applicationsService.getApplication('app-1');

      expect(mockGet).toHaveBeenCalledWith('/v1/applications/app-1');
      expect(result).toEqual(mockApp);
    });
  });

  describe('createApplication', () => {
    it('should call POST /v1/applications', async () => {
      const createData = { name: 'New App', description: 'Test' };
      const mockResponse = { id: 'app-2', ...createData, clientSecret: 'secret-123' };
      mockPost.mockResolvedValueOnce({ data: mockResponse });

      const result = await applicationsService.createApplication(createData as any);

      expect(mockPost).toHaveBeenCalledWith('/v1/applications', createData);
      expect(result.clientSecret).toBe('secret-123');
    });
  });

  describe('updateApplication', () => {
    it('should call PATCH /v1/applications/:id', async () => {
      const updateData = { name: 'Updated App' };
      const mockResponse = { id: 'app-1', name: 'Updated App' };
      mockPatch.mockResolvedValueOnce({ data: mockResponse });

      const result = await applicationsService.updateApplication('app-1', updateData);

      expect(mockPatch).toHaveBeenCalledWith('/v1/applications/app-1', updateData);
      expect(result.name).toBe('Updated App');
    });
  });

  describe('deleteApplication', () => {
    it('should call DELETE /v1/applications/:id', async () => {
      mockDelete.mockResolvedValueOnce({});

      await applicationsService.deleteApplication('app-1');

      expect(mockDelete).toHaveBeenCalledWith('/v1/applications/app-1');
    });
  });

  describe('regenerateSecret', () => {
    it('should call POST /v1/applications/:id/regenerate-secret', async () => {
      const mockResponse = { clientSecret: 'new-secret-456' };
      mockPost.mockResolvedValueOnce({ data: mockResponse });

      const result = await applicationsService.regenerateSecret('app-1');

      expect(mockPost).toHaveBeenCalledWith('/v1/applications/app-1/regenerate-secret');
      expect(result.clientSecret).toBe('new-secret-456');
    });
  });
});
