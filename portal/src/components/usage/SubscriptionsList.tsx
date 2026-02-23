/**
 * SubscriptionsList Component - CAB-280
 * Liste des subscriptions actives
 */

import { CreditCard, ExternalLink } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { ActiveSubscription } from '../../types';

interface SubscriptionsListProps {
  subscriptions: ActiveSubscription[];
  isLoading?: boolean;
}

function formatLastUsed(timestamp: string | null | undefined): string {
  if (!timestamp) return 'Never';

  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;

  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;

  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays}d ago`;

  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function StatusBadge({ status }: { status: string }) {
  const configs: Record<string, { bg: string; text: string }> = {
    active: {
      bg: 'bg-emerald-100 dark:bg-emerald-900/30',
      text: 'text-emerald-700 dark:text-emerald-400',
    },
    suspended: {
      bg: 'bg-amber-100 dark:bg-amber-900/30',
      text: 'text-amber-700 dark:text-amber-400',
    },
    expired: { bg: 'bg-red-100 dark:bg-red-900/20', text: 'text-red-700 dark:text-red-400' },
  };

  const config = configs[status] || {
    bg: 'bg-neutral-100 dark:bg-neutral-700',
    text: 'text-neutral-700 dark:text-neutral-300',
  };

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${config.bg} ${config.text}`}
    >
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

function ListSkeleton() {
  return (
    <div className="space-y-3 animate-pulse">
      {[...Array(4)].map((_, i) => (
        <div
          key={i}
          className="flex items-center gap-3 p-3 bg-neutral-50 dark:bg-neutral-900 rounded-lg"
        >
          <div className="w-8 h-8 bg-neutral-200 dark:bg-neutral-600 rounded" />
          <div className="flex-1">
            <div className="h-4 w-32 bg-neutral-200 dark:bg-neutral-600 rounded mb-1" />
            <div className="h-3 w-24 bg-neutral-200 dark:bg-neutral-600 rounded" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function SubscriptionsList({ subscriptions, isLoading = false }: SubscriptionsListProps) {
  if (isLoading) {
    return (
      <div className="rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 p-6">
        <h3 className="text-lg font-semibold text-neutral-900 dark:text-white mb-4">
          Active Subscriptions
        </h3>
        <ListSkeleton />
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-neutral-900 dark:text-white">
          Active Subscriptions
          <span className="ml-2 text-sm font-normal text-neutral-500 dark:text-neutral-400">
            ({subscriptions.length})
          </span>
        </h3>
        <Link
          to="/subscriptions"
          className="text-sm text-primary-600 hover:text-primary-700 font-medium flex items-center gap-1"
        >
          View all
          <ExternalLink className="w-3 h-3" />
        </Link>
      </div>

      {subscriptions.length === 0 ? (
        <div className="text-center py-8">
          <CreditCard className="w-8 h-8 text-neutral-300 dark:text-neutral-600 mx-auto mb-2" />
          <p className="text-neutral-500 dark:text-neutral-400 text-sm">No active subscriptions</p>
          <Link
            to="/tools"
            className="text-sm text-primary-600 hover:text-primary-700 mt-2 inline-block"
          >
            Browse tools →
          </Link>
        </div>
      ) : (
        <div className="space-y-2">
          {subscriptions.map((sub) => (
            <div
              key={sub.id}
              className="flex items-center gap-3 p-3 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-800 transition-colors group"
            >
              <div className="w-8 h-8 rounded bg-primary-100 flex items-center justify-center">
                <CreditCard className="w-4 h-4 text-primary-600" />
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-neutral-900 dark:text-white truncate">
                    {sub.tool_name}
                  </span>
                  <StatusBadge status={sub.status} />
                </div>
                <div className="flex items-center gap-3 text-xs text-neutral-400 dark:text-neutral-500">
                  <span>{sub.call_count_total.toLocaleString()} calls</span>
                  <span>•</span>
                  <span>Last used {formatLastUsed(sub.last_used_at)}</span>
                </div>
              </div>

              <Link
                to={`/tools/${sub.tool_id}`}
                className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-neutral-200 dark:hover:bg-neutral-600 rounded"
              >
                <ExternalLink className="w-4 h-4 text-neutral-400 dark:text-neutral-500" />
              </Link>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
