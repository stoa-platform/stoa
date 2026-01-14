/**
 * API Catalog Page
 *
 * Browse and discover available APIs in the marketplace.
 */

import { useState, useMemo } from 'react';
import { BookOpen, Grid3X3, List, Loader2, AlertCircle, RefreshCw } from 'lucide-react';
import { useAPIs, useAPICategories } from '../../hooks/useAPIs';
import { APICard } from '../../components/apis/APICard';
import { APIFilters } from '../../components/apis/APIFilters';
import type { API } from '../../types';

type ViewMode = 'grid' | 'list';

export function APICatalog() {
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  const [page, setPage] = useState(1);
  const pageSize = 12;

  // Fetch APIs with search and filter params
  const {
    data: apisResponse,
    isLoading: apisLoading,
    isError: apisError,
    error: apisErrorDetails,
    refetch: refetchAPIs,
  } = useAPIs({
    search: search || undefined,
    category: category || undefined,
    page,
    pageSize,
    // Don't filter by status - show all APIs (draft, published, deprecated)
  });

  // Fetch available categories
  const { data: categories = [], isLoading: categoriesLoading } = useAPICategories();

  // Extract APIs from response
  const apis = apisResponse?.items || [];
  const totalCount = apisResponse?.total || 0;
  const totalPages = Math.ceil(totalCount / pageSize);

  // Filter APIs client-side for immediate feedback (in addition to server-side filtering)
  const filteredAPIs = useMemo(() => {
    if (!apis.length) return [];

    return apis.filter((api: API) => {
      // Search filter (already applied server-side, but double-check for consistency)
      if (search) {
        const searchLower = search.toLowerCase();
        const matchesSearch =
          api.name.toLowerCase().includes(searchLower) ||
          api.description?.toLowerCase().includes(searchLower) ||
          api.tags?.some((tag) => tag.toLowerCase().includes(searchLower));
        if (!matchesSearch) return false;
      }

      // Category filter (already applied server-side)
      if (category && api.category !== category) {
        return false;
      }

      return true;
    });
  }, [apis, search, category]);

  // Reset page when filters change
  const handleSearchChange = (value: string) => {
    setSearch(value);
    setPage(1);
  };

  const handleCategoryChange = (value: string) => {
    setCategory(value);
    setPage(1);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">API Catalog</h1>
          <p className="text-gray-500 mt-1">
            Browse and discover available APIs
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* View mode toggle */}
          <div className="flex items-center border border-gray-200 rounded-lg overflow-hidden">
            <button
              onClick={() => setViewMode('grid')}
              className={`p-2 ${
                viewMode === 'grid'
                  ? 'bg-primary-50 text-primary-700'
                  : 'bg-white text-gray-500 hover:bg-gray-50'
              }`}
              title="Grid view"
            >
              <Grid3X3 className="h-4 w-4" />
            </button>
            <button
              onClick={() => setViewMode('list')}
              className={`p-2 ${
                viewMode === 'list'
                  ? 'bg-primary-50 text-primary-700'
                  : 'bg-white text-gray-500 hover:bg-gray-50'
              }`}
              title="List view"
            >
              <List className="h-4 w-4" />
            </button>
          </div>
          {/* Refresh button */}
          <button
            onClick={() => refetchAPIs()}
            disabled={apisLoading}
            className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50"
            title="Refresh"
          >
            <RefreshCw className={`h-4 w-4 ${apisLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Filters */}
      <APIFilters
        search={search}
        onSearchChange={handleSearchChange}
        category={category}
        onCategoryChange={handleCategoryChange}
        categories={categories}
        isLoading={categoriesLoading}
      />

      {/* Results count */}
      {!apisLoading && !apisError && (
        <div className="text-sm text-gray-500">
          {totalCount === 0 ? (
            'No APIs found'
          ) : totalCount === 1 ? (
            '1 API available'
          ) : (
            `${totalCount} APIs available`
          )}
          {(search || category) && ` matching your filters`}
        </div>
      )}

      {/* Loading state */}
      {apisLoading && (
        <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
          <Loader2 className="h-8 w-8 text-primary-600 animate-spin mx-auto mb-4" />
          <p className="text-gray-500">Loading APIs...</p>
        </div>
      )}

      {/* Error state */}
      {apisError && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-6">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
            <div>
              <h3 className="font-medium text-red-800">Failed to load APIs</h3>
              <p className="text-sm text-red-600 mt-1">
                {(apisErrorDetails as Error)?.message || 'An unexpected error occurred'}
              </p>
              <button
                onClick={() => refetchAPIs()}
                className="mt-3 px-4 py-2 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 text-sm font-medium transition-colors"
              >
                Try Again
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Empty state */}
      {!apisLoading && !apisError && filteredAPIs.length === 0 && (
        <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
          <div className="inline-flex p-4 bg-gray-100 rounded-full mb-4">
            <BookOpen className="h-8 w-8 text-gray-400" />
          </div>
          <h2 className="text-xl font-semibold text-gray-900 mb-2">No APIs Found</h2>
          <p className="text-gray-500 max-w-md mx-auto">
            {search || category
              ? 'No APIs match your current filters. Try adjusting your search criteria.'
              : 'There are no published APIs available yet. Check back later!'}
          </p>
          {(search || category) && (
            <button
              onClick={() => {
                setSearch('');
                setCategory('');
              }}
              className="mt-4 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
            >
              Clear Filters
            </button>
          )}
        </div>
      )}

      {/* API Grid/List */}
      {!apisLoading && !apisError && filteredAPIs.length > 0 && (
        <>
          {viewMode === 'grid' ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {filteredAPIs.map((api: API) => (
                <APICard key={api.id} api={api} />
              ))}
            </div>
          ) : (
            <div className="space-y-4">
              {filteredAPIs.map((api: API) => (
                <APICard key={api.id} api={api} />
              ))}
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between border-t border-gray-200 pt-4">
              <div className="text-sm text-gray-500">
                Page {page} of {totalPages}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Previous
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default APICatalog;
