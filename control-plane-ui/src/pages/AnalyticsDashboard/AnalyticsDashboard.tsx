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
  ChevronDown,
  ChevronUp,
  ArrowUpDown,
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

type SortField = 'calls' | 'errors' | 'latency';

interface ErrorCategory {
  category: string;
  count: number;
  percentage: number;
  avg_duration_ms: number;
}

interface ConsumerUsage {
  consumer_id: string;
  name: string;
  calls: number;
  error_rate: number;
  avg_latency_ms: number;
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
  const [consumerUsage, setConsumerUsage] = useState<ConsumerUsage[]>([]);
  const [loading, setLoading] = useState(true);
  const [_error, setError] = useState<string | null>(null);
  const [sortField, setSortField] = useState<SortField>('calls');
  const [expandedTool, setExpandedTool] = useState<string | null>(null);

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

  // Per-tool error counts (for sort-by-errors)
  const topToolsErrors = usePrometheusQuery(
    `sum by (tool) (increase(stoa_mcp_tools_calls_total{tenant="${tenantId}",status="error"}[${timeRange}]))`,
    AUTO_REFRESH_INTERVAL
  );

  // Per-tool avg latency (for sort-by-latency)
  const topToolsLatency = usePrometheusQuery(
    `sum by (tool) (rate(stoa_mcp_tool_duration_seconds_sum{tenant="${tenantId}"}[5m])) / sum by (tool) (rate(stoa_mcp_tool_duration_seconds_count{tenant="${tenantId}"}[5m]))`,
    AUTO_REFRESH_INTERVAL
  );

  // Expanded tool detail: p50/p95/p99 latency
  const expandedToolP50 = usePrometheusQuery(
    expandedTool
      ? `histogram_quantile(0.5, sum by (le) (rate(stoa_mcp_tool_duration_seconds_bucket{tenant="${tenantId}",tool="${expandedTool}"}[5m])))`
      : '',
    expandedTool ? AUTO_REFRESH_INTERVAL : 0
  );
  const expandedToolP95 = usePrometheusQuery(
    expandedTool
      ? `histogram_quantile(0.95, sum by (le) (rate(stoa_mcp_tool_duration_seconds_bucket{tenant="${tenantId}",tool="${expandedTool}"}[5m])))`
      : '',
    expandedTool ? AUTO_REFRESH_INTERVAL : 0
  );
  const expandedToolP99 = usePrometheusQuery(
    expandedTool
      ? `histogram_quantile(0.99, sum by (le) (rate(stoa_mcp_tool_duration_seconds_bucket{tenant="${tenantId}",tool="${expandedTool}"}[5m])))`
      : '',
    expandedTool ? AUTO_REFRESH_INTERVAL : 0
  );

  // Consumer usage (top 10 by calls)
  const consumerCallsQuery = usePrometheusQuery(
    `topk(10, sum by (consumer_id) (increase(stoa_mcp_tools_calls_total{tenant="${tenantId}"}[${timeRange}])))`,
    AUTO_REFRESH_INTERVAL
  );
  const consumerErrorsQuery = usePrometheusQuery(
    `sum by (consumer_id) (increase(stoa_mcp_tools_calls_total{tenant="${tenantId}",status="error"}[${timeRange}]))`,
    AUTO_REFRESH_INTERVAL
  );
  const consumerLatencyQuery = usePrometheusQuery(
    `sum by (consumer_id) (rate(stoa_mcp_tool_duration_seconds_sum{tenant="${tenantId}"}[5m])) / sum by (consumer_id) (rate(stoa_mcp_tool_duration_seconds_count{tenant="${tenantId}"}[5m]))`,
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
    topToolsErrors.refetch();
    topToolsLatency.refetch();
    consumerCallsQuery.refetch();
    consumerErrorsQuery.refetch();
    consumerLatencyQuery.refetch();
    if (expandedTool) {
      expandedToolP50.refetch();
      expandedToolP95.refetch();
      expandedToolP99.refetch();
    }
    loadApiData();
  };

  const totalCallsVal = scalarValue(totalCalls.data);
  const avgLatencyVal = scalarValue(avgLatency.data);
  const errorRateVal = scalarValue(errorRate.data);
  const activeConsumersVal = scalarValue(activeConsumers.data);

