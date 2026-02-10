import { useMemo } from 'react';
import type { TimeSeriesPoint } from '../../hooks/usePrometheus';

interface SparklineChartProps {
  data: TimeSeriesPoint[];
  color?: string;
  height?: number;
  width?: number;
  showArea?: boolean;
  className?: string;
}

/**
 * Minimal SVG sparkline for time-series data.
 * Follows UsageChart.tsx patterns — no external charting library.
 */
export function SparklineChart({
  data,
  color = '#3b82f6',
  height = 48,
  width = 200,
  showArea = true,
  className = '',
}: SparklineChartProps) {
  const { points, areaPoints } = useMemo(() => {
    if (data.length < 2) return { points: '', areaPoints: '' };

    const values = data.map((d) => d.value);
    const max = Math.max(...values);
    const min = Math.min(...values);
    const range = max - min || 1;
    const padding = 2;
    const chartHeight = height - padding * 2;
    const chartWidth = width - padding * 2;

    const pts = data.map((d, i) => {
      const x = padding + (i / (data.length - 1)) * chartWidth;
      const y = padding + chartHeight - ((d.value - min) / range) * chartHeight;
      return `${x},${y}`;
    });

    const line = pts.join(' ');
    const area = `${padding},${height - padding} ${line} ${width - padding},${height - padding}`;

    return { points: line, areaPoints: area };
  }, [data, height, width]);

  if (data.length < 2) {
    return (
      <div
        className={`flex items-center justify-center text-xs text-gray-400 dark:text-gray-500 ${className}`}
        style={{ height, width }}
      >
        No data
      </div>
    );
  }

  const gradientId = `sparkline-${color.replace('#', '')}`;

  return (
    <svg width={width} height={height} className={className} aria-hidden="true">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.3} />
          <stop offset="100%" stopColor={color} stopOpacity={0.02} />
        </linearGradient>
      </defs>
      {showArea && <polygon points={areaPoints} fill={`url(#${gradientId})`} />}
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinejoin="round"
      />
    </svg>
  );
}
