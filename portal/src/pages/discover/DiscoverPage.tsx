/**
 * Unified Discover Page (CAB-1905)
 *
 * Merges Marketplace, Service Catalog, and API Catalog into a single
 * discovery surface with type tabs, category grouping toggle, and combined filters.
 */

import { useState, useEffect, useMemo, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  Search,
  Grid3X3,
  Layers,
  Loader2,
  AlertCircle,
  RefreshCw,
  Star,
  ArrowLeftRight,
  ChevronDown,
  ChevronRight,
  X,
  Filter,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@stoa/shared/components/Button';
import { useMarketplace, useFeaturedItems } from '../../hooks/useMarketplace';
import { useUniverses, useAPITags } from '../../hooks/useAPIs';
import { useFavorites } from '../../hooks/useFavorites';
import { useAuth } from '../../contexts/AuthContext';
import { apiCatalogService } from '../../services/apiCatalog';
import { config } from '../../config';
import { MarketplaceCard } from '../../components/marketplace/MarketplaceCard';
import { MarketplaceStatsBar } from '../../components/marketplace';
import type { MarketplaceItemType, MarketplaceItem } from '../../types';

type ViewMode = 'grid' | 'grouped';

const ALL_AUDIENCE_OPTIONS = [
  { id: 'public', label: 'Public' },
  { id: 'internal', label: 'Internal' },
  { id: 'partner', label: 'Partner' },
];

const AUDIENCE_BY_ROLE: Record<string, string[]> = {
  'cpi-admin': ['public', 'internal', 'partner'],
  'tenant-admin': ['public', 'internal', 'partner'],
  devops: ['public', 'internal'],
  viewer: ['public'],
};

function getVisibleAudienceOptions(roles: string[]) {
  const allowed = new Set<string>();
  for (const role of roles) {
    for (const aud of AUDIENCE_BY_ROLE[role] || ['public']) {
      allowed.add(aud);
    }
  }
  if (allowed.size === 0) allowed.add('public');
  return ALL_AUDIENCE_OPTIONS.filter((o) => allowed.has(o.id));
}

function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);
  useEffect(() => {
    const handler = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(handler);
  }, [value, delay]);
  return debouncedValue;
}

const typeOptions: { value: MarketplaceItemType | 'all'; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'api', label: 'APIs' },
  { value: 'mcp-server', label: 'AI Tools' },
];

interface CategoryGroup {
  name: string;
  items: MarketplaceItem[];
}

