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
    return (
      <div className="h-[250px] flex items-center justify-center text-sm text-neutral-400 dark:text-neutral-500">
        No throughput data for {timeRange}
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={250}>
      <AreaChart data={merged}>
        <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
        <XAxis
          dataKey="timestamp"
          tickFormatter={formatTime}
          tick={{ fontSize: 11, fill: '#9CA3AF' }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          tick={{ fontSize: 11, fill: '#9CA3AF' }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v: number) =>
            v >= 1000 ? `${(v / 1000).toFixed(1)}K` : String(Math.round(v))
          }
        />
        <Tooltip
          contentStyle={{
            backgroundColor: '#1F2937',
            border: '1px solid #374151',
            borderRadius: 8,
            fontSize: 12,
          }}
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
