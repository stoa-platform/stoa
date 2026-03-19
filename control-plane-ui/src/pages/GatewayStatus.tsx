import { memo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useGatewayStatus, useGatewayPlatformInfo } from '../hooks/useGatewayStatus';
import { config } from '../config';
import { observabilityPath, logsPath } from '../utils/navigation';
import { SubNav } from '../components/SubNav';
import { gatewayTabs } from '../components/subNavGroups';
import {
  Server,
  Activity,
  Box,
  RefreshCw,
  CheckCircle2,
  XCircle,
  AlertCircle,
  ExternalLink,
  GitBranch,
  GitCommit,
  BarChart3,
  Search,
  ShieldAlert,
  Loader2,
  Target,
  Gauge,
} from 'lucide-react';

const healthConfig = {
  healthy: {
    bg: 'bg-green-100 dark:bg-green-900/30',
    text: 'text-green-800 dark:text-green-400',
    icon: CheckCircle2,
    label: 'Online',
  },
  unhealthy: {
    bg: 'bg-red-100 dark:bg-red-900/30',
    text: 'text-red-800 dark:text-red-400',
    icon: XCircle,
    label: 'Offline',
  },
} as const;

const fallbackHealth = {
  bg: 'bg-neutral-100 dark:bg-neutral-700',
  text: 'text-neutral-800 dark:text-neutral-300',
  icon: AlertCircle,
  label: 'Unknown',
};

