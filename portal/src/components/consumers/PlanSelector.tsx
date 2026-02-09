/**
 * Plan Selector Component
 *
 * Grid of available subscription plans for selection (CAB-1121).
 */

import { memo } from 'react';
import { Check, Zap, Clock, Calendar, Sparkles } from 'lucide-react';
import type { Plan } from '../../types';

interface PlanSelectorProps {
  plans: Plan[];
  selectedPlanId?: string | null;
  onSelect: (plan: Plan) => void;
  isLoading?: boolean;
}

function formatLimit(value: number | null | undefined): string {
  if (value === null || value === undefined) return 'Unlimited';
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(0)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)}K`;
  return value.toString();
}

export const PlanSelector = memo(function PlanSelector({
  plans,
  selectedPlanId,
  onSelect,
  isLoading = false,
}: PlanSelectorProps) {
  const activePlans = plans.filter((p) => p.status === 'active');

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="animate-pulse bg-gray-100 dark:bg-neutral-700 rounded-lg h-48" />
        ))}
      </div>
    );
  }

  if (activePlans.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500 dark:text-neutral-400">
        <Sparkles className="h-8 w-8 mx-auto mb-3 text-gray-300 dark:text-neutral-600" />
        <p className="font-medium">No plans available</p>
        <p className="text-sm mt-1">Contact your administrator to set up subscription plans.</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {activePlans.map((plan) => {
        const isSelected = selectedPlanId === plan.id;
        return (
          <button
            key={plan.id}
            type="button"
            onClick={() => onSelect(plan)}
            className={`relative text-left p-5 rounded-lg border-2 transition-all ${
              isSelected
                ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20 ring-1 ring-primary-500'
                : 'border-gray-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 hover:border-primary-300 dark:hover:border-primary-600'
            }`}
          >
            {/* Selected indicator */}
            {isSelected && (
              <div className="absolute top-3 right-3">
                <div className="bg-primary-500 text-white rounded-full p-1">
                  <Check className="h-3 w-3" />
                </div>
              </div>
            )}

            {/* Plan name and description */}
            <h4 className="font-semibold text-gray-900 dark:text-white mb-1">{plan.name}</h4>
            {plan.description && (
              <p className="text-sm text-gray-500 dark:text-neutral-400 mb-4 line-clamp-2">
                {plan.description}
              </p>
            )}

            {/* Rate limits */}
            <div className="space-y-2 text-sm">
              {(plan.rate_limit_per_second !== null || plan.rate_limit_per_minute !== null) && (
                <div className="flex items-center gap-2 text-gray-600 dark:text-neutral-300">
                  <Zap className="h-3.5 w-3.5 text-amber-500" />
                  <span>
                    {plan.rate_limit_per_second !== null && plan.rate_limit_per_second !== undefined
                      ? `${formatLimit(plan.rate_limit_per_second)}/s`
                      : `${formatLimit(plan.rate_limit_per_minute)}/min`}
                  </span>
                </div>
              )}
              {plan.daily_request_limit !== null && plan.daily_request_limit !== undefined && (
                <div className="flex items-center gap-2 text-gray-600 dark:text-neutral-300">
                  <Clock className="h-3.5 w-3.5 text-blue-500" />
                  <span>{formatLimit(plan.daily_request_limit)}/day</span>
                </div>
              )}
              {plan.monthly_request_limit !== null && plan.monthly_request_limit !== undefined && (
                <div className="flex items-center gap-2 text-gray-600 dark:text-neutral-300">
                  <Calendar className="h-3.5 w-3.5 text-violet-500" />
                  <span>{formatLimit(plan.monthly_request_limit)}/month</span>
                </div>
              )}
            </div>

            {/* Approval badge */}
            {plan.requires_approval && (
              <div className="mt-3 inline-flex items-center px-2 py-1 text-xs font-medium bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-300 rounded-full">
                Requires approval
              </div>
            )}
          </button>
        );
      })}
    </div>
  );
});

export default PlanSelector;
