import { memo } from 'react';
import { useGatewayStatus } from '../hooks/useGatewayStatus';
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
} from 'lucide-react';

const healthConfig = {
  healthy: { bg: 'bg-green-100', text: 'text-green-800', icon: CheckCircle2, label: 'Connected' },
  unhealthy: { bg: 'bg-red-100', text: 'text-red-800', icon: XCircle, label: 'Disconnected' },
} as const;

const fallbackHealth = { bg: 'bg-gray-100', text: 'text-gray-800', icon: AlertCircle, label: 'Unknown' };

function StatusBadge({ status }: { status: string }) {
  const config = healthConfig[status as keyof typeof healthConfig] || fallbackHealth;
  const Icon = config.icon;
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${config.bg} ${config.text}`}>
      <Icon className="w-3 h-3 mr-1" />
      {config.label}
    </span>
  );
}

const statsColorClasses = {
  blue: 'bg-blue-50 text-blue-600',
  green: 'bg-green-50 text-green-600',
  purple: 'bg-purple-50 text-purple-600',
  orange: 'bg-orange-50 text-orange-600',
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
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <div className="flex items-center">
        <div className={`p-2 rounded-lg ${statsColorClasses[color]}`}>
          <Icon className="w-5 h-5" />
        </div>
        <div className="ml-3">
          <p className="text-sm font-medium text-gray-500">{title}</p>
          <p className="text-2xl font-semibold text-gray-900">{value}</p>
        </div>
      </div>
    </div>
  );
});

export default function GatewayStatus() {
  const { data, isLoading, error, refetch, dataUpdatedAt } = useGatewayStatus();

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-gray-200 rounded w-1/4"></div>
          <div className="h-32 bg-gray-200 rounded"></div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="h-24 bg-gray-200 rounded"></div>
            <div className="h-24 bg-gray-200 rounded"></div>
            <div className="h-24 bg-gray-200 rounded"></div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <div className="flex items-center">
          <XCircle className="w-5 h-5 text-red-500 mr-2" />
          <span className="text-red-800">Failed to load gateway status</span>
        </div>
        <p className="text-sm text-red-600 mt-1">{(error as Error).message}</p>
        <button
          onClick={() => refetch()}
          className="mt-2 text-sm text-red-700 hover:text-red-900 underline"
        >
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
          <h1 className="text-2xl font-bold text-gray-900">Gateway Adapters</h1>
          <p className="text-sm text-gray-500 mt-1">
            Zero-Touch GitOps monitoring — configured via Git, not UI
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="inline-flex items-center px-3 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50"
        >
          <RefreshCw className="w-4 h-4 mr-2" />
          Refresh
        </button>
      </div>

      {/* Main Status Card */}
      <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
        <div className="p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <div className="p-3 bg-indigo-100 rounded-lg">
                <Server className="w-6 h-6 text-indigo-600" />
              </div>
              <div className="ml-4">
                <h2 className="text-lg font-semibold text-gray-900">webMethods Gateway</h2>
                <p className="text-sm text-gray-500">
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
              value={data?.apis.length || 0}
              icon={Box}
              color="blue"
            />
            <StatsCard
              title="Applications"
              value={data?.applications.length || 0}
              icon={Activity}
              color="green"
            />
            <StatsCard
              title="Last Sync"
              value={lastUpdated}
              icon={RefreshCw}
              color="purple"
            />
          </div>

          {/* Resource Details (collapsible) */}
          {data && (data.apis.length > 0 || data.applications.length > 0) && (
            <details className="mt-6">
              <summary className="cursor-pointer text-sm font-medium text-gray-700 hover:text-gray-900">
                View resource details
              </summary>
              <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* APIs */}
                <div className="bg-gray-50 rounded-lg p-4">
                  <h4 className="text-sm font-medium text-gray-700 mb-2">APIs ({data.apis.length})</h4>
                  <ul className="space-y-1 text-sm text-gray-600 max-h-40 overflow-y-auto">
                    {data.apis.slice(0, 10).map((api) => (
                      <li key={api.id} className="flex items-center">
                        {api.isActive ? (
                          <CheckCircle2 className="w-3 h-3 text-green-500 mr-2 flex-shrink-0" />
                        ) : (
                          <AlertCircle className="w-3 h-3 text-yellow-500 mr-2 flex-shrink-0" />
                        )}
                        {api.apiName} <span className="text-gray-400 ml-1">v{api.apiVersion}</span>
                      </li>
                    ))}
                    {data.apis.length > 10 && (
                      <li className="text-gray-400">... and {data.apis.length - 10} more</li>
                    )}
                  </ul>
                </div>

                {/* Applications */}
                <div className="bg-gray-50 rounded-lg p-4">
                  <h4 className="text-sm font-medium text-gray-700 mb-2">Applications ({data.applications.length})</h4>
                  <ul className="space-y-1 text-sm text-gray-600 max-h-40 overflow-y-auto">
                    {data.applications.slice(0, 10).map((app) => (
                      <li key={app.id} className="flex items-center">
                        <CheckCircle2 className="w-3 h-3 text-green-500 mr-2 flex-shrink-0" />
                        {app.name}
                      </li>
                    ))}
                    {data.applications.length > 10 && (
                      <li className="text-gray-400">... and {data.applications.length - 10} more</li>
                    )}
                  </ul>
                </div>
              </div>
            </details>
          )}
        </div>

        {/* Footer - GitOps */}
        <div className="bg-gray-50 border-t border-gray-200 px-6 py-4 rounded-b-lg">
          <div className="flex items-center justify-between text-sm">
            <div className="flex items-center text-gray-600">
              <GitBranch className="w-4 h-4 mr-2" />
              <span>Configured via GitOps: </span>
              <code className="ml-1 px-1.5 py-0.5 bg-gray-200 rounded text-xs">webmethods/*.yaml</code>
            </div>
            <a
              href="https://docs.gostoa.dev/guides/hybrid-gateway-adapter"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center text-indigo-600 hover:text-indigo-800"
            >
              Documentation
              <ExternalLink className="w-3 h-3 ml-1" />
            </a>
          </div>
        </div>
      </div>

      {/* Info Banner */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="flex">
          <Activity className="h-5 w-5 text-blue-400 flex-shrink-0" />
          <div className="ml-3">
            <h3 className="text-sm font-medium text-blue-800">Zero-Touch GitOps</h3>
            <p className="mt-1 text-sm text-blue-700">
              Gateway configuration is managed declaratively through Git. Changes are automatically
              reconciled via ArgoCD. This dashboard is read-only by design.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
