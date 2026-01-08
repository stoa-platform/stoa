/**
 * MCP Tools Catalog Page
 *
 * Browse and discover MCP Tools with search and category filtering.
 */

import { useState, useEffect } from 'react';
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
} from 'lucide-react';
import { useTools, useToolCategories, useToolCategoriesWithCounts } from '../../hooks/useTools';
import type { MCPTool } from '../../types';

type ToolStatus = 'active' | 'deprecated' | 'beta';

const statusConfig: Record<ToolStatus, {
  label: string;
  color: string;
  bg: string;
}> = {
  active: { label: 'Active', color: 'text-green-700', bg: 'bg-green-100' },
  beta: { label: 'Beta', color: 'text-amber-700', bg: 'bg-amber-100' },
  deprecated: { label: 'Deprecated', color: 'text-red-700', bg: 'bg-red-100' },
};

export function ToolsCatalog() {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('All');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  // Debounce search query for API calls
  const [debouncedSearch, setDebouncedSearch] = useState('');

  // Debounce the search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

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

  const tools = toolsData?.tools || [];
  const allCategories = ['All', ...(categories || [])];

  // Get tag counts from categories for display
  const getCategoryCount = (categoryName: string) => {
    if (categoryName === 'All') return toolsData?.total_count || tools.length;
    return categoriesWithCounts?.categories.find(c => c.name === categoryName)?.count || 0;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">MCP Tools Catalog</h1>
          <p className="text-gray-500 mt-1">
            Discover and subscribe to AI-powered tools
          </p>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isLoading}
          className="inline-flex items-center gap-2 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Search and Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
          <input
            type="text"
            placeholder="Search tools..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter className="h-5 w-5 text-gray-400" />
          <select
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
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
          <span className="text-sm text-gray-500">Active filters:</span>
          {selectedCategory !== 'All' && (
            <span className="inline-flex items-center gap-1 px-3 py-1 bg-primary-100 text-primary-700 rounded-full text-sm">
              Category: {selectedCategory}
              <button
                onClick={() => setSelectedCategory('All')}
                className="hover:text-primary-900 ml-1"
              >
                ×
              </button>
            </span>
          )}
          {selectedTags.map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center gap-1 px-3 py-1 bg-blue-100 text-blue-700 rounded-full text-sm cursor-pointer hover:bg-blue-200"
              onClick={() => setSelectedTags(selectedTags.filter(t => t !== tag))}
            >
              <Tag className="h-3 w-3" />
              {tag}
              <span className="ml-1">×</span>
            </span>
          ))}
          {searchQuery && (
            <span className="inline-flex items-center gap-1 px-3 py-1 bg-gray-100 text-gray-700 rounded-full text-sm">
              Search: "{searchQuery}"
              <button
                onClick={() => setSearchQuery('')}
                className="hover:text-gray-900 ml-1"
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
            className="text-sm text-gray-500 hover:text-gray-700 underline"
          >
            Clear all
          </button>
        </div>
      )}

      {/* Loading state */}
      {isLoading && (
        <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
          <Loader2 className="h-8 w-8 text-primary-600 animate-spin mx-auto mb-4" />
          <p className="text-gray-500">Loading tools...</p>
        </div>
      )}

      {/* Error state */}
      {isError && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-6">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
            <div>
              <h3 className="font-medium text-red-800">Failed to load tools</h3>
              <p className="text-sm text-red-600 mt-1">
                {(error as Error)?.message || 'An unexpected error occurred'}
              </p>
              <button
                onClick={() => refetch()}
                className="mt-3 px-4 py-2 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 text-sm font-medium transition-colors"
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
          <div className="text-sm text-gray-500">
            {tools.length === 1 ? '1 tool' : `${tools.length} tools`}
            {selectedCategory !== 'All' && ` in ${selectedCategory}`}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {tools.map((tool: MCPTool, index: number) => {
              const status = statusConfig[(tool.status || 'active') as ToolStatus] || statusConfig.active;
              const toolId = tool.name || tool.id || `tool-${index}`; // MCP tools use name as identifier

              return (
                <Link
                  key={toolId}
                  to={`/tools/${encodeURIComponent(toolId)}`}
                  className="bg-white rounded-lg border border-gray-200 p-5 hover:border-primary-300 hover:shadow-md transition-all group"
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="p-2 bg-primary-50 rounded-lg">
                      <Wrench className="h-5 w-5 text-primary-600" />
                    </div>
                    <span className={`px-2 py-1 text-xs font-medium rounded ${status.bg} ${status.color}`}>
                      {status.label}
                    </span>
                  </div>

                  <h3 className="font-semibold text-gray-900 group-hover:text-primary-700 transition-colors">
                    {tool.displayName || tool.name}
                  </h3>
                  <p className="text-sm text-gray-500 mt-1 line-clamp-2">
                    {tool.description}
                  </p>

                  <div className="flex items-center gap-4 mt-4 text-sm text-gray-500">
                    {tool.pricing && (
                      <div className="flex items-center gap-1">
                        <Star className="h-4 w-4 text-amber-400 fill-amber-400" />
                        <span className="capitalize">{tool.pricing.model}</span>
                      </div>
                    )}
                    {tool.rateLimit && (
                      <div className="flex items-center gap-1">
                        <Tag className="h-4 w-4" />
                        <span>{tool.rateLimit.requests}/{tool.rateLimit.period}</span>
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
                              ? 'bg-blue-200 text-blue-800'
                              : 'bg-gray-100 text-gray-600 hover:bg-blue-100 hover:text-blue-700'
                          }`}
                        >
                          <Tag className="h-3 w-3" />
                          {toolTag}
                        </button>
                      ))}
                      {tool.tags.length > 3 && (
                        <span className="text-xs text-gray-400">+{tool.tags.length - 3}</span>
                      )}
                    </div>
                  )}

                  <div className="flex items-center justify-between mt-4 pt-4 border-t border-gray-100">
                    {tool.category ? (
                      <span
                        className="text-xs font-medium text-gray-500 bg-gray-100 px-2 py-1 rounded cursor-pointer hover:bg-primary-100 hover:text-primary-700"
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setSelectedCategory(tool.category!);
                        }}
                      >
                        {tool.category}
                      </span>
                    ) : (
                      <span />
                    )}
                    <span className="flex items-center gap-1 text-sm font-medium text-primary-600 group-hover:text-primary-700">
                      View Details
                      <ArrowRight className="h-4 w-4" />
                    </span>
                  </div>
                </Link>
              );
            })}
          </div>
        </>
      )}

      {/* Empty state */}
      {!isLoading && !isError && tools.length === 0 && (
        <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
          <div className="inline-flex p-4 bg-gray-100 rounded-full mb-4">
            <Wrench className="h-8 w-8 text-gray-400" />
          </div>
          <h2 className="text-xl font-semibold text-gray-900 mb-2">No Tools Found</h2>
          <p className="text-gray-500 max-w-md mx-auto mb-6">
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
              className="text-primary-600 hover:text-primary-700 font-medium"
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
