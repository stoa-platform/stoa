import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { CHART_TOOLTIP_STYLE, ChartEmptyState } from '@stoa/shared/components/ChartCard';

interface ErrorEntry {
  code: string;
  count: number;
}

interface ErrorBreakdownProps {
  errors: ErrorEntry[];
  activeCode?: string;
  onSliceClick?: (code: string) => void;
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

export function ErrorBreakdown({ errors, activeCode, onSliceClick }: ErrorBreakdownProps) {
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
          innerRadius={activeCode ? 50 : 55}
          outerRadius={90}
          paddingAngle={3}
          dataKey="count"
          nameKey="code"
          style={{ cursor: onSliceClick ? 'pointer' : 'default' }}
          onClick={(_data, index) => {
            if (!onSliceClick) return;
            const code = data[index]?.code || '';
            onSliceClick(code === activeCode ? '' : code);
          }}
        >
          {data.map((entry) => (
            <Cell
              key={entry.code}
              fill={STATUS_COLORS[entry.code] || '#6B7280'}
              stroke={activeCode === entry.code ? '#fff' : 'transparent'}
              strokeWidth={activeCode === entry.code ? 2 : 0}
              fillOpacity={!activeCode || activeCode === entry.code ? 1 : 0.25}
            />
          ))}
        </Pie>
        <Tooltip
          contentStyle={CHART_TOOLTIP_STYLE}
          formatter={(value) => [`${value} requests`, 'Errors']}
        />
        <Legend
          wrapperStyle={{
            fontSize: 12,
            paddingTop: 8,
            cursor: onSliceClick ? 'pointer' : 'default',
          }}
          iconType="circle"
          iconSize={8}
          formatter={(value: string) => `HTTP ${value}`}
          onClick={(entry) => {
            if (!onSliceClick || !entry.value) return;
            onSliceClick(entry.value === activeCode ? '' : entry.value);
          }}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
