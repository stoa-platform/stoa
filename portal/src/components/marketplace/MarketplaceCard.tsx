import { Link } from 'react-router-dom';
import { BookOpen, Wrench, ArrowRight } from 'lucide-react';
import type { MarketplaceItem } from '../../types';

interface MarketplaceCardProps {
  item: MarketplaceItem;
}

const statusColors: Record<string, string> = {
  active: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400',
  published: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400',
  draft: 'bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400',
  deprecated: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
  maintenance: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
};

function getItemLink(item: MarketplaceItem): string {
  if (item.type === 'api' && item.api) {
    return `/apis/${item.api.id}`;
  }
  if (item.type === 'mcp-server' && item.mcpServer) {
    return `/servers/${item.mcpServer.id}`;
  }
  return '#';
}

export function MarketplaceCard({ item }: MarketplaceCardProps) {
  const Icon = item.type === 'api' ? BookOpen : Wrench;
  const typeLabel = item.type === 'api' ? 'API' : 'AI Tool';
  const link = getItemLink(item);

  return (
    <Link
      to={link}
      className="group block rounded-xl border border-neutral-200 bg-white p-5
        hover:border-emerald-300 hover:shadow-md transition-all
        dark:bg-neutral-800 dark:border-neutral-700 dark:hover:border-emerald-600"
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <div
            className={`p-2 rounded-lg ${
              item.type === 'api'
                ? 'bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400'
                : 'bg-violet-50 text-violet-600 dark:bg-violet-900/30 dark:text-violet-400'
            }`}
          >
            <Icon className="h-4 w-4" />
          </div>
          <span className="text-xs font-medium text-neutral-500 uppercase tracking-wider">
            {typeLabel}
          </span>
        </div>
        {item.featured && (
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
            Featured
          </span>
        )}
      </div>

      <h3 className="text-base font-semibold text-neutral-900 mb-1 group-hover:text-emerald-700 dark:text-white dark:group-hover:text-emerald-400">
        {item.displayName}
      </h3>

      <p className="text-sm text-neutral-600 line-clamp-2 mb-3 dark:text-neutral-400">
        {item.description || 'No description available'}
      </p>

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className={`text-xs px-2 py-0.5 rounded-full font-medium ${
              statusColors[item.status] || statusColors.draft
            }`}
          >
            {item.status}
          </span>
          {item.version && (
            <span className="text-xs text-neutral-500 dark:text-neutral-500">v{item.version}</span>
          )}
        </div>
        <ArrowRight className="h-4 w-4 text-neutral-400 group-hover:text-emerald-600 transition-colors dark:group-hover:text-emerald-400" />
      </div>

      {item.tags.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-3 pt-3 border-t border-neutral-100 dark:border-neutral-700">
          {item.tags.slice(0, 3).map((tag) => (
            <span
              key={tag}
              className="text-xs px-2 py-0.5 rounded bg-neutral-100 text-neutral-600 dark:bg-neutral-700 dark:text-neutral-400"
            >
              {tag}
            </span>
          ))}
          {item.tags.length > 3 && (
            <span className="text-xs text-neutral-400">+{item.tags.length - 3}</span>
          )}
        </div>
      )}
    </Link>
  );
}
