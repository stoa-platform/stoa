import { memo } from 'react';
import { usePrometheusQuery, scalarValue } from '../../hooks/usePrometheus';

/**
 * Inline metric tile: renders loading skeleton / error / formatted value
 * from a Prometheus query. Extracted in CAB-1887 G5 so it can be reused
 * per-gateway in the aggregated Overview.
 */
export const SloMetricTile = memo(function SloMetricTile({
  label,
  query,
  unit,
  digits = 2,
  testId,
}: {
  label: string;
  query: string;
  unit: string;
  digits?: number;
  testId: string;
}) {
  const { data, loading, error } = usePrometheusQuery(query);
  const value = scalarValue(data);
  return (
    <div className="flex-1 min-w-0" data-testid={testId}>
      <p className="text-xs text-neutral-500 dark:text-neutral-400">{label}</p>
      {loading ? (
        <div className="animate-pulse mt-1 h-7 w-20 rounded bg-neutral-100 dark:bg-neutral-700" />
      ) : error ? (
        <p className="mt-1 text-sm text-red-600 dark:text-red-400" title={error}>
          Unavailable
        </p>
      ) : value === null ? (
        <p className="mt-1 text-sm text-neutral-400 dark:text-neutral-500">—</p>
      ) : (
        <p className="mt-1 text-xl font-semibold text-neutral-900 dark:text-white">
          {value.toFixed(digits)}
          <span className="text-sm font-normal text-neutral-500 dark:text-neutral-400 ml-1">
            {unit}
          </span>
        </p>
      )}
    </div>
  );
});
