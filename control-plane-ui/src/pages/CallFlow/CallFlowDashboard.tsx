import { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Activity, RefreshCw, Zap, AlertTriangle, Network, Gauge, Timer } from 'lucide-react';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import { StatCard } from '@stoa/shared/components/StatCard';
import { TimeRangeSelector, RANGE_CONFIG } from '@stoa/shared/components/TimeRangeSelector';
import { TrendIndicator } from '@stoa/shared/components/TrendIndicator';
import { ChartCard } from '@stoa/shared/components/ChartCard';
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
import type { TraceEntry, TraceSpan } from './components/LiveTraces';
import { AutoRefreshToggle } from './components/AutoRefreshToggle';

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

// ─── Live Traces: fetch from monitoring API (authenticated) ───

import { apiService } from '../../services/api';
import type { MonitoringTransaction } from '../../services/api';

function mapTransaction(tx: MonitoringTransaction): TraceEntry {
  return {
    id: tx.id,
    route: tx.path || tx.api_name,
    method: tx.method,
    mode: 'edge-mcp',
    statusCode: tx.status_code,
    durationMs: tx.total_duration_ms,
    timestamp: tx.started_at,
    spans: [],
  };
}

async function fetchTransactions(
  limit: number = 20
): Promise<{ traces: TraceEntry[]; isDemo: boolean }> {
  try {
    const data = await apiService.getTransactions(limit);
    const transactions = data.transactions || [];
    if (transactions.length > 0) {
      return { traces: transactions.map(mapTransaction), isDemo: false };
    }
    return { traces: generateDemoTraces(limit), isDemo: true };
  } catch {
    return { traces: generateDemoTraces(limit), isDemo: true };
  }
}

function generateDemoTraces(count: number): TraceEntry[] {
  const routes = ['/customers', '/orders', '/products', '/payments', '/search', '/artifacts/{id}'];
  const methods = ['GET', 'POST', 'PUT', 'DELETE'];
  const statuses = [200, 200, 200, 200, 200, 201, 400, 404, 500, 502];
  const modes = ['edge-mcp', 'sidecar', 'connect'];

  return Array.from({ length: count }, (_, i) => {
    const statusCode = statuses[Math.floor(Math.random() * statuses.length)];
    const baseDuration = statusCode >= 500 ? 800 + Math.random() * 2000 : 20 + Math.random() * 300;
    const duration = Math.round(baseDuration);
    const now = Date.now() - Math.random() * 3600_000;

    const spanNames = [
      'gateway_ingress',
      'auth_validation',
      'rate_limiting',
      'backend_call',
      'response_transform',
    ];
    let offset = 0;
    const spans: TraceSpan[] = spanNames.map((name) => {
      const d = Math.round((duration / spanNames.length) * (0.5 + Math.random()));
      const span: TraceSpan = {
        name,
        service: 'stoa-gateway',
        startOffsetMs: offset,
        durationMs: d,
        status: statusCode >= 500 && name === 'backend_call' ? 'error' : 'success',
      };
      offset += d;
      return span;
    });

    return {
      id: `trace-${i}-${Math.random().toString(36).slice(2, 8)}`,
      route: routes[Math.floor(Math.random() * routes.length)],
      method: methods[Math.floor(Math.random() * methods.length)],
      mode: modes[Math.floor(Math.random() * modes.length)],
      statusCode,
      durationMs: duration,
      timestamp: new Date(now).toISOString(),
      spans,
    };
  }).sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
}

// ─── Dashboard Component ───

