import { memo } from 'react';
import { Wrench, Tag, ExternalLink, Zap } from 'lucide-react';
import type { MCPTool } from '../../types';

interface ToolCardProps {
  tool: MCPTool;
  onClick?: () => void;
  onSubscribe?: () => void;
  isSubscribed?: boolean;
}

// Move static objects outside component to prevent recreation on each render
const methodColors: Record<string, string> = {
  GET: 'bg-green-100 text-green-800 dark:bg-green-950/30 dark:text-green-400',
  POST: 'bg-blue-100 text-blue-800 dark:bg-blue-950/30 dark:text-blue-400',
  PUT: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-950/30 dark:text-yellow-400',
  PATCH: 'bg-orange-100 text-orange-800 dark:bg-orange-950/30 dark:text-orange-400',
  DELETE: 'bg-red-100 text-red-800 dark:bg-red-950/30 dark:text-red-400',
};

export const ToolCard = memo(function ToolCard({
  tool,
  onClick,
  onSubscribe,
  isSubscribed,
}: ToolCardProps) {
  const paramCount = Object.keys(tool.inputSchema?.properties || {}).length;
  const requiredCount = tool.inputSchema?.required?.length || 0;

  return (
    <div
      className="bg-white dark:bg-neutral-800 rounded-lg shadow-sm border border-gray-200 dark:border-neutral-700 hover:shadow-md hover:border-blue-300 dark:hover:border-blue-600 transition-all cursor-pointer"
      onClick={onClick}
    >
      <div className="p-5">
        {/* Header */}
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-50 dark:bg-blue-950/30 rounded-lg">
              <Wrench className="h-5 w-5 text-blue-600" />
            </div>
            <div>
              <h3 className="font-semibold text-gray-900 dark:text-white text-sm">{tool.name}</h3>
              <span className="text-xs text-gray-500 dark:text-neutral-400">v{tool.version}</span>
            </div>
          </div>
          <span
            className={`px-2 py-0.5 rounded text-xs font-medium ${methodColors[tool.method] || 'bg-gray-100 dark:bg-neutral-700 text-gray-800 dark:text-neutral-300'}`}
          >
            {tool.method}
          </span>
        </div>

        {/* Description */}
        <p className="text-sm text-gray-600 dark:text-neutral-300 mb-4 line-clamp-2">
          {tool.description}
        </p>

        {/* Tags */}
        {tool.tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-4">
            {tool.tags.slice(0, 3).map((tag) => (
              <span
                key={tag}
                className="inline-flex items-center gap-1 px-2 py-0.5 bg-gray-100 dark:bg-neutral-700 text-gray-600 dark:text-neutral-300 rounded text-xs"
              >
                <Tag className="h-3 w-3" />
                {tag}
              </span>
            ))}
            {tool.tags.length > 3 && (
              <span className="text-xs text-gray-400 dark:text-neutral-500">
                +{tool.tags.length - 3} more
              </span>
            )}
          </div>
        )}

        {/* Stats */}
        <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-neutral-400 mb-4">
          <span className="flex items-center gap-1">
            <Zap className="h-3.5 w-3.5" />
            {paramCount} params
          </span>
          {requiredCount > 0 && (
            <span className="flex items-center gap-1 text-orange-600">
              {requiredCount} required
            </span>
          )}
          {tool.endpoint && (
            <span className="flex items-center gap-1">
              <ExternalLink className="h-3.5 w-3.5" />
              API-backed
            </span>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center justify-between pt-3 border-t border-gray-100 dark:border-neutral-700">
          {tool.tenantId && (
            <span className="text-xs text-gray-400 dark:text-neutral-500">
              Tenant: {tool.tenantId}
            </span>
          )}
          {!tool.tenantId && <span />}

          {onSubscribe && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onSubscribe();
              }}
              className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                isSubscribed
                  ? 'bg-gray-100 dark:bg-neutral-700 text-gray-600 dark:text-neutral-300 hover:bg-gray-200 dark:hover:bg-neutral-600'
                  : 'bg-blue-600 text-white hover:bg-blue-700'
              }`}
            >
              {isSubscribed ? 'Subscribed' : 'Subscribe'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
});
