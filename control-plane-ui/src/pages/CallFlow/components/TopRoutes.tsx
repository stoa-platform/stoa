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

interface RouteLatency {
  route: string;
  p95Ms: number;
  calls: number;
}

interface TopRoutesProps {
  routes: RouteLatency[];
}

function latencyColor(ms: number): string {
  if (ms < 50) return '#10B981';
  if (ms < 200) return '#EAB308';
  if (ms < 500) return '#F97316';
  return '#EF4444';
}

export function TopRoutes({ routes }: TopRoutesProps) {
  const data = routes.slice(0, 8);

  if (data.length === 0) {
    return <ChartEmptyState message="No route data available" />;
  }

  return (
    <ResponsiveContainer width="100%" height={250}>
      <BarChart data={data} layout="vertical" barCategoryGap="20%">
        <CartesianGrid {...CHART_GRID_STYLE} horizontal={false} />
        <XAxis
          type="number"
          tick={CHART_AXIS_STYLE}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v: number) => (v < 1 ? '<1ms' : `${Math.round(v)}ms`)}
        />
        <YAxis
          type="category"
          dataKey="route"
          tick={{ ...CHART_AXIS_STYLE, fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          width={100}
        />
        <Tooltip
          contentStyle={CHART_TOOLTIP_STYLE}
          formatter={(value, _name, props) => {
            const v = Number(value);
            const calls = (props.payload as RouteLatency)?.calls ?? 0;
            return [`${v < 1 ? '<1' : Math.round(v)}ms (${calls} req)`, 'P95 Latency'];
          }}
        />
        <Bar dataKey="p95Ms" radius={[0, 4, 4, 0]}>
          {data.map((entry) => (
            <Cell key={entry.route} fill={latencyColor(entry.p95Ms)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
