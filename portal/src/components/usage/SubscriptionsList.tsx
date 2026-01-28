// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
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
    active: { bg: 'bg-emerald-100', text: 'text-emerald-700' },
    suspended: { bg: 'bg-amber-100', text: 'text-amber-700' },
    expired: { bg: 'bg-red-100', text: 'text-red-700' },
  };

  const config = configs[status] || { bg: 'bg-gray-100', text: 'text-gray-700' };

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${config.bg} ${config.text}`}>
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

function ListSkeleton() {
  return (
    <div className="space-y-3 animate-pulse">
      {[...Array(4)].map((_, i) => (
        <div key={i} className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
          <div className="w-8 h-8 bg-gray-200 rounded" />
          <div className="flex-1">
            <div className="h-4 w-32 bg-gray-200 rounded mb-1" />
            <div className="h-3 w-24 bg-gray-200 rounded" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function SubscriptionsList({ subscriptions, isLoading = false }: SubscriptionsListProps) {
  if (isLoading) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Active Subscriptions</h3>
        <ListSkeleton />
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900">
          Active Subscriptions
          <span className="ml-2 text-sm font-normal text-gray-500">
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
          <CreditCard className="w-8 h-8 text-gray-300 mx-auto mb-2" />
          <p className="text-gray-500 text-sm">No active subscriptions</p>
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
              className="flex items-center gap-3 p-3 rounded-lg hover:bg-gray-50 transition-colors group"
            >
              <div className="w-8 h-8 rounded bg-primary-100 flex items-center justify-center">
                <CreditCard className="w-4 h-4 text-primary-600" />
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-gray-900 truncate">
                    {sub.tool_name}
                  </span>
                  <StatusBadge status={sub.status} />
                </div>
                <div className="flex items-center gap-3 text-xs text-gray-400">
                  <span>{sub.call_count_total.toLocaleString()} calls</span>
                  <span>•</span>
                  <span>Last used {formatLastUsed(sub.last_used_at)}</span>
                </div>
              </div>

              <Link
                to={`/tools/${sub.tool_id}`}
                className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-gray-200 rounded"
              >
                <ExternalLink className="w-4 h-4 text-gray-400" />
              </Link>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
