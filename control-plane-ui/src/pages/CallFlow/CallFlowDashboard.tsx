import { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Activity,
  RefreshCw,
  Zap,
  AlertTriangle,
  CheckCircle,
  Network,
  Gauge,
  Timer,
} from 'lucide-react';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import { StatCard } from '@stoa/shared/components/StatCard';
import { TimeRangeSelector, RANGE_CONFIG } from '@stoa/shared/components/TimeRangeSelector';
import { TrendIndicator } from '@stoa/shared/components/TrendIndicator';
import { ChartCard } from '@stoa/shared/components/ChartCard';
import { SubNav } from '../../components/SubNav';
import { observabilityTabs } from '../../components/subNavGroups';
import type { TimeRange } from '@stoa/shared/components/TimeRangeSelector';
import {
  usePrometheusQuery,
  usePrometheusRange,
  scalarValue,
  groupByLabel,
} from '../../hooks/usePrometheus';
import { SparklineChart } from '../../components/charts/SparklineChart';
import { ThroughputChart } from './components/ThroughputChart';
import { LatencyHistogram } from './components/LatencyHistogram';
import { ErrorBreakdown } from './components/ErrorBreakdown';
import { TopRoutes } from './components/TopRoutes';
import { TrafficHeatmap } from './components/TrafficHeatmap';
import { LiveTraces } from './components/LiveTraces';
import type { TraceEntry } from './components/LiveTraces';
import { AutoRefreshToggle } from './components/AutoRefreshToggle';
import { buildLiveCallsQueries, METRICS_TRACES_SPLIT_MESSAGE, ROUTE_LABEL } from './metrics';

const DEFAULT_REFRESH = 15;

const MODE_CONFIG: Record<string, { label: string; color: string; colorClass: string }> = {
  'edge-mcp': { label: 'Gateway', color: '#3274D9', colorClass: 'text-blue-600' },
  sidecar: { label: 'Link', color: '#56A64B', colorClass: 'text-green-600' },
  connect: { label: 'Connect', color: '#FF9830', colorClass: 'text-orange-600' },
  proxy: { label: 'Proxy', color: '#8B5CF6', colorClass: 'text-purple-600' },
  shadow: { label: 'Shadow', color: '#6B7280', colorClass: 'text-neutral-500' },
};

const LATENCY_BUCKETS = [
  { label: '0-1ms', le: 0.001 },
  { label: '1-2ms', le: 0.002 },
  { label: '2-5ms', le: 0.005 },
  { label: '5-10ms', le: 0.01 },
  { label: '10-20ms', le: 0.02 },
  { label: '20-50ms', le: 0.05 },
  { label: '50-100ms', le: 0.1 },
  { label: '100ms+', le: Infinity },
];

function latencyColorClass(ms: number | null): string | undefined {
  if (ms === null) return undefined;
  if (ms < 300) return 'text-green-600';
  if (ms < 500) return 'text-yellow-600';
  return 'text-red-600';
}

function seriesHasTraffic(data: { value: number }[] | null | undefined): boolean {
  return data?.some((point) => point.value > 0) ?? false;
}

// ─── Live Traces: fetch from monitoring API (authenticated) ───

import { apiService } from '../../services/api';
import type { MonitoringTransaction } from '../../services/api';

function mapTransaction(tx: MonitoringTransaction): TraceEntry {
  return {
    id: tx.id,
    route: tx.path || tx.api_name,
    method: tx.method,
    mode: tx.deployment_mode || 'edge-mcp',
    statusCode: tx.status_code,
    durationMs: tx.total_duration_ms,
    timestamp: tx.started_at,
    spans: (tx.spans || []).map((s) => ({
      name: s.name,
      service: s.service,
      startOffsetMs: s.start_offset_ms,
      durationMs: s.duration_ms,
      status: (s.status as 'success' | 'error' | 'timeout') || 'success',
    })),
  };
}

// Map dashboard timeRange labels to API minutes
const LATENCY_RANGE_MAP: Record<string, [number, number]> = {
  '0-1ms': [0, 1],
  '1-2ms': [1, 2],
  '2-5ms': [2, 5],
  '5-10ms': [5, 10],
  '10-20ms': [10, 20],
  '20-50ms': [20, 50],
  '50-100ms': [50, 100],
  '100ms+': [100, Infinity],
};

const TIME_RANGE_MINUTES: Record<string, string> = {
  '1h': '60',
  '6h': '360',
  '24h': '1440',
  '7d': '10080',
};

