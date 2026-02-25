import type { ElementType } from 'react';

export interface ScoreThreshold {
  min: number;
  label: string;
  bg: string;
  text: string;
}

export interface ScoreGaugeProps {
  /** Numeric score (0-100 for percentages, 0-1 for ratios) */
  score: number;
  /** Maximum value (100 for percentage, 1.0 for ratio) */
  max?: number;
  /** Title displayed above the gauge */
  title: string;
  /** Lucide icon component */
  icon?: ElementType;
  /** Target value displayed as reference (e.g., "Target: 0.94") */
  target?: string;
  /** Custom threshold configuration. Default: 4-tier (excellent/good/fair/poor) */
  thresholds?: ScoreThreshold[];
}

const DEFAULT_THRESHOLDS: ScoreThreshold[] = [
  { min: 90, label: 'Excellent', bg: 'bg-green-500', text: 'text-green-700 dark:text-green-400' },
  { min: 70, label: 'Good', bg: 'bg-blue-500', text: 'text-blue-700 dark:text-blue-400' },
  { min: 50, label: 'Fair', bg: 'bg-yellow-500', text: 'text-yellow-700 dark:text-yellow-400' },
  { min: 0, label: 'Poor', bg: 'bg-red-500', text: 'text-red-700 dark:text-red-400' },
];

function resolveThreshold(
  score: number,
  max: number,
  thresholds: ScoreThreshold[],
): ScoreThreshold {
  const normalized = max !== 0 ? (score / max) * 100 : 0;
  for (const t of thresholds) {
    if (normalized >= t.min) return t;
  }
  return thresholds[thresholds.length - 1];
}

/**
 * Score gauge with progress bar and threshold-based coloring.
 *
 * Generalized from APDEXGauge (GatewayObservability). Supports:
 * - Security scores (0-100)
 * - Compliance scores (0-100)
 * - APDEX scores (0-1.0)
 * - Custom threshold configurations
 */
export function ScoreGauge({
  score,
  max = 100,
  title,
  icon: Icon,
  target,
  thresholds = DEFAULT_THRESHOLDS,
}: ScoreGaugeProps) {
  const config = resolveThreshold(score, max, thresholds);
  const percentage = max !== 0 ? Math.min((score / max) * 100, 100) : 0;
  const displayValue = max <= 1 ? score.toFixed(2) : Math.round(score).toString();

  return (
    <div className="bg-white dark:bg-neutral-800 rounded-lg shadow px-4 py-4">
      <div className="flex items-center gap-2 mb-2">
        {Icon && <Icon className="h-4 w-4 text-neutral-500 dark:text-neutral-400" />}
        <p className="text-sm font-medium text-neutral-700 dark:text-neutral-300">{title}</p>
      </div>
      <div className="flex items-end gap-3">
        <span className={`text-3xl font-bold ${config.text}`}>{displayValue}</span>
        <span
          className={`text-xs font-medium px-2 py-0.5 rounded-full ${config.bg} text-white`}
        >
          {config.label}
        </span>
      </div>
      <div className="w-full bg-neutral-200 dark:bg-neutral-700 rounded-full h-2 mt-3">
        <div
          className={`h-2 rounded-full ${config.bg} transition-all duration-500`}
          style={{ width: `${percentage}%` }}
        />
      </div>
      {target && (
        <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-2">{target}</p>
      )}
    </div>
  );
}
