/**
 * StatCard Component - CAB-280
 * Card de statistique avec couleur dynamique
 * Optimized with React.memo for list rendering.
 */

import { memo, ReactNode } from 'react';

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon?: ReactNode;
  trend?: {
    value: number;
    isPositive: boolean;
  };
  color?: 'cyan' | 'emerald' | 'amber' | 'red' | 'purple';
  isLoading?: boolean;
}

const colorClasses = {
  cyan: {
    bg: 'bg-cyan-50 dark:bg-cyan-900/20',
    border: 'border-cyan-200 dark:border-cyan-800',
    text: 'text-cyan-600 dark:text-cyan-400',
    icon: 'text-cyan-500 dark:text-cyan-400',
  },
  emerald: {
    bg: 'bg-emerald-50 dark:bg-emerald-900/20',
    border: 'border-emerald-200 dark:border-emerald-800',
    text: 'text-emerald-600 dark:text-emerald-400',
    icon: 'text-emerald-500 dark:text-emerald-400',
  },
  amber: {
    bg: 'bg-amber-50 dark:bg-amber-900/20',
    border: 'border-amber-200 dark:border-amber-800',
    text: 'text-amber-600 dark:text-amber-400',
    icon: 'text-amber-500 dark:text-amber-400',
  },
  red: {
    bg: 'bg-red-50 dark:bg-red-900/20',
    border: 'border-red-200 dark:border-red-800',
    text: 'text-red-600 dark:text-red-400',
    icon: 'text-red-500 dark:text-red-400',
  },
  purple: {
    bg: 'bg-purple-50 dark:bg-purple-900/20',
    border: 'border-purple-200 dark:border-purple-800',
    text: 'text-purple-600 dark:text-purple-400',
    icon: 'text-purple-500 dark:text-purple-400',
  },
};

export const StatCard = memo(function StatCard({
  title,
  value,
  subtitle,
  icon,
  trend,
  color = 'cyan',
  isLoading = false,
}: StatCardProps) {
  const colors = colorClasses[color];

  if (isLoading) {
    return (
      <div className={`rounded-xl border ${colors.border} ${colors.bg} p-6 animate-pulse`}>
        <div className="h-4 w-24 bg-neutral-200 dark:bg-neutral-700 rounded mb-3" />
        <div className="h-8 w-32 bg-neutral-200 dark:bg-neutral-700 rounded mb-2" />
        <div className="h-3 w-20 bg-neutral-200 dark:bg-neutral-700 rounded" />
      </div>
    );
  }

  return (
    <div
      className={`rounded-xl border ${colors.border} ${colors.bg} p-6 transition-shadow hover:shadow-md`}
    >
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wide">
          {title}
        </span>
        {icon && <span className={colors.icon}>{icon}</span>}
      </div>

      <div className={`text-3xl font-bold ${colors.text} mb-1`}>{value}</div>

      <div className="flex items-center gap-2">
        {subtitle && (
          <span className="text-sm text-neutral-500 dark:text-neutral-400">{subtitle}</span>
        )}

        {trend && (
          <span
            className={`
            text-xs font-medium px-2 py-0.5 rounded-full
            ${
              trend.isPositive
                ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400'
                : 'bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400'
            }
          `}
          >
            {trend.isPositive ? '↑' : '↓'} {Math.abs(trend.value)}%
          </span>
        )}
      </div>
    </div>
  );
});
