/**
 * Plan Selector Component
 *
 * Displays available plans as selectable cards with real rate limit data.
 *
 * Reference: CAB-1121 Phase 5
 */

import { Check, Zap, Crown, Building2, Loader2, LucideIcon } from 'lucide-react';
import type { Plan } from '../../types';

interface PlanSelectorProps {
  plans: Plan[];
  selectedPlanId: string | null;
  onSelect: (planId: string) => void;
  isLoading?: boolean;
  disabled?: boolean;
}

function formatLimit(value: number | undefined | null): string {
  if (value === undefined || value === null) return 'Unlimited';
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(0)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)}K`;
  return value.toString();
}

function getPlanVisual(plan: Plan): {
  icon: LucideIcon;
  color: string;
  bgColor: string;
  borderColor: string;
} {
  const slug = plan.slug.toLowerCase();
  if (slug.includes('enterprise') || slug.includes('dedicated')) {
    return {
      icon: Building2,
      color: 'text-amber-700 dark:text-amber-400',
      bgColor: 'bg-amber-50 dark:bg-amber-900/20',
      borderColor: 'border-amber-200 dark:border-amber-800',
    };
  }
  if (slug.includes('premium') || slug.includes('pro')) {
    return {
      icon: Crown,
      color: 'text-purple-700 dark:text-purple-400',
      bgColor: 'bg-purple-50 dark:bg-purple-900/20',
      borderColor: 'border-purple-200 dark:border-purple-800',
    };
  }
  if (slug.includes('basic') || slug.includes('starter')) {
    return {
      icon: Zap,
      color: 'text-blue-700 dark:text-blue-400',
      bgColor: 'bg-blue-50 dark:bg-blue-900/20',
      borderColor: 'border-blue-200 dark:border-blue-800',
    };
  }
  return {
    icon: Check,
    color: 'text-neutral-700 dark:text-neutral-400',
    bgColor: 'bg-neutral-50 dark:bg-neutral-800',
    borderColor: 'border-neutral-200 dark:border-neutral-700',
  };
}

export function PlanSelector({
  plans,
  selectedPlanId,
  onSelect,
  isLoading = false,
  disabled = false,
}: PlanSelectorProps) {
  if (isLoading) {
    return (
      <div className="flex items-center gap-2 p-4 bg-neutral-50 dark:bg-neutral-800 rounded-lg">
        <Loader2 className="h-4 w-4 animate-spin text-neutral-500 dark:text-neutral-400" />
        <span className="text-sm text-neutral-500 dark:text-neutral-400">Loading plans...</span>
      </div>
    );
  }

  if (plans.length === 0) {
    return (
      <div className="p-4 bg-neutral-50 dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg">
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          No plans available for this tenant. Contact your administrator.
        </p>
      </div>
    );
  }

  return (
    <div
      className="grid grid-cols-1 md:grid-cols-2 gap-3"
      role="radiogroup"
      aria-label="Select a plan"
    >
      {plans.map((plan) => {
        const visual = getPlanVisual(plan);
        const Icon = visual.icon;
        const isSelected = selectedPlanId === plan.id;
        const features: string[] = [];

        if (plan.rate_limit_per_minute) {
          features.push(`${formatLimit(plan.rate_limit_per_minute)} req/min`);
        } else if (plan.rate_limit_per_second) {
          features.push(`${formatLimit(plan.rate_limit_per_second)} req/sec`);
        }
        if (plan.daily_request_limit) {
          features.push(`${formatLimit(plan.daily_request_limit)} req/day`);
        }
        if (plan.monthly_request_limit) {
          features.push(`${formatLimit(plan.monthly_request_limit)} req/month`);
        }
        if (features.length === 0) {
          features.push('Unlimited requests');
        }
        if (plan.requires_approval) {
          features.push('Requires approval');
        }

        return (
          <button
            key={plan.id}
            type="button"
            role="radio"
            aria-checked={isSelected}
            onClick={() => onSelect(plan.id)}
            disabled={disabled}
            className={`relative p-4 rounded-lg border-2 text-left transition-all ${
              isSelected
                ? `${visual.borderColor} ${visual.bgColor} ring-2 ring-offset-1 ring-primary-500 dark:ring-offset-neutral-900`
                : 'border-neutral-200 dark:border-neutral-700 hover:border-neutral-300 dark:hover:border-neutral-600 hover:bg-neutral-50 dark:hover:bg-neutral-800'
            } disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            <div className="flex items-start gap-3">
              <div className={`p-2 rounded-lg ${visual.bgColor}`}>
                <Icon className={`h-5 w-5 ${visual.color}`} />
              </div>
              <div className="flex-1 min-w-0">
                <h4
                  className={`font-semibold ${isSelected ? visual.color : 'text-neutral-900 dark:text-white'}`}
                >
                  {plan.name}
                </h4>
                {plan.description && (
                  <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5 truncate">
                    {plan.description}
                  </p>
                )}
                <ul className="mt-2 space-y-1">
                  {features.map((feature, idx) => (
                    <li
                      key={idx}
                      className="flex items-center gap-1.5 text-xs text-neutral-600 dark:text-neutral-300"
                    >
                      <Check className="h-3 w-3 text-green-500 flex-shrink-0" />
                      {feature}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
            {isSelected && (
              <div className="absolute top-2 right-2">
                <div className="p-1 bg-primary-600 rounded-full">
                  <Check className="h-3 w-3 text-white" />
                </div>
              </div>
            )}
          </button>
        );
      })}
    </div>
  );
}

export default PlanSelector;
