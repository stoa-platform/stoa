/**
 * Platform Dashboard (CAB-1775)
 *
 * Replaces the old ArgoCD-centric dashboard with platform health KPIs,
 * gateway status cards, traffic/error timeseries, and top APIs table.
 * Follows TenantDashboard patterns: Prometheus hooks + shared StatCard.
 */
import { useState } from 'react';
import {
  RefreshCw,
  Activity,
  AlertTriangle,
  Clock,
  Radio,
  Server,
  TrendingUp,
  Zap,
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import { StatCard } from '@stoa/shared/components/StatCard';
import { TimeRangeSelector, RANGE_CONFIG } from '@stoa/shared/components/TimeRangeSelector';
import { TrendIndicator } from '@stoa/shared/components/TrendIndicator';
import type { TimeRange } from '@stoa/shared/components/TimeRangeSelector';
import {
  usePrometheusQuery,
  usePrometheusRange,
  scalarValue,
  groupByLabel,
} from '../../hooks/usePrometheus';
import { SparklineChart } from '../../components/charts/SparklineChart';
import { useGatewayHealthSummary, useGatewayInstances } from '../../hooks/usePlatformMetrics';
import { useTranslation } from 'react-i18next';

const AUTO_REFRESH_INTERVAL = 15_000;

function formatNumber(num: number): string {
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(1)}M`;
  if (num >= 1_000) return `${(num / 1_000).toFixed(1)}K`;
  return Math.round(num).toString();
}

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

const STATUS_CONFIG: Record<string, { color: string; bg: string; dot: string }> = {
  online: {
    color: 'text-green-700 dark:text-green-400',
    bg: 'bg-green-50 dark:bg-green-900/20',
    dot: 'bg-green-500',
  },
  offline: {
    color: 'text-red-700 dark:text-red-400',
    bg: 'bg-red-50 dark:bg-red-900/20',
    dot: 'bg-red-500',
  },
  degraded: {
    color: 'text-yellow-700 dark:text-yellow-400',
    bg: 'bg-yellow-50 dark:bg-yellow-900/20',
    dot: 'bg-yellow-500',
  },
  maintenance: {
    color: 'text-blue-700 dark:text-blue-400',
    bg: 'bg-blue-50 dark:bg-blue-900/20',
    dot: 'bg-blue-500',
  },
};

function formatRelativeTime(isoString: string | null): string {
  if (!isoString) return 'Never';
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60_000);
  const diffHours = Math.floor(diffMins / 60);
  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  return date.toLocaleDateString();
}

export function PlatformDashboard() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [timeRange, setTimeRange] = useState<TimeRange>('24h');
  const rangeCfg = RANGE_CONFIG[timeRange];

  // --- Gateway health data (REST API) ---
  const healthSummary = useGatewayHealthSummary();
  const gatewayInstances = useGatewayInstances();

  // --- Prometheus KPIs (global, no tenant filter) ---
  const totalRequests = usePrometheusQuery(
    `sum(increase(stoa_mcp_tools_calls_total[${timeRange}]))`,
    AUTO_REFRESH_INTERVAL
  );
  const errorRate = usePrometheusQuery(
    'sum(rate(stoa_mcp_tools_calls_total{status="error"}[5m])) / sum(rate(stoa_mcp_tools_calls_total[5m]))',
    AUTO_REFRESH_INTERVAL
  );
  const p95Latency = usePrometheusQuery(
    'histogram_quantile(0.95, sum(rate(stoa_mcp_tool_duration_seconds_bucket[5m])) by (le))',
    AUTO_REFRESH_INTERVAL
  );
  const topApisQuery = usePrometheusQuery(
    `topk(5, sum by (tool) (increase(stoa_mcp_tools_calls_total[${timeRange}])))`,
    AUTO_REFRESH_INTERVAL
  );
  const topApisLatency = usePrometheusQuery(
    'sum by (tool) (rate(stoa_mcp_tool_duration_seconds_sum[5m])) / sum by (tool) (rate(stoa_mcp_tool_duration_seconds_count[5m]))',
    AUTO_REFRESH_INTERVAL
  );
  const topApisErrors = usePrometheusQuery(
    `sum by (tool) (increase(stoa_mcp_tools_calls_total{status="error"}[${timeRange}]))`,
    AUTO_REFRESH_INTERVAL
  );

  // --- Timeseries (sparklines) ---
  const trafficTrend = usePrometheusRange(
    'sum(rate(stoa_mcp_tools_calls_total[5m]))',
    rangeCfg.seconds,
    rangeCfg.step,
    AUTO_REFRESH_INTERVAL
  );
  const errorTrend = usePrometheusRange(
    'sum(rate(stoa_mcp_tools_calls_total{status="error"}[5m]))',
    rangeCfg.seconds,
    rangeCfg.step,
    AUTO_REFRESH_INTERVAL
  );

  // --- Derived values ---
  const totalReqVal = scalarValue(totalRequests.data);
  const errorRateVal = scalarValue(errorRate.data);
  const p95Val = scalarValue(p95Latency.data);

  const healthData = healthSummary.data;
  const gatewaysOnline = healthData?.online ?? 0;
  const gatewaysTotal = healthData?.total ?? 0;

  const topApisCalls = groupByLabel(topApisQuery.data, 'tool');
  const topApisLat = groupByLabel(topApisLatency.data, 'tool');
  const topApisErr = groupByLabel(topApisErrors.data, 'tool');

  const topApisList = Object.entries(topApisCalls)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 5)
    .map(([tool, calls]) => ({
      name: tool,
      calls,
      latencyMs: (topApisLat[tool] || 0) * 1000,
      errors: topApisErr[tool] || 0,
    }));
  const maxApiCalls = topApisList[0]?.calls || 1;

  const prometheusAvailable = !totalRequests.error;
  const isLoading =
    (totalRequests.loading && !totalRequests.data) ||
    (healthSummary.isLoading && !healthSummary.data);

  // Demo mode: show sample data when Prometheus is unreachable
  const isDemoMode = !prometheusAvailable && !totalRequests.loading;

  const demoKPIs = {
    totalRequests: 12_847,
    errorRate: 0.023,
    p95Latency: 0.142,
  };

  const handleRefresh = () => {
    totalRequests.refetch();
    errorRate.refetch();
    p95Latency.refetch();
    topApisQuery.refetch();
    topApisLatency.refetch();
    topApisErrors.refetch();
    trafficTrend.refetch();
    errorTrend.refetch();
    healthSummary.refetch();
    gatewayInstances.refetch();
  };

  // Displayed values (real or demo)
  const displayTotalReq = isDemoMode ? demoKPIs.totalRequests : totalReqVal;
  const displayErrorRate = isDemoMode ? demoKPIs.errorRate : errorRateVal;
  const displayP95 = isDemoMode ? demoKPIs.p95Latency : p95Val;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1
            className="text-2xl font-bold text-neutral-900 dark:text-white"
            data-testid="dashboard-title"
          >
            {t('dashboard.title')}
          </h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            {t('dashboard.hello', { name: user?.name || 'User' })}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <TimeRangeSelector
            value={timeRange}
            onChange={setTimeRange}
            ranges={['1h', '6h', '24h', '7d', '30d']}
          />
          <button
            onClick={handleRefresh}
            className="flex items-center gap-2 border border-neutral-300 dark:border-neutral-600 text-neutral-700 dark:text-neutral-300 px-3 py-2 rounded-lg text-sm hover:bg-neutral-50 dark:hover:bg-neutral-700"
          >
            <RefreshCw className={`h-4 w-4 ${totalRequests.loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Demo mode banner */}
      {isDemoMode && (
        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 px-4 py-3 rounded-lg flex items-center gap-2">
          <Zap className="h-4 w-4 text-blue-600 dark:text-blue-400" />
          <span className="text-sm text-blue-700 dark:text-blue-300">
            Sample Data — Connect Prometheus to see live metrics
          </span>
        </div>
      )}

      {isLoading ? (
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
          {/* Hero KPI Row */}
          <div
            className="grid grid-cols-2 md:grid-cols-4 gap-4"
            role="region"
            aria-label="Platform KPIs"
            data-testid="dashboard-kpi-grid"
          >
            <StatCard
              label={`Requests (${timeRange})`}
              value={displayTotalReq !== null ? formatNumber(displayTotalReq) : '--'}
              icon={Activity}
              colorClass="text-blue-600"
              subtitle="Total tool calls"
              data-testid="dashboard-requests-count"
            />
            <StatCard
              label="Error Rate (5m)"
              value={displayErrorRate !== null ? `${(displayErrorRate * 100).toFixed(2)}%` : '--'}
              icon={AlertTriangle}
              colorClass={
                displayErrorRate !== null ? getErrorRateColor(displayErrorRate) : undefined
              }
              subtitle="5xx + tool errors"
              data-testid="dashboard-error-rate-count"
            />
            <StatCard
              label="Latency P95 (5m)"
              value={displayP95 !== null ? Math.round(displayP95 * 1000).toString() : '--'}
              unit="ms"
              icon={Clock}
              colorClass={displayP95 !== null ? getLatencyColor(displayP95 * 1000) : undefined}
              subtitle="Response time"
              data-testid="dashboard-latency-count"
            />
            <StatCard
              label="Gateways"
              value={`${gatewaysOnline}/${gatewaysTotal}`}
              icon={Radio}
              data-testid="dashboard-gateways-count"
              colorClass={
                gatewaysTotal === 0
                  ? 'text-neutral-500'
                  : gatewaysOnline === gatewaysTotal
                    ? 'text-green-600'
                    : 'text-yellow-600'
              }
              subtitle={
                gatewaysTotal === 0
                  ? 'No gateways registered'
                  : gatewaysOnline === gatewaysTotal
                    ? 'All online'
                    : `${gatewaysTotal - gatewaysOnline} degraded/offline`
              }
            />
          </div>

          {/* Charts Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Traffic Trend */}
            <div
              className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4"
              data-testid="dashboard-traffic-chart"
            >
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
                    Traffic
                  </h2>
                  <p className="text-xs text-neutral-400 dark:text-neutral-500">
                    req/s over {rangeCfg.label}
                  </p>
                </div>
                {trafficTrend.data && trafficTrend.data.length > 1 && (
                  <TrendIndicator data={trafficTrend.data} />
                )}
              </div>
              {trafficTrend.data ? (
                <SparklineChart
                  data={trafficTrend.data}
                  color="#3b82f6"
                  height={120}
                  width={560}
                  showArea
                  className="w-full"
                />
              ) : (
                <div className="h-[120px] flex items-center justify-center text-sm text-neutral-400 dark:text-neutral-500">
                  {trafficTrend.error ? 'Metrics unavailable' : 'Loading...'}
                </div>
              )}
            </div>

            {/* Error Trend */}
            <div
              className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4"
              data-testid="dashboard-error-chart"
            >
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
                    Errors
                  </h2>
                  <p className="text-xs text-neutral-400 dark:text-neutral-500">
                    errors/s over {rangeCfg.label}
                  </p>
                </div>
                {errorTrend.data && errorTrend.data.length > 1 && (
                  <TrendIndicator data={errorTrend.data} invertColor />
                )}
              </div>
              {errorTrend.data ? (
                <SparklineChart
                  data={errorTrend.data}
                  color="#ef4444"
                  height={120}
                  width={560}
                  showArea
                  className="w-full"
                />
              ) : (
                <div className="h-[120px] flex items-center justify-center text-sm text-neutral-400 dark:text-neutral-500">
                  {errorTrend.error ? 'Metrics unavailable' : 'Loading...'}
                </div>
              )}
            </div>
          </div>

          {/* Gateway Health Cards + Top APIs */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Gateway Instances */}
            <div
              className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4"
              data-testid="dashboard-gateway-instances"
            >
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
                  Gateway Instances
                </h2>
                {healthData && (
                  <div className="flex items-center gap-2 text-xs">
                    <span className="flex items-center gap-1 text-green-600">
                      <span className="w-2 h-2 rounded-full bg-green-500" />
                      {healthData.online}
                    </span>
                    {healthData.degraded > 0 && (
                      <span className="flex items-center gap-1 text-yellow-600">
                        <span className="w-2 h-2 rounded-full bg-yellow-500" />
                        {healthData.degraded}
                      </span>
                    )}
                    {healthData.offline > 0 && (
                      <span className="flex items-center gap-1 text-red-600">
                        <span className="w-2 h-2 rounded-full bg-red-500" />
                        {healthData.offline}
                      </span>
                    )}
                  </div>
                )}
              </div>
              {gatewayInstances.data && gatewayInstances.data.items.length > 0 ? (
                <div className="space-y-2">
                  {gatewayInstances.data.items.map((gw: any) => {
                    const cfg = STATUS_CONFIG[gw.status] || STATUS_CONFIG.offline;
                    return (
                      <div
                        key={gw.id}
                        className={`flex items-center justify-between px-3 py-2.5 rounded-lg ${cfg.bg}`}
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <span className={`w-2 h-2 rounded-full flex-shrink-0 ${cfg.dot}`} />
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-neutral-900 dark:text-white truncate">
                              {gw.display_name || gw.name}
                            </p>
                            <p className="text-xs text-neutral-500 dark:text-neutral-400">
                              {gw.gateway_type}
                              {gw.mode ? ` / ${gw.mode}` : ''}
                            </p>
                          </div>
                        </div>
                        <div className="text-right flex-shrink-0 ml-2">
                          <p className={`text-xs font-medium ${cfg.color}`}>{gw.status}</p>
                          <p className="text-xs text-neutral-400 dark:text-neutral-500">
                            {formatRelativeTime(gw.last_health_check)}
                          </p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-8 text-neutral-400 dark:text-neutral-500">
                  <Server className="h-8 w-8 mb-2" />
                  <p className="text-sm">No gateways registered</p>
                  <a href="/gateways" className="text-xs text-blue-600 hover:underline mt-1">
                    Register a gateway
                  </a>
                </div>
              )}
            </div>

            {/* Top APIs */}
            <div
              className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4"
              data-testid="dashboard-top-apis"
            >
              <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase mb-4">
                Top APIs ({timeRange})
              </h2>
              {topApisList.length > 0 ? (
                <div className="space-y-3">
                  {topApisList.map((api, i) => (
                    <div key={api.name} className="flex items-center gap-3">
                      <span className="text-xs font-bold text-neutral-400 dark:text-neutral-500 w-5 text-right">
                        {i + 1}
                      </span>
                      <TrendingUp className="h-4 w-4 text-neutral-400 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-sm font-medium text-neutral-900 dark:text-white truncate">
                            {api.name}
                          </span>
                          <div className="flex items-center gap-3 ml-2">
                            <span className="text-xs text-neutral-500 dark:text-neutral-400">
                              {formatNumber(api.calls)} calls
                            </span>
                            <span className="text-xs text-neutral-400 dark:text-neutral-500 w-16 text-right">
                              {Math.round(api.latencyMs)}ms
                            </span>
                            {api.errors > 0 && (
                              <span className="text-xs text-red-500 w-12 text-right">
                                {formatNumber(api.errors)} err
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="w-full bg-neutral-100 dark:bg-neutral-700 rounded-full h-1.5">
                          <div
                            className="bg-blue-500 h-1.5 rounded-full transition-all"
                            style={{ width: `${(api.calls / maxApiCalls) * 100}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-8 text-neutral-400 dark:text-neutral-500">
                  <Activity className="h-8 w-8 mb-2" />
                  <p className="text-sm">
                    {isDemoMode ? 'Connect Prometheus for live data' : 'No API traffic yet'}
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

export default PlatformDashboard;
