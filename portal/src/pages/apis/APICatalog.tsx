/**
 * API Catalog Page
 *
 * Browse and discover available APIs in the marketplace.
 * Optimized with debounced search and server-side filtering.
 */

import { useState, useEffect, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { BookOpen, Grid3X3, List, Loader2, AlertCircle, RefreshCw } from 'lucide-react';
import { useAPIs, useAPICategories, useUniverses } from '../../hooks/useAPIs';
import { APICard } from '../../components/apis/APICard';
import { APIFilters } from '../../components/apis/APIFilters';
import { apiCatalogService } from '../../services/apiCatalog';
import { config } from '../../config';
import { loadNamespace } from '../../i18n';
import type { API } from '../../types';

type ViewMode = 'grid' | 'list';

// Debounce hook for search optimization
function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(handler);
    };
  }, [value, delay]);

  return debouncedValue;
}

export function APICatalog() {
  const queryClient = useQueryClient();
  const { t, i18n: i18nInstance } = useTranslation('catalog');
  const i18nEnabled = config.features.enableI18n;

  useEffect(() => {
    if (i18nEnabled) {
      const lng = i18nInstance.language;
      loadNamespace(lng, 'catalog');
      if (lng !== 'en') loadNamespace('en', 'catalog');
    }
  }, [i18nEnabled, i18nInstance.language]);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [universe, setUniverse] = useState('');
  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  const [page, setPage] = useState(1);
  const pageSize = 12;

  // Prefetch API detail on hover for faster navigation
  const prefetchAPI = useCallback(
    (id: string) => {
      queryClient.prefetchQuery({
        queryKey: ['api', id],
        queryFn: () => apiCatalogService.getAPI(id),
        staleTime: 60 * 1000, // 1 minute, matches useAPI hook
      });
    },
    [queryClient]
  );

  // Debounce search for better performance (300ms delay)
  const debouncedSearch = useDebounce(search, 300);

  // Fetch APIs with debounced search and filter params
  const {
    data: apisResponse,
    isLoading: apisLoading,
    isError: apisError,
    error: apisErrorDetails,
    refetch: refetchAPIs,
  } = useAPIs({
    search: debouncedSearch || undefined,
    category: category || undefined,
    universe: universe || undefined,
    page,
    pageSize,
  });

  // Fetch available categories and universes
  const { data: categories = [], isLoading: categoriesLoading } = useAPICategories();
  const { data: universes = [] } = useUniverses();

  // Extract APIs from response - server-side filtering is sufficient
  const apis = apisResponse?.items || [];
  const totalCount = apisResponse?.total || 0;
  const totalPages = Math.ceil(totalCount / pageSize);

  // Reset page when filters change
  const handleSearchChange = (value: string) => {
    setSearch(value);
    setPage(1);
  };

  const handleCategoryChange = (value: string) => {
    setCategory(value);
    setPage(1);
  };

  const handleUniverseChange = (value: string) => {
    setUniverse(value);
    setPage(1);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            {i18nEnabled ? t('title') : 'API Catalog'}
          </h1>
          <p className="text-gray-500 dark:text-neutral-400 mt-1">
            {i18nEnabled ? t('subtitle') : 'Browse and discover available APIs'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* View mode toggle */}
          <div className="flex items-center border border-gray-200 dark:border-neutral-700 rounded-lg overflow-hidden">
            <button
              onClick={() => setViewMode('grid')}
              className={`p-2 ${
                viewMode === 'grid'
                  ? 'bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-400'
                  : 'bg-white dark:bg-neutral-800 text-gray-500 dark:text-neutral-400 hover:bg-gray-50 dark:hover:bg-neutral-700'
              }`}
              title={i18nEnabled ? t('gridView') : 'Grid view'}
            >
              <Grid3X3 className="h-4 w-4" />
            </button>
            <button
              onClick={() => setViewMode('list')}
              className={`p-2 ${
                viewMode === 'list'
                  ? 'bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-400'
                  : 'bg-white dark:bg-neutral-800 text-gray-500 dark:text-neutral-400 hover:bg-gray-50 dark:hover:bg-neutral-700'
              }`}
              title={i18nEnabled ? t('listView') : 'List view'}
            >
              <List className="h-4 w-4" />
            </button>
          </div>
          {/* Refresh button */}
          <button
            onClick={() => refetchAPIs()}
            disabled={apisLoading}
            className="p-2 text-gray-500 dark:text-neutral-400 hover:text-gray-700 dark:hover:text-neutral-200 hover:bg-gray-100 dark:hover:bg-neutral-700 rounded-lg transition-colors disabled:opacity-50"
            title={i18nEnabled ? t('refresh') : 'Refresh'}
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
        universe={universe}
        onUniverseChange={handleUniverseChange}
        universes={universes}
        isLoading={categoriesLoading}
      />

      {/* Results count */}
      {!apisLoading && !apisError && (
        <div className="text-sm text-gray-500 dark:text-neutral-400">
          {i18nEnabled
            ? totalCount === 0
              ? t('apiCount.zero')
              : totalCount === 1
                ? t('apiCount.one')
                : t('apiCount.other', { count: totalCount })
            : totalCount === 0
              ? 'No APIs found'
              : totalCount === 1
                ? '1 API available'
                : `${totalCount} APIs available`}
          {(search || category || universe) &&
            (i18nEnabled ? ` ${t('matchingFilters')}` : ' matching your filters')}
        </div>
      )}

      {/* Loading state */}
      {apisLoading && (
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 p-12 text-center">
          <Loader2 className="h-8 w-8 text-primary-600 animate-spin mx-auto mb-4" />
          <p className="text-gray-500 dark:text-neutral-400">
            {i18nEnabled ? t('loadingApis') : 'Loading APIs...'}
          </p>
        </div>
      )}

      {/* Error state */}
      {apisError && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-red-500 dark:text-red-400 mt-0.5" />
            <div>
              <h3 className="font-medium text-red-800 dark:text-red-300">
                {i18nEnabled ? t('failedToLoad') : 'Failed to load APIs'}
              </h3>
              <p className="text-sm text-red-600 dark:text-red-400 mt-1">
                {(apisErrorDetails as Error)?.message || 'An unexpected error occurred'}
              </p>
              <button
                onClick={() => refetchAPIs()}
                className="mt-3 px-4 py-2 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded-lg hover:bg-red-200 dark:hover:bg-red-900/50 text-sm font-medium transition-colors"
              >
                {i18nEnabled ? t('tryAgain') : 'Try Again'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Empty state */}
      {!apisLoading && !apisError && apis.length === 0 && (
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 p-12 text-center">
          <div className="inline-flex p-4 bg-gray-100 dark:bg-neutral-700 rounded-full mb-4">
            <BookOpen className="h-8 w-8 text-gray-400 dark:text-neutral-500" />
          </div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
            {i18nEnabled ? t('noApisFound') : 'No APIs Found'}
          </h2>
          <p className="text-gray-500 dark:text-neutral-400 max-w-md mx-auto">
            {search || category || universe
              ? i18nEnabled
                ? t('noApisFiltered')
                : 'No APIs match your current filters. Try adjusting your search criteria.'
              : i18nEnabled
                ? t('noApisYet')
                : 'There are no published APIs available yet. Check back later!'}
          </p>
          {(search || category || universe) && (
            <button
              onClick={() => {
                setSearch('');
                setCategory('');
                setUniverse('');
              }}
              className="mt-4 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
            >
              {i18nEnabled ? t('clearFilters') : 'Clear Filters'}
            </button>
          )}
        </div>
      )}

      {/* API Grid/List */}
      {!apisLoading && !apisError && apis.length > 0 && (
        <>
          {viewMode === 'grid' ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {apis.map((api: API) => (
                <APICard key={api.id} api={api} onMouseEnter={() => prefetchAPI(api.id)} />
              ))}
            </div>
          ) : (
            <div className="space-y-4">
              {apis.map((api: API) => (
                <APICard key={api.id} api={api} onMouseEnter={() => prefetchAPI(api.id)} />
              ))}
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between border-t border-gray-200 dark:border-neutral-700 pt-4">
              <div className="text-sm text-gray-500 dark:text-neutral-400">
                {i18nEnabled
                  ? t('pagination.page', { current: page, total: totalPages })
                  : `Page ${page} of ${totalPages}`}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="px-4 py-2 border border-gray-300 dark:border-neutral-600 rounded-lg text-sm font-medium text-gray-700 dark:text-neutral-200 hover:bg-gray-50 dark:hover:bg-neutral-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {i18nEnabled ? t('pagination.previous') : 'Previous'}
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="px-4 py-2 border border-gray-300 dark:border-neutral-600 rounded-lg text-sm font-medium text-gray-700 dark:text-neutral-200 hover:bg-gray-50 dark:hover:bg-neutral-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {i18nEnabled ? t('pagination.next') : 'Next'}
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
