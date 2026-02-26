/**
 * FeaturedAPIs Component (CAB-691)
 *
 * Shows a preview of available APIs on the homepage.
 * Uses React Query via useFeaturedAPIs hook for caching.
 */

import { Link } from 'react-router-dom';
import { BookOpen, ArrowRight, Globe, Lock, Tag } from 'lucide-react';
import { useFeaturedAPIs } from '../../hooks/useDashboard';
import { config } from '../../config';

function APISkeleton() {
  return (
    <div className="bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 animate-pulse">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 bg-neutral-200 dark:bg-neutral-700 rounded-lg" />
        <div className="flex-1">
          <div className="h-4 w-32 bg-neutral-200 dark:bg-neutral-700 rounded mb-2" />
          <div className="h-3 w-full bg-neutral-200 dark:bg-neutral-700 rounded mb-1" />
          <div className="h-3 w-2/3 bg-neutral-200 dark:bg-neutral-700 rounded" />
        </div>
      </div>
    </div>
  );
}

export function FeaturedAPIs() {
  const { data: apis = [], isLoading } = useFeaturedAPIs();

  if (!config.features.enableAPICatalog) {
    return null;
  }

  return (
    <div className="bg-white dark:bg-neutral-900 rounded-xl border border-neutral-200 dark:border-neutral-700">
      <div className="px-5 py-4 border-b border-neutral-100 dark:border-neutral-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BookOpen className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
          <h2 className="font-semibold text-neutral-900 dark:text-white">API Catalog</h2>
        </div>
        <Link
          to="/apis"
          className="text-sm text-primary-600 hover:text-primary-700 font-medium flex items-center gap-1"
        >
          Browse all APIs
          <ArrowRight className="h-3 w-3" />
        </Link>
      </div>

      <div className="p-4">
        {isLoading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <APISkeleton />
            <APISkeleton />
            <APISkeleton />
            <APISkeleton />
          </div>
        ) : apis.length === 0 ? (
          <div className="py-8 text-center">
            <BookOpen className="h-8 w-8 text-neutral-300 dark:text-neutral-600 mx-auto mb-2" />
            <p className="text-neutral-500 dark:text-neutral-400 text-sm">No APIs available</p>
            <p className="text-neutral-400 dark:text-neutral-500 text-xs mt-1">
              APIs will appear here once published
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {apis.map((api) => (
              <Link
                key={api.id || api.name}
                to={`/apis/${api.name}`}
                className="group flex items-start gap-3 p-3 rounded-lg border border-neutral-100 dark:border-neutral-800 hover:border-primary-200 dark:hover:border-primary-800 hover:bg-primary-50/50 dark:hover:bg-primary-950/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-neutral-900 transition-all"
              >
                <div className="p-2 bg-indigo-100 dark:bg-indigo-900/50 rounded-lg">
                  <BookOpen className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="font-medium text-neutral-900 dark:text-white group-hover:text-primary-700 dark:group-hover:text-primary-400 truncate">
                      {api.displayName || api.name}
                    </h3>
                    {api.visibility === 'internal' ? (
                      <Lock className="h-3 w-3 text-neutral-400" />
                    ) : (
                      <Globe className="h-3 w-3 text-neutral-400" />
                    )}
                  </div>
                  <p className="text-xs text-neutral-500 dark:text-neutral-400 line-clamp-1 mt-0.5">
                    {api.description}
                  </p>
                  {api.tags && api.tags.length > 0 && (
                    <div className="flex items-center gap-1 mt-1.5">
                      <Tag className="h-3 w-3 text-neutral-400" />
                      <span className="text-xs text-neutral-400">
                        {api.tags.slice(0, 2).join(', ')}
                      </span>
                    </div>
                  )}
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default FeaturedAPIs;
