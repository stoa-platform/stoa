export type TimeRange = '1h' | '6h' | '24h' | '7d' | '30d';

export interface RangeConfig {
  seconds: number;
  step: string;
  label: string;
}

export const RANGE_CONFIG: Record<TimeRange, RangeConfig> = {
  '1h': { seconds: 3600, step: '60s', label: '1 hour' },
  '6h': { seconds: 21600, step: '300s', label: '6 hours' },
  '24h': { seconds: 86400, step: '900s', label: '24 hours' },
  '7d': { seconds: 604800, step: '3600s', label: '7 days' },
  '30d': { seconds: 2592000, step: '14400s', label: '30 days' },
};

export interface TimeRangeSelectorProps {
  /** Current selected range */
  value: TimeRange;
  /** Called when user picks a different range */
  onChange: (range: TimeRange) => void;
  /** Restrict which ranges are shown (default: ['1h','6h','24h']) */
  ranges?: TimeRange[];
}

/**
 * Button-group time range selector used across all STOA dashboards.
 *
 * Extracts the duplicated 1h/6h/24h toggle from TenantDashboard,
 * PlatformMetricsDashboard, and RequestExplorerDashboard.
 * Adds 7d/30d for analytics dashboards (CAB-1476).
 */
export function TimeRangeSelector({
  value,
  onChange,
  ranges = ['1h', '6h', '24h'],
}: TimeRangeSelectorProps) {
  return (
    <div className="flex gap-1 bg-neutral-100 dark:bg-neutral-700 rounded-lg p-0.5">
      {ranges.map((range) => (
        <button
          key={range}
          onClick={() => onChange(range)}
          className={`px-3 py-1 text-sm font-medium rounded-md transition-colors ${
            value === range
              ? 'bg-white dark:bg-neutral-600 text-neutral-900 dark:text-white shadow-sm'
              : 'text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200'
          }`}
        >
          {range}
        </button>
      ))}
    </div>
  );
}
