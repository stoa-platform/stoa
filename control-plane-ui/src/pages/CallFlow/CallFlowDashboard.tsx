import { useState } from 'react';
import { Activity, RefreshCw, Zap, AlertTriangle, Clock, Network } from 'lucide-react';
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

const AUTO_REFRESH_INTERVAL = 15_000;

const MODE_CONFIG: Record<string, { label: string; color: string; colorClass: string }> = {
  'edge-mcp': { label: 'Gateway', color: '#3274D9', colorClass: 'text-blue-600' },
  sidecar: { label: 'Link', color: '#56A64B', colorClass: 'text-green-600' },
  connect: { label: 'Connect', color: '#FF9830', colorClass: 'text-orange-600' },
  proxy: { label: 'Proxy', color: '#8B5CF6', colorClass: 'text-purple-600' },
  shadow: { label: 'Shadow', color: '#6B7280', colorClass: 'text-neutral-500' },
};

export function CallFlowDashboard() {
  const [timeRange, setTimeRange] = useState<TimeRange>('1h');
  const rangeCfg = RANGE_CONFIG[timeRange];

  const totalRequests = usePrometheusQuery(
    `sum(increase(traces_service_graph_request_total{client=~"stoa-.*"}[${timeRange}]))`,
    AUTO_REFRESH_INTERVAL
  );
  const totalErrors = usePrometheusQuery(
    `sum(increase(traces_service_graph_request_failed_total{client=~"stoa-.*"}[${timeRange}]))`,
    AUTO_REFRESH_INTERVAL
  );
  const avgLatency = usePrometheusQuery(
    `sum(rate(traces_service_graph_request_server_seconds_sum{client=~"stoa-.*"}[5m])) / sum(rate(traces_service_graph_request_server_seconds_count{client=~"stoa-.*"}[5m]))`,
    AUTO_REFRESH_INTERVAL
  );
  const activeModes = usePrometheusQuery(
    `count(count by (stoa_deployment_mode) (traces_service_graph_request_total{client=~"stoa-.*"}))`,
    AUTO_REFRESH_INTERVAL
  );

  const requestsByMode = usePrometheusQuery(
    `sum by (stoa_deployment_mode) (increase(traces_service_graph_request_total{client=~"stoa-.*"}[${timeRange}]))`,
    AUTO_REFRESH_INTERVAL
  );
  const errorsByMode = usePrometheusQuery(
    `sum by (stoa_deployment_mode) (increase(traces_service_graph_request_failed_total{client=~"stoa-.*"}[${timeRange}]))`,
    AUTO_REFRESH_INTERVAL
  );
  const latencyByMode = usePrometheusQuery(
    `sum by (stoa_deployment_mode) (rate(traces_service_graph_request_server_seconds_sum{client=~"stoa-.*"}[5m])) / sum by (stoa_deployment_mode) (rate(traces_service_graph_request_server_seconds_count{client=~"stoa-.*"}[5m]))`,
    AUTO_REFRESH_INTERVAL
  );

  const edgeMcpTrend = usePrometheusRange(
    `sum(rate(traces_service_graph_request_total{client=~"stoa-.*",stoa_deployment_mode="edge-mcp"}[5m]))`,
    rangeCfg.seconds,
    rangeCfg.step,
    AUTO_REFRESH_INTERVAL
  );
  const sidecarTrend = usePrometheusRange(
    `sum(rate(traces_service_graph_request_total{client=~"stoa-.*",stoa_deployment_mode="sidecar"}[5m]))`,
    rangeCfg.seconds,
    rangeCfg.step,
    AUTO_REFRESH_INTERVAL
  );
  const connectTrend = usePrometheusRange(
    `sum(rate(traces_service_graph_request_total{client=~"stoa-.*",stoa_deployment_mode="connect"}[5m]))`,
    rangeCfg.seconds,
    rangeCfg.step,
    AUTO_REFRESH_INTERVAL
  );

  const fallbackRequests = usePrometheusQuery(
    `sum(increase(stoa_mcp_tools_calls_total[${timeRange}]))`,
    AUTO_REFRESH_INTERVAL
  );
  const fallbackLatency = usePrometheusQuery(
    `sum(rate(stoa_mcp_tool_duration_seconds_sum[5m])) / sum(rate(stoa_mcp_tool_duration_seconds_count[5m]))`,
    AUTO_REFRESH_INTERVAL
  );
  const fallbackErrors = usePrometheusQuery(
    `sum(increase(stoa_mcp_tools_calls_total{status="error"}[${timeRange}]))`,
    AUTO_REFRESH_INTERVAL
  );
  const fallbackTrend = usePrometheusRange(
    `sum(rate(stoa_mcp_tools_calls_total[5m]))`,
    rangeCfg.seconds,
    rangeCfg.step,
    AUTO_REFRESH_INTERVAL
  );

  const useServiceGraph = !totalRequests.error && scalarValue(totalRequests.data) !== null;
  const totalRequestsVal = useServiceGraph
    ? scalarValue(totalRequests.data)
    : scalarValue(fallbackRequests.data);
  const totalErrorsVal = useServiceGraph
    ? scalarValue(totalErrors.data)
    : scalarValue(fallbackErrors.data);
  const avgLatencyVal = useServiceGraph
    ? scalarValue(avgLatency.data)
    : scalarValue(fallbackLatency.data);
  const activeModesVal = scalarValue(activeModes.data);

  const errorRateVal =
    totalRequestsVal && totalErrorsVal && totalRequestsVal > 0
      ? (totalErrorsVal / totalRequestsVal) * 100
      : 0;

  const requestsMap = groupByLabel(requestsByMode.data, 'stoa_deployment_mode');
  const errorsMap = groupByLabel(errorsByMode.data, 'stoa_deployment_mode');
  const latencyMap = groupByLabel(latencyByMode.data, 'stoa_deployment_mode');

  const modes = Object.entries(requestsMap)
    .map(([mode, calls]) => ({
      mode,
      calls,
      errors: errorsMap[mode] || 0,
      errorRate: calls > 0 ? ((errorsMap[mode] || 0) / calls) * 100 : 0,
      latencyMs: (latencyMap[mode] || 0) * 1000,
      config: MODE_CONFIG[mode] || {
        label: mode,
        color: '#6B7280',
        colorClass: 'text-neutral-500',
      },
    }))
    .sort((a, b) => b.calls - a.calls);

  const maxModeCalls = modes[0]?.calls || 1;
  const prometheusAvailable = !totalRequests.error && !fallbackRequests.error;
  const loading = totalRequests.loading && fallbackRequests.loading;

  const handleRefresh = () => {
    totalRequests.refetch();
    totalErrors.refetch();
    avgLatency.refetch();
    activeModes.refetch();
    requestsByMode.refetch();
    errorsByMode.refetch();
    latencyByMode.refetch();
    edgeMcpTrend.refetch();
    sidecarTrend.refetch();
    connectTrend.refetch();
    fallbackRequests.refetch();
    fallbackLatency.refetch();
    fallbackErrors.refetch();
    fallbackTrend.refetch();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Call Flow</h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            Request flow across deployment modes — Gateway, Link, Connect
          </p>
        </div>
        <div className="flex items-center gap-3">
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
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <CardSkeleton key={i} className="h-24" />
            ))}
          </div>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
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

          <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
                Traffic by Deployment Mode
              </h2>
              <Activity className="h-5 w-5 text-neutral-400" />
            </div>
            {modes.length > 0 ? (
              <div className="space-y-3">
                {modes.map((m) => (
                  <div key={m.mode} className="flex items-center gap-3">
                    <span
                      className="w-3 h-3 rounded-full flex-shrink-0"
                      style={{ backgroundColor: m.config.color }}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm font-medium text-neutral-900 dark:text-white">
                          {m.config.label}{' '}
                          <span className="text-xs text-neutral-400 dark:text-neutral-500 font-normal">
                            ({m.mode})
                          </span>
                        </span>
                        <div className="flex items-center gap-4 ml-2">
                          <span className="text-xs text-neutral-500 dark:text-neutral-400">
                            {m.calls >= 1000
                              ? `${(m.calls / 1000).toFixed(1)}K`
                              : Math.round(m.calls)}{' '}
                            req
                          </span>
                          {m.errors > 0 && (
                            <span className="text-xs text-red-500">
                              {m.errorRate.toFixed(1)}% err
                            </span>
                          )}
                          {m.latencyMs > 0 && (
                            <span className="text-xs text-amber-600 dark:text-amber-400">
                              {Math.round(m.latencyMs)}ms
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="w-full bg-neutral-100 dark:bg-neutral-700 rounded-full h-2">
                        <div
                          className="h-2 rounded-full transition-all"
                          style={{
                            width: `${(m.calls / maxModeCalls) * 100}%`,
                            backgroundColor: m.config.color,
                          }}
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState
                title="No call flow data"
                description="Traffic data will appear here once requests flow through STOA deployment modes."
                illustration={<Network className="h-12 w-12" />}
              />
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default CallFlowDashboard;
