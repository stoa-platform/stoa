/**
 * RecentActivity Component (CAB-299)
 *
 * Shows recent user activity (subscriptions, API calls, etc.)
 */

import { Link } from 'react-router-dom';
import {
  CreditCard,
  CheckCircle,
  XCircle,
  Activity,
  RefreshCw,
  Clock,
  ArrowRight,
} from 'lucide-react';
import type { RecentActivityItem, ActivityType } from '../../types';

interface RecentActivityProps {
  activity: RecentActivityItem[];
  isLoading?: boolean;
}

const activityConfig: Record<
  ActivityType,
  {
    icon: React.ComponentType<{ className?: string }>;
    color: string;
    bgColor: string;
  }
> = {
  'subscription.created': {
    icon: CreditCard,
    color: 'text-primary-600 dark:text-primary-400',
    bgColor: 'bg-primary-100 dark:bg-primary-900/50',
  },
  'subscription.approved': {
    icon: CheckCircle,
    color: 'text-emerald-600 dark:text-emerald-400',
    bgColor: 'bg-emerald-100 dark:bg-emerald-900/50',
  },
  'subscription.revoked': {
    icon: XCircle,
    color: 'text-red-600 dark:text-red-400',
    bgColor: 'bg-red-100 dark:bg-red-900/50',
  },
  'api.call': {
    icon: Activity,
    color: 'text-cyan-600 dark:text-cyan-400',
    bgColor: 'bg-cyan-100 dark:bg-cyan-900/50',
  },
  'key.rotated': {
    icon: RefreshCw,
    color: 'text-amber-600 dark:text-amber-400',
    bgColor: 'bg-amber-100 dark:bg-amber-900/50',
  },
};

function formatRelativeTime(timestamp: string): string {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

function ActivitySkeleton() {
  return (
    <div className="flex items-start gap-3 p-3 animate-pulse">
      <div className="w-8 h-8 bg-neutral-200 dark:bg-neutral-700 rounded-lg" />
      <div className="flex-1">
        <div className="h-4 w-48 bg-neutral-200 dark:bg-neutral-700 rounded mb-2" />
        <div className="h-3 w-24 bg-neutral-200 dark:bg-neutral-700 rounded" />
      </div>
    </div>
  );
}

export function RecentActivity({ activity, isLoading }: RecentActivityProps) {
  return (
    <div className="bg-white dark:bg-neutral-900 rounded-xl border border-neutral-200 dark:border-neutral-700">
      <div className="px-5 py-4 border-b border-neutral-100 dark:border-neutral-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-cyan-600 dark:text-cyan-400" />
          <h2 className="font-semibold text-neutral-900 dark:text-white">Recent Activity</h2>
        </div>
        <Link
          to="/usage"
          className="text-sm text-primary-600 hover:text-primary-700 font-medium flex items-center gap-1"
        >
          View all
          <ArrowRight className="h-3 w-3" />
        </Link>
      </div>

      <div className="divide-y divide-neutral-100 dark:divide-neutral-800">
        {isLoading ? (
          <>
            <ActivitySkeleton />
            <ActivitySkeleton />
            <ActivitySkeleton />
          </>
        ) : activity.length === 0 ? (
          <div className="px-5 py-8 text-center">
            <Clock className="h-8 w-8 text-neutral-300 dark:text-neutral-600 mx-auto mb-2" />
            <p className="text-neutral-500 dark:text-neutral-400 text-sm">No recent activity</p>
            <p className="text-neutral-400 dark:text-neutral-500 text-xs mt-1">
              Subscribe to tools and start making API calls
            </p>
          </div>
        ) : (
          activity.map((item) => {
            const config = activityConfig[item.type] || activityConfig['api.call'];
            const Icon = config.icon;

            return (
              <div
                key={item.id}
                className="flex items-start gap-3 px-5 py-3 hover:bg-neutral-50 dark:hover:bg-neutral-800 transition-colors"
              >
                <div className={`p-2 rounded-lg ${config.bgColor}`}>
                  <Icon className={`h-4 w-4 ${config.color}`} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-neutral-900 dark:text-white truncate">
                    {item.title}
                  </p>
                  {item.description && (
                    <p className="text-xs text-neutral-500 dark:text-neutral-400 truncate">
                      {item.description}
                    </p>
                  )}
                </div>
                <span className="text-xs text-neutral-400 whitespace-nowrap">
                  {formatRelativeTime(item.timestamp)}
                </span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

export default RecentActivity;
