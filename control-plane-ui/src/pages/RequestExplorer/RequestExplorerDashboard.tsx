import { useState } from 'react';
import {
  RefreshCw,
  Activity,
  CheckCircle,
  AlertTriangle,
  Clock,
  Globe,
  ExternalLink,
} from 'lucide-react';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import { usePrometheusQuery, scalarValue, groupByLabel } from '../../hooks/usePrometheus';

const AUTO_REFRESH_INTERVAL = 30_000;

type TimeRange = '1h' | '6h' | '24h';

const RANGE_LABELS: Record<TimeRange, string> = {
  '1h': '1 hour',
  '6h': '6 hours',
  '24h': '24 hours',
};

/** Status code color mapping */
const STATUS_COLORS: Record<string, { bg: string; label: string }> = {
  '2': { bg: 'bg-green-500', label: '2xx' },
  '3': { bg: 'bg-blue-500', label: '3xx' },
  '4': { bg: 'bg-yellow-500', label: '4xx' },
  '5': { bg: 'bg-red-500', label: '5xx' },
};

function getStatusGroup(status: string): string {
  return status.charAt(0);
}

function getErrorRateClass(rate: number): string {
  if (rate < 0.01) return 'text-green-600';
  if (rate < 0.05) return 'text-yellow-600';
  return 'text-red-600';
}

function StatCard({
  label,
  value,
  unit,
  icon: Icon,
  colorClass,
  subtitle,
}: {
  label: string;
  value: string | number;
  unit?: string;
  icon: React.ElementType;
  colorClass?: string;
  subtitle?: string;
}) {
  const bgClass = colorClass?.includes('green')
    ? 'bg-green-100 dark:bg-green-900/30'
    : colorClass?.includes('red')
      ? 'bg-red-100 dark:bg-red-900/30'
      : colorClass?.includes('yellow')
        ? 'bg-yellow-100 dark:bg-yellow-900/30'
        : 'bg-blue-100 dark:bg-blue-900/30';

  return (
    <div className="bg-white dark:bg-neutral-800 rounded-lg shadow px-4 py-4 flex items-start gap-4">
      <div className={`p-2 rounded-lg ${bgClass}`}>
        <Icon className={`h-5 w-5 ${colorClass || 'text-blue-600 dark:text-blue-400'}`} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
          {label}
        </p>
        <div className="flex items-baseline gap-1">
          <p className={`text-2xl font-bold ${colorClass || 'text-neutral-900 dark:text-white'}`}>
            {value}
          </p>
          {unit && <span className="text-sm text-neutral-500 dark:text-neutral-400">{unit}</span>}
        </div>
        {subtitle && (
          <p className="text-xs text-neutral-400 dark:text-neutral-500 mt-0.5">{subtitle}</p>
        )}
      </div>
    </div>
  );
}

interface EndpointRow {
  path: string;
  method: string;
  requests: number;
  errorRate: number;
}

