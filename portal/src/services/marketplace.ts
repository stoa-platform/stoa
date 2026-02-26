import { apiCatalogService } from './apiCatalog';
import { mcpServersService } from './mcpServers';
import type {
  API,
  MCPServer,
  MarketplaceItem,
  MarketplaceCategory,
  MarketplaceFilters,
  MarketplaceStats,
} from '../types';

function apiToMarketplaceItem(api: API): MarketplaceItem {
  return {
    id: `api-${api.id}`,
    type: 'api',
    name: api.name,
    displayName: api.name,
    description: api.description || '',
    category: api.category || 'uncategorized',
    tags: api.tags || [],
    status: api.status,
    version: api.version,
    createdAt: api.createdAt,
    updatedAt: api.updatedAt,
    api,
  };
}

function mcpServerToMarketplaceItem(server: MCPServer): MarketplaceItem {
  return {
    id: `mcp-${server.id}`,
    type: 'mcp-server',
    name: server.name,
    displayName: server.displayName || server.name,
    description: server.description || '',
    category: server.category || 'uncategorized',
    tags: server.tools?.map((t) => t.name).slice(0, 5) || [],
    status: server.status,
    version: server.version,
    createdAt: server.created_at,
    updatedAt: server.updated_at,
    mcpServer: server,
  };
}

function applyFilters(items: MarketplaceItem[], filters: MarketplaceFilters): MarketplaceItem[] {
  let filtered = [...items];

  if (filters.search) {
    const q = filters.search.toLowerCase();
    filtered = filtered.filter(
      (item) =>
        item.name.toLowerCase().includes(q) ||
        item.displayName.toLowerCase().includes(q) ||
        item.description.toLowerCase().includes(q) ||
        item.tags.some((t) => t.toLowerCase().includes(q))
    );
  }

  if (filters.type && filters.type !== 'all') {
    filtered = filtered.filter((item) => item.type === filters.type);
  }

  if (filters.category) {
    filtered = filtered.filter((item) => item.category === filters.category);
  }

  if (filters.status) {
    filtered = filtered.filter((item) => item.status === filters.status);
  }

  if (filters.tags && filters.tags.length > 0) {
    filtered = filtered.filter((item) => filters.tags!.some((tag) => item.tags.includes(tag)));
  }

  return filtered;
}

function extractCategories(items: MarketplaceItem[]): MarketplaceCategory[] {
  const categoryMap = new Map<string, number>();
  for (const item of items) {
    const cat = item.category || 'uncategorized';
    categoryMap.set(cat, (categoryMap.get(cat) || 0) + 1);
  }
  return Array.from(categoryMap.entries())
    .map(([name, count]) => ({ id: name, name, count }))
    .sort((a, b) => b.count - a.count);
}

export const marketplaceService = {
  getItems: async (
    filters?: MarketplaceFilters
  ): Promise<{ items: MarketplaceItem[]; total: number; stats: MarketplaceStats }> => {
    try {
      const [apisResult, servers] = await Promise.all([
        apiCatalogService.listAPIs({ page: 1, pageSize: 100 }),
        mcpServersService.getServers(),
      ]);

      const apiItems = apisResult.items.map(apiToMarketplaceItem);
      const serverItems = servers.map(mcpServerToMarketplaceItem);
      const allItems = [...apiItems, ...serverItems];

      const categories = extractCategories(allItems);
      const stats: MarketplaceStats = {
        totalAPIs: apiItems.length,
        totalMCPServers: serverItems.length,
        totalItems: allItems.length,
        categories,
      };

      const filtered = filters ? applyFilters(allItems, filters) : allItems;

      // Client-side pagination
      const page = filters?.page || 1;
      const pageSize = filters?.pageSize || 20;
      const start = (page - 1) * pageSize;
      const paginated = filtered.slice(start, start + pageSize);

      return { items: paginated, total: filtered.length, stats };
    } catch (error) {
      console.error('Failed to fetch marketplace items:', error);
      return {
        items: [],
        total: 0,
        stats: { totalAPIs: 0, totalMCPServers: 0, totalItems: 0, categories: [] },
      };
    }
  },

  getFeaturedItems: async (): Promise<MarketplaceItem[]> => {
    try {
      const [apisResult, servers] = await Promise.all([
        apiCatalogService.listAPIs({ page: 1, pageSize: 6 }),
        mcpServersService.getServers(),
      ]);

      const apiItems = apisResult.items.slice(0, 3).map((api) => ({
        ...apiToMarketplaceItem(api),
        featured: true,
      }));
      const serverItems = servers.slice(0, 3).map((server) => ({
        ...mcpServerToMarketplaceItem(server),
        featured: true,
      }));

      return [...apiItems, ...serverItems];
    } catch (error) {
      console.error('Failed to fetch featured items:', error);
      return [];
    }
  },
};