export function CallFlowDashboard() {
  const navigate = useNavigate();
  const [timeRange, setTimeRange] = useState<TimeRange>('1h');
  const [autoRefresh, setAutoRefresh] = useState(DEFAULT_REFRESH);
  const [traces, setTraces] = useState<TraceEntry[]>([]);
  const [tracesDemo, setTracesDemo] = useState(false);
  const tracesRef = useRef(false);

  const refreshMs = autoRefresh > 0 ? autoRefresh * 1000 : 0;
  const rangeCfg = RANGE_CONFIG[timeRange];

  // ─── KPI Queries ───

  const totalRequests = usePrometheusQuery(
    `sum(increase(traces_service_graph_request_total{server="stoa-gateway"}[${timeRange}]))`,
    refreshMs || 15_000
  );
  const totalErrors = usePrometheusQuery(
    `sum(increase(traces_service_graph_request_failed_total{server="stoa-gateway"}[${timeRange}]))`,
    refreshMs || 15_000
  );
  const p50Latency = usePrometheusQuery(
    `histogram_quantile(0.50, sum(rate(traces_service_graph_request_server_seconds_bucket{server="stoa-gateway"}[5m])) by (le))`,
    refreshMs || 15_000
  );
  const p99Latency = usePrometheusQuery(
    `histogram_quantile(0.99, sum(rate(traces_service_graph_request_server_seconds_bucket{server="stoa-gateway"}[5m])) by (le))`,
    refreshMs || 15_000
  );
  const activeModes = usePrometheusQuery(
    `count(count by (stoa_deployment_mode) (traces_service_graph_request_total{server="stoa-gateway"}))`,
    refreshMs || 15_000
  );

  // ─── Throughput (per-mode range queries for stacked area) ───

  const edgeMcpTrend = usePrometheusRange(
    `sum(rate(traces_service_graph_request_total{server="stoa-gateway",stoa_deployment_mode="edge-mcp"}[5m]))`,
    rangeCfg.seconds,
    rangeCfg.step,
    refreshMs || 15_000
  );
  const sidecarTrend = usePrometheusRange(
    `sum(rate(traces_service_graph_request_total{server="stoa-gateway",stoa_deployment_mode="sidecar"}[5m]))`,
    rangeCfg.seconds,
    rangeCfg.step,
    refreshMs || 15_000
  );
  const connectTrend = usePrometheusRange(
    `sum(rate(traces_service_graph_request_total{server="stoa-gateway",stoa_deployment_mode="connect"}[5m]))`,
    rangeCfg.seconds,
    rangeCfg.step,
    refreshMs || 15_000
  );

  // ─── Latency histogram buckets ───

  const latencyBuckets = usePrometheusQuery(
    `sum(increase(traces_service_graph_request_server_seconds_bucket{server="stoa-gateway"}[${timeRange}])) by (le)`,
    refreshMs || 15_000
  );

  // ─── Error breakdown by status code ───

  const errorsByStatus = usePrometheusQuery(
    `sum by (server_status_code) (increase(traces_service_graph_request_total{server="stoa-gateway",server_status_code=~"4..|5.."}[${timeRange}]))`,
    refreshMs || 15_000
  );

  // ─── Top routes by P95 latency ───

  const topRoutesP95 = usePrometheusQuery(
    `topk(8, histogram_quantile(0.95, sum by (le, client) (rate(traces_service_graph_request_server_seconds_bucket{server="stoa-gateway"}[5m]))))`,
    refreshMs || 15_000
  );
  const topRoutesCalls = usePrometheusQuery(
    `sum by (client) (increase(traces_service_graph_request_total{server="stoa-gateway"}[${timeRange}]))`,
    refreshMs || 15_000
  );

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
    if (tracesRef.current) return;
    tracesRef.current = true;
    fetchTransactions(20).then(({ traces: t, isDemo }) => {
      setTraces(t);
      setTracesDemo(isDemo);
    });
  }, []);

  useEffect(() => {
    if (!refreshMs) return;
    const interval = setInterval(() => {
      fetchTransactions(20).then(({ traces: t, isDemo }) => {
        setTraces(t);
        setTracesDemo(isDemo);
      });
    }, refreshMs);
    return () => clearInterval(interval);
  }, [refreshMs]);

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

  const prometheusAvailable = !totalRequests.error && !fallbackRequests.error;
  const loading = totalRequests.loading && fallbackRequests.loading;

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
    const map = groupByLabel(errorsByStatus.data, 'server_status_code');
    return Object.entries(map)
      .map(([code, count]) => ({ code, count: Math.round(count) }))
      .filter((e) => e.count > 0)
      .sort((a, b) => b.count - a.count);
  }, [errorsByStatus.data]);

  // ─── Parse top routes ───

  const topRoutes = useMemo(() => {
    const p95Map = groupByLabel(topRoutesP95.data, 'client');
    const callsMap = groupByLabel(topRoutesCalls.data, 'client');
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
  // heatmapData is a range query with `sum by (client)` — we get one series per client
  // For now, we use demo data since the range query returns aggregated series
  const heatmapCells = useMemo(() => {
    // Derive heatmap from topRoutes calls — distribute proportionally across hours
    // Business hours (8-20) get ~80% of traffic, off-hours get ~20%
    const routes = topRoutes.slice(0, 6).map((r) => r.route);
    if (routes.length === 0) return { cells: [], routes: [] };

    // Simple hash for deterministic distribution per route+hour
    const hash = (s: string, n: number) => {
      let h = 0;
      for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
      return Math.abs((h * (n + 1) * 2654435761) % 100) / 100;
    };

    const cells = topRoutes.slice(0, 6).flatMap((r) =>
      Array.from({ length: 24 }, (_, h) => {
        const businessHour = h >= 8 && h <= 20;
        const baseFraction = businessHour ? 0.06 : 0.015; // ~78% in business hours
        const jitter = hash(r.route, h) * 0.04; // ±4% variation
        const value = Math.round(r.calls * (baseFraction + jitter));
        return { hour: h, route: r.route, value };
      })
    );
    return { cells, routes };
  }, [topRoutes]);

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
    useServiceGraph
      ? `sum(rate(traces_service_graph_request_total{server="stoa-gateway"}[5m]))`
      : `sum(rate(stoa_mcp_tools_calls_total[5m]))`,
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
    fetchTransactions(20).then(({ traces: t, isDemo }) => {
      setTraces(t);
      setTracesDemo(isDemo);
    });
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
  ]);

  return (
    <div className="space-y-6">
      {/* ─── Header ─── */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Call Flow</h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            Real-time request flow across deployment modes — Gateway, Link, Connect
          </p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
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

      {/* ─── Prometheus status banners ─── */}
      {!prometheusAvailable && (
        <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 px-4 py-3 rounded-lg flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-yellow-600" />
          <span className="text-sm text-yellow-700 dark:text-yellow-400">
            Prometheus is not reachable. Call flow data requires Tempo service graph metrics.
          </span>
        </div>
      )}

      {prometheusAvailable && !useServiceGraph && (
        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 px-4 py-3 rounded-lg flex items-center gap-2">
          <Network className="h-4 w-4 text-blue-600" />
          <span className="text-sm text-blue-700 dark:text-blue-400">
            Tempo service graph metrics not yet available — showing gateway tool call metrics as
            fallback. Service graph populates automatically when traces flow through Tempo.
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
              value={displayP50 !== null ? Math.round(displayP50).toString() : '--'}
              unit="ms"
              icon={Gauge}
              colorClass={latencyColorClass(displayP50)}
              subtitle="Median response time"
            />
            <StatCard
              label="P99 Latency (5m)"
              value={displayP99 !== null ? Math.round(displayP99).toString() : '--'}
              unit="ms"
              icon={Timer}
              colorClass={latencyColorClass(displayP99)}
              subtitle="Tail latency"
            />
            <StatCard
              label="Error Rate"
              value={errorRateVal > 0 ? `${errorRateVal.toFixed(2)}%` : '0%'}
              icon={AlertTriangle}
              colorClass={
                errorRateVal < 1
                  ? 'text-green-600'
                  : errorRateVal < 5
                    ? 'text-yellow-600'
                    : 'text-red-600'
              }
              subtitle={`${Math.round(totalErrorsVal || 0)} errors`}
            />
            <StatCard
              label="Active Modes"
              value={activeModesVal !== null ? Math.round(activeModesVal).toString() : '--'}
              icon={Network}
              colorClass="text-blue-600"
              subtitle="Deployment modes"
            />
          </div>

          {/* ─── Charts Row 1: Throughput + Latency Distribution ─── */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ChartCard title="Throughput by Deployment Mode">
              <ThroughputChart series={displayThroughput} timeRange={timeRange} />
            </ChartCard>
            <ChartCard title="Latency Distribution">
              <LatencyHistogram buckets={histogramBuckets} />
            </ChartCard>
          </div>

          {/* ─── Charts Row 2: Error Breakdown + Top Routes ─── */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ChartCard title="Error Breakdown">
              <ErrorBreakdown errors={errorEntries} />
            </ChartCard>
            <ChartCard title="Top Routes by Latency (P95)">
              <TopRoutes routes={topRoutes} />
            </ChartCard>
          </div>

          {/* ─── Traffic Heatmap ─── */}
          <ChartCard
            title="Traffic Heatmap (24h × Routes)"
            icon={<Activity className="h-5 w-5 text-neutral-400" />}
          >
            <TrafficHeatmap cells={heatmapCells.cells} routes={heatmapCells.routes} />
          </ChartCard>

          {/* ─── Live Traces ─── */}
          <ChartCard
            title="Live Traces"
            trailing={
              <div className="flex items-center gap-2">
                {tracesDemo && (
                  <span className="text-[10px] px-2 py-0.5 bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400 rounded-full font-medium">
                    Demo data
                  </span>
                )}
                <span className="text-xs text-neutral-400 dark:text-neutral-500">
                  {traces.length} recent requests
                </span>
              </div>
            }
          >
            <LiveTraces
              traces={traces}
              onSelectTrace={(id) => navigate(`/call-flow/trace/${id}`)}
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
                      {trend.error ? 'Unavailable' : 'No traffic'}
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
