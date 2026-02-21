/**
 * Error Taxonomy Chart — SVG horizontal bar chart (CAB-1318)
 *
 * Color-coded: auth=red, rate_limit=amber, backend=orange, timeout=purple, validation=blue.
 */

interface TaxonomyItem {
  category: string;
  count: number;
  avg_duration_ms: number | null;
  percentage: number;
}

interface ErrorTaxonomyChartProps {
  items: TaxonomyItem[];
  totalErrors: number;
}

const CATEGORY_COLORS: Record<string, { bar: string; text: string }> = {
  auth: { bar: '#ef4444', text: 'text-red-600' },
  rate_limit: { bar: '#f59e0b', text: 'text-amber-600' },
  backend: { bar: '#f97316', text: 'text-orange-600' },
  timeout: { bar: '#8b5cf6', text: 'text-purple-600' },
  validation: { bar: '#3b82f6', text: 'text-blue-600' },
};

const CATEGORY_LABELS: Record<string, string> = {
  auth: 'Auth',
  rate_limit: 'Rate Limit',
  backend: 'Backend',
  timeout: 'Timeout',
  validation: 'Validation',
};

export function ErrorTaxonomyChart({ items, totalErrors }: ErrorTaxonomyChartProps) {
  if (items.length === 0) {
    return <p className="text-sm text-gray-500 dark:text-neutral-400">No error data available</p>;
  }

  const maxCount = Math.max(...items.map((i) => i.count));

  return (
    <div className="space-y-3">
      {items.map((item) => {
        const colors = CATEGORY_COLORS[item.category] || {
          bar: '#6b7280',
          text: 'text-gray-600',
        };
        const label = CATEGORY_LABELS[item.category] || item.category;
        const widthPct = maxCount > 0 ? (item.count / maxCount) * 100 : 0;

        return (
          <div key={item.category} className="flex items-center gap-4">
            <div className="w-24 text-sm font-medium text-gray-700 dark:text-neutral-300">
              {label}
            </div>
            <div className="flex-1">
              <svg width="100%" height="24" role="img" aria-label={`${label}: ${item.count}`}>
                <rect x="0" y="2" width="100%" height="20" rx="4" fill="#e5e7eb" opacity="0.3" />
                <rect x="0" y="2" width={`${widthPct}%`} height="20" rx="4" fill={colors.bar} />
              </svg>
            </div>
            <div className="w-16 text-right text-sm font-semibold text-gray-900 dark:text-white">
              {item.count}
            </div>
            <div className="w-16 text-right text-xs text-gray-500 dark:text-neutral-400">
              {item.percentage}%
            </div>
          </div>
        );
      })}
      <p className="text-xs text-gray-500 dark:text-neutral-400 mt-2">
        {totalErrors} total errors across {items.length} categories
      </p>
    </div>
  );
}
