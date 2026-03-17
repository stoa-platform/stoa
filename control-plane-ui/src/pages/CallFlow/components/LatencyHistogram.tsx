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
    return (
      <div className="h-[250px] flex items-center justify-center text-sm text-neutral-400 dark:text-neutral-500">
        No latency distribution data
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={250}>
      <BarChart data={buckets} barCategoryGap="15%">
        <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
        <XAxis
          dataKey="label"
          tick={{ fontSize: 11, fill: '#9CA3AF' }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis tick={{ fontSize: 11, fill: '#9CA3AF' }} axisLine={false} tickLine={false} />
        <Tooltip
          contentStyle={{
            backgroundColor: '#1F2937',
            border: '1px solid #374151',
            borderRadius: 8,
            fontSize: 12,
          }}
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