  const topToolsCalls = groupByLabel(topToolsQuery.data, 'tool');
  const topToolsErrorMap = groupByLabel(topToolsErrors.data, 'tool');
  const topToolsLatencyMap = groupByLabel(topToolsLatency.data, 'tool');

  const enrichedTools = Object.entries(topToolsCalls)
    .map(([tool, calls]) => ({
      name: tool,
      calls,
      errors: topToolsErrorMap[tool] || 0,
      latency: topToolsLatencyMap[tool] || 0,
    }))
    .sort((a, b) => {
      if (sortField === 'errors') return b.errors - a.errors;
      if (sortField === 'latency') return b.latency - a.latency;
      return b.calls - a.calls;
    })
    .slice(0, 10);
  const maxToolCalls = enrichedTools[0]?.calls || 1;

  // Build consumer usage from Prometheus results
  const consumerCallsMap = groupByLabel(consumerCallsQuery.data, 'consumer_id');
  const consumerErrorsMap = groupByLabel(consumerErrorsQuery.data, 'consumer_id');
  const consumerLatencyMap = groupByLabel(consumerLatencyQuery.data, 'consumer_id');

  useEffect(() => {
    const ids = Object.keys(consumerCallsMap);
    if (ids.length === 0) return;
    const usage: ConsumerUsage[] = ids.map((id) => {
      const calls = consumerCallsMap[id] || 0;
      const errors = consumerErrorsMap[id] || 0;
      return {
        consumer_id: id,
        name: id,
        calls,
        error_rate: calls > 0 ? errors / calls : 0,
        avg_latency_ms: (consumerLatencyMap[id] || 0) * 1000,
      };
    });
    usage.sort((a, b) => b.calls - a.calls);
    setConsumerUsage(usage);
  }, [consumerCallsQuery.data, consumerErrorsQuery.data, consumerLatencyQuery.data]); // eslint-disable-line react-hooks/exhaustive-deps

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
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
                  Top Tools ({timeRange})
                </h2>
                <div className="flex items-center gap-1" role="group" aria-label="Sort tools by">
                  {(['calls', 'errors', 'latency'] as SortField[]).map((field) => (
                    <button
                      key={field}
                      onClick={() => setSortField(field)}
                      className={`px-2 py-1 text-xs rounded ${
                        sortField === field
                          ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300 font-medium'
                          : 'text-neutral-500 dark:text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-700'
                      }`}
                      aria-label={`Sort by ${field}`}
                    >
                      <ArrowUpDown className="h-3 w-3 inline mr-1" />
                      {field}
                    </button>
                  ))}
                </div>
              </div>
              {enrichedTools.length > 0 ? (
                <div className="space-y-2">
                  {enrichedTools.map((tool, i) => (
                    <div key={tool.name}>
                      <button
                        onClick={() =>
                          setExpandedTool(expandedTool === tool.name ? null : tool.name)
                        }
                        className="w-full flex items-center gap-3 py-1 hover:bg-neutral-50 dark:hover:bg-neutral-700/50 rounded transition-colors text-left"
                        aria-expanded={expandedTool === tool.name}
                        aria-label={`Tool ${tool.name}`}
                      >
                        <span className="text-xs font-bold text-neutral-400 dark:text-neutral-500 w-5 text-right">
                          {i + 1}
                        </span>
                        {expandedTool === tool.name ? (
                          <ChevronUp className="h-4 w-4 text-blue-500 flex-shrink-0" />
                        ) : (
                          <ChevronDown className="h-4 w-4 text-neutral-400 flex-shrink-0" />
                        )}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-sm font-medium text-neutral-900 dark:text-white truncate">
                              {tool.name}
                            </span>
                            <div className="flex items-center gap-3 ml-2">
                              <span className="text-xs text-neutral-500 dark:text-neutral-400">
                                {tool.calls >= 1000
                                  ? `${(tool.calls / 1000).toFixed(1)}K`
                                  : Math.round(tool.calls)}{' '}
                                calls
                              </span>
                              {tool.errors > 0 && (
                                <span className="text-xs text-red-500">
                                  {Math.round(tool.errors)} err
                                </span>
                              )}
                              {tool.latency > 0 && (
                                <span className="text-xs text-amber-600 dark:text-amber-400">
                                  {Math.round(tool.latency * 1000)}ms
                                </span>
                              )}
                            </div>
                          </div>
                          <div className="w-full bg-neutral-100 dark:bg-neutral-700 rounded-full h-1.5">
                            <div
                              className="bg-blue-500 h-1.5 rounded-full transition-all"
                              style={{ width: `${(tool.calls / maxToolCalls) * 100}%` }}
                            />
                          </div>
                        </div>
                      </button>
                      {expandedTool === tool.name && (
                        <div
                          className="ml-12 mt-2 mb-3 p-3 bg-neutral-50 dark:bg-neutral-700/30 rounded-lg"
                          data-testid="tool-detail-panel"
                        >
                          <h4 className="text-xs font-semibold text-neutral-500 dark:text-neutral-400 uppercase mb-2">
                            Latency Percentiles
                          </h4>
                          <div className="grid grid-cols-3 gap-2">
                            <div className="text-center">
                              <p className="text-xs text-neutral-400 dark:text-neutral-500">p50</p>
                              <p className="text-sm font-semibold text-neutral-900 dark:text-white">
                                {scalarValue(expandedToolP50.data) !== null
                                  ? `${Math.round(scalarValue(expandedToolP50.data)! * 1000)}ms`
                                  : '--'}
                              </p>
                            </div>
                            <div className="text-center">
                              <p className="text-xs text-neutral-400 dark:text-neutral-500">p95</p>
                              <p className="text-sm font-semibold text-neutral-900 dark:text-white">
                                {scalarValue(expandedToolP95.data) !== null
                                  ? `${Math.round(scalarValue(expandedToolP95.data)! * 1000)}ms`
                                  : '--'}
                              </p>
                            </div>
                            <div className="text-center">
                              <p className="text-xs text-neutral-400 dark:text-neutral-500">p99</p>
                              <p className="text-sm font-semibold text-neutral-900 dark:text-white">
                                {scalarValue(expandedToolP99.data) !== null
                                  ? `${Math.round(scalarValue(expandedToolP99.data)! * 1000)}ms`
                                  : '--'}
                              </p>
                            </div>
                          </div>
                        </div>
                      )}
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

          {/* Consumer Activity Table */}
          <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
                  Consumer Activity
                </h2>
                <p className="text-xs text-neutral-400 dark:text-neutral-500">
                  Top consumers by usage ({timeRange})
                </p>
              </div>
              <Users className="h-5 w-5 text-neutral-400" />
            </div>
            {consumerUsage.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-neutral-200 dark:border-neutral-700">
                      <th className="text-left py-2 px-2 text-xs font-semibold text-neutral-500 dark:text-neutral-400 uppercase">
                        Consumer
                      </th>
                      <th className="text-right py-2 px-2 text-xs font-semibold text-neutral-500 dark:text-neutral-400 uppercase">
                        Calls
                      </th>
                      <th className="text-right py-2 px-2 text-xs font-semibold text-neutral-500 dark:text-neutral-400 uppercase">
                        Error Rate
                      </th>
                      <th className="text-right py-2 px-2 text-xs font-semibold text-neutral-500 dark:text-neutral-400 uppercase">
                        Avg Latency
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {consumerUsage.map((c) => (
                      <tr
                        key={c.consumer_id}
                        className="border-b border-neutral-100 dark:border-neutral-700/50 hover:bg-neutral-50 dark:hover:bg-neutral-700/30"
                      >
                        <td className="py-2 px-2">
                          <span className="font-medium text-neutral-900 dark:text-white">
                            {c.name}
                          </span>
                        </td>
                        <td className="py-2 px-2 text-right text-neutral-700 dark:text-neutral-300">
                          {c.calls >= 1000
                            ? `${(c.calls / 1000).toFixed(1)}K`
                            : Math.round(c.calls)}
                        </td>
                        <td className="py-2 px-2 text-right">
                          <span
                            className={
                              c.error_rate > 0.05
                                ? 'text-red-600 dark:text-red-400 font-medium'
                                : c.error_rate > 0.01
                                  ? 'text-yellow-600 dark:text-yellow-400'
                                  : 'text-green-600 dark:text-green-400'
                            }
                          >
                            {(c.error_rate * 100).toFixed(1)}%
                          </span>
                        </td>
                        <td className="py-2 px-2 text-right text-neutral-700 dark:text-neutral-300">
                          {Math.round(c.avg_latency_ms)}ms
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState
                title="No consumer data"
                description="Consumer activity will appear here once consumers start making API calls."
                illustration={<Users className="h-12 w-12" />}
              />
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default AnalyticsDashboard;
