/**
 * FeaturedAITools Component (CAB-691)
 *
 * Shows a preview of available AI Tools on the homepage.
 * Uses React Query via useFeaturedAITools hook for caching.
 */

import { Link } from 'react-router-dom';
import { Wrench, ArrowRight, Settings, Users, Globe } from 'lucide-react';
import { useFeaturedAITools } from '../../hooks/useDashboard';
import { config } from '../../config';

function ToolSkeleton() {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 animate-pulse">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 bg-gray-200 rounded-lg" />
        <div className="flex-1">
          <div className="h-4 w-32 bg-gray-200 rounded mb-2" />
          <div className="h-3 w-full bg-gray-200 rounded mb-1" />
          <div className="h-3 w-2/3 bg-gray-200 rounded" />
        </div>
      </div>
    </div>
  );
}

const categoryIcons: Record<string, typeof Settings> = {
  platform: Settings,
  tenant: Users,
  public: Globe,
};

export function FeaturedAITools() {
  const { data: tools = [], isLoading } = useFeaturedAITools();

  if (!config.features.enableMCPTools) {
    return null;
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200">
      <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Wrench className="h-5 w-5 text-primary-600" />
          <h2 className="font-semibold text-gray-900">AI Tools</h2>
        </div>
        <Link
          to="/servers"
          className="text-sm text-primary-600 hover:text-primary-700 font-medium flex items-center gap-1"
        >
          Browse all tools
          <ArrowRight className="h-3 w-3" />
        </Link>
      </div>

      <div className="p-4">
        {isLoading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <ToolSkeleton />
            <ToolSkeleton />
            <ToolSkeleton />
            <ToolSkeleton />
          </div>
        ) : tools.length === 0 ? (
          <div className="py-8 text-center">
            <Wrench className="h-8 w-8 text-gray-300 mx-auto mb-2" />
            <p className="text-gray-500 text-sm">No AI tools available</p>
            <p className="text-gray-400 text-xs mt-1">
              AI tools will appear here once configured
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {tools.map((tool) => {
              const CategoryIcon = categoryIcons[tool.category] || Globe;
              return (
                <Link
                  key={tool.id || tool.name}
                  to={`/servers/${tool.id || tool.name}`}
                  className="group flex items-start gap-3 p-3 rounded-lg border border-gray-100 hover:border-primary-200 hover:bg-primary-50/50 transition-all"
                >
                  <div className="p-2 bg-primary-100 rounded-lg">
                    <CategoryIcon className="h-4 w-4 text-primary-600" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="font-medium text-gray-900 group-hover:text-primary-700 truncate">
                      {tool.displayName || tool.name}
                    </h3>
                    <p className="text-xs text-gray-500 line-clamp-1 mt-0.5">
                      {tool.description}
                    </p>
                    <div className="flex items-center gap-2 mt-1.5">
                      <span className="text-xs text-gray-400 flex items-center gap-1">
                        <Wrench className="h-3 w-3" />
                        {tool.tools?.length || 0} tools
                      </span>
                      <span className="text-xs px-1.5 py-0.5 bg-gray-100 text-gray-500 rounded capitalize">
                        {tool.category}
                      </span>
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

export default FeaturedAITools;
