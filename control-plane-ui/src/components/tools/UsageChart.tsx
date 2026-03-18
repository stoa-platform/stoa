import { useMemo } from 'react';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import {
  ChartCard,
  ChartEmptyState,
  CHART_TOOLTIP_STYLE,
  CHART_AXIS_STYLE,
  CHART_GRID_STYLE,
  CHART_EMPTY_STATE_HEIGHT,
} from '@stoa/shared/components/ChartCard';

interface DataPoint {
  timestamp: string;
  calls: number;
  successRate: number;
  avgLatencyMs: number;
  costUnits: number;
}

interface UsageChartProps {
  data: DataPoint[];
  metric: 'calls' | 'successRate' | 'avgLatencyMs' | 'costUnits';
  title: string;
  height?: number;
}

const BAR_COLORS: Record<string, string> = {
  calls: '#3B82F6',
  successRate: '#10B981',
  avgLatencyMs: '#F97316',
  costUnits: '#8B5CF6',
};

function formatValue(value: number, metric: string): string {
  if (metric === 'successRate') return `${(value * 100).toFixed(1)}%`;
  if (metric === 'costUnits') return `$${value.toFixed(4)}`;
  if (metric === 'avgLatencyMs') return `${value.toFixed(0)}ms`;
  return value.toLocaleString();
}

function formatLabel(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

export function UsageChart({
  data,
  metric,
  title,
  height = CHART_EMPTY_STATE_HEIGHT,
}: UsageChartProps) {
  const { trend, chartData } = useMemo(() => {
    const vals = data.map((d) => d[metric]);

    let trendVal = 0;
    if (vals.length >= 6) {
      const recent = vals.slice(-3).reduce((a, b) => a + b, 0) / 3;
      const previous = vals.slice(-6, -3).reduce((a, b) => a + b, 0) / 3;
      trendVal = previous > 0 ? ((recent - previous) / previous) * 100 : 0;
    }

    const formatted = data.map((d) => ({
      ...d,
      label: formatLabel(d.timestamp),
    }));

    return { trend: trendVal, chartData: formatted };
  }, [data, metric]);

  const TrendIcon = trend > 5 ? TrendingUp : trend < -5 ? TrendingDown : Minus;
  const trendColor =
    metric === 'successRate'
      ? trend > 0
        ? 'text-green-600'
        : trend < 0
          ? 'text-red-600'
          : 'text-neutral-500'
      : metric === 'avgLatencyMs'
        ? trend < 0
          ? 'text-green-600'
          : trend > 0
            ? 'text-red-600'
            : 'text-neutral-500'
        : trend > 0
          ? 'text-green-600'
          : trend < 0
            ? 'text-red-600'
            : 'text-neutral-500';

  if (data.length === 0) {
    return (
      <ChartCard
        title={title}
        trailing={
          <div className={`flex items-center gap-1 text-sm ${trendColor}`}>
            <TrendIcon className="h-4 w-4" />
            <span>{Math.abs(trend).toFixed(1)}%</span>
          </div>
        }
      >
        <ChartEmptyState height={height} />
      </ChartCard>
    );
  }

  return (
    <ChartCard
      title={title}
      trailing={
        <div className={`flex items-center gap-1 text-sm ${trendColor}`}>
          <TrendIcon className="h-4 w-4" />
          <span>{Math.abs(trend).toFixed(1)}%</span>
        </div>
      }
    >
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={chartData}>
          <CartesianGrid {...CHART_GRID_STYLE} />
          <XAxis dataKey="label" tick={CHART_AXIS_STYLE} axisLine={false} tickLine={false} />
          <YAxis
            tick={CHART_AXIS_STYLE}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v: number) =>
              metric === 'successRate'
                ? `${(v * 100).toFixed(0)}%`
                : v >= 1000
                  ? `${(v / 1000).toFixed(1)}K`
                  : String(Math.round(v))
            }
          />
          <Tooltip
            contentStyle={CHART_TOOLTIP_STYLE}
            formatter={(value) => [formatValue(Number(value), metric), title]}
          />
          <Bar dataKey={metric} fill={BAR_COLORS[metric] || '#3B82F6'} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

interface UsageStatsCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  trend?: number;
  icon?: React.ReactNode;
  color?: 'blue' | 'green' | 'orange' | 'purple' | 'red';
}

export function UsageStatsCard({
  title,
  value,
  subtitle,
  trend,
  icon,
  color = 'blue',
}: UsageStatsCardProps) {
  const colorClasses = {
    blue: 'bg-blue-50 dark:bg-blue-950/30 text-blue-600 dark:text-blue-400',
    green: 'bg-green-50 dark:bg-green-950/30 text-green-600 dark:text-green-400',
    orange: 'bg-orange-50 dark:bg-orange-950/30 text-orange-600 dark:text-orange-400',
    purple: 'bg-purple-50 dark:bg-purple-950/30 text-purple-600 dark:text-purple-400',
    red: 'bg-red-50 dark:bg-red-950/30 text-red-600 dark:text-red-400',
  };

  return (
    <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-neutral-500 dark:text-neutral-400">{title}</span>
        {icon && <div className={`p-2 rounded-lg ${colorClasses[color]}`}>{icon}</div>}
      </div>
      <div className="text-2xl font-bold text-neutral-900 dark:text-white">{value}</div>
      <div className="flex items-center justify-between mt-1">
        {subtitle && (
          <span className="text-xs text-neutral-400 dark:text-neutral-500">{subtitle}</span>
        )}
        {trend !== undefined && (
          <span
            className={`flex items-center gap-1 text-xs ${trend >= 0 ? 'text-green-600' : 'text-red-600'}`}
          >
            {trend >= 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
            {Math.abs(trend).toFixed(1)}%
          </span>
        )}
      </div>
    </div>
  );
}
