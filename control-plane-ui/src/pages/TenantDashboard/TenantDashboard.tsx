import { useState } from 'react';
import { RefreshCw, Activity, AlertTriangle, Clock, Shield, Cpu } from 'lucide-react';
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

const ACTIVE_TENANT_KEY = 'stoa-active-tenant';
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

export function TenantDashboard() {
  const { user } = useAuth();
  const [timeRange, setTimeRange] = useState<TimeRange>('1h');

  const tenantId = localStorage.getItem(ACTIVE_TENANT_KEY) || user?.tenant_id || 'default';
  const rangeCfg = RANGE_CONFIG[timeRange];

  // --- Prometheus instant queries ---
  const toolCalls = usePrometheusQuery(
    `sum(increase(stoa_mcp_tools_calls_total{tenant="${tenantId}"}[${timeRange}]))`,
    AUTO_REFRESH_INTERVAL
  );
  const avgLatency = usePrometheusQuery(
    `sum(rate(stoa_mcp_tool_duration_seconds_sum{tenant="${tenantId}"}[5m])) / sum(rate(stoa_mcp_tool_duration_seconds_count{tenant="${tenantId}"}[5m]))`,
    AUTO_REFRESH_INTERVAL
  );
  const errorRate = usePrometheusQuery(
    `sum(rate(stoa_mcp_tools_calls_total{tenant="${tenantId}",status="error"}[5m])) / sum(rate(stoa_mcp_tools_calls_total{tenant="${tenantId}"}[5m]))`,
    AUTO_REFRESH_INTERVAL
  );
  const rateLimitHits = usePrometheusQuery(
    `sum(increase(stoa_rate_limit_hits_total{tenant="${tenantId}"}[${timeRange}]))`,
    AUTO_REFRESH_INTERVAL
  );
  const topToolsQuery = usePrometheusQuery(
    `topk(5, sum by (tool) (increase(stoa_mcp_tools_calls_total{tenant="${tenantId}"}[${timeRange}])))`,
    AUTO_REFRESH_INTERVAL
  );
  const toolLatencyQuery = usePrometheusQuery(
    `sum by (tool) (rate(stoa_mcp_tool_duration_seconds_sum{tenant="${tenantId}"}[5m])) / sum by (tool) (rate(stoa_mcp_tool_duration_seconds_count{tenant="${tenantId}"}[5m]))`,
    AUTO_REFRESH_INTERVAL
  );

  // --- Prometheus range queries (sparklines) ---
  const usageTrend = usePrometheusRange(
    `sum(rate(stoa_mcp_tools_calls_total{tenant="${tenantId}"}[5m]))`,
    rangeCfg.seconds,
    rangeCfg.step,
    AUTO_REFRESH_INTERVAL
  );
  const errorTrend = usePrometheusRange(
    `sum(rate(stoa_mcp_tools_calls_total{tenant="${tenantId}",status="error"}[5m]))`,
    rangeCfg.seconds,
    rangeCfg.step,
    AUTO_REFRESH_INTERVAL
  );

  // --- Derived values ---
  const toolCallsVal = scalarValue(toolCalls.data);
  const avgLatencyVal = scalarValue(avgLatency.data);
  const errorRateVal = scalarValue(errorRate.data);
  const rateLimitVal = scalarValue(rateLimitHits.data);

  const topToolsCalls = groupByLabel(topToolsQuery.data, 'tool');
  const topToolsLatency = groupByLabel(toolLatencyQuery.data, 'tool');

  const topToolsList = Object.entries(topToolsCalls)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 5)
    .map(([tool, calls]) => ({
      name: tool,
      calls,
      latencyMs: (topToolsLatency[tool] || 0) * 1000,
    }));
  const maxToolCalls = topToolsList[0]?.calls || 1;

  const prometheusAvailable = !toolCalls.error;
  const isLoading = toolCalls.loading && !toolCalls.data;

  const handleRefresh = () => {
    toolCalls.refetch();
    avgLatency.refetch();
    errorRate.refetch();
    rateLimitHits.refetch();
    topToolsQuery.refetch();
    toolLatencyQuery.refetch();
    usageTrend.refetch();
    errorTrend.refetch();
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">My Usage</h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            Metrics for{' '}
            <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300">
              {tenantId}
            </span>
          </p>
        </div>
        <div className="flex items-center gap-3">
          <TimeRangeSelector value={timeRange} onChange={setTimeRange} />
          <button
            onClick={handleRefresh}
            className="flex items-center gap-2 border border-neutral-300 dark:border-neutral-600 text-neutral-700 dark:text-neutral-300 px-3 py-2 rounded-lg text-sm hover:bg-neutral-50 dark:hover:bg-neutral-700 disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${toolCalls.loading ? 'animate-spin' : ''}`} />
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
              Prometheus is not reachable. Metrics are unavailable.
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
          {/* KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard
              label={`Tool Calls (${timeRange})`}
              value={toolCallsVal !== null ? formatNumber(toolCallsVal) : '--'}
              icon={Activity}
              colorClass="text-blue-600"
              subtitle="All tools"
            />
            <StatCard
              label="Avg Latency (5m)"
              value={avgLatencyVal !== null ? Math.round(avgLatencyVal * 1000).toString() : '--'}
              unit="ms"
              icon={Clock}
              colorClass={
                avgLatencyVal !== null ? getLatencyColor(avgLatencyVal * 1000) : undefined
              }
              subtitle="Response time"
            />
            <StatCard
              label="Error Rate (5m)"
              value={errorRateVal !== null ? `${(errorRateVal * 100).toFixed(2)}%` : '--'}
              icon={AlertTriangle}
              colorClass={errorRateVal !== null ? getErrorRateColor(errorRateVal) : undefined}
              subtitle="Error responses"
            />
            <StatCard
              label={`Rate Limit Hits (${timeRange})`}
              value={rateLimitVal !== null ? formatNumber(rateLimitVal) : '--'}
              icon={Shield}
              colorClass={
                rateLimitVal !== null && rateLimitVal > 0 ? 'text-orange-600' : 'text-green-600'
              }
              subtitle={rateLimitVal === 0 ? 'No throttling' : 'Requests throttled'}
            />
          </div>

          {/* Charts Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Usage Trend */}
            <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
                    Usage Trend
                  </h2>
                  <p className="text-xs text-neutral-400 dark:text-neutral-500">
                    req/s over {rangeCfg.label}
                  </p>
                </div>
                {usageTrend.data && usageTrend.data.length > 1 && (
                  <TrendIndicator data={usageTrend.data} />
                )}
              </div>
              {usageTrend.data ? (
                <SparklineChart
                  data={usageTrend.data}
                  color="#3b82f6"
                  height={120}
                  width={560}
                  showArea
                  className="w-full"
                />
              ) : (
                <div className="h-[120px] flex items-center justify-center text-sm text-neutral-400 dark:text-neutral-500">
                  {usageTrend.error ? 'Metrics unavailable' : 'Loading...'}
                </div>
              )}
            </div>

            {/* Error Trend */}
            <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
                    Error Trend
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

          {/* Top Tools */}
          <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
            <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase mb-4">
              Top 5 Tools ({timeRange})
            </h2>
            {topToolsList.length > 0 ? (
              <div className="space-y-3">
                {topToolsList.map((tool, i) => (
                  <div key={tool.name} className="flex items-center gap-3">
                    <span className="text-xs font-bold text-neutral-400 dark:text-neutral-500 w-5 text-right">
                      {i + 1}
                    </span>
                    <Cpu className="h-4 w-4 text-neutral-400 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm font-medium text-neutral-900 dark:text-white truncate">
                          {tool.name}
                        </span>
                        <div className="flex items-center gap-3 ml-2">
                          <span className="text-xs text-neutral-500 dark:text-neutral-400">
                            {formatNumber(tool.calls)} calls
                          </span>
                          <span className="text-xs text-neutral-400 dark:text-neutral-500 w-16 text-right">
                            {Math.round(tool.latencyMs)}ms avg
                          </span>
                        </div>
                      </div>
                      <div className="w-full bg-neutral-100 dark:bg-neutral-700 rounded-full h-1.5">
                        <div
                          className="bg-blue-500 h-1.5 rounded-full transition-all"
                          style={{ width: `${(tool.calls / maxToolCalls) * 100}%` }}
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-neutral-500 dark:text-neutral-400 text-center py-8">
                No tool usage data available
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default TenantDashboard;
