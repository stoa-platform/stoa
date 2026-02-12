/**
 * Subscription Card Component
 *
 * Displays a subscription with status, usage, and actions.
 * Optimized with React.memo to prevent unnecessary re-renders.
 */

import { memo, useMemo, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  CheckCircle,
  Clock,
  PauseCircle,
  XCircle,
  ExternalLink,
  BarChart3,
  Calendar,
  Zap,
  Crown,
  Building2,
  Check,
} from 'lucide-react';
import type { APISubscription } from '../../types';

interface SubscriptionCardProps {
  subscription: APISubscription;
  onCancel?: (subscriptionId: string) => void;
  isCancelling?: boolean;
}

type SubscriptionStatus = 'active' | 'pending' | 'suspended' | 'cancelled';
type SubscriptionPlan = 'free' | 'basic' | 'premium' | 'enterprise';

const statusConfig: Record<
  SubscriptionStatus,
  {
    icon: React.ComponentType<{ className?: string }>;
    color: string;
    bg: string;
    text: string;
    label: string;
  }
> = {
  active: {
    icon: CheckCircle,
    color: 'text-green-500',
    bg: 'bg-green-100 dark:bg-green-900/30',
    text: 'text-green-800 dark:text-green-400',
    label: 'Active',
  },
  pending: {
    icon: Clock,
    color: 'text-amber-500',
    bg: 'bg-amber-100 dark:bg-amber-900/30',
    text: 'text-amber-800 dark:text-amber-400',
    label: 'Pending',
  },
  suspended: {
    icon: PauseCircle,
    color: 'text-orange-500',
    bg: 'bg-orange-100 dark:bg-orange-900/30',
    text: 'text-orange-800 dark:text-orange-400',
    label: 'Suspended',
  },
  cancelled: {
    icon: XCircle,
    color: 'text-gray-500 dark:text-neutral-400',
    bg: 'bg-gray-100 dark:bg-neutral-700',
    text: 'text-gray-800 dark:text-neutral-200',
    label: 'Cancelled',
  },
};

const planConfig: Record<
  SubscriptionPlan,
  {
    icon: React.ComponentType<{ className?: string }>;
    color: string;
    bg: string;
    label: string;
  }
> = {
  free: {
    icon: Check,
    color: 'text-gray-600 dark:text-neutral-400',
    bg: 'bg-gray-100 dark:bg-neutral-700',
    label: 'Free',
  },
  basic: {
    icon: Zap,
    color: 'text-blue-600',
    bg: 'bg-blue-100 dark:bg-blue-900/30',
    label: 'Basic',
  },
  premium: {
    icon: Crown,
    color: 'text-purple-600',
    bg: 'bg-purple-100 dark:bg-purple-900/30',
    label: 'Premium',
  },
  enterprise: {
    icon: Building2,
    color: 'text-amber-600',
    bg: 'bg-amber-100 dark:bg-amber-900/30',
    label: 'Enterprise',
  },
};

// Date formatting options - created once
const dateFormatOptions: Intl.DateTimeFormatOptions = {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
};

export const SubscriptionCard = memo(function SubscriptionCard({
  subscription,
  onCancel,
  isCancelling = false,
}: SubscriptionCardProps) {
  const status = statusConfig[subscription.status as SubscriptionStatus] || statusConfig.active;
  const plan = planConfig[(subscription.plan as SubscriptionPlan) || 'free'] || planConfig.free;
  const StatusIcon = status.icon;
  const PlanIcon = plan.icon;

  // Memoize formatted date
  const formattedDate = useMemo(() => {
    return new Date(subscription.createdAt).toLocaleDateString('en-US', dateFormatOptions);
  }, [subscription.createdAt]);

  // Memoize cancel handler
  const handleCancel = useCallback(() => {
    if (onCancel && !isCancelling) {
      onCancel(subscription.id);
    }
  }, [onCancel, isCancelling, subscription.id]);

  return (
    <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 p-5 hover:shadow-md transition-shadow">
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Link
              to={`/apis/${subscription.apiId}`}
              className="text-lg font-semibold text-gray-900 dark:text-white hover:text-primary-600 truncate"
            >
              {subscription.api?.name || subscription.apiId}
            </Link>
            <ExternalLink className="h-4 w-4 text-gray-400 dark:text-neutral-500 flex-shrink-0" />
          </div>
          {subscription.api?.version && (
            <p className="text-sm text-gray-500 dark:text-neutral-400">
              v{subscription.api.version}
            </p>
          )}
        </div>

        {/* Status Badge */}
        <span
          className={`inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-full ${status.bg} ${status.text}`}
        >
          <StatusIcon className={`h-3.5 w-3.5 ${status.color}`} />
          {status.label}
        </span>
      </div>

      {/* Plan and App Info */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        {/* Plan Badge */}
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full ${plan.bg} ${plan.color}`}
        >
          <PlanIcon className="h-3.5 w-3.5" />
          {plan.label} Plan
        </span>

        {/* Application */}
        {subscription.application && (
          <Link
            to={`/apps/${subscription.applicationId}`}
            className="inline-flex items-center gap-1.5 text-xs text-gray-600 dark:text-neutral-400 hover:text-primary-600"
          >
            <span className="font-medium">{subscription.application.name}</span>
          </Link>
        )}
      </div>

      {/* Usage Stats */}
      {subscription.usage && (
        <div className="bg-gray-50 dark:bg-neutral-900 rounded-lg p-3 mb-4">
          <div className="flex items-center gap-2 mb-2">
            <BarChart3 className="h-4 w-4 text-gray-500 dark:text-neutral-400" />
            <span className="text-xs font-medium text-gray-700 dark:text-neutral-300">
              Usage Today
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-2xl font-bold text-gray-900 dark:text-white">
              {subscription.usage.callsToday?.toLocaleString() || 0}
            </span>
            {subscription.usage.dailyLimit && (
              <span className="text-sm text-gray-500 dark:text-neutral-400">
                / {subscription.usage.dailyLimit.toLocaleString()} limit
              </span>
            )}
          </div>
          {subscription.usage.dailyLimit && (
            <div className="mt-2">
              <div className="h-2 bg-gray-200 dark:bg-neutral-600 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${
                    (subscription.usage.callsToday || 0) / subscription.usage.dailyLimit > 0.9
                      ? 'bg-red-500'
                      : (subscription.usage.callsToday || 0) / subscription.usage.dailyLimit > 0.7
                        ? 'bg-amber-500'
                        : 'bg-green-500'
                  }`}
                  style={{
                    width: `${Math.min(
                      ((subscription.usage.callsToday || 0) / subscription.usage.dailyLimit) * 100,
                      100
                    )}%`,
                  }}
                />
              </div>
            </div>
          )}
        </div>
      )}

      {/* Metadata */}
      <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-neutral-400 mb-4">
        <div className="flex items-center gap-1">
          <Calendar className="h-3.5 w-3.5" />
          Subscribed {formattedDate}
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center justify-between pt-3 border-t border-gray-100 dark:border-neutral-700">
        <Link
          to={`/apis/${subscription.apiId}`}
          className="text-sm font-medium text-primary-600 hover:text-primary-700"
        >
          View API Details
        </Link>

        {subscription.status === 'active' && onCancel && (
          <button
            onClick={handleCancel}
            disabled={isCancelling}
            className="text-sm font-medium text-red-600 hover:text-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isCancelling ? 'Cancelling...' : 'Cancel Subscription'}
          </button>
        )}
      </div>
    </div>
  );
});

export default SubscriptionCard;
