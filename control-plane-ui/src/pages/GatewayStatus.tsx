import { memo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useGatewayStatus, useGatewayPlatformInfo } from '../hooks/useGatewayStatus';
import { config } from '../config';
import { observabilityPath, logsPath } from '../utils/navigation';
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
    label: 'Connected',
  },
  unhealthy: {
    bg: 'bg-red-100 dark:bg-red-900/30',
    text: 'text-red-800 dark:text-red-400',
    icon: XCircle,
    label: 'Disconnected',
  },
} as const;

const fallbackHealth = {
  bg: 'bg-gray-100 dark:bg-neutral-700',
  text: 'text-gray-800 dark:text-neutral-300',
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
    <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 p-4">
      <div className="flex items-center">
        <div className={`p-2 rounded-lg ${statsColorClasses[color]}`}>
          <Icon className="w-5 h-5" />
        </div>
        <div className="ml-3">
          <p className="text-sm font-medium text-gray-500 dark:text-neutral-400">{title}</p>
          <p className="text-2xl font-semibold text-gray-900 dark:text-white">{value}</p>
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
      bg: 'bg-gray-100 dark:bg-neutral-700',
      text: 'text-gray-800 dark:text-neutral-300',
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
      bg: 'bg-gray-100 dark:bg-neutral-700',
      text: 'text-gray-800 dark:text-neutral-300',
    },
    Missing: { bg: 'bg-red-100 dark:bg-red-900/30', text: 'text-red-800 dark:text-red-400' },
  };
  const c = cfg[status] || {
    bg: 'bg-gray-100 dark:bg-neutral-700',
    text: 'text-gray-800 dark:text-neutral-300',
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
          <div className="h-8 bg-gray-200 dark:bg-neutral-700 rounded w-1/4"></div>
          <div className="h-32 bg-gray-200 dark:bg-neutral-700 rounded"></div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="h-24 bg-gray-200 dark:bg-neutral-700 rounded"></div>
            <div className="h-24 bg-gray-200 dark:bg-neutral-700 rounded"></div>
            <div className="h-24 bg-gray-200 dark:bg-neutral-700 rounded"></div>
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
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Gateway Adapters</h1>
          <p className="text-sm text-gray-500 dark:text-neutral-400 mt-1">
            Zero-Touch GitOps monitoring — configured via Git, not UI
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="inline-flex items-center px-3 py-2 border border-gray-300 dark:border-neutral-600 rounded-md text-sm font-medium text-gray-700 dark:text-neutral-300 bg-white dark:bg-neutral-800 hover:bg-gray-50 dark:hover:bg-neutral-700"
        >
          <RefreshCw className="w-4 h-4 mr-2" />
          Refresh
        </button>
      </div>

      {/* Main Status Card */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 shadow-sm">
        <div className="p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <div className="p-3 bg-indigo-100 dark:bg-indigo-900/30 rounded-lg">
                <Server className="w-6 h-6 text-indigo-600 dark:text-indigo-400" />
              </div>
              <div className="ml-4">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                  webMethods Gateway
                </h2>
                <p className="text-sm text-gray-500 dark:text-neutral-400">
                  {data?.health.proxy_mode ? 'OIDC Proxy' : 'Direct'} mode
                </p>
              </div>
            </div>
            <StatusBadge status={data?.health.status || 'unknown'} />
          </div>

          {/* Stats Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6">
            <StatsCard title="APIs Synced" value={data?.apis.length || 0} icon={Box} color="blue" />
            <StatsCard
              title="Applications"
              value={data?.applications.length || 0}
              icon={Activity}
              color="green"
            />
            <StatsCard title="Last Sync" value={lastUpdated} icon={RefreshCw} color="purple" />
          </div>

          {/* Resource Details (collapsible) */}
          {data && (data.apis.length > 0 || data.applications.length > 0) && (
            <details className="mt-6">
              <summary className="cursor-pointer text-sm font-medium text-gray-700 dark:text-neutral-300 hover:text-gray-900 dark:hover:text-white">
                View resource details
              </summary>
              <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* APIs */}
                <div className="bg-gray-50 dark:bg-neutral-900 rounded-lg p-4">
                  <h4 className="text-sm font-medium text-gray-700 dark:text-neutral-300 mb-2">
                    APIs ({data.apis.length})
                  </h4>
                  <ul className="space-y-1 text-sm text-gray-600 dark:text-neutral-400 max-h-40 overflow-y-auto">
                    {data.apis.slice(0, 10).map((api) => (
                      <li key={api.id} className="flex items-center">
                        {api.isActive ? (
                          <CheckCircle2 className="w-3 h-3 text-green-500 mr-2 flex-shrink-0" />
                        ) : (
                          <AlertCircle className="w-3 h-3 text-yellow-500 mr-2 flex-shrink-0" />
                        )}
                        {api.apiName}{' '}
                        <span className="text-gray-400 dark:text-neutral-500 ml-1">
                          v{api.apiVersion}
                        </span>
                      </li>
                    ))}
                    {data.apis.length > 10 && (
                      <li className="text-gray-400 dark:text-neutral-500">
                        ... and {data.apis.length - 10} more
                      </li>
                    )}
                  </ul>
                </div>

                {/* Applications */}
                <div className="bg-gray-50 dark:bg-neutral-900 rounded-lg p-4">
                  <h4 className="text-sm font-medium text-gray-700 dark:text-neutral-300 mb-2">
                    Applications ({data.applications.length})
                  </h4>
                  <ul className="space-y-1 text-sm text-gray-600 dark:text-neutral-400 max-h-40 overflow-y-auto">
                    {data.applications.slice(0, 10).map((app) => (
                      <li key={app.id} className="flex items-center">
                        <CheckCircle2 className="w-3 h-3 text-green-500 mr-2 flex-shrink-0" />
                        {app.name}
                      </li>
                    ))}
                    {data.applications.length > 10 && (
                      <li className="text-gray-400 dark:text-neutral-500">
                        ... and {data.applications.length - 10} more
                      </li>
                    )}
                  </ul>
                </div>
              </div>
            </details>
          )}
        </div>

        {/* Footer - GitOps */}
        <div className="bg-gray-50 dark:bg-neutral-900 border-t border-gray-200 dark:border-neutral-700 px-6 py-4 rounded-b-lg">
          <div className="flex items-center justify-between text-sm">
            <div className="flex items-center text-gray-600 dark:text-neutral-400">
              <GitBranch className="w-4 h-4 mr-2" />
              <span>Configured via GitOps: </span>
              <code className="ml-1 px-1.5 py-0.5 bg-gray-200 dark:bg-neutral-700 rounded text-xs">
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
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 shadow-sm p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center">
              <div className="p-2 bg-green-50 dark:bg-green-900/30 rounded-lg">
                <Target className="w-5 h-5 text-green-600" />
              </div>
              <h3 className="ml-3 text-sm font-semibold text-gray-900 dark:text-white">
                SLO Compliance
              </h3>
            </div>
            <span className="text-xs font-medium px-2 py-1 rounded-full bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400">
              On Track
            </span>
          </div>
          <div className="space-y-3">
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-gray-600 dark:text-neutral-400">
                  Availability (99.9% target)
                </span>
                <span className="font-medium text-gray-900 dark:text-white">99.95%</span>
              </div>
              <div className="w-full bg-gray-200 dark:bg-neutral-700 rounded-full h-2">
                <div className="h-2 rounded-full bg-green-500" style={{ width: '99.95%' }} />
              </div>
            </div>
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-gray-600 dark:text-neutral-400">
                  Latency P95 (&lt;500ms target)
                </span>
                <span className="font-medium text-gray-900 dark:text-white">342ms</span>
              </div>
              <div className="w-full bg-gray-200 dark:bg-neutral-700 rounded-full h-2">
                <div className="h-2 rounded-full bg-green-500" style={{ width: '68%' }} />
              </div>
            </div>
          </div>
        </div>

        {/* Error Budget Card */}
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 shadow-sm p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center">
              <div className="p-2 bg-blue-50 dark:bg-blue-900/30 rounded-lg">
                <Gauge className="w-5 h-5 text-blue-600 dark:text-blue-400" />
              </div>
              <h3 className="ml-3 text-sm font-semibold text-gray-900 dark:text-white">
                Error Budget
              </h3>
            </div>
            <span className="text-xs font-medium px-2 py-1 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400">
              30d Window
            </span>
          </div>
          <div className="flex items-end gap-4">
            <div>
              <p className="text-3xl font-bold text-blue-600">67.2%</p>
              <p className="text-xs text-gray-500 dark:text-neutral-400">remaining this month</p>
            </div>
            <div className="flex-1">
              <div className="w-full bg-gray-200 dark:bg-neutral-700 rounded-full h-4">
                <div
                  className="h-4 rounded-full bg-gradient-to-r from-blue-500 to-blue-400"
                  style={{ width: '67.2%' }}
                />
              </div>
              <div className="flex justify-between text-xs text-gray-500 dark:text-neutral-400 mt-1">
                <span>0%</span>
                <span>Consumed: 32.8%</span>
                <span>100%</span>
              </div>
            </div>
          </div>
          <p className="text-xs text-gray-500 dark:text-neutral-400 mt-3">
            Based on 99.9% availability SLO = 43.2 min downtime/month allowed
          </p>
        </div>
      </div>

      {/* Extension Cards (CAB-1023) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Card 1: ArgoCD Sync Status */}
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 shadow-sm p-5">
          <div className="flex items-center mb-4">
            <div className="p-2 bg-orange-50 dark:bg-orange-900/30 rounded-lg">
              <GitCommit className="w-5 h-5 text-orange-600 dark:text-orange-400" />
            </div>
            <h3 className="ml-3 text-sm font-semibold text-gray-900 dark:text-white">
              ArgoCD Sync
            </h3>
          </div>
          {platform.isLoading ? (
            <div className="flex items-center text-sm text-gray-500 dark:text-neutral-400">
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
                <p className="text-xs text-gray-500 dark:text-neutral-400">
                  Rev:{' '}
                  <code className="px-1 py-0.5 bg-gray-100 dark:bg-neutral-700 rounded">
                    {platform.gatewayComponent.revision.slice(0, 7)}
                  </code>
                </p>
              )}
              {platform.gatewayComponent.last_sync && (
                <p className="text-xs text-gray-500 dark:text-neutral-400">
                  Last sync: {new Date(platform.gatewayComponent.last_sync).toLocaleTimeString()}
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm text-gray-500 dark:text-neutral-400">
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
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 shadow-sm p-5">
          <div className="flex items-center mb-4">
            <div className="p-2 bg-blue-50 dark:bg-blue-900/30 rounded-lg">
              <BarChart3 className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            </div>
            <h3 className="ml-3 text-sm font-semibold text-gray-900 dark:text-white">
              Observability
            </h3>
          </div>
          <p className="text-xs text-gray-500 dark:text-neutral-400 mb-3">
            Metrics, dashboards &amp; logs
          </p>
          <div className="space-y-2">
            <button
              onClick={() => navigate(observabilityPath())}
              className="flex items-center w-full p-2 rounded-md hover:bg-gray-50 dark:hover:bg-neutral-700 text-sm text-gray-700 dark:text-neutral-300 text-left"
            >
              <BarChart3 className="w-4 h-4 mr-2 text-orange-500" />
              Grafana Dashboards
            </button>
            <button
              onClick={() => navigate(observabilityPath(config.services.prometheus.url))}
              className="flex items-center w-full p-2 rounded-md hover:bg-gray-50 dark:hover:bg-neutral-700 text-sm text-gray-700 dark:text-neutral-300 text-left"
            >
              <Search className="w-4 h-4 mr-2 text-red-500" />
              Prometheus
            </button>
            <button
              onClick={() => navigate(logsPath())}
              className="flex items-center w-full p-2 rounded-md hover:bg-gray-50 dark:hover:bg-neutral-700 text-sm text-gray-700 dark:text-neutral-300 text-left"
            >
              <Activity className="w-4 h-4 mr-2 text-green-500" />
              Logs Explorer
            </button>
          </div>
        </div>

        {/* Card 3: Platform Health */}
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 shadow-sm p-5">
          <div className="flex items-center mb-4">
            <div className="p-2 bg-red-50 dark:bg-red-900/30 rounded-lg">
              <ShieldAlert className="w-5 h-5 text-red-600 dark:text-red-400" />
            </div>
            <h3 className="ml-3 text-sm font-semibold text-gray-900 dark:text-white">
              Platform Health
            </h3>
          </div>
          {platform.isLoading ? (
            <div className="flex items-center text-sm text-gray-500 dark:text-neutral-400">
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
                  <p className="text-xs text-gray-500 dark:text-neutral-400">Healthy</p>
                </div>
                <div>
                  <p className="text-lg font-semibold text-yellow-600">
                    {platform.healthSummary.progressing}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-neutral-400">In Progress</p>
                </div>
                <div>
                  <p className="text-lg font-semibold text-red-600">
                    {platform.healthSummary.degraded}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-neutral-400">Degraded</p>
                </div>
              </div>
              <p className="text-xs text-gray-500 dark:text-neutral-400 text-center">
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
      <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 shadow-sm p-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center">
            <div className="p-2 bg-purple-50 dark:bg-purple-900/30 rounded-lg">
              <Gauge className="w-5 h-5 text-purple-600 dark:text-purple-400" />
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Gateway Arena</h3>
              <p className="text-xs text-gray-500 dark:text-neutral-400">
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
