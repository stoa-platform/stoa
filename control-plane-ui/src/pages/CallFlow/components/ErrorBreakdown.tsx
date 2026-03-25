import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { CHART_TOOLTIP_STYLE, ChartEmptyState } from '@stoa/shared/components/ChartCard';

interface ErrorEntry {
  code: string;
  count: number;
}

interface ErrorBreakdownProps {
  errors: ErrorEntry[];
}

const STATUS_COLORS: Record<string, string> = {
  '401': '#F59E0B',
  '403': '#F97316',
  '404': '#8B5CF6',
  '429': '#EC4899',
  '500': '#EF4444',
  '502': '#DC2626',
  '503': '#B91C1C',
  '504': '#991B1B',
};

export function ErrorBreakdown({ errors }: ErrorBreakdownProps) {
  const data = errors.filter((e) => e.count > 0);

  if (data.length === 0) {
    return <ChartEmptyState message="No errors in this period" />;
  }

  return (
    <ResponsiveContainer width="100%" height={250}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={55}
          outerRadius={90}
          paddingAngle={3}
          dataKey="count"
          nameKey="code"
        >
          {data.map((entry) => (
            <Cell
              key={entry.code}
              fill={STATUS_COLORS[entry.code] || '#6B7280'}
              stroke="transparent"
            />
          ))}
        </Pie>
        <Tooltip
          contentStyle={CHART_TOOLTIP_STYLE}
          formatter={(value) => [`${value} requests`, 'Errors']}
        />
        <Legend
          wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
          iconType="circle"
          iconSize={8}
          formatter={(value: string) => `HTTP ${value}`}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
