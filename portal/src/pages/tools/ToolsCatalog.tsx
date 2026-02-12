/**
 * MCP Tools Catalog Page
 *
 * Browse and discover MCP Tools with search and category filtering.
 */

import { useState, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  Search,
  Filter,
  Wrench,
  ArrowRight,
  Star,
  Tag,
  Loader2,
  AlertCircle,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { useTools, useToolCategories, useToolCategoriesWithCounts } from '../../hooks/useTools';
import type { MCPTool } from '../../types';

type ToolStatus = 'active' | 'deprecated' | 'beta';

const statusConfig: Record<
  ToolStatus,
  {
    label: string;
    color: string;
    bg: string;
  }
> = {
  active: {
    label: 'Active',
    color: 'text-green-700 dark:text-green-400',
    bg: 'bg-green-100 dark:bg-green-900/30',
  },
  beta: {
    label: 'Beta',
    color: 'text-amber-700 dark:text-amber-400',
    bg: 'bg-amber-100 dark:bg-amber-900/30',
  },
  deprecated: {
    label: 'Deprecated',
    color: 'text-red-700 dark:text-red-400',
    bg: 'bg-red-100 dark:bg-red-900/20',
  },
};

const PAGE_SIZE = 24; // Multiple of 3 for grid layout

export function ToolsCatalog() {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('All');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [currentPage, setCurrentPage] = useState(1);
  // Debounce search query for API calls
  const [debouncedSearch, setDebouncedSearch] = useState('');

  // Debounce the search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Reset to page 1 when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [debouncedSearch, selectedCategory, selectedTags]);

  const {
    data: toolsData,
    isLoading,
    isError,
    error,
    refetch,
  } = useTools({
    category: selectedCategory !== 'All' ? selectedCategory : undefined,
    tags: selectedTags.length > 0 ? selectedTags.join(',') : undefined,
    search: debouncedSearch || undefined,
  });

  const { data: categories } = useToolCategories();
  const { data: categoriesWithCounts } = useToolCategoriesWithCounts();

  // Memoize tools to ensure stable reference for pagination useMemo
  const tools = useMemo(() => toolsData?.tools || [], [toolsData?.tools]);
  const allCategories = ['All', ...(categories || [])];

  // Pagination
  const totalPages = Math.max(1, Math.ceil(tools.length / PAGE_SIZE));
  const paginatedTools = useMemo(
    () => tools.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE),
    [tools, currentPage]
  );

  // Get tag counts from categories for display
  const getCategoryCount = (categoryName: string) => {
    if (categoryName === 'All') return toolsData?.total_count || tools.length;
    return categoriesWithCounts?.categories.find((c) => c.name === categoryName)?.count || 0;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">AI Tools Catalog</h1>
          <p className="text-gray-500 dark:text-neutral-400 mt-1">
            Discover and subscribe to AI-powered tools
          </p>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isLoading}
          className="inline-flex items-center gap-2 px-4 py-2 border border-gray-300 dark:border-neutral-600 text-gray-700 dark:text-neutral-300 rounded-lg hover:bg-gray-50 dark:hover:bg-neutral-800 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Search and Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400 dark:text-neutral-500" />
          <input
            type="text"
            placeholder="Search tools..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 dark:text-white focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter className="h-5 w-5 text-gray-400 dark:text-neutral-500" />
          <select
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
            className="px-3 py-2 border border-gray-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 dark:text-white focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          >
            {allCategories.map((cat) => (
              <option key={cat} value={cat}>
                {cat} {getCategoryCount(cat) > 0 && `(${getCategoryCount(cat)})`}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Active Filters / Tags */}
      {(selectedTags.length > 0 || selectedCategory !== 'All' || searchQuery) && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-gray-500 dark:text-neutral-400">Active filters:</span>
          {selectedCategory !== 'All' && (
            <span className="inline-flex items-center gap-1 px-3 py-1 bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-400 rounded-full text-sm">
              Category: {selectedCategory}
              <button
                onClick={() => setSelectedCategory('All')}
                className="hover:text-primary-900 dark:hover:text-primary-300 ml-1"
              >
                ×
              </button>
            </span>
          )}
          {selectedTags.map((tag) => (
            <button
              key={tag}
              type="button"
              className="inline-flex items-center gap-1 px-3 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 rounded-full text-sm cursor-pointer hover:bg-blue-200 dark:hover:bg-blue-900/50"
              onClick={() => setSelectedTags(selectedTags.filter((t) => t !== tag))}
              aria-label={`Remove ${tag} filter`}
            >
              <Tag className="h-3 w-3" aria-hidden="true" />
              {tag}
              <span className="ml-1" aria-hidden="true">
                ×
              </span>
            </button>
          ))}
          {searchQuery && (
            <span className="inline-flex items-center gap-1 px-3 py-1 bg-gray-100 dark:bg-neutral-700 text-gray-700 dark:text-neutral-300 rounded-full text-sm">
              Search: &quot;{searchQuery}&quot;
              <button
                onClick={() => setSearchQuery('')}
                className="hover:text-gray-900 dark:hover:text-white ml-1"
              >
                ×
              </button>
            </span>
          )}
          <button
            onClick={() => {
              setSearchQuery('');
              setSelectedCategory('All');
              setSelectedTags([]);
            }}
            className="text-sm text-gray-500 dark:text-neutral-400 hover:text-gray-700 dark:hover:text-neutral-200 underline"
          >
            Clear all
          </button>
        </div>
      )}

      {/* Loading state */}
      {isLoading && (
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 p-12 text-center">
          <Loader2 className="h-8 w-8 text-primary-600 animate-spin mx-auto mb-4" />
          <p className="text-gray-500 dark:text-neutral-400">Loading tools...</p>
        </div>
      )}

      {/* Error state */}
      {isError && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
            <div>
              <h3 className="font-medium text-red-800 dark:text-red-300">Failed to load tools</h3>
              <p className="text-sm text-red-600 dark:text-red-400 mt-1">
                {(error as Error)?.message || 'An unexpected error occurred'}
              </p>
              <button
                onClick={() => refetch()}
                className="mt-3 px-4 py-2 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 rounded-lg hover:bg-red-200 dark:hover:bg-red-900/50 text-sm font-medium transition-colors"
              >
                Try Again
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Tools Grid */}
      {!isLoading && !isError && tools.length > 0 && (
        <>
          <div className="flex items-center justify-between">
            <div className="text-sm text-gray-500 dark:text-neutral-400">
              {tools.length === 1 ? '1 tool' : `${tools.length} tools`}
              {selectedCategory !== 'All' && ` in ${selectedCategory}`}
              {totalPages > 1 && ` — Page ${currentPage}/${totalPages}`}
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {paginatedTools.map((tool: MCPTool, index: number) => {
              const status =
                statusConfig[(tool.status || 'active') as ToolStatus] || statusConfig.active;
              const toolId = tool.name || tool.id || `tool-${index}`; // MCP tools use name as identifier

              return (
                <Link
                  key={toolId}
                  to={`/tools/${encodeURIComponent(toolId)}`}
                  className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 p-5 hover:border-primary-300 hover:shadow-md transition-all group"
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="p-2 bg-primary-50 dark:bg-primary-900/30 rounded-lg">
                      <Wrench className="h-5 w-5 text-primary-600" />
                    </div>
                    <span
                      className={`px-2 py-1 text-xs font-medium rounded ${status.bg} ${status.color}`}
                    >
                      {status.label}
                    </span>
                  </div>

                  <h3 className="font-semibold text-gray-900 dark:text-white group-hover:text-primary-700 dark:group-hover:text-primary-400 transition-colors">
                    {tool.displayName || tool.name}
                  </h3>
                  <p className="text-sm text-gray-500 dark:text-neutral-400 mt-1 line-clamp-2">
                    {tool.description}
                  </p>

                  <div className="flex items-center gap-4 mt-4 text-sm text-gray-500 dark:text-neutral-400">
                    {tool.pricing && (
                      <div className="flex items-center gap-1">
                        <Star className="h-4 w-4 text-amber-400 fill-amber-400" />
                        <span className="capitalize">{tool.pricing.model}</span>
                      </div>
                    )}
                    {tool.rateLimit && (
                      <div className="flex items-center gap-1">
                        <Tag className="h-4 w-4" />
                        <span>
                          {tool.rateLimit.requests}/{tool.rateLimit.period}
                        </span>
                      </div>
                    )}
                  </div>

                  {/* Tags */}
                  {tool.tags && tool.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-3">
                      {tool.tags.slice(0, 3).map((toolTag: string) => (
                        <button
                          key={toolTag}
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            if (!selectedTags.includes(toolTag)) {
                              setSelectedTags([...selectedTags, toolTag]);
                            }
                          }}
                          className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full transition-colors ${
                            selectedTags.includes(toolTag)
                              ? 'bg-blue-200 dark:bg-blue-900/50 text-blue-800 dark:text-blue-300'
                              : 'bg-gray-100 dark:bg-neutral-700 text-gray-600 dark:text-neutral-400 hover:bg-blue-100 dark:hover:bg-blue-900/30 hover:text-blue-700 dark:hover:text-blue-400'
                          }`}
                        >
                          <Tag className="h-3 w-3" />
                          {toolTag}
                        </button>
                      ))}
                      {tool.tags.length > 3 && (
                        <span className="text-xs text-gray-400 dark:text-neutral-500">
                          +{tool.tags.length - 3}
                        </span>
                      )}
                    </div>
                  )}

                  <div className="flex items-center justify-between mt-4 pt-4 border-t border-gray-100 dark:border-neutral-700">
                    {tool.category ? (
                      <button
                        type="button"
                        className="text-xs font-medium text-gray-500 dark:text-neutral-400 bg-gray-100 dark:bg-neutral-700 px-2 py-1 rounded cursor-pointer hover:bg-primary-100 dark:hover:bg-primary-900/30 hover:text-primary-700 dark:hover:text-primary-400"
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setSelectedCategory(tool.category!);
                        }}
                        aria-label={`Filter by ${tool.category} category`}
                      >
                        {tool.category}
                      </button>
                    ) : (
                      <span />
                    )}
                    <span className="flex items-center gap-1 text-sm font-medium text-primary-600 group-hover:text-primary-700 dark:group-hover:text-primary-400">
                      View Details
                      <ArrowRight className="h-4 w-4" />
                    </span>
                  </div>
                </Link>
              );
            })}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-4 pt-4">
              <button
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="flex items-center gap-1 px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 dark:border-neutral-600 disabled:opacity-50 hover:bg-gray-50 dark:hover:bg-neutral-800 transition-colors dark:text-neutral-300"
              >
                <ChevronLeft className="h-4 w-4" />
                Previous
              </button>
              <span className="text-sm text-gray-500 dark:text-neutral-400">
                Page {currentPage} of {totalPages}
              </span>
              <button
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="flex items-center gap-1 px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 dark:border-neutral-600 disabled:opacity-50 hover:bg-gray-50 dark:hover:bg-neutral-800 transition-colors dark:text-neutral-300"
              >
                Next
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          )}
        </>
      )}

      {/* Empty state */}
      {!isLoading && !isError && tools.length === 0 && (
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 p-12 text-center">
          <div className="inline-flex p-4 bg-gray-100 dark:bg-neutral-700 rounded-full mb-4">
            <Wrench className="h-8 w-8 text-gray-400 dark:text-neutral-500" />
          </div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
            No Tools Found
          </h2>
          <p className="text-gray-500 dark:text-neutral-400 max-w-md mx-auto mb-6">
            {searchQuery || selectedCategory !== 'All' || selectedTags.length > 0
              ? 'No tools match your current filters. Try adjusting your search, category, or tags.'
              : 'No MCP tools are currently available. Check back later.'}
          </p>
          {(searchQuery || selectedCategory !== 'All' || selectedTags.length > 0) && (
            <button
              onClick={() => {
                setSearchQuery('');
                setSelectedCategory('All');
                setSelectedTags([]);
              }}
              className="text-primary-600 hover:text-primary-700 dark:hover:text-primary-400 font-medium"
            >
              Clear Filters
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default ToolsCatalog;
