import type { ReactNode } from 'react';

/** Shared Recharts tooltip style — dark background, consistent across all dashboards. */
export const CHART_TOOLTIP_STYLE: React.CSSProperties = {
  backgroundColor: '#1F2937',
  border: '1px solid #374151',
  borderRadius: 8,
  fontSize: 12,
};

/** Shared axis tick style — small, neutral, no axis/tick lines. */
export const CHART_AXIS_STYLE = {
  fontSize: 11,
  fill: '#9CA3AF',
};

/** Shared CartesianGrid style. */
export const CHART_GRID_STYLE = {
  strokeDasharray: '3 3',
  stroke: '#374151',
  opacity: 0.3,
};

/** Standard chart content height in px. */
export const CHART_EMPTY_STATE_HEIGHT = 250;

export interface ChartCardProps {
  /** Section title — rendered uppercase, small, semibold. */
  title: string;
  /** Optional icon rendered to the right of the title. */
  icon?: ReactNode;
  /** Optional badge or metadata rendered to the right of the title. */
  trailing?: ReactNode;
  /** Chart content. */
  children: ReactNode;
  /** Additional className on the outer card. */
  className?: string;
}

/**
 * Unified card wrapper for all chart panels across Console and Portal.
 *
 * Provides consistent: rounded-lg shadow, dark mode, header styling.
 * Chart content is rendered as children — no opinion on chart library.
 */
export function ChartCard({ title, icon, trailing, children, className = '' }: ChartCardProps) {
  return (
    <div className={`bg-white dark:bg-neutral-800 rounded-lg shadow p-4 ${className}`}>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
          {title}
        </h2>
        {(icon || trailing) && (
          <div className="flex items-center gap-2">
            {trailing}
            {icon}
          </div>
        )}
      </div>
      {children}
    </div>
  );
}

export interface ChartEmptyStateProps {
  message?: string;
  height?: number;
}

/** Consistent empty state placeholder for charts with no data. */
export function ChartEmptyState({
  message = 'No data available',
  height = CHART_EMPTY_STATE_HEIGHT,
}: ChartEmptyStateProps) {
  return (
    <div
      className="flex items-center justify-center text-sm text-neutral-400 dark:text-neutral-500"
      style={{ height }}
    >
      {message}
    </div>
  );
}
