import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import type { TimeSeriesPoint } from '../../../hooks/usePrometheus';
import {
  CHART_TOOLTIP_STYLE,
  CHART_AXIS_STYLE,
  CHART_GRID_STYLE,
  ChartEmptyState,
} from '@stoa/shared/components/ChartCard';

interface ModeTimeSeries {
  label: string;
  color: string;
  data: TimeSeriesPoint[] | null;
}

interface ThroughputChartProps {
  series: ModeTimeSeries[];
  timeRange: string;
}

function mergeTimeSeries(series: ModeTimeSeries[]): Record<string, number | string>[] {
  const timeMap = new Map<number, Record<string, number | string>>();

  for (const s of series) {
    if (!s.data) continue;
    for (const pt of s.data) {
      const ts = Math.floor(pt.timestamp);
      if (!timeMap.has(ts)) {
        timeMap.set(ts, { timestamp: ts });
      }
      const row = timeMap.get(ts)!;
      row[s.label] = pt.value;
    }
  }

  return Array.from(timeMap.values()).sort(
    (a, b) => (a.timestamp as number) - (b.timestamp as number)
  );
}

function formatTime(ts: number): string {
  const d = new Date(ts * 1000);
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
}

export function ThroughputChart({ series, timeRange }: ThroughputChartProps) {
  const merged = mergeTimeSeries(series);

  if (merged.length === 0) {
    return <ChartEmptyState message={`No throughput data for ${timeRange}`} />;
  }

  return (
    <ResponsiveContainer width="100%" height={250}>
      <AreaChart data={merged}>
        <CartesianGrid {...CHART_GRID_STYLE} />
        <XAxis
          dataKey="timestamp"
          tickFormatter={formatTime}
          tick={CHART_AXIS_STYLE}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          tick={CHART_AXIS_STYLE}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v: number) =>
            v >= 1000 ? `${(v / 1000).toFixed(1)}K` : String(Math.round(v))
          }
        />
        <Tooltip
          contentStyle={CHART_TOOLTIP_STYLE}
          labelFormatter={(label) => formatTime(Number(label))}
          formatter={(value) => [Number(value).toFixed(2), undefined]}
        />
        <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} iconType="circle" iconSize={8} />
        {series.map((s) => (
          <Area
            key={s.label}
            type="monotone"
            dataKey={s.label}
            stackId="throughput"
            stroke={s.color}
            fill={s.color}
            fillOpacity={0.4}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}
