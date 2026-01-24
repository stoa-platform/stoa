/**
 * DashboardStats Component (CAB-299)
 *
 * Three stat cards showing key metrics.
 */

import { Wrench, CreditCard, Activity, TrendingUp, TrendingDown } from 'lucide-react';
import type { DashboardStats as DashboardStatsType } from '../../types';

interface DashboardStatsProps {
  stats: DashboardStatsType | null;
  isLoading?: boolean;
}

interface StatCardProps {
  title: string;
  value: number | string;
  subtitle: string;
  icon: React.ReactNode;
  color: 'primary' | 'emerald' | 'cyan';
  trend?: number;
  isLoading?: boolean;
}

const colorConfig = {
  primary: {
    bg: 'bg-primary-50',
    border: 'border-primary-200',
    iconBg: 'bg-primary-100',
    iconColor: 'text-primary-600',
    valueColor: 'text-primary-700',
  },
  emerald: {
    bg: 'bg-emerald-50',
    border: 'border-emerald-200',
    iconBg: 'bg-emerald-100',
    iconColor: 'text-emerald-600',
    valueColor: 'text-emerald-700',
  },
  cyan: {
    bg: 'bg-cyan-50',
    border: 'border-cyan-200',
    iconBg: 'bg-cyan-100',
    iconColor: 'text-cyan-600',
    valueColor: 'text-cyan-700',
  },
};

function StatCard({ title, value, subtitle, icon, color, trend, isLoading }: StatCardProps) {
  const colors = colorConfig[color];

  if (isLoading) {
    return (
      <div className={`rounded-xl border ${colors.border} ${colors.bg} p-6 animate-pulse`}>
        <div className="flex items-start justify-between">
          <div className={`p-3 rounded-xl ${colors.iconBg}`}>
            <div className="h-6 w-6 bg-gray-200 rounded" />
          </div>
        </div>
        <div className="mt-4">
          <div className="h-10 w-20 bg-gray-200 rounded mb-2" />
          <div className="h-4 w-24 bg-gray-200 rounded" />
        </div>
      </div>
    );
  }

  return (
    <div className={`rounded-xl border ${colors.border} ${colors.bg} p-6 transition-all hover:shadow-lg hover:scale-[1.02]`}>
      <div className="flex items-start justify-between">
        <div className={`p-3 rounded-xl ${colors.iconBg}`}>
          <span className={colors.iconColor}>{icon}</span>
        </div>
        {trend !== undefined && trend !== 0 && (
          <div className={`flex items-center gap-1 text-sm font-medium ${
            trend > 0 ? 'text-emerald-600' : 'text-red-500'
          }`}>
            {trend > 0 ? (
              <TrendingUp className="h-4 w-4" />
            ) : (
              <TrendingDown className="h-4 w-4" />
            )}
            <span>{Math.abs(trend)}%</span>
          </div>
        )}
      </div>

      <div className="mt-4">
        <p className={`text-4xl font-bold ${colors.valueColor}`}>
          {typeof value === 'number' ? value.toLocaleString() : value}
        </p>
        <p className="text-sm font-medium text-gray-600 mt-1">{title}</p>
        <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>
      </div>
    </div>
  );
}

export function DashboardStats({ stats, isLoading }: DashboardStatsProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 lg:gap-6">
      <StatCard
        title="Tools Available"
        value={stats?.tools_available ?? 0}
        subtitle="Ready to integrate"
        icon={<Wrench className="h-6 w-6" />}
        color="primary"
        trend={stats?.tools_trend}
        isLoading={isLoading}
      />

      <StatCard
        title="Active Subscriptions"
        value={stats?.active_subscriptions ?? 0}
        subtitle="Currently active"
        icon={<CreditCard className="h-6 w-6" />}
        color="emerald"
        trend={stats?.subscriptions_trend}
        isLoading={isLoading}
      />

      <StatCard
        title="API Calls"
        value={stats?.api_calls_this_week ?? 0}
        subtitle="This week"
        icon={<Activity className="h-6 w-6" />}
        color="cyan"
        trend={stats?.calls_trend}
        isLoading={isLoading}
      />
    </div>
  );
}

export default DashboardStats;
