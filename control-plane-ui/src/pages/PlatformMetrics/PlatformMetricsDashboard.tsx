import { useState, useEffect, useCallback } from 'react';
import {
  RefreshCw,
  Activity,
  AlertTriangle,
  Clock,
  CheckCircle,
  Server,
  TrendingUp,
  TrendingDown,
  ExternalLink,
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { apiService } from '../../services/api';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import { usePrometheusQuery, usePrometheusRange, scalarValue } from '../../hooks/usePrometheus';
import { SparklineChart } from '../../components/charts/SparklineChart';
import type { TopAPI } from '../../services/api';

const AUTO_REFRESH_INTERVAL = 15_000;

type TimeRange = '1h' | '6h' | '24h';

const RANGE_CONFIG: Record<TimeRange, { seconds: number; step: string; label: string }> = {
  '1h': { seconds: 3600, step: '60s', label: '1 hour' },
  '6h': { seconds: 21600, step: '300s', label: '6 hours' },
  '24h': { seconds: 86400, step: '900s', label: '24 hours' },
};

function getErrorRateColor(rate: number): string {
  if (rate < 0.01) return 'text-green-600';
  if (rate < 0.05) return 'text-yellow-600';
  return 'text-red-600';
}

function getLatencyColor(ms: number): string {
  if (ms < 300) return 'text-green-600';
  if (ms < 500) return 'text-yellow-600';
  return 'text-red-600';
}

function StatCard({
  label,
  value,
  unit,
  icon: Icon,
  colorClass,
  subtitle,
  sparkline,
}: {
  label: string;
  value: string | number;
  unit?: string;
  icon: React.ElementType;
  colorClass?: string;
  subtitle?: string;
  sparkline?: React.ReactNode;
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
        <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">{label}</p>
        <div className="flex items-baseline gap-1">
          <p className={`text-2xl font-bold ${colorClass || 'text-gray-900 dark:text-white'}`}>
            {value}
          </p>
          {unit && <span className="text-sm text-gray-500 dark:text-gray-400">{unit}</span>}
        </div>
        {subtitle && <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{subtitle}</p>}
        {sparkline && <div className="mt-2">{sparkline}</div>}
      </div>
    </div>
  );
}

export function PlatformMetricsDashboard() {
  const { isReady } = useAuth();
  const [timeRange, setTimeRange] = useState<TimeRange>('1h');
  const [topApis, setTopApis] = useState<TopAPI[]>([]);
  const [componentHealth, setComponentHealth] = useState<
    { name: string; healthy: boolean }[] | null
  >(null);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  const rangeCfg = RANGE_CONFIG[timeRange];

  // Prometheus queries
  const totalRequests = usePrometheusQuery(
    `sum(increase(stoa_control_plane_http_requests_total[${timeRange}]))`,
    AUTO_REFRESH_INTERVAL
  );
  const errorRate = usePrometheusQuery(
    'sum(rate(stoa_control_plane_http_requests_total{status=~"5.."}[5m])) / sum(rate(stoa_control_plane_http_requests_total[5m]))',
    AUTO_REFRESH_INTERVAL
  );
  const p95Latency = usePrometheusQuery(
    'histogram_quantile(0.95, sum(rate(stoa_control_plane_http_request_duration_seconds_bucket[5m])) by (le))',
    AUTO_REFRESH_INTERVAL
  );
  const servicesUp = usePrometheusQuery('count(up == 1)', AUTO_REFRESH_INTERVAL);

  // Sparklines
  const requestRateSeries = usePrometheusRange(
    'sum(rate(stoa_control_plane_http_requests_total[5m]))',
    rangeCfg.seconds,
    rangeCfg.step,
    AUTO_REFRESH_INTERVAL
  );
  const errorRateSeries = usePrometheusRange(
    'sum(rate(stoa_control_plane_http_requests_total{status=~"5.."}[5m])) / sum(rate(stoa_control_plane_http_requests_total[5m]))',
    rangeCfg.seconds,
    rangeCfg.step,
    AUTO_REFRESH_INTERVAL
  );

  // CP API data
  const loadApiData = useCallback(async () => {
    try {
      const [apis, status] = await Promise.all([
        apiService.getTopAPIs(5).catch(() => []),
        apiService
          .get<{ gitops: { components: { name: string; health_status: string }[] } }>(
            '/v1/platform/status'
          )
          .then((r) =>
            r.data.gitops?.components?.map((c) => ({
              name: c.name,
              healthy: c.health_status === 'Healthy',
            }))
          )
          .catch(() => null),
      ]);
      setTopApis(apis);
      setComponentHealth(status ?? null);
      setLastRefresh(new Date());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isReady) loadApiData();
  }, [isReady, loadApiData]);

  useEffect(() => {
    if (!isReady) return;
    const interval = setInterval(loadApiData, AUTO_REFRESH_INTERVAL);
    return () => clearInterval(interval);
  }, [isReady, loadApiData]);

  const handleRefresh = () => {
    totalRequests.refetch();
    errorRate.refetch();
    p95Latency.refetch();
    servicesUp.refetch();
    requestRateSeries.refetch();
    errorRateSeries.refetch();
    loadApiData();
  };

  const prometheusAvailable = !totalRequests.error;
  const totalReqVal = scalarValue(totalRequests.data);
  const errorRateVal = scalarValue(errorRate.data);
  const p95Val = scalarValue(p95Latency.data);
  const servicesUpVal = scalarValue(servicesUp.data);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Platform Metrics</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Real-time platform performance and health
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Time range selector */}
          <div className="flex items-center bg-white dark:bg-neutral-800 border border-gray-300 dark:border-neutral-600 rounded-lg overflow-hidden">
            {(['1h', '6h', '24h'] as const).map((range) => (
              <button
                key={range}
                onClick={() => setTimeRange(range)}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                  timeRange === range
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-neutral-700'
                }`}
              >
                {range}
              </button>
            ))}
          </div>
          <span className="text-xs text-gray-400 dark:text-gray-500">
            {lastRefresh.toLocaleTimeString('fr-FR')}
          </span>
          <button
            onClick={handleRefresh}
            className="flex items-center gap-2 border border-gray-300 dark:border-neutral-600 text-gray-700 dark:text-gray-300 px-3 py-2 rounded-lg text-sm hover:bg-gray-50 dark:hover:bg-neutral-700 disabled:opacity-50"
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
              Prometheus is not reachable. Showing API-only data.
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

      {loading && !prometheusAvailable ? (
        <div className="space-y-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <CardSkeleton key={i} className="h-24" />
            ))}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <CardSkeleton className="h-64" />
            <CardSkeleton className="h-64" />
          </div>
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
              subtitle="All endpoints"
            />
            <StatCard
              label="Error Rate (5m)"
              value={errorRateVal !== null ? `${(errorRateVal * 100).toFixed(2)}%` : '--'}
              icon={AlertTriangle}
              colorClass={errorRateVal !== null ? getErrorRateColor(errorRateVal) : undefined}
              subtitle="5xx responses"
            />
            <StatCard
              label="P95 Latency (5m)"
              value={p95Val !== null ? Math.round(p95Val * 1000).toString() : '--'}
              unit="ms"
              icon={Clock}
              colorClass={p95Val !== null ? getLatencyColor(p95Val * 1000) : undefined}
              subtitle="95th percentile"
            />
            <StatCard
              label="Services Up"
              value={servicesUpVal !== null ? Math.round(servicesUpVal).toString() : '--'}
              icon={Server}
              colorClass={
                servicesUpVal !== null && servicesUpVal > 0 ? 'text-green-600' : 'text-gray-400'
              }
              subtitle="Healthy targets"
            />
          </div>

          {/* Sparkline Charts Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Request Rate */}
            <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase">
                    Request Rate
                  </h2>
                  <p className="text-xs text-gray-400 dark:text-gray-500">
                    req/s over {rangeCfg.label}
                  </p>
                </div>
                {requestRateSeries.data && requestRateSeries.data.length > 1 && (
                  <TrendIndicator data={requestRateSeries.data} />
                )}
              </div>
              {requestRateSeries.data ? (
                <SparklineChart
                  data={requestRateSeries.data}
                  color="#3b82f6"
                  height={120}
                  width={560}
                  showArea
                  className="w-full"
                />
              ) : (
                <div className="h-[120px] flex items-center justify-center text-sm text-gray-400 dark:text-gray-500">
                  {requestRateSeries.error ? 'Metrics unavailable' : 'Loading...'}
                </div>
              )}
            </div>

            {/* Error Rate Over Time */}
            <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase">
                    Error Rate
                  </h2>
                  <p className="text-xs text-gray-400 dark:text-gray-500">
                    5xx ratio over {rangeCfg.label}
                  </p>
                </div>
                {errorRateSeries.data && errorRateSeries.data.length > 1 && (
                  <TrendIndicator data={errorRateSeries.data} invertColor />
                )}
              </div>
              {errorRateSeries.data ? (
                <SparklineChart
                  data={errorRateSeries.data}
                  color="#ef4444"
                  height={120}
                  width={560}
                  showArea
                  className="w-full"
                />
              ) : (
                <div className="h-[120px] flex items-center justify-center text-sm text-gray-400 dark:text-gray-500">
                  {errorRateSeries.error ? 'Metrics unavailable' : 'Loading...'}
                </div>
              )}
            </div>
          </div>

          {/* Bottom Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Top Endpoints */}
            <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase">
                  Top Endpoints
                </h2>
                <a
                  href="/business"
                  className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
                >
                  View All
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
              {topApis.length > 0 ? (
                <div className="space-y-3">
                  {topApis.map((api, i) => {
                    const maxCalls = topApis[0]?.calls || 1;
                    return (
                      <div key={api.tool_name} className="flex items-center gap-3">
                        <span className="text-xs font-bold text-gray-400 dark:text-gray-500 w-5 text-right">
                          {i + 1}
                        </span>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-sm font-medium text-gray-900 dark:text-white truncate">
                              {api.display_name || api.tool_name}
                            </span>
                            <span className="text-xs text-gray-500 dark:text-gray-400 ml-2">
                              {api.calls.toLocaleString()} calls
                            </span>
                          </div>
                          <div className="w-full bg-gray-100 dark:bg-neutral-700 rounded-full h-1.5">
                            <div
                              className="bg-blue-500 h-1.5 rounded-full transition-all"
                              style={{ width: `${(api.calls / maxCalls) * 100}%` }}
                            />
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-8">
                  No API data available
                </p>
              )}
            </div>

            {/* Component Health */}
            <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase">
                  Component Health
                </h2>
                <a
                  href="/operations"
                  className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
                >
                  Operations
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
              {componentHealth && componentHealth.length > 0 ? (
                <div className="grid grid-cols-2 gap-3">
                  {componentHealth.map((c) => (
                    <div
                      key={c.name}
                      className="flex items-center gap-2 p-2 rounded-lg border border-gray-100 dark:border-neutral-700"
                    >
                      <CheckCircle
                        className={`h-4 w-4 flex-shrink-0 ${c.healthy ? 'text-green-500' : 'text-red-500'}`}
                      />
                      <span className="text-sm text-gray-700 dark:text-gray-300 truncate">
                        {c.name}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-8">
                  <Server className="h-8 w-8 text-gray-300 dark:text-gray-600 mb-2" />
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    Component status unavailable
                  </p>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

/** Small trend indicator showing % change between first and last third of data */
function TrendIndicator({
  data,
  invertColor = false,
}: {
  data: { value: number }[];
  invertColor?: boolean;
}) {
  if (data.length < 6) return null;
  const third = Math.floor(data.length / 3);
  const firstAvg = data.slice(0, third).reduce((s, d) => s + d.value, 0) / third;
  const lastAvg = data.slice(-third).reduce((s, d) => s + d.value, 0) / third;
  if (firstAvg === 0) return null;
  const change = ((lastAvg - firstAvg) / firstAvg) * 100;
  const isUp = change > 0;
  const Icon = isUp ? TrendingUp : TrendingDown;
  // For error rates, up = bad (red), down = good (green)
  const color = invertColor
    ? isUp
      ? 'text-red-500'
      : 'text-green-500'
    : isUp
      ? 'text-green-500'
      : 'text-red-500';

  return (
    <div className={`flex items-center gap-1 text-xs ${color}`}>
      <Icon className="h-3.5 w-3.5" />
      <span>{Math.abs(change).toFixed(1)}%</span>
    </div>
  );
}

export default PlatformMetricsDashboard;
