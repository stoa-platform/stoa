/**
 * QuotaBar Component (CAB-1907)
 *
 * Displays subscription usage as a visual progress bar with color coding:
 * - Green: < 60% usage
 * - Yellow: 60-80% usage
 * - Red: > 80% usage
 */

interface QuotaBarProps {
  used: number;
  limit: number;
  label?: string;
  /** Show percentage text. Default: true */
  showPercent?: boolean;
}

function getQuotaColor(percent: number): {
  bar: string;
  text: string;
  bg: string;
} {
  if (percent >= 80) {
    return {
      bar: 'bg-red-500',
      text: 'text-red-700 dark:text-red-400',
      bg: 'bg-red-100 dark:bg-red-900/30',
    };
  }
  if (percent >= 60) {
    return {
      bar: 'bg-amber-500',
      text: 'text-amber-700 dark:text-amber-400',
      bg: 'bg-amber-100 dark:bg-amber-900/30',
    };
  }
  return {
    bar: 'bg-emerald-500',
    text: 'text-emerald-700 dark:text-emerald-400',
    bg: 'bg-emerald-100 dark:bg-emerald-900/30',
  };
}

export function QuotaBar({ used, limit, label, showPercent = true }: QuotaBarProps) {
  const percent = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  const colors = getQuotaColor(percent);

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        {label && <span className="text-neutral-500 dark:text-neutral-400">{label}</span>}
        <span className={`font-medium ${colors.text}`}>
          {showPercent && `${percent}% — `}
          {used.toLocaleString()} / {limit.toLocaleString()}
        </span>
      </div>
      <div className="w-full h-2 rounded-full bg-neutral-200 dark:bg-neutral-700 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-300 ${colors.bar}`}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}
