import { memo, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useGatewayPlatformInfo } from '../hooks/useGatewayStatus';
import { useGatewayHealthSummary, useGatewayInstances } from '../hooks/usePlatformMetrics';
import { config } from '../config';
import { observabilityPath, logsPath } from '../utils/navigation';
import { SubNav } from '../components/SubNav';
import { gatewayTabs } from '../components/subNavGroups';
import { SloMetricTile } from '../components/gateway/SloMetricTile';
import type { GatewayInstance, GatewayInstanceStatus } from '../types';
import {
  Server,
  Activity,
  RefreshCw,
  XCircle,
  ExternalLink,
  GitCommit,
  BarChart3,
  Search,
  ShieldAlert,
  Info,
  Loader2,
  Gauge,
  Zap,
} from 'lucide-react';

const STATUS_COLORS: Record<GatewayInstanceStatus, { dot: string; badge: string; label: string }> =
  {
    online: {
      dot: 'bg-green-500',
      label: 'Online',
      badge: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
    },
    offline: {
      dot: 'bg-neutral-400',
      label: 'Offline',
      badge: 'bg-neutral-100 text-neutral-600 dark:bg-neutral-700 dark:text-neutral-400',
    },
    degraded: {
      dot: 'bg-yellow-500',
      label: 'Degraded',
      badge: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
    },
    maintenance: {
      dot: 'bg-blue-500',
      label: 'Maintenance',
      badge: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
    },
  };

function isStoa(type: string): boolean {
  return type.startsWith('stoa');
}

