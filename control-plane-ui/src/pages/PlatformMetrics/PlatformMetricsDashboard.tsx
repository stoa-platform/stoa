import { useState, useEffect, useCallback } from 'react';
import {
  RefreshCw,
  Activity,
  AlertTriangle,
  Clock,
  CheckCircle,
  Server,
  ExternalLink,
  Gauge,
  Shield,
  Zap,
  Radio,
  Search as SearchIcon,
  Cpu,
  HeartPulse,
  Award,
  CircuitBoard,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { apiService } from '../../services/api';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import { TimeRangeSelector, RANGE_CONFIG } from '@stoa/shared/components/TimeRangeSelector';
import { TrendIndicator } from '@stoa/shared/components/TrendIndicator';
import type { TimeRange } from '@stoa/shared/components/TimeRangeSelector';
import { usePrometheusRange } from '../../hooks/usePrometheus';
import { SparklineChart } from '../../components/charts/SparklineChart';
import { MetricCard } from '../../components/metrics/MetricCard';
import { MetricTimeseries } from '../../components/metrics/MetricTimeseries';
import { config } from '../../config';
import { observabilityPath } from '../../utils/navigation';
import type { TopAPI } from '../../services/api';
import { SubNav } from '../../components/SubNav';
import { observabilityTabs } from '../../components/subNavGroups';

const AUTO_REFRESH_INTERVAL = 15_000;
const dashboards = config.services.grafana.dashboards;

// Format helpers
const fmtPercent = (v: number | null) => (v === null ? '--' : `${v.toFixed(2)}%`);
const fmtMs = (v: number | null) => (v === null ? '--' : v < 1 ? '<1 ms' : `${v.toFixed(0)} ms`);
const fmtBudget = (v: number | null) =>
  v === null ? '--' : v > 100 ? '100%' : v < 0 ? '0%' : `${v.toFixed(1)}%`;
const fmtCount = (v: number | null) => (v === null ? '--' : v.toFixed(0));
const fmtRequests = (v: number | null) => {
  if (v === null) return '--';
  if (v >= 1000) return `${(v / 1000).toFixed(1)}K`;
  return Math.round(v).toString();
};
const fmtScore = (v: number | null) => (v === null ? '--' : `${v.toFixed(1)}/100`);
const fmtCujStatus = (v: number | null) => (v === null ? '--' : v >= 1 ? 'OK' : 'FAIL');

// PromQL queries
const QUERIES = {
  // KPI Row
  totalRequests: (range: string) => `sum(increase(stoa_http_requests_total[${range}]))`,
  errorRate:
    'sum(rate(stoa_http_requests_total{status=~"5.."}[5m])) / sum(rate(stoa_http_requests_total[5m])) * 100',
  latencyP95:
    'histogram_quantile(0.95, sum(rate(stoa_http_request_duration_seconds_bucket[5m])) by (le)) * 1000',
  servicesUp: 'count(up == 1)',
  // SLO Row
  availability:
    '(1 - (sum(increase(stoa_http_requests_total{status=~"5.."}[1h])) + sum(increase(stoa_control_plane_http_requests_total{status_code=~"5.."}[1h])) or vector(0)) / (sum(increase(stoa_http_requests_total[1h])) + sum(increase(stoa_control_plane_http_requests_total[1h])) or vector(1))) * 100',
  errorBudget:
    '(1 - ((sum(increase(stoa_http_requests_total{status=~"5.."}[24h])) or vector(0)) / (sum(increase(stoa_http_requests_total[24h])) or vector(1))) / 0.001) * 100',
  // MCP & AI Activity
  mcpSessionsActive: 'sum(stoa_mcp_sessions_active) or vector(0)',
  mcpToolCallsPerHour: 'sum(increase(stoa_mcp_tools_calls_total[1h])) or vector(0)',
  mcpToolP95:
    'histogram_quantile(0.95, sum(rate(stoa_mcp_tool_duration_seconds_bucket[5m])) by (le)) * 1000 or vector(0)',
  discoveryFailures: 'sum(increase(stoa_tool_discovery_failures_total[1h])) or vector(0)',
  mcpToolCallsTimeseries: 'sum(increase(stoa_mcp_tools_calls_total[5m]))',
  // Gateway Adapters
  adapterOpsPerHour: 'sum(increase(stoa_adapter_operations_total[1h])) or vector(0)',
  adapterErrorsPerHour:
    'sum(increase(stoa_adapter_operations_total{status="error"}[1h])) or vector(0)',
  adapterHealthP95:
    'histogram_quantile(0.95, sum(rate(stoa_adapter_health_check_latency_seconds_bucket[5m])) by (le)) * 1000 or vector(0)',
  circuitBreakersOpen: 'sum(stoa_circuit_breaker_state == 1) or vector(0)',
  // Arena Benchmark
  arenaScore: 'gateway_arena_score{gateway="stoa-k8s"} or vector(0)',
  enterpriseScore: 'gateway_arena_enterprise_score{gateway="stoa-k8s"} or vector(0)',
  arenaAvailability: 'gateway_arena_availability{gateway="stoa-k8s"} or vector(0)',
  // Platform CUJs
  cujOverallScore: 'platform_verify_overall_score or vector(0)',
  cujHealthChain: 'platform_verify_cuj_status{cuj="health_chain"} or vector(0)',
  cujAuthFlow: 'platform_verify_cuj_status{cuj="auth_flow"} or vector(0)',
  cujMcpDiscovery: 'platform_verify_cuj_status{cuj="mcp_discovery"} or vector(0)',
};

function CujBadge({ query, label }: { query: string; label: string }) {
  return (
    <MetricCard
      label={label}
      query={query}
      format={fmtCujStatus}
      color="#10b981"
      icon={HeartPulse}
    />
  );
}

export function PlatformMetricsDashboard() {
  const navigate = useNavigate();
  const { isReady } = useAuth();
  const [timeRange, setTimeRange] = useState<TimeRange>('1h');
  const [topApis, setTopApis] = useState<TopAPI[]>([]);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  const rangeCfg = RANGE_CONFIG[timeRange];

  // Sparklines
  const requestRateSeries = usePrometheusRange(
    'sum(rate(stoa_http_requests_total[5m]))',
    rangeCfg.seconds,
    rangeCfg.step,
    AUTO_REFRESH_INTERVAL
  );
  const errorRateSeries = usePrometheusRange(
    'sum(rate(stoa_http_requests_total{status=~"5.."}[5m])) / sum(rate(stoa_http_requests_total[5m]))',
    rangeCfg.seconds,
    rangeCfg.step,
    AUTO_REFRESH_INTERVAL
  );

  // CP API data
  const loadApiData = useCallback(async () => {
    try {
      const apis = await apiService.getTopAPIs(5).catch(() => []);
      setTopApis(apis);
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
    requestRateSeries.refetch();
    errorRateSeries.refetch();
    loadApiData();
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">
            Platform Observability
          </h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            Real-time platform metrics, MCP activity, arena benchmarks
          </p>
        </div>
        <div className="flex items-center gap-3">
          <TimeRangeSelector value={timeRange} onChange={setTimeRange} />
          <span className="text-xs text-neutral-400 dark:text-neutral-500">
            {lastRefresh.toLocaleTimeString('fr-FR')}
          </span>
          <button
            onClick={handleRefresh}
            className="flex items-center gap-2 border border-neutral-300 dark:border-neutral-600 text-neutral-700 dark:text-neutral-300 px-3 py-2 rounded-lg text-sm hover:bg-neutral-50 dark:hover:bg-neutral-700 disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${requestRateSeries.loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      <SubNav tabs={observabilityTabs} />

      {/* Cross-links */}
      <div className="flex items-center gap-4 text-sm">
        <button
          onClick={() => navigate('/monitoring')}
          className="text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
        >
          Transaction Tracing <ExternalLink className="h-3 w-3" />
        </button>
        <button
          onClick={() => navigate('/operations')}
          className="text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
        >
          SLO & Deployments <ExternalLink className="h-3 w-3" />
        </button>
      </div>

      {loading ? (
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
          {/* KPI Row — Core Platform Metrics */}
          <section>
            <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase mb-3">
              Platform KPIs
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <MetricCard
                label={`Total Requests (${timeRange})`}
                query={QUERIES.totalRequests(timeRange)}
                format={fmtRequests}
                color="#3b82f6"
                icon={Activity}
              />
              <MetricCard
                label="Error Rate (5m)"
                query={QUERIES.errorRate}
                format={fmtPercent}
                color="#ef4444"
                icon={AlertTriangle}
              />
              <MetricCard
                label="P95 Latency (5m)"
                query={QUERIES.latencyP95}
                format={fmtMs}
                color="#f59e0b"
                icon={Clock}
              />
              <MetricCard
                label="Services Up"
                query={QUERIES.servicesUp}
                format={fmtCount}
                color="#10b981"
                icon={Server}
              />
            </div>
          </section>

          {/* SLO Row */}
          <section>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
                SLO Status
              </h2>
              <button
                onClick={() => navigate(observabilityPath(dashboards.slo))}
                className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
              >
                View SLO Dashboard <ExternalLink className="h-3 w-3" />
              </button>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <MetricCard
                label="Availability (1h)"
                query={QUERIES.availability}
                format={fmtPercent}
                color="#10b981"
                icon={CheckCircle}
              />
              <MetricCard
                label="Error Budget (24h)"
                query={QUERIES.errorBudget}
                format={fmtBudget}
                color="#8b5cf6"
                icon={Gauge}
              />
            </div>
          </section>

          {/* Sparkline Charts Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Request Rate */}
            <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
                    Request Rate
                  </h2>
                  <p className="text-xs text-neutral-400 dark:text-neutral-500">
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
                <div className="h-[120px] flex items-center justify-center text-sm text-neutral-400 dark:text-neutral-500">
                  {requestRateSeries.error ? 'Metrics unavailable' : 'Loading...'}
                </div>
              )}
            </div>

            {/* Error Rate Over Time */}
            <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
                    Error Rate
                  </h2>
                  <p className="text-xs text-neutral-400 dark:text-neutral-500">
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
                <div className="h-[120px] flex items-center justify-center text-sm text-neutral-400 dark:text-neutral-500">
                  {errorRateSeries.error ? 'Metrics unavailable' : 'Loading...'}
                </div>
              )}
            </div>
          </div>

          {/* MCP & AI Activity */}
          <section>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
                MCP & AI Activity
              </h2>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <MetricCard
                label="MCP Sessions Active"
                query={QUERIES.mcpSessionsActive}
                format={fmtCount}
                color="#8b5cf6"
                icon={Radio}
              />
              <MetricCard
                label="Tool Calls / h"
                query={QUERIES.mcpToolCallsPerHour}
                format={fmtCount}
                color="#3b82f6"
                icon={Zap}
              />
              <MetricCard
                label="Tool P95 Latency"
                query={QUERIES.mcpToolP95}
                format={fmtMs}
                color="#f59e0b"
                icon={Clock}
              />
              <MetricCard
                label="Discovery Failures / h"
                query={QUERIES.discoveryFailures}
                format={fmtCount}
                color="#ef4444"
                icon={SearchIcon}
              />
            </div>
            <div className="mt-4">
              <MetricTimeseries
                label="MCP Tool Calls over Time"
                query={QUERIES.mcpToolCallsTimeseries}
                duration={3600}
                step="5m"
                color="#8b5cf6"
              />
            </div>
          </section>

          {/* Gateway Adapters */}
          <section>
            <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase mb-3">
              Gateway Adapters
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <MetricCard
                label="Adapter Ops / h"
                query={QUERIES.adapterOpsPerHour}
                format={fmtCount}
                color="#3b82f6"
                icon={Cpu}
              />
              <MetricCard
                label="Adapter Errors / h"
                query={QUERIES.adapterErrorsPerHour}
                format={fmtCount}
                color="#ef4444"
                icon={AlertTriangle}
              />
              <MetricCard
                label="Health Check P95"
                query={QUERIES.adapterHealthP95}
                format={fmtMs}
                color="#f59e0b"
                icon={Clock}
              />
              <MetricCard
                label="Circuit Breakers Open"
                query={QUERIES.circuitBreakersOpen}
                format={fmtCount}
                color="#10b981"
                icon={CircuitBoard}
              />
            </div>
          </section>

          {/* Arena Benchmark */}
          <section>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
                Arena Benchmark
              </h2>
              <button
                onClick={() => navigate(observabilityPath(dashboards.gatewayArena))}
                className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
              >
                View in Grafana <ExternalLink className="h-3 w-3" />
              </button>
            </div>
            <div className="grid grid-cols-3 gap-4">
              <MetricCard
                label="STOA Score"
                query={QUERIES.arenaScore}
                format={fmtScore}
                color="#3b82f6"
                icon={Award}
              />
              <MetricCard
                label="Enterprise Score"
                query={QUERIES.enterpriseScore}
                format={fmtScore}
                color="#8b5cf6"
                icon={Shield}
              />
              <MetricCard
                label="Arena Availability"
                query={QUERIES.arenaAvailability}
                format={fmtPercent}
                color="#10b981"
                icon={CheckCircle}
              />
            </div>
          </section>

          {/* Platform Health (CUJs) */}
          <section>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
                Platform Health (CUJs)
              </h2>
              <button
                onClick={() => navigate(observabilityPath(dashboards.platformHealth))}
                className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
              >
                View in Grafana <ExternalLink className="h-3 w-3" />
              </button>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <MetricCard
                label="Overall CUJ Score"
                query={QUERIES.cujOverallScore}
                format={fmtPercent}
                color="#3b82f6"
                icon={Gauge}
              />
              <CujBadge query={QUERIES.cujHealthChain} label="Health Chain" />
              <CujBadge query={QUERIES.cujAuthFlow} label="Auth Flow" />
              <CujBadge query={QUERIES.cujMcpDiscovery} label="MCP Discovery" />
            </div>
          </section>

          {/* Top Endpoints */}
          <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
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
                      <span className="text-xs font-bold text-neutral-400 dark:text-neutral-500 w-5 text-right">
                        {i + 1}
                      </span>
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
              <p className="text-sm text-neutral-500 dark:text-neutral-400 text-center py-8">
                No API data available
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default PlatformMetricsDashboard;
