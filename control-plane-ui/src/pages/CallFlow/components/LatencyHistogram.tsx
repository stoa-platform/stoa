import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import {
  CHART_TOOLTIP_STYLE,
  CHART_AXIS_STYLE,
  CHART_GRID_STYLE,
  ChartEmptyState,
} from '@stoa/shared/components/ChartCard';

interface LatencyBucket {
  label: string;
  count: number;
}

interface LatencyHistogramProps {
  buckets: LatencyBucket[];
}

const BUCKET_COLORS = [
  '#10B981', // 0-1ms green
  '#34D399', // 1-2ms
  '#6EE7B7', // 2-5ms
  '#FCD34D', // 5-10ms yellow
  '#FBBF24', // 10-20ms
  '#F59E0B', // 20-50ms orange
  '#EF4444', // 50-100ms red
  '#DC2626', // 100ms+
];

export function LatencyHistogram({ buckets }: LatencyHistogramProps) {
  if (buckets.length === 0 || buckets.every((b) => b.count === 0)) {
    return <ChartEmptyState message="No latency distribution data" />;
  }

  return (
    <ResponsiveContainer width="100%" height={250}>
      <BarChart data={buckets} barCategoryGap="15%">
        <CartesianGrid {...CHART_GRID_STYLE} />
        <XAxis dataKey="label" tick={CHART_AXIS_STYLE} axisLine={false} tickLine={false} />
        <YAxis tick={CHART_AXIS_STYLE} axisLine={false} tickLine={false} />
        <Tooltip
          contentStyle={CHART_TOOLTIP_STYLE}
          formatter={(value) => [`${value} requests`, 'Count']}
        />
        <Bar dataKey="count" radius={[4, 4, 0, 0]}>
          {buckets.map((_entry, index) => (
            <Cell key={index} fill={BUCKET_COLORS[index % BUCKET_COLORS.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
