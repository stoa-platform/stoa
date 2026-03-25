import { memo, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useGatewayPlatformInfo } from '../hooks/useGatewayStatus';
import { useGatewayHealthSummary, useGatewayInstances } from '../hooks/usePlatformMetrics';
import { config } from '../config';
import { observabilityPath, logsPath } from '../utils/navigation';
import { SubNav } from '../components/SubNav';
import { gatewayTabs } from '../components/subNavGroups';
import type { GatewayInstance, GatewayInstanceStatus } from '../types';
import {
  Server,
  Activity,
  RefreshCw,
  CheckCircle2,
  XCircle,
  ExternalLink,
  GitCommit,
  BarChart3,
  Search,
  ShieldAlert,
  Loader2,
  Target,
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

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

const statsColorClasses = {
  blue: 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400',
  green: 'bg-green-50 dark:bg-green-900/30 text-green-600 dark:text-green-400',
  purple: 'bg-purple-50 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400',
  orange: 'bg-orange-50 dark:bg-orange-900/30 text-orange-600 dark:text-orange-400',
} as const;

const StatsCard = memo(function StatsCard({
  title,
  value,
  icon: Icon,
  color = 'blue',
}: {
  title: string;
  value: number | string;
  icon: React.ElementType;
  color?: keyof typeof statsColorClasses;
}) {
  return (
    <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4">
      <div className="flex items-center">
        <div className={`p-2 rounded-lg ${statsColorClasses[color]}`}>
          <Icon className="w-5 h-5" />
        </div>
        <div className="ml-3">
          <p className="text-sm font-medium text-neutral-500 dark:text-neutral-400">{title}</p>
          <p className="text-2xl font-semibold text-neutral-900 dark:text-white">{value}</p>
        </div>
      </div>
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
    const stoaCount = gateways.filter((g) => isStoa(g.gateway_type)).length;
    const thirdPartyCount = gateways.length - stoaCount;
    return { online, offline, degraded, total: gateways.length, stoaCount, thirdPartyCount };
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

      {/* Stats Summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatsCard title="Total Gateways" value={stats.total} icon={Server} color="blue" />
        <StatsCard title="Online" value={stats.online} icon={CheckCircle2} color="green" />
        <StatsCard title="STOA Gateways" value={stats.stoaCount} icon={Zap} color="purple" />
        <StatsCard
          title="Third-Party"
          value={stats.thirdPartyCount}
          icon={Activity}
          color="orange"
        />
      </div>

      {/* Gateway Instance List */}
      {gateways.length > 0 && (
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 shadow-sm">
          <div className="px-6 py-4 border-b border-neutral-200 dark:border-neutral-700">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-neutral-900 dark:text-white">
                All Gateways
              </h2>
              <button
                onClick={() => navigate('/gateways')}
                className="text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300"
              >
                View Registry →
              </button>
            </div>
          </div>
          <div className="divide-y divide-neutral-100 dark:divide-neutral-700/50">
            {gateways.slice(0, 10).map((gw) => {
              const sc = STATUS_COLORS[gw.status];
              return (
                <div
                  key={gw.id}
                  className="flex items-center gap-4 px-6 py-3 hover:bg-neutral-50 dark:hover:bg-neutral-750 cursor-pointer"
                  onClick={() => navigate('/gateways')}
                >
                  <div className="flex-shrink-0 relative">
                    <div
                      className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                        isStoa(gw.gateway_type)
                          ? 'bg-indigo-100 dark:bg-indigo-900/30'
                          : 'bg-neutral-100 dark:bg-neutral-700'
                      }`}
                    >
                      {isStoa(gw.gateway_type) ? (
                        <Zap className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
                      ) : (
                        <Server className="w-4 h-4 text-neutral-500 dark:text-neutral-400" />
                      )}
                    </div>
                    <span
                      className={`absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-white dark:border-neutral-800 ${sc.dot}`}
                    />
                  </div>
                  <div className="min-w-0 flex-1">
                    <span className="text-sm font-medium text-neutral-900 dark:text-white truncate block">
                      {gw.display_name}
                    </span>
                    <span className="text-xs text-neutral-500 dark:text-neutral-400">
                      {gw.gateway_type} · {gw.environment}
                    </span>
                  </div>
                  <span
                    className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-medium rounded-full ${sc.badge}`}
                  >
                    <span className={`w-1.5 h-1.5 rounded-full ${sc.dot}`} />
                    {sc.label}
                  </span>
                  <span className="text-xs text-neutral-400 dark:text-neutral-500 w-16 text-right">
                    {gw.last_health_check ? timeAgo(gw.last_health_check) : 'never'}
                  </span>
                </div>
              );
            })}
            {gateways.length > 10 && (
              <div className="px-6 py-3 text-center">
                <button
                  onClick={() => navigate('/gateways')}
                  className="text-sm text-indigo-600 dark:text-indigo-400 hover:text-indigo-800"
                >
                  View all {gateways.length} gateways →
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* SLO Compliance Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 shadow-sm p-5">
          <div className="flex items-center mb-4">
            <div className="p-2 bg-neutral-100 dark:bg-neutral-700 rounded-lg">
              <Target className="w-5 h-5 text-neutral-500 dark:text-neutral-400" />
            </div>
            <h3 className="ml-3 text-sm font-semibold text-neutral-900 dark:text-white">
              SLO Compliance
            </h3>
          </div>
          <div className="text-center py-4">
            <p className="text-sm text-neutral-500 dark:text-neutral-400">No metrics available</p>
            <p className="text-xs text-neutral-400 dark:text-neutral-500 mt-1">
              Connect Prometheus to enable SLO tracking
            </p>
          </div>
        </div>
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 shadow-sm p-5">
          <div className="flex items-center mb-4">
            <div className="p-2 bg-neutral-100 dark:bg-neutral-700 rounded-lg">
              <Gauge className="w-5 h-5 text-neutral-500 dark:text-neutral-400" />
            </div>
            <h3 className="ml-3 text-sm font-semibold text-neutral-900 dark:text-white">
              Error Budget
            </h3>
          </div>
          <div className="text-center py-4">
            <p className="text-sm text-neutral-500 dark:text-neutral-400">No metrics available</p>
            <p className="text-xs text-neutral-400 dark:text-neutral-500 mt-1">
              Connect Prometheus to enable error budget tracking
            </p>
          </div>
        </div>
      </div>

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