// PromQL queries for per-STOA-gateway SLO tiles. Each query is scoped to the
// gateway's `job` label so each card reflects its own fleet slice. Aligned
// with PlatformMetricsDashboard recording rules.
function sloQueriesForGateway(job: string) {
  const j = job.replace(/"/g, '\\"');
  return {
    availability: `(1 - (sum(rate(stoa_http_requests_total{job="${j}",status=~"5.."}[1h])) or vector(0)) / (sum(rate(stoa_http_requests_total{job="${j}"}[1h])) or vector(1))) * 100`,
    p95Latency: `histogram_quantile(0.95, sum(rate(stoa_http_request_duration_seconds_bucket{job="${j}"}[5m])) by (le)) * 1000`,
    errorRate: `sum(rate(stoa_http_requests_total{job="${j}",status=~"5.."}[5m])) / sum(rate(stoa_http_requests_total{job="${j}"}[5m])) * 100`,
  } as const;
}

/** Fleet summary header: totals + status breakdown + type breakdown. */
const FleetSummaryHeader = memo(function FleetSummaryHeader({
  total,
  online,
  offline,
  degraded,
  maintenance,
  stoaCount,
  thirdPartyCount,
}: {
  total: number;
  online: number;
  offline: number;
  degraded: number;
  maintenance: number;
  stoaCount: number;
  thirdPartyCount: number;
}) {
  return (
    <div
      data-testid="fleet-summary"
      className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 shadow-sm p-5"
    >
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <p className="text-xs uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
            Fleet
          </p>
          <p
            data-testid="fleet-total-count"
            className="text-3xl font-bold text-neutral-900 dark:text-white"
          >
            {total}
          </p>
          <p className="text-xs text-neutral-500 dark:text-neutral-400">Registered gateways</p>
        </div>
        <div className="flex gap-6 flex-wrap">
          <FleetCounter
            label="Online"
            value={online}
            testId="fleet-status-online-count"
            dotClass="bg-green-500"
          />
          <FleetCounter
            label="Offline"
            value={offline}
            testId="fleet-status-offline-count"
            dotClass="bg-neutral-400"
          />
          <FleetCounter
            label="Degraded"
            value={degraded}
            testId="fleet-status-degraded-count"
            dotClass="bg-yellow-500"
          />
          <FleetCounter
            label="Maintenance"
            value={maintenance}
            testId="fleet-status-maintenance-count"
            dotClass="bg-blue-500"
          />
        </div>
        <div className="flex gap-6">
          <FleetCounter label="STOA" value={stoaCount} testId="fleet-type-stoa-count" />
          <FleetCounter
            label="3rd-party"
            value={thirdPartyCount}
            testId="fleet-type-thirdparty-count"
          />
        </div>
      </div>
    </div>
  );
});

function FleetCounter({
  label,
  value,
  testId,
  dotClass,
}: {
  label: string;
  value: number;
  testId: string;
  dotClass?: string;
}) {
  return (
    <div className="text-center">
      <div className="flex items-center justify-center gap-1.5">
        {dotClass && <span className={`w-2 h-2 rounded-full ${dotClass}`} />}
        <p className="text-xs text-neutral-500 dark:text-neutral-400">{label}</p>
      </div>
      <p data-testid={testId} className="text-xl font-semibold text-neutral-900 dark:text-white">
        {value}
      </p>
    </div>
  );
}

/** Per-gateway card: name, type badge, status pill, SLO tiles (STOA) or "No metrics" (3rd-party). */
const GatewayCard = memo(function GatewayCard({ gw }: { gw: GatewayInstance }) {
  const sc = STATUS_COLORS[gw.status];
  const stoa = isStoa(gw.gateway_type);
  const queries = useMemo(() => sloQueriesForGateway(`stoa-gateway-${gw.name}`), [gw.name]);
  return (
    <div
      data-testid={`gateway-card-${gw.id}`}
      className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 shadow-sm p-5"
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3 min-w-0">
          <div
            className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${
              stoa ? 'bg-indigo-100 dark:bg-indigo-900/30' : 'bg-neutral-100 dark:bg-neutral-700'
            }`}
          >
            {stoa ? (
              <Zap className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
            ) : (
              <Server className="w-4 h-4 text-neutral-500 dark:text-neutral-400" />
            )}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-neutral-900 dark:text-white truncate">
              {gw.display_name}
            </p>
            <p className="text-xs text-neutral-500 dark:text-neutral-400 truncate">
              <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-neutral-100 dark:bg-neutral-700 font-mono text-[10px] mr-1">
                {gw.gateway_type}
              </span>
              · {gw.environment}
            </p>
          </div>
        </div>
        <span
          data-testid={`gateway-card-status-${gw.id}`}
          className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-medium rounded-full flex-shrink-0 ${sc.badge}`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${sc.dot}`} />
          {sc.label}
        </span>
      </div>
      {stoa ? (
        <div className="grid grid-cols-3 gap-3 pt-3 border-t border-neutral-100 dark:border-neutral-700">
          <SloMetricTile
            label="Availability"
            query={queries.availability}
            unit="%"
            digits={3}
            testId={`gateway-card-slo-availability-${gw.id}`}
          />
          <SloMetricTile
            label="p95 latency"
            query={queries.p95Latency}
            unit="ms"
            digits={0}
            testId={`gateway-card-slo-latency-${gw.id}`}
          />
          <SloMetricTile
            label="Error rate"
            query={queries.errorRate}
            unit="%"
            digits={2}
            testId={`gateway-card-slo-error-${gw.id}`}
          />
        </div>
      ) : (
        <div
          className="pt-3 border-t border-neutral-100 dark:border-neutral-700 flex items-center gap-2 text-xs text-neutral-500 dark:text-neutral-400"
          title="3rd-party gateway metrics require a separate exporter — follow-up ticket."
          data-testid={`gateway-card-no-metrics-${gw.id}`}
        >
          <Info className="w-3.5 h-3.5" />
          No metrics available
        </div>
      )}
    </div>
  );
});

// Sync status badge for ArgoCD card
function SyncBadge({ status }: { status: string }) {
  const cfg: Record<string, { bg: string; text: string; label: string }> = {
    Synced: {
      bg: 'bg-green-100 dark:bg-green-900/30',
      text: 'text-green-800 dark:text-green-400',
      label: 'Synced',
    },
    OutOfSync: {
      bg: 'bg-yellow-100 dark:bg-yellow-900/30',
      text: 'text-yellow-800 dark:text-yellow-400',
      label: 'Out of Sync',
    },
    Unknown: {
      bg: 'bg-neutral-100 dark:bg-neutral-700',
      text: 'text-neutral-800 dark:text-neutral-300',
      label: 'Unknown',
    },
  };
  const c = cfg[status] || cfg.Unknown;
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${c.bg} ${c.text}`}
    >
      {c.label}
    </span>
  );
}

function HealthBadge({ status }: { status: string }) {
  const cfg: Record<string, { bg: string; text: string }> = {
    Healthy: {
      bg: 'bg-green-100 dark:bg-green-900/30',
      text: 'text-green-800 dark:text-green-400',
    },
    Progressing: {
      bg: 'bg-blue-100 dark:bg-blue-900/30',
      text: 'text-blue-800 dark:text-blue-400',
    },
    Degraded: { bg: 'bg-red-100 dark:bg-red-900/30', text: 'text-red-800 dark:text-red-400' },
    Suspended: {
      bg: 'bg-neutral-100 dark:bg-neutral-700',
      text: 'text-neutral-800 dark:text-neutral-300',
    },
    Missing: { bg: 'bg-red-100 dark:bg-red-900/30', text: 'text-red-800 dark:text-red-400' },
  };
  const c = cfg[status] || {
    bg: 'bg-neutral-100 dark:bg-neutral-700',
    text: 'text-neutral-800 dark:text-neutral-300',
  };
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${c.bg} ${c.text}`}
    >
      {status}
    </span>
  );
}

export default function GatewayStatus() {
  const navigate = useNavigate();
  const platform = useGatewayPlatformInfo();
  const healthSummary = useGatewayHealthSummary();
  const gatewayInstances = useGatewayInstances();

  const gateways: GatewayInstance[] = useMemo(
    () => gatewayInstances.data?.items ?? [],
    [gatewayInstances.data]
  );
  const isLoading = healthSummary.isLoading || gatewayInstances.isLoading;
  const error = healthSummary.error || gatewayInstances.error;

  const refetch = () => {
    healthSummary.refetch();
    gatewayInstances.refetch();
  };

  // Compute aggregated stats
  const stats = useMemo(() => {
    const online = gateways.filter((g) => g.status === 'online').length;
    const offline = gateways.filter((g) => g.status === 'offline').length;
    const degraded = gateways.filter((g) => g.status === 'degraded').length;
    const maintenance = gateways.filter((g) => g.status === 'maintenance').length;
    const stoaCount = gateways.filter((g) => isStoa(g.gateway_type)).length;
    const thirdPartyCount = gateways.length - stoaCount;
    return {
      online,
      offline,
      degraded,
      maintenance,
      total: gateways.length,
      stoaCount,
      thirdPartyCount,
    };
  }, [gateways]);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-neutral-200 dark:bg-neutral-700 rounded w-1/4"></div>
          <div className="h-32 bg-neutral-200 dark:bg-neutral-700 rounded"></div>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="h-24 bg-neutral-200 dark:bg-neutral-700 rounded"></div>
            <div className="h-24 bg-neutral-200 dark:bg-neutral-700 rounded"></div>
            <div className="h-24 bg-neutral-200 dark:bg-neutral-700 rounded"></div>
            <div className="h-24 bg-neutral-200 dark:bg-neutral-700 rounded"></div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6">
        <div className="flex items-center mb-2">
          <XCircle className="w-5 h-5 text-red-500 dark:text-red-400 mr-2" />
          <span className="text-red-800 dark:text-red-300 font-medium">
            Failed to load gateway status
          </span>
        </div>
        <p className="text-sm text-red-600 dark:text-red-400 mb-3">{(error as Error).message}</p>
        <button
          onClick={refetch}
          className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-red-700 dark:text-red-300 bg-white dark:bg-neutral-800 border border-red-300 dark:border-red-700 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Gateway Overview</h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            {stats.total} gateways — {stats.online} online, {stats.offline} offline
            {stats.degraded > 0 && `, ${stats.degraded} degraded`}
          </p>
        </div>
        <button
          onClick={refetch}
          className="inline-flex items-center px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-md text-sm font-medium text-neutral-700 dark:text-neutral-300 bg-white dark:bg-neutral-800 hover:bg-neutral-50 dark:hover:bg-neutral-700"
        >
          <RefreshCw className="w-4 h-4 mr-2" />
          Refresh
        </button>
      </div>

      {/* Contextual sub-navigation (CAB-1785) */}
      <SubNav tabs={gatewayTabs} />

      {/* Fleet summary header — totals + status/type breakdown */}
      <FleetSummaryHeader
        total={stats.total}
        online={stats.online}
        offline={stats.offline}
        degraded={stats.degraded}
        maintenance={stats.maintenance}
        stoaCount={stats.stoaCount}
        thirdPartyCount={stats.thirdPartyCount}
      />

      {/* Per-gateway cards grid — aggregated multi-gateway view (CAB-1887 G5) */}
      {gateways.length > 0 ? (
        <div
          data-testid="gateway-cards-grid"
          className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4"
        >
          {gateways.map((gw) => (
            <GatewayCard key={gw.id} gw={gw} />
          ))}
        </div>
      ) : (
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 shadow-sm p-8 text-center">
          <Server className="w-8 h-8 mx-auto text-neutral-400 dark:text-neutral-500 mb-2" />
          <p className="text-sm text-neutral-500 dark:text-neutral-400">
            No gateways registered yet.
          </p>
          <button
            onClick={() => navigate('/gateways')}
            className="mt-3 text-sm text-indigo-600 dark:text-indigo-400 hover:text-indigo-800"
          >
            Go to Gateway Registry →
          </button>
        </div>
      )}

      {/* Extension Cards (CAB-1023) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Card 1: ArgoCD Sync Status */}
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 shadow-sm p-5">
          <div className="flex items-center mb-4">
            <div className="p-2 bg-orange-50 dark:bg-orange-900/30 rounded-lg">
              <GitCommit className="w-5 h-5 text-orange-600 dark:text-orange-400" />
            </div>
            <h3 className="ml-3 text-sm font-semibold text-neutral-900 dark:text-white">
              Infrastructure Sync
            </h3>
          </div>
          {platform.isLoading ? (
            <div className="flex items-center text-sm text-neutral-500 dark:text-neutral-400">
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              Loading...
            </div>
          ) : platform.error ? (
            <p className="text-sm text-red-600 dark:text-red-400">Unavailable</p>
          ) : platform.gatewayComponent ? (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <SyncBadge status={platform.gatewayComponent.sync_status} />
                <HealthBadge status={platform.gatewayComponent.health_status} />
              </div>
              {platform.gatewayComponent.revision && (
                <p className="text-xs text-neutral-500 dark:text-neutral-400">
                  Rev:{' '}
                  <code className="px-1 py-0.5 bg-neutral-100 dark:bg-neutral-700 rounded">
                    {platform.gatewayComponent.revision.slice(0, 7)}
                  </code>
                </p>
              )}
              {platform.gatewayComponent.last_sync && (
                <p className="text-xs text-neutral-500 dark:text-neutral-400">
                  Last sync: {new Date(platform.gatewayComponent.last_sync).toLocaleTimeString()}
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              No gateway component found in ArgoCD
            </p>
          )}
          <a
            href={
              platform.gatewayComponent
                ? config.services.argocd.getAppUrl(platform.gatewayComponent.name)
                : config.services.argocd.url
            }
            target="_blank"
            rel="noopener noreferrer"
            className="mt-3 inline-flex items-center text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300"
          >
            Open ArgoCD <ExternalLink className="w-3 h-3 ml-1" />
          </a>
        </div>

        {/* Card 2: Observability */}
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 shadow-sm p-5">
          <div className="flex items-center mb-4">
            <div className="p-2 bg-blue-50 dark:bg-blue-900/30 rounded-lg">
              <BarChart3 className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            </div>
            <h3 className="ml-3 text-sm font-semibold text-neutral-900 dark:text-white">
              Observability
            </h3>
          </div>
          <p className="text-xs text-neutral-500 dark:text-neutral-400 mb-3">
            Metrics, dashboards &amp; logs
          </p>
          <div className="space-y-2">
            <button
              onClick={() => navigate(observabilityPath())}
              className="flex items-center w-full p-2 rounded-md hover:bg-neutral-50 dark:hover:bg-neutral-700 text-sm text-neutral-700 dark:text-neutral-300 text-left"
            >
              <BarChart3 className="w-4 h-4 mr-2 text-orange-500" />
              Grafana Dashboards
            </button>
            <button
              onClick={() => navigate(observabilityPath(config.services.prometheus.url))}
              className="flex items-center w-full p-2 rounded-md hover:bg-neutral-50 dark:hover:bg-neutral-700 text-sm text-neutral-700 dark:text-neutral-300 text-left"
            >
              <Search className="w-4 h-4 mr-2 text-red-500" />
              Prometheus
            </button>
            <button
              onClick={() => navigate(logsPath())}
              className="flex items-center w-full p-2 rounded-md hover:bg-neutral-50 dark:hover:bg-neutral-700 text-sm text-neutral-700 dark:text-neutral-300 text-left"
            >
              <Activity className="w-4 h-4 mr-2 text-green-500" />
              Logs Explorer
            </button>
          </div>
        </div>

        {/* Card 3: Platform Health */}
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 shadow-sm p-5">
          <div className="flex items-center mb-4">
            <div className="p-2 bg-red-50 dark:bg-red-900/30 rounded-lg">
              <ShieldAlert className="w-5 h-5 text-red-600 dark:text-red-400" />
            </div>
            <h3 className="ml-3 text-sm font-semibold text-neutral-900 dark:text-white">
              Platform Health
            </h3>
          </div>
          {platform.isLoading ? (
            <div className="flex items-center text-sm text-neutral-500 dark:text-neutral-400">
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              Loading...
            </div>
          ) : platform.error ? (
            <p className="text-sm text-red-600 dark:text-red-400">Unavailable</p>
          ) : platform.healthSummary ? (
            <div className="space-y-3">
              <div className="grid grid-cols-3 gap-2 text-center">
                <div>
                  <p className="text-lg font-semibold text-green-600">
                    {platform.healthSummary.healthy}
                  </p>
                  <p className="text-xs text-neutral-500 dark:text-neutral-400">Healthy</p>
                </div>
                <div>
                  <p className="text-lg font-semibold text-yellow-600">
                    {platform.healthSummary.progressing}
                  </p>
                  <p className="text-xs text-neutral-500 dark:text-neutral-400">In Progress</p>
                </div>
                <div>
                  <p className="text-lg font-semibold text-red-600">
                    {platform.healthSummary.degraded}
                  </p>
                  <p className="text-xs text-neutral-500 dark:text-neutral-400">Degraded</p>
                </div>
              </div>
              <p className="text-xs text-neutral-500 dark:text-neutral-400 text-center">
                {platform.healthSummary.total} components monitored
              </p>
            </div>
          ) : null}
          <button
            onClick={() => navigate(observabilityPath(`${config.services.prometheus.url}/alerts`))}
            className="mt-3 inline-flex items-center text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300"
          >
            View Alerts
          </button>
        </div>
      </div>

      {/* Gateway Arena */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 shadow-sm p-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center">
            <div className="p-2 bg-purple-50 dark:bg-purple-900/30 rounded-lg">
              <Gauge className="w-5 h-5 text-purple-600 dark:text-purple-400" />
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-semibold text-neutral-900 dark:text-white">
                Gateway Arena
              </h3>
              <p className="text-xs text-neutral-500 dark:text-neutral-400">
                Continuous benchmark leaderboard — STOA vs Kong vs Gravitee
              </p>
            </div>
          </div>
          <button
            onClick={() =>
              navigate(
                `/observability/benchmarks?url=${encodeURIComponent(config.services.grafana.arenaDashboardUrl)}`
              )
            }
            className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-white bg-purple-600 rounded-lg hover:bg-purple-700 transition-colors"
          >
            <BarChart3 className="w-4 h-4" />
            View Benchmarks
          </button>
        </div>
      </div>

      {/* Info Banner */}
      <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
        <div className="flex">
          <Activity className="h-5 w-5 text-blue-400 flex-shrink-0" />
          <div className="ml-3">
            <h3 className="text-sm font-medium text-blue-800 dark:text-blue-300">
              Zero-Touch GitOps
            </h3>
            <p className="mt-1 text-sm text-blue-700 dark:text-blue-400">
              Gateway configuration is managed declaratively through Git. Changes are automatically
              reconciled via ArgoCD. This dashboard is read-only by design.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
