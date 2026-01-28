// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
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
    bg: 'bg-cyan-50',
    border: 'border-cyan-200',
    text: 'text-cyan-600',
    icon: 'text-cyan-500',
  },
  emerald: {
    bg: 'bg-emerald-50',
    border: 'border-emerald-200',
    text: 'text-emerald-600',
    icon: 'text-emerald-500',
  },
  amber: {
    bg: 'bg-amber-50',
    border: 'border-amber-200',
    text: 'text-amber-600',
    icon: 'text-amber-500',
  },
  red: {
    bg: 'bg-red-50',
    border: 'border-red-200',
    text: 'text-red-600',
    icon: 'text-red-500',
  },
  purple: {
    bg: 'bg-purple-50',
    border: 'border-purple-200',
    text: 'text-purple-600',
    icon: 'text-purple-500',
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
        <div className="h-4 w-24 bg-gray-200 rounded mb-3" />
        <div className="h-8 w-32 bg-gray-200 rounded mb-2" />
        <div className="h-3 w-20 bg-gray-200 rounded" />
      </div>
    );
  }

  return (
    <div className={`rounded-xl border ${colors.border} ${colors.bg} p-6 transition-shadow hover:shadow-md`}>
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-medium text-gray-500 uppercase tracking-wide">
          {title}
        </span>
        {icon && (
          <span className={colors.icon}>
            {icon}
          </span>
        )}
      </div>

      <div className={`text-3xl font-bold ${colors.text} mb-1`}>
        {value}
      </div>

      <div className="flex items-center gap-2">
        {subtitle && (
          <span className="text-sm text-gray-500">{subtitle}</span>
        )}

        {trend && (
          <span className={`
            text-xs font-medium px-2 py-0.5 rounded-full
            ${trend.isPositive
              ? 'bg-emerald-100 text-emerald-600'
              : 'bg-red-100 text-red-600'
            }
          `}>
            {trend.isPositive ? '↑' : '↓'} {Math.abs(trend.value)}%
          </span>
        )}
      </div>
    </div>
  );
});
