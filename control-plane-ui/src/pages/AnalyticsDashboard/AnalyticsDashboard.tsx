import { useState, useEffect, useCallback } from 'react';
import {
  RefreshCw,
  BarChart3,
  TrendingUp,
  Users,
  Cpu,
  Clock,
  AlertTriangle,
  Zap,
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { apiService } from '../../services/api';
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
import { EmptyState } from '@stoa/shared/components/EmptyState';
import type { TopAPI } from '../../services/api';

const AUTO_REFRESH_INTERVAL = 30_000;
const ACTIVE_TENANT_KEY = 'stoa-active-tenant';

interface ErrorCategory {
  category: string;
  count: number;
  percentage: number;
  avg_duration_ms: number;
}

const ERROR_CATEGORY_COLORS: Record<string, string> = {
  auth: 'bg-red-500',
  rate_limit: 'bg-orange-500',
  backend: 'bg-yellow-500',
  timeout: 'bg-purple-500',
  validation: 'bg-blue-500',
};

export function AnalyticsDashboard() {
  const { user, isReady } = useAuth();
  const [timeRange, setTimeRange] = useState<TimeRange>('24h');
  const [topApis, setTopApis] = useState<TopAPI[]>([]);
  const [errorCategories, setErrorCategories] = useState<ErrorCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [_error, setError] = useState<string | null>(null);

  const tenantId = localStorage.getItem(ACTIVE_TENANT_KEY) || user?.tenant_id || 'default';
  const rangeCfg = RANGE_CONFIG[timeRange];

  // Prometheus KPIs
  const totalCalls = usePrometheusQuery(
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
  const activeConsumers = usePrometheusQuery(
    `count(count by (consumer_id) (increase(stoa_mcp_tools_calls_total{tenant="${tenantId}"}[${timeRange}]) > 0))`,
    AUTO_REFRESH_INTERVAL
  );

  // Sparklines
  const callsTrend = usePrometheusRange(
    `sum(rate(stoa_mcp_tools_calls_total{tenant="${tenantId}"}[5m]))`,
    rangeCfg.seconds,
    rangeCfg.step,
    AUTO_REFRESH_INTERVAL
  );
  const latencyTrend = usePrometheusRange(
    `sum(rate(stoa_mcp_tool_duration_seconds_sum{tenant="${tenantId}"}[5m])) / sum(rate(stoa_mcp_tool_duration_seconds_count{tenant="${tenantId}"}[5m]))`,
    rangeCfg.seconds,
    rangeCfg.step,
    AUTO_REFRESH_INTERVAL
  );

  // Top tools by label
  const topToolsQuery = usePrometheusQuery(
    `topk(10, sum by (tool) (increase(stoa_mcp_tools_calls_total{tenant="${tenantId}"}[${timeRange}])))`,
    AUTO_REFRESH_INTERVAL
  );

  // API data
  const loadApiData = useCallback(async () => {
    try {
      const [apis, taxonomy] = await Promise.all([
        apiService.getTopAPIs(10).catch(() => []),
        apiService
          .get<{
            items: ErrorCategory[];
            total_errors: number;
            error_rate: number;
          }>(`/v1/tenants/${tenantId}/executions/taxonomy`)
          .then((r) => r.data)
          .catch(() => ({ items: [], total_errors: 0, error_rate: 0 })),
      ]);
      setTopApis(apis);
      setErrorCategories(taxonomy.items || []);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load analytics');
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    if (isReady) loadApiData();
  }, [isReady, loadApiData]);

  useEffect(() => {
    if (!isReady) return;
    const interval = setInterval(loadApiData, AUTO_REFRESH_INTERVAL);
    return () => clearInterval(interval);
  }, [isReady, loadApiData]);

  const handleRefresh = () => {
    totalCalls.refetch();
    avgLatency.refetch();
    errorRate.refetch();
    activeConsumers.refetch();
    callsTrend.refetch();
    latencyTrend.refetch();
    topToolsQuery.refetch();
    loadApiData();
  };

  const totalCallsVal = scalarValue(totalCalls.data);
  const avgLatencyVal = scalarValue(avgLatency.data);
  const errorRateVal = scalarValue(errorRate.data);
  const activeConsumersVal = scalarValue(activeConsumers.data);

  const topToolsCalls = groupByLabel(topToolsQuery.data, 'tool');
  const topToolsList = Object.entries(topToolsCalls)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 10)
    .map(([tool, calls]) => ({ name: tool, calls }));
  const maxToolCalls = topToolsList[0]?.calls || 1;

  const prometheusAvailable = !totalCalls.error;
  const isInitialLoading = loading && !prometheusAvailable;

  const errorCategoryTotal = errorCategories.reduce((s, c) => s + c.count, 0);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Usage Analytics</h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            API usage patterns, consumer activity, and error distribution for{' '}
            <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300">
              {tenantId}
            </span>
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
            <RefreshCw className={`h-4 w-4 ${totalCalls.loading ? 'animate-spin' : ''}`} />
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

      {isInitialLoading ? (
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
              label={`Total Calls (${timeRange})`}
              value={
                totalCallsVal !== null
                  ? totalCallsVal >= 1000
                    ? `${(totalCallsVal / 1000).toFixed(1)}K`
                    : Math.round(totalCallsVal).toString()
                  : '--'
              }
              icon={Zap}
              colorClass="text-blue-600"
              subtitle={`Over ${rangeCfg.label}`}
            />
            <StatCard
              label="Avg Latency (5m)"
              value={avgLatencyVal !== null ? Math.round(avgLatencyVal * 1000).toString() : '--'}
              unit="ms"
              icon={Clock}
              colorClass={
                avgLatencyVal !== null && avgLatencyVal * 1000 < 300
                  ? 'text-green-600'
                  : avgLatencyVal !== null && avgLatencyVal * 1000 < 500
                    ? 'text-yellow-600'
                    : avgLatencyVal !== null
                      ? 'text-red-600'
                      : undefined
              }
              subtitle="Response time"
            />
            <StatCard
              label="Error Rate (5m)"
              value={errorRateVal !== null ? `${(errorRateVal * 100).toFixed(2)}%` : '--'}
              icon={AlertTriangle}
              colorClass={
                errorRateVal !== null && errorRateVal < 0.01
                  ? 'text-green-600'
                  : errorRateVal !== null && errorRateVal < 0.05
                    ? 'text-yellow-600'
                    : errorRateVal !== null
                      ? 'text-red-600'
                      : undefined
              }
              subtitle="Error responses"
            />
            <StatCard
              label="Active Consumers"
              value={activeConsumersVal !== null ? Math.round(activeConsumersVal).toString() : '--'}
              icon={Users}
              colorClass="text-blue-600"
              subtitle={`In last ${rangeCfg.label}`}
            />
          </div>

          {/* Charts Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Call Volume Trend */}
            <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
                    Call Volume
                  </h2>
                  <p className="text-xs text-neutral-400 dark:text-neutral-500">
                    calls/s over {rangeCfg.label}
                  </p>
                </div>
                {callsTrend.data && callsTrend.data.length > 1 && (
                  <TrendIndicator data={callsTrend.data} />
                )}
              </div>
              {callsTrend.data ? (
                <SparklineChart
                  data={callsTrend.data}
                  color="#3b82f6"
                  height={120}
                  width={560}
                  showArea
                  className="w-full"
                />
              ) : (
                <div className="h-[120px] flex items-center justify-center text-sm text-neutral-400 dark:text-neutral-500">
                  {callsTrend.error ? 'Metrics unavailable' : 'Loading...'}
                </div>
              )}
            </div>

            {/* Latency Trend */}
            <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
                    Latency Trend
                  </h2>
                  <p className="text-xs text-neutral-400 dark:text-neutral-500">
                    avg response time over {rangeCfg.label}
                  </p>
                </div>
                {latencyTrend.data && latencyTrend.data.length > 1 && (
                  <TrendIndicator data={latencyTrend.data} invertColor />
                )}
              </div>
              {latencyTrend.data ? (
                <SparklineChart
                  data={latencyTrend.data}
                  color="#f59e0b"
                  height={120}
                  width={560}
                  showArea
                  className="w-full"
                />
              ) : (
                <div className="h-[120px] flex items-center justify-center text-sm text-neutral-400 dark:text-neutral-500">
                  {latencyTrend.error ? 'Metrics unavailable' : 'Loading...'}
                </div>
              )}
            </div>
          </div>

          {/* Bottom Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Top Tools */}
            <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
              <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase mb-4">
                Top Tools ({timeRange})
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
                          <span className="text-xs text-neutral-500 dark:text-neutral-400 ml-2">
                            {tool.calls >= 1000
                              ? `${(tool.calls / 1000).toFixed(1)}K`
                              : Math.round(tool.calls)}{' '}
                            calls
                          </span>
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
              ) : topApis.length > 0 ? (
                <div className="space-y-3">
                  {topApis.map((api, i) => {
                    const maxCalls = topApis[0]?.calls || 1;
                    return (
                      <div key={api.tool_name} className="flex items-center gap-3">
                        <span className="text-xs font-bold text-neutral-400 dark:text-neutral-500 w-5 text-right">
                          {i + 1}
                        </span>
                        <Cpu className="h-4 w-4 text-neutral-400 flex-shrink-0" />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-sm font-medium text-neutral-900 dark:text-white truncate">
                              {api.display_name || api.tool_name}
                            </span>
                            <span className="text-xs text-neutral-500 dark:text-neutral-400 ml-2">
                              {api.calls.toLocaleString()} calls
                            </span>
                          </div>
                          <div className="w-full bg-neutral-100 dark:bg-neutral-700 rounded-full h-1.5">
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
                <EmptyState
                  title="No usage data"
                  description="Tool usage data will appear here once APIs are called."
                  illustration={<BarChart3 className="h-12 w-12" />}
                />
              )}
            </div>

            {/* Error Distribution */}
            <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
              <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase mb-4">
                Error Distribution
              </h2>
              {errorCategories.length > 0 ? (
                <>
                  {/* Stacked bar */}
                  <div className="flex h-4 rounded-full overflow-hidden mb-4">
                    {errorCategories.map((cat) => {
                      const pct =
                        errorCategoryTotal > 0 ? (cat.count / errorCategoryTotal) * 100 : 0;
                      if (pct === 0) return null;
                      return (
                        <div
                          key={cat.category}
                          className={`${ERROR_CATEGORY_COLORS[cat.category] || 'bg-neutral-500'} transition-all`}
                          style={{ width: `${pct}%` }}
                          title={`${cat.category}: ${cat.count} (${pct.toFixed(1)}%)`}
                        />
                      );
                    })}
                  </div>
                  {/* Legend */}
                  <div className="space-y-2">
                    {errorCategories.map((cat) => (
                      <div key={cat.category} className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span
                            className={`w-3 h-3 rounded-full ${ERROR_CATEGORY_COLORS[cat.category] || 'bg-neutral-500'}`}
                          />
                          <span className="text-sm text-neutral-700 dark:text-neutral-300 capitalize">
                            {cat.category.replace(/_/g, ' ')}
                          </span>
                        </div>
                        <div className="flex items-center gap-4">
                          <span className="text-sm font-medium text-neutral-900 dark:text-white">
                            {cat.count}
                          </span>
                          <span className="text-xs text-neutral-500 dark:text-neutral-400 w-12 text-right">
                            {cat.percentage.toFixed(1)}%
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <EmptyState
                  title="No errors"
                  description="Error distribution will appear here when errors are detected."
                  illustration={<TrendingUp className="h-12 w-12" />}
                />
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default AnalyticsDashboard;
