import type { ElementType, ReactNode } from 'react';

type TrendDirection = 'up' | 'down' | 'stable';

export interface StatCardProps {
  /** KPI label (uppercase, small text) */
  label: string;
  /** Primary value (number or formatted string) */
  value: string | number;
  /** Unit displayed next to the value */
  unit?: string;
  /** Lucide icon component */
  icon?: ElementType;
  /** Tailwind text color class — also controls icon background tint */
  colorClass?: string;
  /** Small text below the value */
  subtitle?: string;
  /** Optional sparkline or chart rendered below the value */
  sparkline?: ReactNode;
  /** Trend arrow indicator */
  trend?: TrendDirection;
}

const BG_MAP: Record<string, string> = {
  green: 'bg-green-100 dark:bg-green-900/30',
  red: 'bg-red-100 dark:bg-red-900/30',
  yellow: 'bg-yellow-100 dark:bg-yellow-900/30',
  orange: 'bg-orange-100 dark:bg-orange-900/30',
  purple: 'bg-purple-100 dark:bg-purple-900/30',
  blue: 'bg-blue-100 dark:bg-blue-900/30',
};

function inferBg(colorClass: string | undefined): string {
  if (!colorClass) return BG_MAP.blue;
  for (const key of Object.keys(BG_MAP)) {
    if (colorClass.includes(key)) return BG_MAP[key];
  }
  return BG_MAP.blue;
}

const TREND_CONFIG: Record<TrendDirection, { symbol: string; color: string }> = {
  up: { symbol: '\u2191', color: 'text-green-500' },
  down: { symbol: '\u2193', color: 'text-red-500' },
  stable: { symbol: '\u2192', color: 'text-neutral-400' },
};

/**
 * Unified stat card for all STOA dashboards.
 *
 * Supports 3 usage modes:
 * - Full: icon + value + unit + sparkline + trend (Platform, Tenant dashboards)
 * - Standard: icon + value + subtitle (Operations, Request Explorer)
 * - Minimal: label + value + color (Gateway Observability)
 */
export function StatCard({
  label,
  value,
  unit,
  icon: Icon,
  colorClass,
  subtitle,
  sparkline,
  trend,
}: StatCardProps) {
  const bgClass = inferBg(colorClass);

  return (
    <div className="bg-white dark:bg-neutral-800 rounded-lg shadow px-4 py-4 flex items-start gap-4">
      {Icon && (
        <div className={`p-2 rounded-lg ${bgClass}`}>
          <Icon className={`h-5 w-5 ${colorClass || 'text-blue-600 dark:text-blue-400'}`} />
        </div>
      )}
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
          {label}
        </p>
        <div className="flex items-baseline gap-1">
          <p
            className={`text-2xl font-bold ${colorClass || 'text-neutral-900 dark:text-white'}`}
          >
            {value}
          </p>
          {unit && (
            <span className="text-sm text-neutral-500 dark:text-neutral-400">{unit}</span>
          )}
          {trend && (
            <span className={`text-sm font-medium ${TREND_CONFIG[trend].color}`}>
              {TREND_CONFIG[trend].symbol}
            </span>
          )}
        </div>
        {subtitle && (
          <p className="text-xs text-neutral-400 dark:text-neutral-500 mt-0.5">{subtitle}</p>
        )}
        {sparkline && <div className="mt-2">{sparkline}</div>}
      </div>
    </div>
  );
}
