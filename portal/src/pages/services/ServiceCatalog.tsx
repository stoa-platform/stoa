/**
 * Service Catalog Page (CAB-1760)
 *
 * Unified view of all published APIs grouped by category with search and filtering.
 * Differentiates from APICatalog by showing a category-grouped layout with metadata.
 */

import { useState, useEffect, useMemo, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  Search,
  Loader2,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Layers,
  Tag,
  Clock,
  RefreshCw,
} from 'lucide-react';
import { useAPIs } from '../../hooks/useAPIs';
import type { API } from '../../types';

function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);
  useEffect(() => {
    const handler = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(handler);
  }, [value, delay]);
  return debouncedValue;
}

const statusColors: Record<string, string> = {
  published: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  deprecated: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  draft: 'bg-neutral-100 text-neutral-600 dark:bg-neutral-700 dark:text-neutral-400',
};

interface CategoryGroup {
  name: string;
  apis: API[];
}

export function ServiceCatalog() {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [collapsedCategories, setCollapsedCategories] = useState<Set<string>>(new Set());

  const debouncedSearch = useDebounce(search, 300);

  const {
    data: apisResponse,
    isLoading,
    isError,
    refetch,
  } = useAPIs({
    search: debouncedSearch || undefined,
    status: (statusFilter as 'published' | 'deprecated' | 'draft') || undefined,
    pageSize: 100,
  });

  const groupedAPIs = useMemo<CategoryGroup[]>(() => {
    const apis = apisResponse?.items || [];
    const groups = new Map<string, API[]>();

    for (const api of apis) {
      const cat = api.category || 'Uncategorized';
      const list = groups.get(cat) || [];
      list.push(api);
      groups.set(cat, list);
    }

    return Array.from(groups.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([name, apis]) => ({ name, apis }));
  }, [apisResponse]);

  const totalCount = apisResponse?.total || 0;

  const toggleCategory = useCallback((name: string) => {
    setCollapsedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }, []);

  const handleSearchChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setSearch(e.target.value);
  }, []);

  const handleStatusChange = useCallback((e: React.ChangeEvent<HTMLSelectElement>) => {
    setStatusFilter(e.target.value);
  }, []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Service Catalog</h1>
          <p className="text-neutral-500 dark:text-neutral-400 mt-1">
            Browse available APIs organized by category
          </p>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isLoading}
          className="p-2 text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded-lg transition-colors disabled:opacity-50 self-start"
          title="Refresh"
        >
          <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Search + Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-neutral-400" />
          <input
            type="text"
            placeholder="Search APIs by name, description, or tag..."
            value={search}
            onChange={handleSearchChange}
            className="w-full pl-10 pr-4 py-2 border border-neutral-200 dark:border-neutral-700 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white placeholder-neutral-400 dark:placeholder-neutral-500 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
          />
        </div>
        <select
          value={statusFilter}
          onChange={handleStatusChange}
          className="px-3 py-2 border border-neutral-200 dark:border-neutral-700 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
        >
          <option value="">All statuses</option>
          <option value="published">Published</option>
          <option value="deprecated">Deprecated</option>
          <option value="draft">Draft</option>
        </select>
      </div>

      {/* Results count */}
      {!isLoading && !isError && (
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          {totalCount} {totalCount === 1 ? 'service' : 'services'} across {groupedAPIs.length}{' '}
          {groupedAPIs.length === 1 ? 'category' : 'categories'}
        </p>
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
              <h3 className="font-medium text-red-800 dark:text-red-300">
                Failed to load services
              </h3>
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

      {/* Empty state */}
      {!isLoading && !isError && groupedAPIs.length === 0 && (
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-12 text-center">
          <Layers className="h-8 w-8 text-neutral-400 mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-neutral-900 dark:text-white mb-2">
            No services found
          </h2>
          <p className="text-neutral-500 dark:text-neutral-400">
            {search || statusFilter
              ? 'Try adjusting your search or filters.'
              : 'No APIs are published yet. Check back later!'}
          </p>
        </div>
      )}

      {/* Category groups */}
      {!isLoading &&
        !isError &&
        groupedAPIs.map((group) => {
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
                  ({group.apis.length})
                </span>
              </button>

              {!isCollapsed && (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {group.apis.map((api) => (
                    <Link
                      key={api.id}
                      to={`/apis/${api.id}`}
                      className="block p-4 bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 hover:border-primary-300 dark:hover:border-primary-600 hover:shadow-sm transition-all"
                    >
                      <div className="flex items-start justify-between gap-2 mb-2">
                        <h3 className="font-medium text-neutral-900 dark:text-white truncate">
                          {api.name}
                        </h3>
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium whitespace-nowrap ${statusColors[api.status] || statusColors.draft}`}
                        >
                          {api.status}
                        </span>
                      </div>
                      <p className="text-sm text-neutral-600 dark:text-neutral-400 line-clamp-2 mb-3">
                        {api.description || 'No description available'}
                      </p>
                      <div className="flex items-center gap-3 text-xs text-neutral-500 dark:text-neutral-400">
                        <span className="flex items-center gap-1">
                          <Tag className="h-3 w-3" />v{api.version}
                        </span>
                        {api.tenantName && <span className="truncate">{api.tenantName}</span>}
                        {api.deployedEnvironments && api.deployedEnvironments.length > 0 && (
                          <span className="flex items-center gap-1">
                            {api.deployedEnvironments.map((env) => (
                              <span
                                key={env}
                                className={`px-1.5 py-0 rounded text-[10px] font-semibold uppercase ${
                                  env === 'production'
                                    ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                                    : env === 'staging'
                                      ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
                                      : 'bg-neutral-100 text-neutral-600 dark:bg-neutral-700 dark:text-neutral-400'
                                }`}
                              >
                                {env}
                              </span>
                            ))}
                          </span>
                        )}
                        <span className="flex items-center gap-1 ml-auto">
                          <Clock className="h-3 w-3" />
                          {new Date(api.updatedAt).toLocaleDateString()}
                        </span>
                      </div>
                      {api.tags && api.tags.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-2">
                          {api.tags.slice(0, 3).map((tag) => (
                            <span
                              key={tag}
                              className="px-1.5 py-0.5 text-xs bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-400 rounded"
                            >
                              {tag}
                            </span>
                          ))}
                          {api.tags.length > 3 && (
                            <span className="text-xs text-neutral-400">+{api.tags.length - 3}</span>
                          )}
                        </div>
                      )}
                    </Link>
                  ))}
                </div>
              )}
            </section>
          );
        })}
    </div>
  );
}
