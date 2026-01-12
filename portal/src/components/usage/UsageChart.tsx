/**
 * UsageChart Component - CAB-280
 * Graphique d'évolution des appels sur 7 jours
 */

import type { DailyCallStat } from '../../types';

interface UsageChartProps {
  data: DailyCallStat[];
  isLoading?: boolean;
}

function ChartSkeleton() {
  return (
    <div className="animate-pulse">
      <div className="flex items-end gap-2 h-40">
        {[...Array(7)].map((_, i) => (
          <div
            key={i}
            className="flex-1 bg-gray-200 rounded-t"
            style={{ height: `${Math.random() * 60 + 20}%` }}
          />
        ))}
      </div>
    </div>
  );
}

export function UsageChart({ data, isLoading = false }: UsageChartProps) {
  if (isLoading) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Call Volume (7 days)</h3>
        <ChartSkeleton />
      </div>
    );
  }

  const maxCalls = Math.max(...data.map(d => d.calls), 1);

  // Format date for display
  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { weekday: 'short' });
  };

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6">
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-lg font-semibold text-gray-900">Call Volume (7 days)</h3>
        <span className="text-sm text-gray-500">
          Total: {data.reduce((sum, d) => sum + d.calls, 0).toLocaleString()} calls
        </span>
      </div>

      {/* Chart */}
      <div className="flex items-end gap-3 h-40">
        {data.map((day, index) => {
          const height = (day.calls / maxCalls) * 100;
          const isToday = index === data.length - 1;

          return (
            <div key={day.date} className="flex-1 flex flex-col items-center gap-2">
              {/* Bar */}
              <div className="w-full relative group">
                <div
                  className={`
                    w-full rounded-t transition-all duration-300
                    ${isToday ? 'bg-primary-500' : 'bg-primary-200 hover:bg-primary-300'}
                  `}
                  style={{ height: `${Math.max(height, 5)}%`, minHeight: '8px' }}
                />

                {/* Tooltip */}
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                  <div className="bg-gray-900 text-white text-xs rounded px-2 py-1 whitespace-nowrap">
                    {day.calls.toLocaleString()} calls
                  </div>
                </div>
              </div>

              {/* Label */}
              <span className={`text-xs ${isToday ? 'text-primary-600 font-medium' : 'text-gray-400'}`}>
                {formatDate(day.date)}
              </span>
            </div>
          );
        })}
      </div>

      {/* Y-axis labels */}
      <div className="flex justify-between mt-4 text-xs text-gray-400">
        <span>0</span>
        <span>{Math.round(maxCalls / 2).toLocaleString()}</span>
        <span>{maxCalls.toLocaleString()}</span>
      </div>
    </div>
  );
}