export function DiscoverPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { user, isAuthenticated, hasScope } = useAuth();

  // Filters
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<MarketplaceItemType | 'all'>('all');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [audienceFilter, setAudienceFilter] = useState('');
  const [universeFilter, setUniverseFilter] = useState('');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [authTypeFilter, setAuthTypeFilter] = useState('');
  const [sortBy, setSortBy] = useState<'name' | 'updated_at' | 'created_at'>('name');
  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  const [page, setPage] = useState(1);
  const pageSize = 12;

  // Category grouping state
  const [collapsedCategories, setCollapsedCategories] = useState<Set<string>>(new Set());

  const debouncedSearch = useDebounce(search, 300);

  // Audience options based on user roles
  const visibleAudienceOptions = getVisibleAudienceOptions(user?.roles || []);

  // Marketplace data (unified: APIs + MCP servers)
  const filters = useMemo(
    () => ({
      search: debouncedSearch || undefined,
      type: typeFilter,
      category: categoryFilter || undefined,
      tags: selectedTags.length > 0 ? selectedTags : undefined,
      authType: authTypeFilter || undefined,
      sortBy,
      page,
      pageSize,
    }),
    [debouncedSearch, typeFilter, categoryFilter, selectedTags, authTypeFilter, sortBy, page]
  );

  const { data, isLoading, isError, refetch } = useMarketplace(filters);
  const { data: featuredItems } = useFeaturedItems();
  const { data: favoritesData } = useFavorites();
  const { data: universes = [] } = useUniverses();
  const { data: availableTags = [] } = useAPITags();

  const totalPages = data ? Math.ceil(data.total / pageSize) : 0;
  const showFeatured = !debouncedSearch && typeFilter === 'all' && !categoryFilter && page === 1;
  const showFavorites = config.features.enableFavorites && isAuthenticated && showFeatured;
  const favorites = favoritesData?.favorites ?? [];
  const previewFavorites = favorites.slice(0, 6);

  // Active filters check
  const hasFilters =
    search ||
    typeFilter !== 'all' ||
    categoryFilter ||
    audienceFilter ||
    universeFilter ||
    selectedTags.length > 0 ||
    authTypeFilter ||
    sortBy !== 'name';

  // Grouped view: group items by category
  const groupedItems = useMemo<CategoryGroup[]>(() => {
    if (viewMode !== 'grouped' || !data?.items) return [];
    const groups = new Map<string, MarketplaceItem[]>();
    for (const item of data.items) {
      const cat = item.category || 'Uncategorized';
      const list = groups.get(cat) || [];
      list.push(item);
      groups.set(cat, list);
    }
    return Array.from(groups.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([name, items]) => ({ name, items }));
  }, [data?.items, viewMode]);

  // Prefetch API detail on hover
  const prefetchItem = useCallback(
    (item: MarketplaceItem) => {
      if (item.type === 'api' && item.api) {
        queryClient.prefetchQuery({
          queryKey: ['api', item.api.id],
          queryFn: () => apiCatalogService.getAPI(item.api!.id),
          staleTime: 60 * 1000,
        });
      }
    },
    [queryClient]
  );

  // Filter handlers
  const handleSearchChange = useCallback((value: string) => {
    setSearch(value);
    setPage(1);
  }, []);

  const handleTypeChange = useCallback((type: MarketplaceItemType | 'all') => {
    setTypeFilter(type);
    setPage(1);
  }, []);

  const handleCategoryChange = useCallback((category: string) => {
    setCategoryFilter(category);
    setPage(1);
  }, []);

  const clearFilters = useCallback(() => {
    setSearch('');
    setTypeFilter('all');
    setCategoryFilter('');
    setAudienceFilter('');
    setUniverseFilter('');
    setSelectedTags([]);
    setAuthTypeFilter('');
    setSortBy('name');
    setPage(1);
  }, []);

  const toggleTag = useCallback((tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    );
    setPage(1);
  }, []);

  const toggleCategory = useCallback((name: string) => {
    setCollapsedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }, []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Discover</h1>
          <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
            Browse APIs and AI tools available on the platform
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* View mode toggle */}
          <div className="flex items-center border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden">
            <button
              onClick={() => setViewMode('grid')}
              className={`p-2 ${
                viewMode === 'grid'
                  ? 'bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-400'
                  : 'bg-white dark:bg-neutral-800 text-neutral-500 dark:text-neutral-400 hover:bg-neutral-50 dark:hover:bg-neutral-700'
              }`}
              title="Grid view"
            >
              <Grid3X3 className="h-4 w-4" />
            </button>
            <button
              onClick={() => setViewMode('grouped')}
              className={`p-2 ${
                viewMode === 'grouped'
                  ? 'bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-400'
                  : 'bg-white dark:bg-neutral-800 text-neutral-500 dark:text-neutral-400 hover:bg-neutral-50 dark:hover:bg-neutral-700'
              }`}
              title="Grouped by category"
            >
              <Layers className="h-4 w-4" />
            </button>
          </div>

          {/* Compare */}
          {config.features.enableAPIComparison && hasScope('stoa:catalog:read') && (
            <button
              onClick={() => navigate('/api-compare')}
              className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-neutral-700 dark:text-neutral-300 bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors"
            >
              <ArrowLeftRight className="h-4 w-4" />
              Compare
            </button>
          )}

          {/* Refresh */}
          <button
            onClick={() => refetch()}
            disabled={isLoading}
            className="p-2 text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded-lg transition-colors disabled:opacity-50"
            title="Refresh"
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Stats */}
      {data?.stats && <MarketplaceStatsBar stats={data.stats} />}

      {/* My Favorites Preview */}
      {showFavorites && (
        <section>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Star className="w-4 h-4 text-amber-500 fill-amber-500" />
              <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">
                My Favorites
              </h2>
            </div>
            {favorites.length > 0 && (
              <button
                onClick={() => navigate('/workspace?tab=subscriptions')}
                className="text-sm text-primary-600 dark:text-primary-400 hover:underline"
              >
                View all ({favorites.length})
              </button>
            )}
          </div>
          {previewFavorites.length === 0 ? (
            <p className="text-sm text-neutral-400 dark:text-neutral-500 italic">
              No favorites yet — bookmark items from their detail pages
            </p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {previewFavorites.map((fav) => (
                <button
                  key={fav.id}
                  onClick={() =>
                    navigate(
                      fav.item_type === 'api' ? `/apis/${fav.item_id}` : `/servers/${fav.item_id}`
                    )
                  }
                  className="flex items-center gap-3 p-3 bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 hover:border-primary-300 dark:hover:border-primary-600 transition-colors text-left"
                >
                  <Star className="w-4 h-4 text-amber-500 fill-amber-500 flex-shrink-0" />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-neutral-900 dark:text-white truncate">
                      {fav.item_name}
                    </p>
                    <p className="text-xs text-neutral-500 dark:text-neutral-400 truncate">
                      {fav.item_type === 'api' ? 'API' : 'MCP Server'}
                    </p>
                  </div>
                </button>
              ))}
            </div>
          )}
        </section>
      )}

      {/* Search + Filters */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4">
        <div className="flex flex-col gap-4">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-neutral-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => handleSearchChange(e.target.value)}
              placeholder="Search APIs, AI tools, and more..."
              className="w-full pl-10 pr-4 py-3 rounded-lg border border-neutral-200 bg-white text-sm placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent dark:bg-neutral-800 dark:border-neutral-700 dark:text-white"
            />
          </div>

          {/* Filter row */}
          <div className="flex flex-wrap items-center gap-3">
            {/* Type filter pills */}
            <div className="flex items-center gap-1 rounded-lg bg-neutral-100 p-1 dark:bg-neutral-700">
              {typeOptions.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => handleTypeChange(opt.value)}
                  className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                    typeFilter === opt.value
                      ? 'bg-white text-primary-700 shadow-sm dark:bg-neutral-600 dark:text-primary-400'
                      : 'text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-white'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>

            {/* Category dropdown */}
            {(data?.stats?.categories?.length ?? 0) > 0 && (
              <div className="relative sm:w-48">
                <Filter className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-neutral-400 dark:text-neutral-500" />
                <select
                  value={categoryFilter}
                  onChange={(e) => handleCategoryChange(e.target.value)}
                  className="w-full pl-10 pr-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm appearance-none bg-white dark:bg-neutral-800 dark:text-white cursor-pointer"
                >
                  <option value="">All Categories</option>
                  {data?.stats?.categories?.map((cat) => (
                    <option key={cat.id} value={cat.id}>
                      {cat.name} ({cat.count})
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Universe filter (CAB-848) */}
            {universes.length > 0 && (
              <div className="relative sm:w-44">
                <Filter className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-neutral-400 dark:text-neutral-500" />
                <select
                  value={universeFilter}
                  onChange={(e) => {
                    setUniverseFilter(e.target.value);
                    setPage(1);
                  }}
                  className="w-full pl-10 pr-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm appearance-none bg-white dark:bg-neutral-800 dark:text-white cursor-pointer"
                >
                  <option value="">All Universes</option>
                  {universes.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.label}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Audience filter */}
            {visibleAudienceOptions.length > 1 && (
              <div className="relative sm:w-44">
                <Filter className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-neutral-400 dark:text-neutral-500" />
                <select
                  value={audienceFilter}
                  onChange={(e) => {
                    setAudienceFilter(e.target.value);
                    setPage(1);
                  }}
                  className="w-full pl-10 pr-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm appearance-none bg-white dark:bg-neutral-800 dark:text-white cursor-pointer"
                >
                  <option value="">All Audiences</option>
                  {visibleAudienceOptions.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.label}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Auth type filter (CAB-1906) */}
            <div className="relative sm:w-44">
              <Filter className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-neutral-400 dark:text-neutral-500" />
              <select
                value={authTypeFilter}
                onChange={(e) => {
                  setAuthTypeFilter(e.target.value);
                  setPage(1);
                }}
                className="w-full pl-10 pr-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm appearance-none bg-white dark:bg-neutral-800 dark:text-white cursor-pointer"
              >
                <option value="">All Auth Types</option>
                <option value="oauth2">OAuth2</option>
                <option value="api_key">API Key</option>
                <option value="mtls">mTLS</option>
                <option value="basic">Basic</option>
              </select>
            </div>

            {/* Sort (CAB-1906) */}
            <div className="relative sm:w-44">
              <select
                value={sortBy}
                onChange={(e) => {
                  setSortBy(e.target.value as 'name' | 'updated_at' | 'created_at');
                  setPage(1);
                }}
                className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm appearance-none bg-white dark:bg-neutral-800 dark:text-white cursor-pointer"
              >
                <option value="name">Sort: A-Z</option>
                <option value="updated_at">Sort: Recently updated</option>
                <option value="created_at">Sort: Newest first</option>
              </select>
            </div>

            {/* Clear */}
            {hasFilters && (
              <button
                onClick={clearFilters}
                className="inline-flex items-center gap-1 px-3 py-2 text-sm text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-white hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded-lg transition-colors"
              >
                <X className="h-4 w-4" />
                Clear
              </button>
            )}
          </div>

          {/* Tag filter chips (CAB-1906) */}
          {availableTags.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 pt-3 border-t border-neutral-100 dark:border-neutral-700">
              <span className="text-xs text-neutral-500 dark:text-neutral-400 mr-1">Tags:</span>
              {availableTags.slice(0, 12).map((tag) => (
                <button
                  key={tag}
                  onClick={() => toggleTag(tag)}
                  className={`text-xs px-2.5 py-1 rounded-full transition-colors ${
                    selectedTags.includes(tag)
                      ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/40 dark:text-primary-400 font-medium'
                      : 'bg-neutral-100 text-neutral-600 hover:bg-neutral-200 dark:bg-neutral-700 dark:text-neutral-400 dark:hover:bg-neutral-600'
                  }`}
                >
                  {tag}
                  {selectedTags.includes(tag) && <span className="ml-1 font-bold">&times;</span>}
                </button>
              ))}
              {availableTags.length > 12 && (
                <span className="text-xs text-neutral-400">+{availableTags.length - 12} more</span>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Featured Section */}
      {showFeatured && featuredItems && featuredItems.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold text-neutral-900 mb-3 dark:text-white">Featured</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {featuredItems.map((item) => (
              <div key={item.id} onMouseEnter={() => prefetchItem(item)}>
                <MarketplaceCard item={item} />
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 text-primary-600 animate-spin" />
        </div>
      )}

      {/* Error */}
      {isError && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
            <div>
              <h3 className="font-medium text-red-800 dark:text-red-300">Failed to load items</h3>
              <button
                onClick={() => refetch()}
                className="mt-2 text-sm text-red-600 dark:text-red-400 hover:underline"
              >
                Try again
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Results */}
      {data && !isLoading && (
        <>
          <div className="flex items-center justify-between">
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              {data.total} {data.total === 1 ? 'item' : 'items'} found
              {hasFilters ? ' matching your filters' : ''}
            </p>
          </div>

          {data.items.length === 0 ? (
            <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-12 text-center">
              <Layers className="h-8 w-8 text-neutral-400 mx-auto mb-4" />
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-white mb-2">
                No items found
              </h2>
              <p className="text-neutral-500 dark:text-neutral-400">
                {hasFilters
                  ? 'Try adjusting your search or filters.'
                  : 'No APIs or tools are published yet. Check back later!'}
              </p>
              {hasFilters && (
                <Button className="mt-4" onClick={clearFilters}>
                  Clear Filters
                </Button>
              )}
            </div>
          ) : viewMode === 'grouped' ? (
            /* Grouped view */
            <div className="space-y-6">
              {groupedItems.map((group) => {
                const isCollapsed = collapsedCategories.has(group.name);
                return (
                  <section key={group.name} className="space-y-3">
                    <button
                      onClick={() => toggleCategory(group.name)}
                      className="flex items-center gap-2 w-full text-left group"
                    >
                      {isCollapsed ? (
                        <ChevronRight className="h-4 w-4 text-neutral-400 group-hover:text-neutral-600 dark:group-hover:text-neutral-300" />
                      ) : (
                        <ChevronDown className="h-4 w-4 text-neutral-400 group-hover:text-neutral-600 dark:group-hover:text-neutral-300" />
                      )}
                      <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">
                        {group.name}
                      </h2>
                      <span className="text-sm text-neutral-400 dark:text-neutral-500">
                        ({group.items.length})
                      </span>
                    </button>

                    {!isCollapsed && (
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        {group.items.map((item) => (
                          <div key={item.id} onMouseEnter={() => prefetchItem(item)}>
                            <MarketplaceCard item={item} />
                          </div>
                        ))}
                      </div>
                    )}
                  </section>
                );
              })}
            </div>
          ) : (
            /* Grid view */
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {data.items.map((item) => (
                <div key={item.id} onMouseEnter={() => prefetchItem(item)}>
                  <MarketplaceCard item={item} />
                </div>
              ))}
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between border-t border-neutral-200 dark:border-neutral-700 pt-4">
              <div className="text-sm text-neutral-500 dark:text-neutral-400">
                Page {page} of {totalPages}
              </div>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                >
                  Previous
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                >
                  Next
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
