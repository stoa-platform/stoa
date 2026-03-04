import { useState, useMemo, useCallback } from 'react';
import { Star } from 'lucide-react';
import { useMarketplace, useFeaturedItems } from '../../hooks/useMarketplace';
import { useFavorites } from '../../hooks/useFavorites';
import { useAuth } from '../../contexts/AuthContext';
import { config } from '../../config';
import {
  MarketplaceSearch,
  MarketplaceFilterBar,
  MarketplaceCard,
  MarketplaceStatsBar,
} from '../../components/marketplace';
import type { MarketplaceItemType } from '../../types';

export function MarketplacePage() {
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<MarketplaceItemType | 'all'>('all');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 12;

  const filters = useMemo(
    () => ({
      search: search || undefined,
      type: typeFilter,
      category: categoryFilter || undefined,
      page,
      pageSize,
    }),
    [search, typeFilter, categoryFilter, page]
  );

  const { data, isLoading, isError } = useMarketplace(filters);
  const { data: featuredItems } = useFeaturedItems();
  const { isAuthenticated } = useAuth();
  const { data: favoritesData } = useFavorites();

  const totalPages = data ? Math.ceil(data.total / pageSize) : 0;
  const showFeatured = !search && typeFilter === 'all' && !categoryFilter && page === 1;
  const showFavorites = config.features.enableFavorites && isAuthenticated && showFeatured;
  const favorites = favoritesData?.favorites ?? [];
  const previewFavorites = favorites.slice(0, 6);

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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Marketplace</h1>
        <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
          Discover APIs and AI tools available on the platform
        </p>
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
              <a
                href="/favorites"
                className="text-sm text-primary-600 dark:text-primary-400 hover:underline"
              >
                View all ({favorites.length})
              </a>
            )}
          </div>
          {previewFavorites.length === 0 ? (
            <p className="text-sm text-neutral-400 dark:text-neutral-500 italic">
              No favorites yet — bookmark items from their detail pages
            </p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {previewFavorites.map((fav) => (
                <a
                  key={fav.id}
                  href={
                    fav.item_type === 'api' ? `/apis/${fav.item_id}` : `/mcp-servers/${fav.item_id}`
                  }
                  className="flex items-center gap-3 p-3 bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 hover:border-primary-300 dark:hover:border-primary-600 transition-colors"
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
                </a>
              ))}
            </div>
          )}
        </section>
      )}

      {/* Search + Filters */}
      <div className="space-y-3">
        <MarketplaceSearch value={search} onChange={handleSearchChange} />
        <MarketplaceFilterBar
          selectedType={typeFilter}
          onTypeChange={handleTypeChange}
          categories={data?.stats.categories || []}
          selectedCategory={categoryFilter}
          onCategoryChange={handleCategoryChange}
        />
      </div>

      {/* Featured Section */}
      {showFeatured && featuredItems && featuredItems.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold text-neutral-900 mb-3 dark:text-white">Featured</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {featuredItems.map((item) => (
              <MarketplaceCard key={item.id} item={item} />
            ))}
          </div>
        </section>
      )}

      {/* Results */}
      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin h-8 w-8 border-2 border-emerald-500 border-t-transparent rounded-full" />
        </div>
      )}

      {isError && (
        <div className="text-center py-12">
          <p className="text-neutral-500 dark:text-neutral-400">
            Failed to load marketplace items. Please try again.
          </p>
        </div>
      )}

      {data && !isLoading && (
        <>
          <div className="flex items-center justify-between">
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              {data.total} {data.total === 1 ? 'item' : 'items'} found
            </p>
          </div>

          {data.items.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-neutral-500 dark:text-neutral-400">
                No items match your filters. Try adjusting your search.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {data.items.map((item) => (
                <MarketplaceCard key={item.id} item={item} />
              ))}
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 pt-4">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="px-3 py-1.5 text-sm rounded-md border border-neutral-200
                  disabled:opacity-50 disabled:cursor-not-allowed
                  hover:bg-neutral-50 dark:border-neutral-700 dark:hover:bg-neutral-800"
              >
                Previous
              </button>
              <span className="text-sm text-neutral-600 dark:text-neutral-400">
                Page {page} of {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="px-3 py-1.5 text-sm rounded-md border border-neutral-200
                  disabled:opacity-50 disabled:cursor-not-allowed
                  hover:bg-neutral-50 dark:border-neutral-700 dark:hover:bg-neutral-800"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
