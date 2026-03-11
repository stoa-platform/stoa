import { usePrometheusRange } from '../../hooks/usePrometheus';
import { SparklineChart } from '../charts/SparklineChart';

interface MetricTimeseriesProps {
  label: string;
  query: string;
  /** Duration in seconds (default 3600 = 1h) */
  duration?: number;
  /** Step resolution (default "1m") */
  step?: string;
  /** Chart height (default 200) */
  height?: number;
  /** Line color */
  color?: string;
  className?: string;
}

/**
 * Full-width time-series chart powered by Prometheus range query.
 * Uses SparklineChart (custom SVG) — no charting library required.
 */
export function MetricTimeseries({
  label,
  query,
  duration = 3600,
  step = '1m',
  height = 200,
  color = '#ef4444',
  className = '',
}: MetricTimeseriesProps) {
  const { data, loading, error } = usePrometheusRange(query, duration, step);

  return (
    <div
      className={`bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 ${className}`}
    >
      <h3 className="text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-3">{label}</h3>

      {loading ? (
        <div
          className="animate-pulse bg-neutral-100 dark:bg-neutral-700 rounded"
          style={{ height }}
        />
      ) : error ? (
        <div
          className="flex items-center justify-center text-sm text-neutral-400 dark:text-neutral-500 rounded border border-dashed border-neutral-300 dark:border-neutral-600"
          style={{ height }}
        >
          Metrics unavailable
        </div>
      ) : data && data.length >= 2 ? (
        <SparklineChart data={data} color={color} height={height} width={800} showArea />
      ) : (
        <div
          className="flex items-center justify-center text-sm text-neutral-400 dark:text-neutral-500"
          style={{ height }}
        >
          No data
        </div>
      )}
    </div>
  );
}
