// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
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

const statusConfig: Record<SubscriptionStatus, {
  icon: React.ComponentType<{ className?: string }>;
  color: string;
  bg: string;
  text: string;
  label: string;
}> = {
  active: {
    icon: CheckCircle,
    color: 'text-green-500',
    bg: 'bg-green-100',
    text: 'text-green-800',
    label: 'Active',
  },
  pending: {
    icon: Clock,
    color: 'text-amber-500',
    bg: 'bg-amber-100',
    text: 'text-amber-800',
    label: 'Pending',
  },
  suspended: {
    icon: PauseCircle,
    color: 'text-orange-500',
    bg: 'bg-orange-100',
    text: 'text-orange-800',
    label: 'Suspended',
  },
  cancelled: {
    icon: XCircle,
    color: 'text-gray-500',
    bg: 'bg-gray-100',
    text: 'text-gray-800',
    label: 'Cancelled',
  },
};

const planConfig: Record<SubscriptionPlan, {
  icon: React.ComponentType<{ className?: string }>;
  color: string;
  bg: string;
  label: string;
}> = {
  free: {
    icon: Check,
    color: 'text-gray-600',
    bg: 'bg-gray-100',
    label: 'Free',
  },
  basic: {
    icon: Zap,
    color: 'text-blue-600',
    bg: 'bg-blue-100',
    label: 'Basic',
  },
  premium: {
    icon: Crown,
    color: 'text-purple-600',
    bg: 'bg-purple-100',
    label: 'Premium',
  },
  enterprise: {
    icon: Building2,
    color: 'text-amber-600',
    bg: 'bg-amber-100',
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
    <div className="bg-white rounded-lg border border-gray-200 p-5 hover:shadow-md transition-shadow">
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Link
              to={`/apis/${subscription.apiId}`}
              className="text-lg font-semibold text-gray-900 hover:text-primary-600 truncate"
            >
              {subscription.api?.name || subscription.apiId}
            </Link>
            <ExternalLink className="h-4 w-4 text-gray-400 flex-shrink-0" />
          </div>
          {subscription.api?.version && (
            <p className="text-sm text-gray-500">v{subscription.api.version}</p>
          )}
        </div>

        {/* Status Badge */}
        <span className={`inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-full ${status.bg} ${status.text}`}>
          <StatusIcon className={`h-3.5 w-3.5 ${status.color}`} />
          {status.label}
        </span>
      </div>

      {/* Plan and App Info */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        {/* Plan Badge */}
        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full ${plan.bg} ${plan.color}`}>
          <PlanIcon className="h-3.5 w-3.5" />
          {plan.label} Plan
        </span>

        {/* Application */}
        {subscription.application && (
          <Link
            to={`/apps/${subscription.applicationId}`}
            className="inline-flex items-center gap-1.5 text-xs text-gray-600 hover:text-primary-600"
          >
            <span className="font-medium">{subscription.application.name}</span>
          </Link>
        )}
      </div>

      {/* Usage Stats */}
      {subscription.usage && (
        <div className="bg-gray-50 rounded-lg p-3 mb-4">
          <div className="flex items-center gap-2 mb-2">
            <BarChart3 className="h-4 w-4 text-gray-500" />
            <span className="text-xs font-medium text-gray-700">Usage Today</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-2xl font-bold text-gray-900">
              {subscription.usage.callsToday?.toLocaleString() || 0}
            </span>
            {subscription.usage.dailyLimit && (
              <span className="text-sm text-gray-500">
                / {subscription.usage.dailyLimit.toLocaleString()} limit
              </span>
            )}
          </div>
          {subscription.usage.dailyLimit && (
            <div className="mt-2">
              <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
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
      <div className="flex items-center gap-4 text-xs text-gray-500 mb-4">
        <div className="flex items-center gap-1">
          <Calendar className="h-3.5 w-3.5" />
          Subscribed {formattedDate}
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center justify-between pt-3 border-t border-gray-100">
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
