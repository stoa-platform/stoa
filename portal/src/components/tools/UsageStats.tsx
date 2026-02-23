/**
 * Usage Stats Component
 *
 * Displays tool usage statistics including:
 * - Calls this month
 * - Average latency
 * - Success rate
 * - Last called
 */

import { BarChart3, Clock, CheckCircle, Activity, TrendingUp, Calendar } from 'lucide-react';

interface UsageStatsProps {
  stats?: {
    callsThisMonth?: number;
    callsToday?: number;
    avgLatencyMs?: number;
    successRate?: number;
    lastCalledAt?: string;
    trend?: 'up' | 'down' | 'stable';
    errorCount?: number;
  };
  className?: string;
}

interface StatCardProps {
  icon: React.ComponentType<{ className?: string }>;
  iconColor: string;
  label: string;
  value: string | number;
  subtext?: string;
  trend?: 'up' | 'down' | 'stable';
}

function StatCard({ icon: Icon, iconColor, label, value, subtext, trend }: StatCardProps) {
  return (
    <div className="bg-neutral-50 dark:bg-neutral-800 rounded-lg p-4">
      <div className="flex items-start justify-between">
        <div className={`p-2 rounded-lg ${iconColor}`}>
          <Icon className="h-5 w-5" />
        </div>
        {trend && (
          <div
            className={`flex items-center gap-1 text-xs font-medium ${
              trend === 'up'
                ? 'text-green-600 dark:text-green-400'
                : trend === 'down'
                  ? 'text-red-600 dark:text-red-400'
                  : 'text-neutral-500 dark:text-neutral-400'
            }`}
          >
            <TrendingUp className={`h-3 w-3 ${trend === 'down' ? 'rotate-180' : ''}`} />
            {trend === 'up' ? 'Increasing' : trend === 'down' ? 'Decreasing' : 'Stable'}
          </div>
        )}
      </div>
      <div className="mt-3">
        <p className="text-2xl font-bold text-neutral-900 dark:text-white">{value}</p>
        <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">{label}</p>
        {subtext && (
          <p className="text-xs text-neutral-400 dark:text-neutral-500 mt-1">{subtext}</p>
        )}
      </div>
    </div>
  );
}

function formatLatency(ms: number): string {
  if (ms < 1000) {
    return `${Math.round(ms)}ms`;
  }
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatNumber(num: number): string {
  if (num >= 1000000) {
    return `${(num / 1000000).toFixed(1)}M`;
  }
  if (num >= 1000) {
    return `${(num / 1000).toFixed(1)}K`;
  }
  return num.toString();
}

function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
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

export function UsageStats({ stats, className = '' }: UsageStatsProps) {
  // Default/demo stats if not provided
  const displayStats = stats || {
    callsThisMonth: 0,
    callsToday: 0,
    avgLatencyMs: 0,
    successRate: 0,
    lastCalledAt: undefined,
    errorCount: 0,
  };

  const hasStats = displayStats.callsThisMonth && displayStats.callsThisMonth > 0;

  return (
    <div
      className={`bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-6 ${className}`}
    >
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">Usage Statistics</h2>
        <span className="text-xs text-neutral-500 dark:text-neutral-400 bg-neutral-100 dark:bg-neutral-700 px-2 py-1 rounded">
          This month
        </span>
      </div>

      {!hasStats ? (
        <div className="text-center py-8">
          <Activity className="h-12 w-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-3" />
          <p className="text-neutral-500 dark:text-neutral-400 text-sm">
            No usage data available yet
          </p>
          <p className="text-neutral-400 dark:text-neutral-500 text-xs mt-1">
            Statistics will appear once you start using this tool
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Calls This Month */}
          <StatCard
            icon={BarChart3}
            iconColor="bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400"
            label="Calls this month"
            value={formatNumber(displayStats.callsThisMonth || 0)}
            subtext={displayStats.callsToday ? `${displayStats.callsToday} today` : undefined}
            trend={displayStats.trend}
          />

          {/* Average Latency */}
          <StatCard
            icon={Clock}
            iconColor="bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400"
            label="Avg. latency"
            value={displayStats.avgLatencyMs ? formatLatency(displayStats.avgLatencyMs) : '-'}
            subtext="p50 response time"
          />

          {/* Success Rate */}
          <StatCard
            icon={
              displayStats.successRate && displayStats.successRate >= 99 ? CheckCircle : Activity
            }
            iconColor={
              displayStats.successRate && displayStats.successRate >= 99
                ? 'bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400'
                : displayStats.successRate && displayStats.successRate >= 95
                  ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400'
                  : 'bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400'
            }
            label="Success rate"
            value={displayStats.successRate ? `${displayStats.successRate.toFixed(1)}%` : '-'}
            subtext={displayStats.errorCount ? `${displayStats.errorCount} errors` : undefined}
          />

          {/* Last Called */}
          <StatCard
            icon={Calendar}
            iconColor="bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400"
            label="Last called"
            value={
              displayStats.lastCalledAt ? formatRelativeTime(displayStats.lastCalledAt) : 'Never'
            }
          />
        </div>
      )}

      {/* Usage Trend Graph Placeholder */}
      {hasStats && (
        <div className="mt-6 pt-4 border-t border-neutral-200 dark:border-neutral-700">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
              Daily usage (last 7 days)
            </span>
          </div>
          <div className="h-20 bg-neutral-50 dark:bg-neutral-900 rounded-lg flex items-end justify-around px-4 py-2">
            {/* Simple bar chart visualization */}
            {[40, 65, 45, 80, 55, 70, 90].map((height, idx) => (
              <div
                key={idx}
                className="w-8 bg-primary-200 hover:bg-primary-400 rounded-t transition-colors cursor-pointer"
                style={{ height: `${height}%` }}
                title={`Day ${idx + 1}`}
              />
            ))}
          </div>
          <div className="flex justify-between mt-2 text-xs text-neutral-400 dark:text-neutral-500">
            <span>Mon</span>
            <span>Tue</span>
            <span>Wed</span>
            <span>Thu</span>
            <span>Fri</span>
            <span>Sat</span>
            <span>Sun</span>
          </div>
        </div>
      )}
    </div>
  );
}

export default UsageStats;
