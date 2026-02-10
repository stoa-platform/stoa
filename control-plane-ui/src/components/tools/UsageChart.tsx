import { useMemo } from 'react';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

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

export function UsageChart({ data, metric, title, height = 200 }: UsageChartProps) {
  const { values, max, min, trend, formattedValues } = useMemo(() => {
    const vals = data.map((d) => d[metric]);
    const maxVal = Math.max(...vals, 1);
    const minVal = Math.min(...vals, 0);

    // Calculate trend (compare last 3 points vs previous 3)
    let trendVal = 0;
    if (vals.length >= 6) {
      const recent = vals.slice(-3).reduce((a, b) => a + b, 0) / 3;
      const previous = vals.slice(-6, -3).reduce((a, b) => a + b, 0) / 3;
      trendVal = previous > 0 ? ((recent - previous) / previous) * 100 : 0;
    }

    // Format values for display
    const formatted = vals.map((v) => {
      if (metric === 'successRate') return `${(v * 100).toFixed(1)}%`;
      if (metric === 'costUnits') return `$${v.toFixed(4)}`;
      if (metric === 'avgLatencyMs') return `${v.toFixed(0)}ms`;
      return v.toLocaleString();
    });

    return { values: vals, max: maxVal, min: minVal, trend: trendVal, formattedValues: formatted };
  }, [data, metric]);

  const getBarHeight = (value: number): number => {
    if (max === min) return 50;
    return ((value - min) / (max - min)) * 100;
  };

  const formatLabel = (timestamp: string): string => {
    const date = new Date(timestamp);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  const TrendIcon = trend > 5 ? TrendingUp : trend < -5 ? TrendingDown : Minus;
  const trendColor =
    metric === 'successRate'
      ? trend > 0
        ? 'text-green-600'
        : trend < 0
          ? 'text-red-600'
          : 'text-gray-500'
      : metric === 'avgLatencyMs'
        ? trend < 0
          ? 'text-green-600'
          : trend > 0
            ? 'text-red-600'
            : 'text-gray-500'
        : trend > 0
          ? 'text-green-600'
          : trend < 0
            ? 'text-red-600'
            : 'text-gray-500';

  const barColor = {
    calls: 'bg-blue-500',
    successRate: 'bg-green-500',
    avgLatencyMs: 'bg-orange-500',
    costUnits: 'bg-purple-500',
  }[metric];

  if (data.length === 0) {
    return (
      <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 p-4">
        <h3 className="text-sm font-medium text-gray-700 dark:text-neutral-300 mb-4">{title}</h3>
        <div
          className="flex items-center justify-center text-gray-400 dark:text-neutral-500 text-sm"
          style={{ height }}
        >
          No data available
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-gray-700 dark:text-neutral-300">{title}</h3>
        <div className={`flex items-center gap-1 text-sm ${trendColor}`}>
          <TrendIcon className="h-4 w-4" />
          <span>{Math.abs(trend).toFixed(1)}%</span>
        </div>
      </div>

      {/* Chart */}
      <div className="relative" style={{ height }}>
        <div className="absolute inset-0 flex items-end gap-1">
          {values.map((value, index) => (
            <div key={index} className="flex-1 flex flex-col items-center group">
              {/* Tooltip */}
              <div className="opacity-0 group-hover:opacity-100 absolute bottom-full mb-2 px-2 py-1 bg-gray-800 text-white text-xs rounded whitespace-nowrap transition-opacity z-10">
                <div className="font-medium">{formattedValues[index]}</div>
                <div className="text-gray-400">{formatLabel(data[index].timestamp)}</div>
              </div>

              {/* Bar */}
              <div
                className={`w-full ${barColor} rounded-t transition-all hover:opacity-80`}
                style={{ height: `${getBarHeight(value)}%` }}
              />
            </div>
          ))}
        </div>

        {/* Y-axis labels */}
        <div className="absolute left-0 top-0 bottom-0 flex flex-col justify-between text-xs text-gray-400 dark:text-neutral-500 -ml-8 w-8 text-right">
          <span>
            {metric === 'successRate' ? `${(max * 100).toFixed(0)}%` : max.toLocaleString()}
          </span>
          <span>
            {metric === 'successRate' ? `${(min * 100).toFixed(0)}%` : min.toLocaleString()}
          </span>
        </div>
      </div>

      {/* X-axis labels */}
      <div className="flex justify-between mt-2 text-xs text-gray-400 dark:text-neutral-500">
        <span>{data.length > 0 ? formatLabel(data[0].timestamp) : ''}</span>
        <span>{data.length > 0 ? formatLabel(data[data.length - 1].timestamp) : ''}</span>
      </div>
    </div>
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
    <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-gray-500 dark:text-neutral-400">{title}</span>
        {icon && <div className={`p-2 rounded-lg ${colorClasses[color]}`}>{icon}</div>}
      </div>
      <div className="text-2xl font-bold text-gray-900 dark:text-white">{value}</div>
      <div className="flex items-center justify-between mt-1">
        {subtitle && (
          <span className="text-xs text-gray-400 dark:text-neutral-500">{subtitle}</span>
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
