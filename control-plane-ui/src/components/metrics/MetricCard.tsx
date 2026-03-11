import { useMemo } from 'react';
import { usePrometheusQuery, usePrometheusRange, scalarValue } from '../../hooks/usePrometheus';
import { SparklineChart } from '../charts/SparklineChart';

interface MetricCardProps {
  label: string;
  query: string;
  /** Optional range query for sparkline (defaults to same query over 1h) */
  rangeQuery?: string;
  /** Format function for the displayed value */
  format?: (value: number | null) => string;
  /** Sparkline color */
  color?: string;
  /** Icon component */
  icon?: React.ComponentType<{ className?: string }>;
  /** Range duration in seconds (default 3600 = 1h) */
  rangeDuration?: number;
  /** Range step (default "5m") */
  rangeStep?: string;
  className?: string;
}

const defaultFormat = (v: number | null) => (v === null ? '—' : v.toFixed(1));

/**
 * Self-contained metric card: fetches data from Prometheus, renders value + sparkline.
 * No Grafana iframe — pure React + SVG.
 */
export function MetricCard({
  label,
  query,
  rangeQuery,
  format = defaultFormat,
  color = '#3b82f6',
  icon: Icon,
  rangeDuration = 3600,
  rangeStep = '5m',
  className = '',
}: MetricCardProps) {
  const {
    data: instantData,
    loading: instantLoading,
    error: instantError,
  } = usePrometheusQuery(query);
  const { data: rangeData, loading: rangeLoading } = usePrometheusRange(
    rangeQuery || query,
    rangeDuration,
    rangeStep
  );

  const value = useMemo(() => scalarValue(instantData), [instantData]);
  const loading = instantLoading || rangeLoading;

  return (
    <div
      className={`bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 ${className}`}
    >
      <div className="flex items-center gap-2 text-sm text-neutral-500 dark:text-neutral-400 mb-1">
        {Icon && <Icon className="h-4 w-4" />}
        {label}
      </div>

      {loading ? (
        <div className="animate-pulse h-8 bg-neutral-100 dark:bg-neutral-700 rounded w-20 mt-1" />
      ) : instantError ? (
        <div className="text-sm text-neutral-400 dark:text-neutral-500 mt-1">Unavailable</div>
      ) : (
        <div className="text-2xl font-semibold text-neutral-900 dark:text-white mt-1">
          {format(value)}
        </div>
      )}

      {/* Sparkline */}
      <div className="mt-2">
        {rangeData && rangeData.length >= 2 ? (
          <SparklineChart data={rangeData} color={color} height={40} width={200} />
        ) : (
          <div className="h-10" />
        )}
      </div>
    </div>
  );
}