export function RequestExplorerDashboard() {
  const [timeRange, setTimeRange] = useState<TimeRange>('1h');
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  // KPI queries
  const totalRequests = usePrometheusQuery(
    `sum(increase(stoa_http_requests_total[${timeRange}]))`,
    AUTO_REFRESH_INTERVAL
  );
  const successRate = usePrometheusQuery(
    `sum(rate(stoa_http_requests_total{status=~"2.."}[5m])) / sum(rate(stoa_http_requests_total[5m]))`,
    AUTO_REFRESH_INTERVAL
  );
  const avgLatency = usePrometheusQuery(
    'sum(rate(stoa_http_request_duration_seconds_sum[5m])) / sum(rate(stoa_http_request_duration_seconds_count[5m]))',
    AUTO_REFRESH_INTERVAL
  );
  const activeEndpoints = usePrometheusQuery(
    `count(count by (path) (increase(stoa_http_requests_total[${timeRange}]) > 0))`,
    AUTO_REFRESH_INTERVAL
  );

  // Status breakdown
  const statusBreakdown = usePrometheusQuery(
    `sum by (status) (increase(stoa_http_requests_total[${timeRange}]))`,
    AUTO_REFRESH_INTERVAL
  );

  // Top endpoints
  const topEndpoints = usePrometheusQuery(
    `topk(10, sum by (path, method) (increase(stoa_http_requests_total[${timeRange}])))`,
    AUTO_REFRESH_INTERVAL
  );
  const topEndpointErrors = usePrometheusQuery(
    `sum by (path, method) (increase(stoa_http_requests_total{status=~"5.."}[${timeRange}]))`,
    AUTO_REFRESH_INTERVAL
  );

  const handleRefresh = () => {
    totalRequests.refetch();
    successRate.refetch();
    avgLatency.refetch();
    activeEndpoints.refetch();
    statusBreakdown.refetch();
    topEndpoints.refetch();
    topEndpointErrors.refetch();
    setLastRefresh(new Date());
  };

  const prometheusAvailable = !totalRequests.error;
  const totalReqVal = scalarValue(totalRequests.data);
  const successRateVal = scalarValue(successRate.data);
  const avgLatVal = scalarValue(avgLatency.data);
  const activeEndpointsVal = scalarValue(activeEndpoints.data);

  // Status breakdown data
  const statusGroups = groupByLabel(statusBreakdown.data, 'status');
  const groupedByPrefix: Record<string, number> = {};
  for (const [status, count] of Object.entries(statusGroups)) {
    const group = getStatusGroup(status);
    groupedByPrefix[group] = (groupedByPrefix[group] || 0) + count;
  }
  const statusTotal = Object.values(groupedByPrefix).reduce((s, v) => s + v, 0);

  // Endpoint table data
  const endpointRows: EndpointRow[] = [];
  if (topEndpoints.data) {
    const errorMap: Record<string, number> = {};
    if (topEndpointErrors.data) {
      for (const r of topEndpointErrors.data) {
        const key = `${r.metric.method}:${r.metric.path}`;
        errorMap[key] = parseFloat(r.value?.[1] || '0');
      }
    }
    for (const r of topEndpoints.data) {
      const reqs = parseFloat(r.value?.[1] || '0');
      if (reqs < 1) continue;
      const key = `${r.metric.method}:${r.metric.path}`;
      const errors = errorMap[key] || 0;
      endpointRows.push({
        path: r.metric.path || '/',
        method: r.metric.method || 'GET',
        requests: Math.round(reqs),
        errorRate: reqs > 0 ? errors / reqs : 0,
      });
    }
    endpointRows.sort((a, b) => b.requests - a.requests);
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Request Explorer</h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            Analyze API traffic patterns and error distribution
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center bg-white dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 rounded-lg overflow-hidden">
            {(['1h', '6h', '24h'] as const).map((range) => (
              <button
                key={range}
                onClick={() => setTimeRange(range)}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                  timeRange === range
                    ? 'bg-blue-600 text-white'
                    : 'text-neutral-600 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-700'
                }`}
              >
                {range}
              </button>
            ))}
          </div>
          <span className="text-xs text-neutral-400 dark:text-neutral-500">
            {lastRefresh.toLocaleTimeString('fr-FR')}
          </span>
          <button
            onClick={handleRefresh}
            className="flex items-center gap-2 border border-neutral-300 dark:border-neutral-600 text-neutral-700 dark:text-neutral-300 px-3 py-2 rounded-lg text-sm hover:bg-neutral-50 dark:hover:bg-neutral-700 disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${totalRequests.loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Prometheus unavailable banner */}
      {!prometheusAvailable && (
        <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 px-4 py-3 rounded-lg flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-yellow-600" />
            <span className="text-sm text-yellow-700 dark:text-yellow-400">
              Prometheus is not reachable. Request data unavailable.
            </span>
          </div>
          <button
            onClick={handleRefresh}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-yellow-700 dark:text-yellow-300 bg-white dark:bg-neutral-800 border border-yellow-300 dark:border-yellow-700 rounded-lg hover:bg-yellow-50 dark:hover:bg-yellow-900/30 transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Retry
          </button>
        </div>
      )}

      {totalRequests.loading && !prometheusAvailable ? (
        <div className="space-y-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <CardSkeleton key={i} className="h-24" />
            ))}
          </div>
          <CardSkeleton className="h-16" />
          <CardSkeleton className="h-64" />
        </div>
      ) : (
        <>
          {/* KPI Row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard
              label={`Total Requests (${timeRange})`}
              value={
                totalReqVal !== null
                  ? totalReqVal >= 1000
                    ? `${(totalReqVal / 1000).toFixed(1)}K`
                    : Math.round(totalReqVal).toString()
                  : '--'
              }
              icon={Activity}
              colorClass="text-blue-600"
              subtitle={`Over ${RANGE_LABELS[timeRange]}`}
            />
            <StatCard
              label="Success Rate (5m)"
              value={successRateVal !== null ? `${(successRateVal * 100).toFixed(1)}%` : '--'}
              icon={CheckCircle}
              colorClass={
                successRateVal !== null && successRateVal >= 0.99
                  ? 'text-green-600'
                  : successRateVal !== null && successRateVal >= 0.95
                    ? 'text-yellow-600'
                    : successRateVal !== null
                      ? 'text-red-600'
                      : undefined
              }
              subtitle="2xx responses"
            />
            <StatCard
              label="Avg Response Time"
              value={avgLatVal !== null ? Math.round(avgLatVal * 1000).toString() : '--'}
              unit="ms"
              icon={Clock}
              colorClass={
                avgLatVal !== null && avgLatVal * 1000 < 200
                  ? 'text-green-600'
                  : avgLatVal !== null && avgLatVal * 1000 < 500
                    ? 'text-yellow-600'
                    : avgLatVal !== null
                      ? 'text-red-600'
                      : undefined
              }
              subtitle="Mean latency"
            />
            <StatCard
              label="Active Endpoints"
              value={activeEndpointsVal !== null ? Math.round(activeEndpointsVal).toString() : '--'}
              icon={Globe}
              colorClass="text-blue-600"
              subtitle={`In last ${RANGE_LABELS[timeRange]}`}
            />
          </div>

          {/* Status Breakdown Bar */}
          {statusTotal > 0 && (
            <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
              <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase mb-3">
                Status Code Distribution
              </h2>
              {/* Stacked bar */}
              <div className="flex h-4 rounded-full overflow-hidden mb-3">
                {['2', '3', '4', '5'].map((group) => {
                  const count = groupedByPrefix[group] || 0;
                  if (count === 0) return null;
                  const pct = (count / statusTotal) * 100;
                  const colorCfg = STATUS_COLORS[group];
                  return (
                    <div
                      key={group}
                      className={`${colorCfg.bg} transition-all`}
                      style={{ width: `${pct}%` }}
                      title={`${colorCfg.label}: ${Math.round(count).toLocaleString()} (${pct.toFixed(1)}%)`}
                    />
                  );
                })}
              </div>
              {/* Legend */}
              <div className="flex items-center gap-4 text-xs">
                {['2', '3', '4', '5'].map((group) => {
                  const count = groupedByPrefix[group] || 0;
                  if (count === 0) return null;
                  const colorCfg = STATUS_COLORS[group];
                  return (
                    <div key={group} className="flex items-center gap-1.5">
                      <span className={`w-2.5 h-2.5 rounded-full ${colorCfg.bg}`} />
                      <span className="text-neutral-600 dark:text-neutral-400">
                        {colorCfg.label}: {Math.round(count).toLocaleString()}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Request Table */}
          <div className="bg-white dark:bg-neutral-800 rounded-lg shadow overflow-hidden">
            <div className="flex items-center justify-between p-4 border-b border-neutral-100 dark:border-neutral-700">
              <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
                Top Endpoints
              </h2>
              <a
                href="/errors"
                className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
              >
                Error Snapshots
                <ExternalLink className="h-3 w-3" />
              </a>
            </div>
            {endpointRows.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase border-b border-neutral-100 dark:border-neutral-700">
                      <th className="px-4 py-3">Endpoint</th>
                      <th className="px-4 py-3">Method</th>
                      <th className="px-4 py-3 text-right">Requests</th>
                      <th className="px-4 py-3 text-right">Error Rate</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-neutral-50 dark:divide-neutral-700">
                    {endpointRows.map((row) => (
                      <tr
                        key={`${row.method}:${row.path}`}
                        className="hover:bg-neutral-50 dark:hover:bg-neutral-750"
                      >
                        <td className="px-4 py-3 font-mono text-xs text-neutral-900 dark:text-white">
                          {row.path}
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
                              row.method === 'GET'
                                ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                                : row.method === 'POST'
                                  ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
                                  : row.method === 'PUT'
                                    ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
                                    : row.method === 'DELETE'
                                      ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                                      : 'bg-neutral-100 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-400'
                            }`}
                          >
                            {row.method}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right text-neutral-700 dark:text-neutral-300">
                          {row.requests.toLocaleString()}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <span className={getErrorRateClass(row.errorRate)}>
                            {(row.errorRate * 100).toFixed(2)}%
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-12">
                <Activity className="h-8 w-8 text-neutral-300 dark:text-neutral-600 mb-2" />
                <p className="text-sm text-neutral-500 dark:text-neutral-400">
                  {prometheusAvailable
                    ? 'No request data in this time range'
                    : 'Metrics unavailable'}
                </p>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default RequestExplorerDashboard;
