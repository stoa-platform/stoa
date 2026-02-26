import { useState, useMemo, useCallback } from 'react';
import { useMarketplace, useFeaturedItems } from '../../hooks/useMarketplace';
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

  const totalPages = data ? Math.ceil(data.total / pageSize) : 0;
  const showFeatured = !search && typeFilter === 'all' && !categoryFilter && page === 1;

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
