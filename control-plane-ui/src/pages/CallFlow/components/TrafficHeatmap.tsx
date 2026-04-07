import { useState } from 'react';
import { ChartEmptyState } from '@stoa/shared/components/ChartCard';

interface HeatmapCell {
  hour: number;
  route: string;
  value: number;
}

interface TrafficHeatmapProps {
  cells: HeatmapCell[];
  routes: string[];
  activeRoute?: string;
  onCellClick?: (route: string) => void;
}

function intensityClass(value: number, max: number): string {
  if (max === 0) return 'bg-neutral-100 dark:bg-neutral-800';
  const ratio = value / max;
  if (ratio === 0) return 'bg-neutral-100 dark:bg-neutral-800';
  if (ratio < 0.15) return 'bg-blue-100 dark:bg-blue-900/30';
  if (ratio < 0.35) return 'bg-blue-200 dark:bg-blue-800/40';
  if (ratio < 0.55) return 'bg-blue-300 dark:bg-blue-700/50';
  if (ratio < 0.75) return 'bg-blue-400 dark:bg-blue-600/60';
  return 'bg-blue-500 dark:bg-blue-500/70';
}

interface TooltipState {
  x: number;
  y: number;
  route: string;
  hour: number;
  value: number;
}

export function TrafficHeatmap({ cells, routes, activeRoute, onCellClick }: TrafficHeatmapProps) {
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  if (cells.length === 0 || routes.length === 0) {
    return <ChartEmptyState message="No traffic heatmap data" height={200} />;
  }

  const max = Math.max(...cells.map((c) => c.value), 1);
  const hours = Array.from({ length: 24 }, (_, i) => i);

  const cellMap = new Map<string, number>();
  for (const c of cells) {
    cellMap.set(`${c.route}-${c.hour}`, c.value);
  }

  return (
    <div className="overflow-x-auto relative">
      <div className="min-w-[600px]">
        {/* Hour labels */}
        <div className="flex ml-28 mb-1">
          {hours.map((h) => (
            <div
              key={h}
              className="flex-1 text-center text-[10px] text-neutral-400 dark:text-neutral-500"
            >
              {h % 3 === 0 ? `${h}h` : ''}
            </div>
          ))}
        </div>

        {/* Rows */}
        {routes.slice(0, 6).map((route) => (
          <div
            key={route}
            className={`flex items-center mb-0.5 transition-opacity ${onCellClick ? 'cursor-pointer' : ''} ${activeRoute && activeRoute !== route ? 'opacity-30' : ''}`}
            onClick={() => {
              if (!onCellClick) return;
              onCellClick(route === activeRoute ? '' : route);
            }}
          >
            <div className="w-28 text-xs font-mono text-neutral-500 dark:text-neutral-400 truncate pr-2 text-right">
              {route}
            </div>
            <div className="flex flex-1 gap-px">
              {hours.map((h) => {
                const val = cellMap.get(`${route}-${h}`) || 0;
                return (
                  <div
                    key={h}
                    className={`flex-1 h-5 rounded-sm ${intensityClass(val, max)} transition-colors cursor-crosshair`}
                    onMouseEnter={(e) => {
                      const rect = e.currentTarget.getBoundingClientRect();
                      const parent = e.currentTarget.closest('.overflow-x-auto');
                      const parentRect = parent?.getBoundingClientRect();
                      setTooltip({
                        x: rect.left - (parentRect?.left || 0) + rect.width / 2,
                        y: rect.top - (parentRect?.top || 0) - 8,
                        route,
                        hour: h,
                        value: val,
                      });
                    }}
                    onMouseLeave={() => setTooltip(null)}
                  />
                );
              })}
            </div>
          </div>
        ))}

        {/* Legend */}
        <div className="flex items-center justify-end mt-2 gap-1">
          <span className="text-[10px] text-neutral-400 mr-1">Low</span>
          {[
            'bg-neutral-100 dark:bg-neutral-800',
            'bg-blue-200 dark:bg-blue-800/40',
            'bg-blue-400 dark:bg-blue-600/60',
            'bg-blue-500 dark:bg-blue-500/70',
          ].map((cls, i) => (
            <div key={i} className={`w-4 h-3 rounded-sm ${cls}`} />
          ))}
          <span className="text-[10px] text-neutral-400 ml-1">High</span>
        </div>
      </div>

      {/* Styled tooltip */}
      {tooltip && (
        <div
          className="absolute z-20 pointer-events-none px-2.5 py-1.5 rounded-lg text-xs"
          style={{
            left: tooltip.x,
            top: tooltip.y,
            transform: 'translate(-50%, -100%)',
            backgroundColor: '#1F2937',
            border: '1px solid #374151',
            color: '#F3F4F6',
          }}
        >
          <div className="font-medium">{tooltip.value.toLocaleString()} requests</div>
          <div className="text-neutral-400">
            {tooltip.route} @ {tooltip.hour}:00
          </div>
        </div>
      )}
    </div>
  );
}