function StatusBadge({ status }: { status: string }) {
  const cfg = healthConfig[status as keyof typeof healthConfig] || fallbackHealth;
  const Icon = cfg.icon;
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${cfg.bg} ${cfg.text}`}
    >
      <Icon className="w-3 h-3 mr-1" />
      {cfg.label}
    </span>
  );
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
  const { data, isLoading, error, refetch, dataUpdatedAt } = useGatewayStatus();
  const platform = useGatewayPlatformInfo();

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-neutral-200 dark:bg-neutral-700 rounded w-1/4"></div>
          <div className="h-32 bg-neutral-200 dark:bg-neutral-700 rounded"></div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
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
          onClick={() => refetch()}
          className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-red-700 dark:text-red-300 bg-white dark:bg-neutral-800 border border-red-300 dark:border-red-700 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          Retry
        </button>
      </div>
    );
  }

  const lastUpdated = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : 'N/A';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Gateway Adapters</h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            Zero-Touch GitOps monitoring — configured via Git, not UI
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="inline-flex items-center px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-md text-sm font-medium text-neutral-700 dark:text-neutral-300 bg-white dark:bg-neutral-800 hover:bg-neutral-50 dark:hover:bg-neutral-700"
        >
          <RefreshCw className="w-4 h-4 mr-2" />
          Refresh
        </button>
      </div>

      {/* Contextual sub-navigation (CAB-1785) */}
      <SubNav tabs={gatewayTabs} />

      {/* Main Status Card */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 shadow-sm">
        <div className="p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <div className="p-3 bg-indigo-100 dark:bg-indigo-900/30 rounded-lg">
                <Server className="w-6 h-6 text-indigo-600 dark:text-indigo-400" />
              </div>
              <div className="ml-4">
                <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">
                  webMethods Gateway
                </h2>
                <p className="text-sm text-neutral-500 dark:text-neutral-400">
                  {data?.health.proxy_mode ? 'OIDC Proxy' : 'Direct'} mode
                </p>
              </div>
            </div>
            <StatusBadge status={data?.health.status || 'unknown'} />
          </div>

          {/* Stats Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6">
            <StatsCard
              title="APIs Synced"
              value={data?.apis === null ? '—' : (data?.apis.length ?? 0)}
              icon={Box}
              color="blue"
            />
            <StatsCard
              title="Applications"
              value={data?.applications === null ? '—' : (data?.applications.length ?? 0)}
              icon={Activity}
              color="green"
            />
            <StatsCard title="Last Sync" value={lastUpdated} icon={RefreshCw} color="purple" />
          </div>

          {/* Fetch error notice */}
          {data && (data.apis === null || data.applications === null) && (
            <div className="mt-3 flex items-center gap-2 px-3 py-2 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg text-sm text-amber-700 dark:text-amber-400">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              Unable to fetch{' '}
              {data.apis === null && data.applications === null
                ? 'APIs and applications'
                : data.apis === null
                  ? 'APIs'
                  : 'applications'}{' '}
              from the gateway. The gateway may be unreachable.
            </div>
          )}

          {/* Resource Details (collapsible) */}
          {data && ((data.apis?.length ?? 0) > 0 || (data.applications?.length ?? 0) > 0) && (
            <details className="mt-6">
              <summary className="cursor-pointer text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:text-neutral-900 dark:hover:text-white">
                View resource details
              </summary>
              <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* APIs */}
                {data.apis && data.apis.length > 0 && (
                  <div className="bg-neutral-50 dark:bg-neutral-900 rounded-lg p-4">
                    <h4 className="text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                      APIs ({data.apis.length})
                    </h4>
                    <ul className="space-y-1 text-sm text-neutral-600 dark:text-neutral-400 max-h-40 overflow-y-auto">
                      {data.apis.slice(0, 10).map((api) => (
                        <li key={api.id} className="flex items-center">
                          {api.isActive ? (
                            <CheckCircle2 className="w-3 h-3 text-green-500 mr-2 flex-shrink-0" />
                          ) : (
                            <AlertCircle className="w-3 h-3 text-yellow-500 mr-2 flex-shrink-0" />
                          )}
                          {api.apiName}{' '}
                          <span className="text-neutral-400 dark:text-neutral-500 ml-1">
                            v{api.apiVersion}
                          </span>
                        </li>
                      ))}
                      {data.apis.length > 10 && (
                        <li className="text-neutral-400 dark:text-neutral-500">
                          ... and {data.apis.length - 10} more
                        </li>
                      )}
                    </ul>
                  </div>
                )}

                {/* Applications */}
                {data.applications && data.applications.length > 0 && (
                  <div className="bg-neutral-50 dark:bg-neutral-900 rounded-lg p-4">
                    <h4 className="text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                      Applications ({data.applications.length})
                    </h4>
                    <ul className="space-y-1 text-sm text-neutral-600 dark:text-neutral-400 max-h-40 overflow-y-auto">
                      {data.applications.slice(0, 10).map((app) => (
                        <li key={app.id} className="flex items-center">
                          <CheckCircle2 className="w-3 h-3 text-green-500 mr-2 flex-shrink-0" />
                          {app.name}
                        </li>
                      ))}
                      {data.applications.length > 10 && (
                        <li className="text-neutral-400 dark:text-neutral-500">
                          ... and {data.applications.length - 10} more
                        </li>
                      )}
                    </ul>
                  </div>
                )}
              </div>
            </details>
          )}
        </div>

        {/* Footer - GitOps */}
        <div className="bg-neutral-50 dark:bg-neutral-900 border-t border-neutral-200 dark:border-neutral-700 px-6 py-4 rounded-b-lg">
          <div className="flex items-center justify-between text-sm">
            <div className="flex items-center text-neutral-600 dark:text-neutral-400">
              <GitBranch className="w-4 h-4 mr-2" />
              <span>Configured via GitOps: </span>
              <code className="ml-1 px-1.5 py-0.5 bg-neutral-200 dark:bg-neutral-700 rounded text-xs">
                webmethods/*.yaml
              </code>
            </div>
            <a
              href="https://docs.gostoa.dev/guides/hybrid-gateway-adapter"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300"
            >
              Documentation
              <ExternalLink className="w-3 h-3 ml-1" />
            </a>
          </div>
        </div>
      </div>

      {/* SLO Compliance Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* SLO Compliance Card */}
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 shadow-sm p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center">
              <div className="p-2 bg-neutral-100 dark:bg-neutral-700 rounded-lg">
                <Target className="w-5 h-5 text-neutral-500 dark:text-neutral-400" />
              </div>
              <h3 className="ml-3 text-sm font-semibold text-neutral-900 dark:text-white">
                SLO Compliance
              </h3>
            </div>
          </div>
          <div className="text-center py-4">
            <p className="text-sm text-neutral-500 dark:text-neutral-400">No metrics available</p>
            <p className="text-xs text-neutral-400 dark:text-neutral-500 mt-1">
              Connect Prometheus to enable SLO tracking
            </p>
          </div>
        </div>

        {/* Error Budget Card */}
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 shadow-sm p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center">
              <div className="p-2 bg-neutral-100 dark:bg-neutral-700 rounded-lg">
                <Gauge className="w-5 h-5 text-neutral-500 dark:text-neutral-400" />
              </div>
              <h3 className="ml-3 text-sm font-semibold text-neutral-900 dark:text-white">
                Error Budget
              </h3>
            </div>
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
