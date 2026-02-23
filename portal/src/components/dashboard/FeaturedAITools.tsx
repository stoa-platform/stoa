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
    <div className="bg-white dark:bg-neutral-900 rounded-xl border border-neutral-200 dark:border-neutral-700">
      <div className="px-5 py-4 border-b border-neutral-100 dark:border-neutral-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Wrench className="h-5 w-5 text-primary-600 dark:text-primary-400" />
          <h2 className="font-semibold text-neutral-900 dark:text-white">AI Tools</h2>
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
            <Wrench className="h-8 w-8 text-neutral-300 dark:text-neutral-600 mx-auto mb-2" />
            <p className="text-neutral-500 dark:text-neutral-400 text-sm">No AI tools available</p>
            <p className="text-neutral-400 dark:text-neutral-500 text-xs mt-1">
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
                  className="group flex items-start gap-3 p-3 rounded-lg border border-neutral-100 dark:border-neutral-800 hover:border-primary-200 dark:hover:border-primary-800 hover:bg-primary-50/50 dark:hover:bg-primary-950/30 transition-all"
                >
                  <div className="p-2 bg-primary-100 dark:bg-primary-900/50 rounded-lg">
                    <CategoryIcon className="h-4 w-4 text-primary-600 dark:text-primary-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="font-medium text-neutral-900 dark:text-white group-hover:text-primary-700 dark:group-hover:text-primary-400 truncate">
                      {tool.displayName || tool.name}
                    </h3>
                    <p className="text-xs text-neutral-500 dark:text-neutral-400 line-clamp-1 mt-0.5">
                      {tool.description}
                    </p>
                    <div className="flex items-center gap-2 mt-1.5">
                      <span className="text-xs text-neutral-400 flex items-center gap-1">
                        <Wrench className="h-3 w-3" />
                        {tool.tools?.length || 0} tools
                      </span>
                      <span className="text-xs px-1.5 py-0.5 bg-neutral-100 dark:bg-neutral-800 text-neutral-500 dark:text-neutral-400 rounded capitalize">
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
