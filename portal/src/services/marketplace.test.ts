import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { marketplaceService } from './marketplace';

vi.mock('./apiCatalog', () => ({
  apiCatalogService: {
    listAPIs: vi.fn(),
  },
}));

vi.mock('./mcpServers', () => ({
  mcpServersService: {
    getServers: vi.fn(),
  },
}));

import { apiCatalogService } from './apiCatalog';
import { mcpServersService } from './mcpServers';

const mockListAPIs = apiCatalogService.listAPIs as Mock;
const mockGetServers = mcpServersService.getServers as Mock;

const mockAPIs = [
  {
    id: 'api-1',
    name: 'Payment API',
    description: 'Process payments',
    category: 'finance',
    tags: ['payment', 'stripe'],
    status: 'active',
    version: '2.0',
    createdAt: '2026-01-01',
    updatedAt: '2026-01-15',
  },
  {
    id: 'api-2',
    name: 'Auth API',
    description: 'Authentication service',
    category: 'security',
    tags: ['oauth', 'jwt'],
    status: 'active',
    version: '1.0',
    createdAt: '2026-01-05',
    updatedAt: '2026-01-10',
  },
];

const mockServers = [
  {
    id: 'mcp-1',
    name: 'data-fetcher',
    displayName: 'Data Fetcher',
    description: 'Fetch data from sources',
    category: 'data',
    tools: [{ name: 'fetch' }, { name: 'transform' }],
    status: 'active',
    version: '1.0',
    created_at: '2026-02-01',
    updated_at: '2026-02-10',
  },
];

describe('marketplaceService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListAPIs.mockResolvedValue({ items: mockAPIs, total: 2 });
    mockGetServers.mockResolvedValue(mockServers);
  });

  describe('getItems', () => {
    it('returns combined API and MCP server items', async () => {
      const result = await marketplaceService.getItems();

      expect(result.items).toHaveLength(3);
      expect(result.total).toBe(3);
      expect(result.stats.totalAPIs).toBe(2);
      expect(result.stats.totalMCPServers).toBe(1);
      expect(result.stats.totalItems).toBe(3);
    });

    it('filters by type', async () => {
      const result = await marketplaceService.getItems({ type: 'api' });

      expect(result.items).toHaveLength(2);
      expect(result.items.every((item) => item.type === 'api')).toBe(true);
    });

    it('filters by search term', async () => {
      const result = await marketplaceService.getItems({ search: 'payment' });

      expect(result.items).toHaveLength(1);
      expect(result.items[0].name).toBe('Payment API');
    });

    it('filters by category', async () => {
      const result = await marketplaceService.getItems({ category: 'finance' });

      expect(result.items).toHaveLength(1);
      expect(result.items[0].name).toBe('Payment API');
    });

    it('paginates results', async () => {
      const result = await marketplaceService.getItems({ page: 1, pageSize: 2 });

      expect(result.items).toHaveLength(2);
      expect(result.total).toBe(3);
    });

    it('extracts categories with counts', async () => {
      const result = await marketplaceService.getItems();

      expect(result.stats.categories).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ name: 'finance', count: 1 }),
          expect.objectContaining({ name: 'security', count: 1 }),
          expect.objectContaining({ name: 'data', count: 1 }),
        ])
      );
    });

    it('returns fallback on error', async () => {
      mockListAPIs.mockRejectedValueOnce(new Error('Network error'));

      const result = await marketplaceService.getItems();

      expect(result.items).toEqual([]);
      expect(result.total).toBe(0);
      expect(result.stats.totalItems).toBe(0);
    });
  });

  describe('getFeaturedItems', () => {
    it('returns top 3 APIs and top 3 MCP servers', async () => {
      const result = await marketplaceService.getFeaturedItems();

      expect(result).toHaveLength(3); // 2 APIs + 1 MCP server (only 1 available)
      expect(result.every((item) => item.featured)).toBe(true);
    });

    it('returns empty array on error', async () => {
      mockListAPIs.mockRejectedValueOnce(new Error('Network error'));

      const result = await marketplaceService.getFeaturedItems();

      expect(result).toEqual([]);
    });
  });
});
