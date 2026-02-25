export interface TrendIndicatorProps {
  /** Time-series data points — needs at least 6 for a meaningful trend */
  data: { value: number }[];
  /**
   * Invert color semantics (e.g., for error rates: "up" = bad = red).
   * Default: up = green, down = red.
   */
  invertColor?: boolean;
}

/**
 * Compact trend indicator comparing the first and last third of a dataset.
 *
 * Extracted from TenantDashboard and PlatformMetricsDashboard where
 * identical implementations were duplicated.
 */
export function TrendIndicator({ data, invertColor = false }: TrendIndicatorProps) {
  if (data.length < 6) return null;

  const third = Math.floor(data.length / 3);
  const firstAvg = data.slice(0, third).reduce((s, d) => s + d.value, 0) / third;
  const lastAvg = data.slice(-third).reduce((s, d) => s + d.value, 0) / third;

  if (firstAvg === 0) return null;

  const change = ((lastAvg - firstAvg) / firstAvg) * 100;
  const isUp = change > 0;

  const color = invertColor
    ? isUp
      ? 'text-red-500'
      : 'text-green-500'
    : isUp
      ? 'text-green-500'
      : 'text-red-500';

  return (
    <div className={`flex items-center gap-1 text-xs ${color}`}>
      <span className="text-sm">{isUp ? '\u2191' : '\u2193'}</span>
      <span>{Math.abs(change).toFixed(1)}%</span>
    </div>
  );
}
