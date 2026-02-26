import { BookOpen, Wrench, Layers } from 'lucide-react';
import type { MarketplaceStats as Stats } from '../../types';

interface MarketplaceStatsProps {
  stats: Stats;
}

export function MarketplaceStatsBar({ stats }: MarketplaceStatsProps) {
  return (
    <div className="grid grid-cols-3 gap-4">
      <div className="flex items-center gap-3 rounded-lg bg-blue-50 p-3 dark:bg-blue-900/20">
        <BookOpen className="h-5 w-5 text-blue-600 dark:text-blue-400" />
        <div>
          <p className="text-lg font-semibold text-blue-900 dark:text-blue-300">
            {stats.totalAPIs}
          </p>
          <p className="text-xs text-blue-600 dark:text-blue-400">APIs</p>
        </div>
      </div>
      <div className="flex items-center gap-3 rounded-lg bg-violet-50 p-3 dark:bg-violet-900/20">
        <Wrench className="h-5 w-5 text-violet-600 dark:text-violet-400" />
        <div>
          <p className="text-lg font-semibold text-violet-900 dark:text-violet-300">
            {stats.totalMCPServers}
          </p>
          <p className="text-xs text-violet-600 dark:text-violet-400">AI Tools</p>
        </div>
      </div>
      <div className="flex items-center gap-3 rounded-lg bg-emerald-50 p-3 dark:bg-emerald-900/20">
        <Layers className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
        <div>
          <p className="text-lg font-semibold text-emerald-900 dark:text-emerald-300">
            {stats.totalItems}
          </p>
          <p className="text-xs text-emerald-600 dark:text-emerald-400">Total</p>
        </div>
      </div>
    </div>
  );
}
