import { ChartEmptyState } from '@stoa/shared/components/ChartCard';

export type StatusClass = '2xx' | '3xx' | '4xx' | '5xx';

export interface StatusMixEntry {
  statusClass: StatusClass;
  label: string;
  count: number;
}

const STATUS_CLASS_COLORS: Record<StatusClass, string> = {
  '2xx': '#10B981',
  '3xx': '#3B82F6',
  '4xx': '#F59E0B',
  '5xx': '#EF4444',
};

function formatCount(count: number): string {
  return count >= 1000 ? `${(count / 1000).toFixed(1)}K` : String(Math.round(count));
}

function formatShare(count: number, total: number): string {
  if (total <= 0) return '0.0%';
  return `${((count / total) * 100).toFixed(1)}%`;
}

export function StatusMix({ entries }: { entries: StatusMixEntry[] }) {
  const total = entries.reduce((sum, entry) => sum + entry.count, 0);

  if (total <= 0) {
    return <ChartEmptyState message="No status mix data in this period" />;
  }

  return (
    <div data-testid="status-mix-chart" className="h-[250px] flex flex-col justify-center gap-6">
      <div
        className="flex h-12 w-full overflow-hidden rounded-md bg-neutral-100 dark:bg-neutral-700"
        aria-label="HTTP status class mix"
      >
        {entries
          .filter((entry) => entry.count > 0)
          .map((entry) => {
            const share = (entry.count / total) * 100;
            return (
              <div
                key={entry.statusClass}
                data-testid={`status-mix-segment-${entry.statusClass}`}
                className="flex shrink-0 items-center justify-center px-2 text-xs font-semibold text-white tabular-nums"
                style={{
                  width: `${share}%`,
                  backgroundColor: STATUS_CLASS_COLORS[entry.statusClass],
                }}
                title={`${entry.label}: ${formatCount(entry.count)} requests (${formatShare(
                  entry.count,
                  total
                )})`}
              >
                {share >= 8 ? entry.statusClass : ''}
              </div>
            );
          })}
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4" role="list">
        {entries.map((entry) => (
          <div
            key={entry.statusClass}
            role="listitem"
            className="rounded-md border border-neutral-200 px-3 py-2 dark:border-neutral-700"
          >
            <div className="flex items-center gap-2">
              <span
                className="h-2.5 w-2.5 rounded-sm"
                style={{ backgroundColor: STATUS_CLASS_COLORS[entry.statusClass] }}
              />
              <span className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
                {entry.label}
              </span>
            </div>
            <div className="mt-2 flex items-baseline justify-between gap-2">
              <span className="text-sm font-semibold tabular-nums text-neutral-900 dark:text-white">
                {formatCount(entry.count)}
              </span>
              <span
                data-testid={`status-mix-share-${entry.statusClass}`}
                className="text-xs tabular-nums text-neutral-500 dark:text-neutral-400"
              >
                {formatShare(entry.count, total)}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
