import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Search, Filter, Tag, RefreshCw, Wrench, AlertCircle } from 'lucide-react';
import { mcpGatewayService } from '../../services/mcpGatewayApi';
import { ToolCard } from '../../components/tools';
import type { MCPTool } from '../../types';

export function ToolCatalog() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // State
  const [tools, setTools] = useState<MCPTool[]>([]);
  const [tags, setTags] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [totalCount, setTotalCount] = useState(0);

  // Filters from URL
  const searchQuery = searchParams.get('search') || '';
  const selectedTag = searchParams.get('tag') || '';
  const selectedTenant = searchParams.get('tenant') || '';

  // Load data
  const loadTools = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const [toolsResponse, tagsResponse] = await Promise.all([
        mcpGatewayService.getTools({
          search: searchQuery || undefined,
          tag: selectedTag || undefined,
          tenant: selectedTenant || undefined,
          limit: 50,
        }),
        mcpGatewayService.getToolTags(),
      ]);

      setTools(toolsResponse.tools);
      setTotalCount(toolsResponse.totalCount);
      setTags(tagsResponse);
    } catch (err) {
      console.error('Failed to load tools:', err);
      setError(err instanceof Error ? err.message : 'Failed to load tools');
    } finally {
      setLoading(false);
    }
  }, [searchQuery, selectedTag, selectedTenant]);

  useEffect(() => {
    loadTools();
  }, [loadTools]);

  // Handlers
  const handleSearch = (value: string) => {
    const params = new URLSearchParams(searchParams);
    if (value) {
      params.set('search', value);
    } else {
      params.delete('search');
    }
    setSearchParams(params);
  };

  const handleTagFilter = (tag: string) => {
    const params = new URLSearchParams(searchParams);
    if (tag && tag !== selectedTag) {
      params.set('tag', tag);
    } else {
      params.delete('tag');
    }
    setSearchParams(params);
  };

  const handleToolClick = (tool: MCPTool) => {
    navigate(`/ai-tools/${encodeURIComponent(tool.name)}`);
  };

  const clearFilters = () => {
    setSearchParams(new URLSearchParams());
  };

  const hasActiveFilters = searchQuery || selectedTag || selectedTenant;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">AI Tool Catalog</h1>
          <p className="text-sm text-gray-500 mt-1">
            Browse MCP tools available for AI-powered API interactions
          </p>
        </div>
        <button
          onClick={loadTools}
          className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-50 transition-colors"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Filters Bar */}
      <div className="bg-white rounded-lg border border-gray-200 p-4">
        <div className="flex flex-wrap items-center gap-4">
          {/* Search */}
          <div className="flex-1 min-w-[250px]">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <input
                type="text"
                placeholder="Search tools by name or description..."
                value={searchQuery}
                onChange={(e) => handleSearch(e.target.value)}
                className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
          </div>

          {/* Tag Filter */}
          <div className="relative">
            <select
              value={selectedTag}
              onChange={(e) => handleTagFilter(e.target.value)}
              className="appearance-none pl-10 pr-8 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">All Tags</option>
              {tags.map((tag) => (
                <option key={tag} value={tag}>
                  {tag}
                </option>
              ))}
            </select>
            <Tag className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          </div>

          {/* Clear Filters */}
          {hasActiveFilters && (
            <button
              onClick={clearFilters}
              className="flex items-center gap-1 px-3 py-2 text-sm text-gray-600 hover:text-gray-900 transition-colors"
            >
              <Filter className="h-4 w-4" />
              Clear filters
            </button>
          )}
        </div>

        {/* Active Filters */}
        {hasActiveFilters && (
          <div className="flex flex-wrap gap-2 mt-3 pt-3 border-t border-gray-100">
            {searchQuery && (
              <span className="inline-flex items-center gap-1 px-2 py-1 bg-blue-50 text-blue-700 rounded text-xs">
                Search: {searchQuery}
                <button onClick={() => handleSearch('')} className="hover:text-blue-900">
                  &times;
                </button>
              </span>
            )}
            {selectedTag && (
              <span className="inline-flex items-center gap-1 px-2 py-1 bg-green-50 text-green-700 rounded text-xs">
                Tag: {selectedTag}
                <button onClick={() => handleTagFilter('')} className="hover:text-green-900">
                  &times;
                </button>
              </span>
            )}
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
          <AlertCircle className="h-5 w-5 flex-shrink-0" />
          <span className="text-sm">{error}</span>
          <button onClick={loadTools} className="ml-auto text-sm underline hover:no-underline">
            Retry
          </button>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
        </div>
      )}

      {/* Results */}
      {!loading && !error && (
        <>
          {/* Results Count */}
          <div className="flex items-center justify-between text-sm text-gray-500">
            <span>
              Showing {tools.length} of {totalCount} tools
            </span>
          </div>

          {/* Tools Grid */}
          {tools.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {tools.map((tool) => (
                <ToolCard
                  key={tool.name}
                  tool={tool}
                  onClick={() => handleToolClick(tool)}
                />
              ))}
            </div>
          ) : (
            <div className="text-center py-12 bg-white rounded-lg border border-gray-200">
              <Wrench className="h-12 w-12 text-gray-300 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-gray-900 mb-2">No tools found</h3>
              <p className="text-sm text-gray-500">
                {hasActiveFilters
                  ? 'Try adjusting your search or filter criteria'
                  : 'No tools are available at the moment'}
              </p>
              {hasActiveFilters && (
                <button
                  onClick={clearFilters}
                  className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 transition-colors"
                >
                  Clear all filters
                </button>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
