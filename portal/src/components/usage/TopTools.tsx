/**
 * TopTools Component - CAB-280
 * Top 5 tools les plus utilisés
 */

import { useMemo, memo } from 'react';
import { Wrench } from 'lucide-react';
import type { ToolUsageStat } from '../../types';
import { formatLatency } from '../../services/usage';

interface TopToolsProps {
  tools: ToolUsageStat[];
  isLoading?: boolean;
}

function ToolsSkeleton() {
  return (
    <div className="space-y-3 animate-pulse">
      {[...Array(5)].map((_, i) => (
        <div key={i} className="flex items-center gap-3">
          <div className="w-6 h-6 bg-gray-200 dark:bg-neutral-600 rounded" />
          <div className="flex-1">
            <div className="h-4 w-32 bg-gray-200 dark:bg-neutral-600 rounded mb-1" />
            <div className="h-3 w-20 bg-gray-200 dark:bg-neutral-600 rounded" />
          </div>
          <div className="h-4 w-16 bg-gray-200 dark:bg-neutral-600 rounded" />
        </div>
      ))}
    </div>
  );
}

export const TopTools = memo(function TopTools({ tools, isLoading = false }: TopToolsProps) {
  // Memoize maxCalls for performance - only recalculate when tools change
  // Note: Must be called before any early returns to satisfy React Hooks rules
  const maxCalls = useMemo(() => Math.max(...tools.map((t) => t.call_count), 1), [tools]);

  if (isLoading) {
    return (
      <div className="rounded-xl border border-gray-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Top Tools</h3>
        <ToolsSkeleton />
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-gray-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 p-6">
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Top Tools</h3>

      {tools.length === 0 ? (
        <div className="text-center py-8">
          <Wrench className="w-8 h-8 text-gray-300 dark:text-neutral-600 mx-auto mb-2" />
          <p className="text-gray-500 dark:text-neutral-400 text-sm">No tools used yet</p>
        </div>
      ) : (
        <div className="space-y-4">
          {tools.map((tool, index) => {
            const barWidth = (tool.call_count / maxCalls) * 100;

            return (
              <div key={tool.tool_id} className="group">
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-gray-400 dark:text-neutral-500 w-4">
                      {index + 1}.
                    </span>
                    <span className="text-sm font-medium text-gray-900 dark:text-white truncate max-w-[150px]">
                      {tool.tool_name}
                    </span>
                  </div>
                  <span className="text-sm font-semibold text-gray-700 dark:text-neutral-300">
                    {tool.call_count.toLocaleString()}
                  </span>
                </div>

                {/* Progress bar */}
                <div className="ml-6 h-2 bg-gray-100 dark:bg-neutral-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary-400 rounded-full transition-all duration-500"
                    style={{ width: `${barWidth}%` }}
                  />
                </div>

                {/* Stats on hover */}
                <div className="ml-6 flex items-center gap-4 mt-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <span className="text-xs text-gray-400 dark:text-neutral-500">
                    {tool.success_rate.toFixed(1)}% success
                  </span>
                  <span className="text-xs text-gray-400 dark:text-neutral-500">
                    {formatLatency(tool.avg_latency_ms)} avg
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
});