async function fetchTransactions(
  limit: number = 20,
  serviceType?: string,
  timeRange?: string,
  statusFilter?: string,
  routeFilter?: string
): Promise<TraceEntry[]> {
  try {
    const rangeMinutes = timeRange ? TIME_RANGE_MINUTES[timeRange] || '60' : undefined;
    const statusCodeNum = statusFilter ? parseInt(statusFilter, 10) : undefined;
    const data = await apiService.getTransactions(
      limit,
      undefined,
      rangeMinutes,
      serviceType || undefined,
      statusCodeNum && !isNaN(statusCodeNum) ? statusCodeNum : undefined,
      routeFilter || undefined
    );
    const transactions = data.transactions || [];
    return transactions.map(mapTransaction);
  } catch {
    return [];
  }
}

// ─── Dashboard Component ───

export function CallFlowDashboard() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [timeRange, setTimeRange] = useState<TimeRange>('1h');
  const [autoRefresh, setAutoRefresh] = useState(DEFAULT_REFRESH);
  const [traces, setTraces] = useState<TraceEntry[]>([]);
  const [serviceType, setServiceType] = useState<string>(searchParams.get('serviceType') || '');
  const [routeFilter, setRouteFilter] = useState<string>(searchParams.get('route') || '');
  const [statusFilter, setStatusFilter] = useState<string>(searchParams.get('status') || '');
  const [latencyFilter, setLatencyFilter] = useState<string>(searchParams.get('latency') || '');
  const tracesRef = useRef(false);

  const refreshMs = autoRefresh > 0 ? autoRefresh * 1000 : 0;
  const rangeCfg = RANGE_CONFIG[timeRange];
  const queries = useMemo(() => buildLiveCallsQueries(timeRange), [timeRange]);

  // ─── KPI Queries ───

  const totalRequests = usePrometheusQuery(queries.totalRequests, refreshMs || 15_000);
  const totalErrors = usePrometheusQuery(queries.totalErrors, refreshMs || 15_000);
  const p50Latency = usePrometheusQuery(queries.p50Latency, refreshMs || 15_000);
  const p99Latency = usePrometheusQuery(queries.p99Latency, refreshMs || 15_000);
  const activeModes = usePrometheusQuery(queries.activeModes, refreshMs || 15_000);

  // ─── Throughput (per-mode range queries for stacked area) ───

  const edgeMcpTrend = usePrometheusRange(
    queries.edgeMcpTrend,
    rangeCfg.seconds,
    rangeCfg.step,
    refreshMs || 15_000
  );
  const sidecarTrend = usePrometheusRange(
    queries.sidecarTrend,
    rangeCfg.seconds,
    rangeCfg.step,
    refreshMs || 15_000
  );
  const connectTrend = usePrometheusRange(
    queries.connectTrend,
    rangeCfg.seconds,
    rangeCfg.step,
    refreshMs || 15_000
  );

  // ─── Latency histogram buckets ───

  const latencyBuckets = usePrometheusQuery(queries.latencyBuckets, refreshMs || 15_000);

  // ─── Error breakdown by status code ───

  const errorsByStatus = usePrometheusQuery(queries.errorsByStatus, refreshMs || 15_000);

  // ─── Top routes by P95 latency ───

  const topRoutesP95 = usePrometheusQuery(queries.topRoutesP95, refreshMs || 15_000);
  const topRoutesCalls = usePrometheusQuery(queries.topRoutesCalls, refreshMs || 15_000);

  // ─── Fallback queries (when service graph is not available) ───

  const fallbackRequests = usePrometheusQuery(
    `sum(increase(stoa_mcp_tools_calls_total[${timeRange}]))`,
    refreshMs || 15_000
  );
  const fallbackLatency = usePrometheusQuery(
    `sum(rate(stoa_mcp_tool_duration_seconds_sum[5m])) / sum(rate(stoa_mcp_tool_duration_seconds_count[5m]))`,
    refreshMs || 15_000
  );
  const fallbackErrors = usePrometheusQuery(
    `sum(increase(stoa_mcp_tools_calls_total{status="error"}[${timeRange}]))`,
    refreshMs || 15_000
  );
  const fallbackTrend = usePrometheusRange(
    `sum(rate(stoa_mcp_tools_calls_total[5m]))`,
    rangeCfg.seconds,
    rangeCfg.step,
    refreshMs || 15_000
  );

  // ─── Fetch live traces ───

  useEffect(() => {
    tracesRef.current = true;
    fetchTransactions(50, serviceType, timeRange, statusFilter, routeFilter).then(setTraces);
  }, [serviceType, timeRange, statusFilter, routeFilter]);

  useEffect(() => {
    if (!refreshMs) return;
    const interval = setInterval(() => {
      fetchTransactions(50, serviceType, timeRange, statusFilter, routeFilter).then(setTraces);
    }, refreshMs);
    return () => clearInterval(interval);
  }, [refreshMs, serviceType, timeRange, statusFilter, routeFilter]);

  // ─── Derived values ───

  const useServiceGraph = !totalRequests.error && scalarValue(totalRequests.data) !== null;
  const totalRequestsVal = useServiceGraph
    ? scalarValue(totalRequests.data)
    : scalarValue(fallbackRequests.data);
  const totalErrorsVal = useServiceGraph
    ? scalarValue(totalErrors.data)
    : scalarValue(fallbackErrors.data);
  const p50Val = scalarValue(p50Latency.data);
  const p99Val = scalarValue(p99Latency.data);
  const p50Ms = p50Val !== null ? p50Val * 1000 : null;
  const p99Ms = p99Val !== null ? p99Val * 1000 : null;

  // Fallback to avg latency if percentile histograms unavailable
  const fallbackLatencyVal = scalarValue(fallbackLatency.data);
  const displayP50 = p50Ms ?? (fallbackLatencyVal !== null ? fallbackLatencyVal * 1000 : null);
  const displayP99 = p99Ms ?? displayP50;

  const activeModesVal = scalarValue(activeModes.data);

  const errorRateVal =
    totalRequestsVal && totalErrorsVal && totalRequestsVal > 0
      ? (totalErrorsVal / totalRequestsVal) * 100
      : 0;
  const successRateVal = totalRequestsVal && totalRequestsVal > 0 ? 100 - errorRateVal : null;

  const prometheusAvailable = !totalRequests.error && !fallbackRequests.error;
  const loading = totalRequests.loading && fallbackRequests.loading;
  const modeBreakdownLoading = edgeMcpTrend.loading || sidecarTrend.loading || connectTrend.loading;
  const modeBreakdownHasTraffic =
    seriesHasTraffic(edgeMcpTrend.data) ||
    seriesHasTraffic(sidecarTrend.data) ||
    seriesHasTraffic(connectTrend.data);
  const showScopeMismatch =
    useServiceGraph &&
    !modeBreakdownLoading &&
    (totalRequestsVal ?? 0) > 0 &&
    !modeBreakdownHasTraffic;

  // ─── Client-side trace filters (from chart clicks) ───

  const filteredTraces = useMemo(() => {
    let result = traces;
    if (routeFilter) {
      result = result.filter((t) => t.route.includes(routeFilter));
    }
    // statusFilter is handled server-side via status_code param
    if (latencyFilter && LATENCY_RANGE_MAP[latencyFilter]) {
      const [min, max] = LATENCY_RANGE_MAP[latencyFilter];
      result = result.filter((t) => t.durationMs >= min && t.durationMs < max);
    }
    return result;
  }, [traces, routeFilter, latencyFilter]);

  const activeFilterCount = [serviceType, routeFilter, statusFilter, latencyFilter].filter(
    Boolean
  ).length;

  // ─── Parse latency histogram ───

  const histogramBuckets = useMemo(() => {
    if (!latencyBuckets.data) return LATENCY_BUCKETS.map((b) => ({ label: b.label, count: 0 }));
    const bucketMap = groupByLabel(latencyBuckets.data, 'le');
    const sorted = Object.entries(bucketMap)
      .map(([le, cumulative]) => ({ le: le === '+Inf' ? Infinity : parseFloat(le), cumulative }))
      .sort((a, b) => a.le - b.le);

    return LATENCY_BUCKETS.map((bucket, i) => {
      const cumThis = sorted.find((s) => s.le === bucket.le)?.cumulative || 0;
      const prevLe = i > 0 ? LATENCY_BUCKETS[i - 1].le : 0;
      const cumPrev = sorted.find((s) => s.le === prevLe)?.cumulative || 0;
      return { label: bucket.label, count: Math.max(0, Math.round(cumThis - cumPrev)) };
    });
  }, [latencyBuckets.data]);

  // ─── Parse error breakdown ───

  const errorEntries = useMemo(() => {
    const map = groupByLabel(errorsByStatus.data, 'status');
    return Object.entries(map)
      .map(([code, count]) => ({ code, count: Math.round(count) }))
      .filter((e) => e.count > 0)
      .sort((a, b) => b.count - a.count);
  }, [errorsByStatus.data]);

  // ─── Parse top routes ───

  const topRoutes = useMemo(() => {
    const p95Map = groupByLabel(topRoutesP95.data, ROUTE_LABEL);
    const callsMap = groupByLabel(topRoutesCalls.data, ROUTE_LABEL);
    return Object.entries(p95Map)
      .map(([route, p95Secs]) => ({
        route,
        p95Ms: p95Secs * 1000,
        calls: Math.round(callsMap[route] || 0),
      }))
      .filter((r) => r.calls > 0)
      .sort((a, b) => b.p95Ms - a.p95Ms)
      .slice(0, 8);
  }, [topRoutesP95.data, topRoutesCalls.data]);

  // ─── Parse traffic heatmap ───
  // TODO: implement real heatmap with Prometheus query_range grouped by http_route (separate ticket).
  const heatmapCells = useMemo(() => {
    return { cells: [], routes: [] };
  }, []);

  // ─── Throughput series for stacked area ───

  const throughputSeries = useMemo(
    () => [
      { label: 'Gateway', color: MODE_CONFIG['edge-mcp'].color, data: edgeMcpTrend.data },
      { label: 'Link', color: MODE_CONFIG.sidecar.color, data: sidecarTrend.data },
      { label: 'Connect', color: MODE_CONFIG.connect.color, data: connectTrend.data },
    ],
    [edgeMcpTrend.data, sidecarTrend.data, connectTrend.data]
  );

  // If no service graph, use fallback single series
  const displayThroughput = useMemo(() => {
    if (useServiceGraph) return throughputSeries;
    return [{ label: 'All Traffic', color: '#3274D9', data: fallbackTrend.data }];
  }, [useServiceGraph, throughputSeries, fallbackTrend.data]);

  // ─── Sparkline data for KPI cards ───

  const requestsTrend = usePrometheusRange(
    useServiceGraph ? queries.requestsTrend : `sum(rate(stoa_mcp_tools_calls_total[5m]))`,
    rangeCfg.seconds,
    rangeCfg.step,
    refreshMs || 15_000
  );

  // ─── Handlers ───

  const handleRefresh = useCallback(() => {
    totalRequests.refetch();
    totalErrors.refetch();
    p50Latency.refetch();
    p99Latency.refetch();
    activeModes.refetch();
    edgeMcpTrend.refetch();
    sidecarTrend.refetch();
    connectTrend.refetch();
    latencyBuckets.refetch();
    errorsByStatus.refetch();
    topRoutesP95.refetch();
    topRoutesCalls.refetch();
    fallbackRequests.refetch();
    fallbackLatency.refetch();
    fallbackErrors.refetch();
    fallbackTrend.refetch();
    requestsTrend.refetch();
    fetchTransactions(50, serviceType, timeRange, statusFilter, routeFilter).then(setTraces);
  }, [
    totalRequests,
    totalErrors,
    p50Latency,
    p99Latency,
    activeModes,
    edgeMcpTrend,
    sidecarTrend,
    connectTrend,
    latencyBuckets,
    errorsByStatus,
    topRoutesP95,
    topRoutesCalls,
    fallbackRequests,
    fallbackLatency,
    fallbackErrors,
    fallbackTrend,
    requestsTrend,
    serviceType,
    statusFilter,
    routeFilter,
    timeRange,
  ]);

  const liveTracesEmptyMessage =
    activeFilterCount > 0
      ? 'No trace spans found for this filter — metrics (Prometheus) and traces (OpenSearch) may not cover the same time window'
      : (totalRequestsVal ?? 0) > 0
        ? METRICS_TRACES_SPLIT_MESSAGE
        : 'No traces yet — ensure gateway routes are configured and the observability pipeline (Alloy, Tempo, OpenSearch) is active';

  return (
    <div className="space-y-6">
      {/* ─── Header ─── */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Live Calls</h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            Recent calls, trace IDs, latency, and request flow across Gateway, Link, and Connect
          </p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <select
            value={serviceType}
            onChange={(e) => setServiceType(e.target.value)}
            className="border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300 px-3 py-2 rounded-lg text-sm"
          >
            <option value="">All Services</option>
            <option value="gateway">STOA Gateway</option>
            <option value="link">STOA Link</option>
            <option value="connect">STOA Connect</option>
          </select>
          <AutoRefreshToggle value={autoRefresh} onChange={setAutoRefresh} />
          <TimeRangeSelector
            value={timeRange}
            onChange={setTimeRange}
            ranges={['1h', '6h', '24h', '7d']}
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

      <SubNav tabs={observabilityTabs} />

      {/* ─── Prometheus status banners ─── */}
      {!prometheusAvailable && (
        <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 px-4 py-3 rounded-lg flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-yellow-600" />
          <span className="text-sm text-yellow-700 dark:text-yellow-400">
            Prometheus is not reachable. Live Calls request metrics require Prometheus.
          </span>
        </div>
      )}

      {prometheusAvailable && !useServiceGraph && (
        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 px-4 py-3 rounded-lg flex items-center gap-2">
          <Network className="h-4 w-4 text-blue-600" />
          <span className="text-sm text-blue-700 dark:text-blue-400">
            Gateway HTTP request metrics are not available — showing gateway tool call metrics as
            fallback. Request metrics populate when gateway Prometheus scraping is active.
          </span>
        </div>
      )}

      {showScopeMismatch && (
        <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 px-4 py-3 rounded-lg flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-yellow-600" />
          <span className="text-sm text-yellow-700 dark:text-yellow-400">
            Total requests are available, but no Gateway/Link/Connect breakdown traffic was found
            for the selected window. Some scraped series may not match the expected job scope.
          </span>
        </div>
      )}

      {loading ? (
        <div className="space-y-6">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            {[1, 2, 3, 4, 5].map((i) => (
              <CardSkeleton key={i} className="h-28" />
            ))}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <CardSkeleton className="h-[300px]" />
            <CardSkeleton className="h-[300px]" />
          </div>
        </div>
      ) : (
        <>
          {/* ─── 5 KPI Cards ─── */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <StatCard
              label={`Total Requests (${timeRange})`}
              value={
                totalRequestsVal !== null
                  ? totalRequestsVal >= 1000
                    ? `${(totalRequestsVal / 1000).toFixed(1)}K`
                    : Math.round(totalRequestsVal).toString()
                  : '--'
              }
              icon={Zap}
              colorClass="text-blue-600"
              subtitle={`Over ${rangeCfg.label}`}
              sparkline={
                requestsTrend.data && requestsTrend.data.length >= 2 ? (
                  <SparklineChart
                    data={requestsTrend.data}
                    color="#3B82F6"
                    height={32}
                    width={120}
                    showArea
                  />
                ) : undefined
              }
              trend={
                requestsTrend.data && requestsTrend.data.length >= 2
                  ? requestsTrend.data[requestsTrend.data.length - 1].value >
                    requestsTrend.data[0].value
                    ? 'up'
                    : requestsTrend.data[requestsTrend.data.length - 1].value <
                        requestsTrend.data[0].value
                      ? 'down'
                      : 'stable'
                  : undefined
              }
            />
            <StatCard
              label="P50 Latency (5m)"
              value={
                displayP50 !== null
                  ? displayP50 < 1
                    ? Math.round(displayP50 * 1000).toString()
                    : Math.round(displayP50).toString()
                  : '--'
              }
              unit={displayP50 !== null && displayP50 < 1 ? 'µs' : 'ms'}
              icon={Gauge}
              colorClass={latencyColorClass(displayP50)}
              subtitle="Median response time"
            />
            <StatCard
              label="P99 Latency (5m)"
              value={
                displayP99 !== null
                  ? displayP99 < 1
                    ? Math.round(displayP99 * 1000).toString()
                    : Math.round(displayP99).toString()
                  : '--'
              }
              unit={displayP99 !== null && displayP99 < 1 ? 'µs' : 'ms'}
              icon={Timer}
              colorClass={latencyColorClass(displayP99)}
              subtitle="Tail latency"
            />
            <StatCard
              label="Success Rate"
              value={successRateVal !== null ? `${successRateVal.toFixed(2)}%` : '--'}
              icon={CheckCircle}
              colorClass={
                successRateVal === null
                  ? 'text-neutral-400'
                  : successRateVal >= 99
                    ? 'text-green-600'
                    : successRateVal >= 95
                      ? 'text-yellow-600'
                      : 'text-red-600'
              }
              subtitle={
                totalRequestsVal && totalRequestsVal > 0
                  ? `${Math.round(totalErrorsVal || 0)} server errors (5xx)`
                  : 'No requests in this period'
              }
            />
            <StatCard
              label="Active Modes"
              value={activeModesVal !== null ? Math.round(activeModesVal).toString() : '--'}
              icon={Network}
              colorClass="text-blue-600"
              subtitle="Gateway / Link / Connect jobs reporting traffic"
            />
          </div>

          {/* ─── Charts Row 1: Throughput + Latency Distribution ─── */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ChartCard title="Throughput by Deployment Mode">
              <ThroughputChart
                series={displayThroughput}
                timeRange={timeRange}
                activeLabel={
                  (
                    { gateway: 'Gateway', link: 'Link', connect: 'Connect' } as Record<
                      string,
                      string
                    >
                  )[serviceType] || ''
                }
                onLegendClick={(label) => {
                  const map: Record<string, string> = {
                    Gateway: 'gateway',
                    Link: 'link',
                    Connect: 'connect',
                  };
                  setServiceType(map[label] || '');
                }}
              />
            </ChartCard>
            <ChartCard title="Latency Distribution">
              <LatencyHistogram
                buckets={histogramBuckets}
                activeLabel={latencyFilter}
                onBucketClick={setLatencyFilter}
              />
            </ChartCard>
          </div>

          {/* ─── Charts Row 2: Error Breakdown + Top Routes ─── */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ChartCard title="Error Breakdown">
              <ErrorBreakdown
                errors={errorEntries}
                activeCode={statusFilter}
                onSliceClick={setStatusFilter}
              />
            </ChartCard>
            <ChartCard title="Top Routes by Latency (P95)">
              <TopRoutes
                routes={topRoutes}
                activeRoute={routeFilter}
                onRouteClick={setRouteFilter}
              />
            </ChartCard>
          </div>

          {/* ─── Traffic Heatmap ─── */}
          <ChartCard
            title="Traffic Heatmap (24h × Routes)"
            icon={<Activity className="h-5 w-5 text-neutral-400" />}
          >
            <TrafficHeatmap
              cells={heatmapCells.cells}
              routes={heatmapCells.routes}
              activeRoute={routeFilter}
              onCellClick={setRouteFilter}
            />
          </ChartCard>

          {/* ─── Live Traces ─── */}
          <ChartCard
            title="Live Traces"
            trailing={
              <div className="flex items-center gap-2">
                {activeFilterCount > 0 && (
                  <button
                    onClick={() => {
                      setServiceType('');
                      setRouteFilter('');
                      setStatusFilter('');
                      setLatencyFilter('');
                    }}
                    className="text-[10px] px-2 py-0.5 bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 rounded-full font-medium hover:bg-blue-200 dark:hover:bg-blue-900/50 transition-colors"
                  >
                    {activeFilterCount} filter{activeFilterCount > 1 ? 's' : ''} — clear
                  </button>
                )}
                <span className="text-xs text-neutral-400 dark:text-neutral-500">
                  {filteredTraces.length}/{traces.length} traces
                </span>
              </div>
            }
          >
            <LiveTraces
              traces={filteredTraces}
              onSelectTrace={(id) => navigate(`/observability/live-calls/trace/${id}`)}
              emptyMessage={liveTracesEmptyMessage}
            />
          </ChartCard>

          {/* ─── Per-Mode Sparklines (preserved from v1) ─── */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {[
              { key: 'edge-mcp', trend: edgeMcpTrend },
              { key: 'sidecar', trend: sidecarTrend },
              { key: 'connect', trend: connectTrend },
            ].map(({ key, trend }) => {
              const cfg = MODE_CONFIG[key];
              const trendData = useServiceGraph
                ? trend.data
                : key === 'edge-mcp'
                  ? fallbackTrend.data
                  : null;
              return (
                <div key={key} className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <span
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: cfg.color }}
                      />
                      <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300">
                        {cfg.label}
                      </h2>
                    </div>
                    {trendData && trendData.length > 1 && <TrendIndicator data={trendData} />}
                  </div>
                  {trendData && trendData.length >= 2 ? (
                    <SparklineChart
                      data={trendData}
                      color={cfg.color}
                      height={100}
                      width={400}
                      showArea
                      className="w-full"
                    />
                  ) : (
                    <div className="h-[100px] flex items-center justify-center text-sm text-neutral-400 dark:text-neutral-500">
                      {trend.error
                        ? 'Unavailable'
                        : key === 'edge-mcp'
                          ? 'No traffic'
                          : 'Awaiting traffic'}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

export default CallFlowDashboard;
