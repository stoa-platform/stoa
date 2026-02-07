/**
 * Tests for API Catalog Service
 */

import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { apiCatalogService } from './apiCatalog';

vi.mock('./api', () => ({
  apiClient: {
    get: vi.fn(),
  },
}));

import { apiClient } from './api';

const mockGet = apiClient.get as Mock;

describe('apiCatalogService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('listAPIs', () => {
    it('should call GET /v1/portal/apis and transform response', async () => {
      const portalResponse = {
        apis: [
          {
            id: 'api-1',
            name: 'payments',
            display_name: 'Payments API',
            version: '2.0',
            description: 'Payment processing',
            tenant_id: 'acme',
            tenant_name: 'Acme Corp',
            status: 'published',
            category: 'finance',
            tags: ['payments'],
            is_promoted: true,
            created_at: '2026-01-01T00:00:00Z',
            updated_at: '2026-01-15T00:00:00Z',
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
      };
      mockGet.mockResolvedValueOnce({ data: portalResponse });

      const result = await apiCatalogService.listAPIs();

      expect(mockGet).toHaveBeenCalledWith('/v1/portal/apis', {
        params: {
          page: 1,
          page_size: 20,
          search: undefined,
          category: undefined,
          universe: undefined,
          status: undefined,
          include_unpromoted: false,
        },
      });
      expect(result.items).toHaveLength(1);
      expect(result.items[0].id).toBe('api-1');
      expect(result.items[0].tenantId).toBe('acme');
      expect(result.total).toBe(1);
      expect(result.totalPages).toBe(1);
    });

    it('should pass custom search params', async () => {
      mockGet.mockResolvedValueOnce({ data: { apis: [], total: 0, page: 1, page_size: 10 } });

      await apiCatalogService.listAPIs({
        page: 2,
        pageSize: 10,
        search: 'payment',
        category: 'finance',
        status: 'published',
      });

      expect(mockGet).toHaveBeenCalledWith('/v1/portal/apis', {
        params: expect.objectContaining({
          page: 2,
          page_size: 10,
          search: 'payment',
          category: 'finance',
          status: 'published',
        }),
      });
    });

    it('should return empty response on error', async () => {
      mockGet.mockRejectedValueOnce(new Error('Network error'));

      const result = await apiCatalogService.listAPIs();

      expect(result.items).toEqual([]);
      expect(result.total).toBe(0);
    });

    it('should handle missing apis array gracefully', async () => {
      mockGet.mockResolvedValueOnce({ data: { apis: null, total: 0, page: 1, page_size: 20 } });

      const result = await apiCatalogService.listAPIs();

      expect(result.items).toEqual([]);
    });

    it('should calculate totalPages correctly', async () => {
      mockGet.mockResolvedValueOnce({
        data: { apis: [], total: 55, page: 1, page_size: 20 },
      });

      const result = await apiCatalogService.listAPIs();

      expect(result.totalPages).toBe(3); // ceil(55/20)
    });
  });

  describe('getAPI', () => {
    it('should call GET /v1/portal/apis/:id and transform', async () => {
      const portalApi = {
        id: 'api-1',
        name: 'payments',
        version: '2.0',
        description: 'desc',
        tenant_id: 'acme',
        status: 'published',
        is_promoted: true,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-15T00:00:00Z',
      };
      mockGet.mockResolvedValueOnce({ data: portalApi });

      const result = await apiCatalogService.getAPI('api-1');

      expect(mockGet).toHaveBeenCalledWith('/v1/portal/apis/api-1');
      expect(result).not.toBeNull();
      expect(result!.id).toBe('api-1');
      expect(result!.tenantId).toBe('acme');
    });

    it('should return null on error', async () => {
      mockGet.mockRejectedValueOnce(new Error('Not found'));

      const result = await apiCatalogService.getAPI('nonexistent');

      expect(result).toBeNull();
    });
  });

  describe('getOpenAPISpec', () => {
    it('should call GET /v1/portal/apis/:id/openapi', async () => {
      const spec = { openapi: '3.0.0', info: { title: 'Test' } };
      mockGet.mockResolvedValueOnce({ data: spec });

      const result = await apiCatalogService.getOpenAPISpec('api-1');

      expect(mockGet).toHaveBeenCalledWith('/v1/portal/apis/api-1/openapi');
      expect(result).toEqual(spec);
    });

    it('should return null on error', async () => {
      mockGet.mockRejectedValueOnce(new Error('Not available'));

      const result = await apiCatalogService.getOpenAPISpec('api-1');

      expect(result).toBeNull();
    });
  });

  describe('getCategories', () => {
    it('should call GET /v1/portal/api-categories', async () => {
      const categories = ['finance', 'crm', 'analytics'];
      mockGet.mockResolvedValueOnce({ data: categories });

      const result = await apiCatalogService.getCategories();

      expect(result).toEqual(categories);
    });

    it('should return empty array on error', async () => {
      mockGet.mockRejectedValueOnce(new Error('Failed'));

      const result = await apiCatalogService.getCategories();

      expect(result).toEqual([]);
    });
  });

  describe('getUniverses', () => {
    it('should call GET /v1/portal/api-universes', async () => {
      const universes = [{ id: 'u1', label: 'Finance' }];
      mockGet.mockResolvedValueOnce({ data: universes });

      const result = await apiCatalogService.getUniverses();

      expect(result).toEqual(universes);
    });

    it('should return empty array on error', async () => {
      mockGet.mockRejectedValueOnce(new Error('Failed'));

      const result = await apiCatalogService.getUniverses();

      expect(result).toEqual([]);
    });
  });

  describe('getTags', () => {
    it('should call GET /v1/portal/api-tags', async () => {
      const tags = ['payments', 'crm'];
      mockGet.mockResolvedValueOnce({ data: tags });

      const result = await apiCatalogService.getTags();

      expect(result).toEqual(tags);
    });

    it('should return empty array on error', async () => {
      mockGet.mockRejectedValueOnce(new Error('Failed'));

      const result = await apiCatalogService.getTags();

      expect(result).toEqual([]);
    });
  });
});
