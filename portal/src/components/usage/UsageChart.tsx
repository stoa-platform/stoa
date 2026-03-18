/**
 * UsageChart Component - CAB-280
 * Interactive bar chart for 7-day call volume with hover tooltips.
 * Migrated from div bars to Recharts for interactive data navigation (CAB-1883).
 */

import { memo } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import {
  CHART_TOOLTIP_STYLE,
  CHART_AXIS_STYLE,
  CHART_GRID_STYLE,
  ChartEmptyState,
} from '@stoa/shared/components/ChartCard';
import type { DailyCallStat } from '../../types';

interface UsageChartProps {
  data: DailyCallStat[];
  isLoading?: boolean;
}

function ChartSkeleton() {
  return (
    <div className="animate-pulse">
      <div className="flex items-end gap-2 h-40">
        {[...Array(7)].map((_, i) => (
          <div
            key={i}
            className="flex-1 bg-neutral-200 dark:bg-neutral-600 rounded-t"
            style={{ height: `${Math.random() * 60 + 20}%` }}
          />
        ))}
      </div>
    </div>
  );
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString('en-US', { weekday: 'short' });
}

export const UsageChart = memo(function UsageChart({ data, isLoading = false }: UsageChartProps) {
  if (isLoading) {
    return (
      <div className="rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 p-6">
        <h3 className="text-lg font-semibold text-neutral-900 dark:text-white mb-4">
          Call Volume (7 days)
        </h3>
        <ChartSkeleton />
      </div>
    );
  }

  const chartData = data.map((d, i) => ({
    ...d,
    label: formatDate(d.date),
    isToday: i === data.length - 1,
  }));

  const totalCalls = data.reduce((sum, d) => sum + d.calls, 0);

  return (
    <div className="rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 p-6">
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-lg font-semibold text-neutral-900 dark:text-white">
          Call Volume (7 days)
        </h3>
        <span className="text-sm text-neutral-500 dark:text-neutral-400">
          Total: {totalCalls.toLocaleString()} calls
        </span>
      </div>

      {data.length === 0 ? (
        <ChartEmptyState message="No call data available" height={160} />
      ) : (
        <ResponsiveContainer width="100%" height={160}>
          <BarChart data={chartData} barCategoryGap="20%">
            <CartesianGrid {...CHART_GRID_STYLE} />
            <XAxis dataKey="label" tick={CHART_AXIS_STYLE} axisLine={false} tickLine={false} />
            <YAxis
              tick={CHART_AXIS_STYLE}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: number) => (v >= 1000 ? `${(v / 1000).toFixed(1)}K` : String(v))}
            />
            <Tooltip
              contentStyle={CHART_TOOLTIP_STYLE}
              formatter={(value) => [`${Number(value).toLocaleString()} calls`, 'Volume']}
            />
            <Bar dataKey="calls" radius={[4, 4, 0, 0]}>
              {chartData.map((entry, index) => (
                <Cell key={index} fill={entry.isToday ? '#6366F1' : '#A5B4FC'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
});
