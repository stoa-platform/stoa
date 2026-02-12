/**
 * PlatformStatus Component (CAB-654)
 *
 * Displays GitOps sync status for platform components via Argo CD.
 * Shows sync status, health, and external links.
 * Gracefully handles ArgoCD unreachable state (no error spam).
 */
import { useState, useEffect, useCallback, memo } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePlatformStatus, useSyncComponent } from '../hooks/usePlatformStatus';
import { ComponentStatus } from '../services/api';
import { observabilityPath, logsPath } from '../utils/navigation';

// Status color mappings — light + dark
const syncStatusColors: Record<string, string> = {
  Synced: 'text-green-600 bg-green-50 dark:bg-green-900/30 dark:text-green-400',
  OutOfSync: 'text-yellow-600 bg-yellow-50 dark:bg-yellow-900/30 dark:text-yellow-400',
  Unknown: 'text-neutral-500 bg-neutral-100 dark:bg-neutral-800 dark:text-neutral-400',
  Error: 'text-red-600 bg-red-50 dark:bg-red-900/30 dark:text-red-400',
  NotFound: 'text-neutral-400 bg-neutral-50 dark:bg-neutral-800 dark:text-neutral-500',
};

const healthStatusColors: Record<string, string> = {
  Healthy: 'text-green-600 dark:text-green-400',
  Progressing: 'text-blue-600 dark:text-blue-400',
  Degraded: 'text-red-600 dark:text-red-400',
  Suspended: 'text-yellow-600 dark:text-yellow-400',
  Missing: 'text-neutral-400 dark:text-neutral-500',
  Unknown: 'text-neutral-500 dark:text-neutral-400',
};

const overallStatusConfig: Record<string, { color: string; bg: string; label: string }> = {
  healthy: {
    color: 'text-green-700 dark:text-green-400',
    bg: 'bg-green-100 dark:bg-green-900/30',
    label: 'All Systems Operational',
  },
  degraded: {
    color: 'text-red-700 dark:text-red-400',
    bg: 'bg-red-100 dark:bg-red-900/30',
    label: 'System Degraded',
  },
  syncing: {
    color: 'text-blue-700 dark:text-blue-400',
    bg: 'bg-blue-100 dark:bg-blue-900/30',
    label: 'Sync In Progress',
  },
  unknown: {
    color: 'text-neutral-500 dark:text-neutral-400',
    bg: 'bg-neutral-100 dark:bg-neutral-800',
    label: 'Checking Status...',
  },
};

// Icons
function CheckCircleIcon({ className = '' }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
      />
    </svg>
  );
}

function ExclamationCircleIcon({ className = '' }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
      />
    </svg>
  );
}

function RefreshIcon({ className = '' }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
      />
    </svg>
  );
}

function ExternalLinkIcon({ className = '' }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
      />
    </svg>
  );
}

interface PlatformStatusProps {
  compact?: boolean;
  onStatusChange?: (status: string) => void;
}

export function PlatformStatus({ compact = false, onStatusChange }: PlatformStatusProps) {
  const navigate = useNavigate();
  const {
    data: status,
    isLoading,
    error,
    refetch,
  } = usePlatformStatus({
    refetchInterval: 30000,
  });
  const syncMutation = useSyncComponent();
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  useEffect(() => {
    if (status) {
      setLastUpdated(new Date());
      onStatusChange?.(status.gitops.status);
    }
  }, [status, onStatusChange]);

  const handleRefresh = useCallback(() => {
    refetch();
    setLastUpdated(new Date());
  }, [refetch]);

  const handleSync = useCallback(
    async (componentName: string) => {
      try {
        await syncMutation.mutateAsync(componentName);
        setLastUpdated(new Date());
      } catch {
        // Sync failed silently — status will refresh automatically
      }
    },
    [syncMutation]
  );

  if (isLoading && !status) {
    return (
      <div className="bg-white dark:bg-neutral-800 rounded-xl shadow dark:shadow-none p-6">
        <div className="flex items-center justify-center">
          <RefreshIcon className="w-5 h-5 animate-spin text-neutral-400" />
          <span className="ml-2 text-neutral-500 dark:text-neutral-400">
            Loading platform status...
          </span>
        </div>
      </div>
    );
  }

  // Graceful error state — no scary messages
  if (error && !status) {
    return (
      <div className="bg-white dark:bg-neutral-800 rounded-xl shadow dark:shadow-none border border-neutral-200 dark:border-neutral-700 p-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-neutral-100 dark:bg-neutral-700">
              <ExclamationCircleIcon className="w-5 h-5 text-neutral-400 dark:text-neutral-500" />
            </div>
            <div>
              <h3 className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
                Platform Status
              </h3>
              <p className="text-xs text-neutral-500 dark:text-neutral-400">
                Status monitoring unavailable
              </p>
            </div>
          </div>
          <button
            onClick={handleRefresh}
            className="px-3 py-1.5 text-xs font-medium text-neutral-600 dark:text-neutral-300 bg-neutral-100 dark:bg-neutral-700 hover:bg-neutral-200 dark:hover:bg-neutral-600 rounded-lg transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!status) return null;

  const overallConfig = overallStatusConfig[status.gitops.status] || overallStatusConfig.unknown;

  if (compact) {
    return (
      <div className={`rounded-xl p-3 ${overallConfig.bg}`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {status.gitops.status === 'healthy' ? (
              <CheckCircleIcon className={`w-5 h-5 ${overallConfig.color}`} />
            ) : (
              <ExclamationCircleIcon className={`w-5 h-5 ${overallConfig.color}`} />
            )}
            <span className={`font-medium ${overallConfig.color}`}>{overallConfig.label}</span>
          </div>
          <button
            onClick={handleRefresh}
            disabled={isLoading}
            className="p-1 hover:bg-white/50 dark:hover:bg-neutral-700/50 rounded transition-colors"
            title="Refresh status"
          >
            <RefreshIcon className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-neutral-800 rounded-xl shadow dark:shadow-none border border-neutral-200 dark:border-neutral-700">
      {/* Header */}
      <div className="px-6 py-4 border-b border-neutral-200 dark:border-neutral-700">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-neutral-900 dark:text-white">
              Platform Status
            </h3>
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              GitOps sync status via Argo CD
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span
              className={`px-3 py-1 rounded-full text-sm font-medium ${overallConfig.bg} ${overallConfig.color}`}
            >
              {overallConfig.label}
            </span>
            <button
              onClick={handleRefresh}
              disabled={isLoading}
              className="p-2 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded-lg transition-colors"
              title="Refresh status"
            >
              <RefreshIcon
                className={`w-5 h-5 text-neutral-500 dark:text-neutral-400 ${isLoading ? 'animate-spin' : ''}`}
              />
            </button>
          </div>
        </div>
      </div>

      {/* Components Grid */}
      <div className="p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {status.gitops.components.map((component) => (
            <ComponentCard
              key={component.name}
              component={component}
              onSync={handleSync}
              isSyncing={syncMutation.isPending}
            />
          ))}
        </div>

        {/* External Links */}
        {status.external_links && (
          <div className="mt-6 pt-6 border-t border-neutral-200 dark:border-neutral-700">
            <h4 className="text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-3">
              Quick Links
            </h4>
            <div className="flex flex-wrap gap-2">
              <a
                href={status.external_links.argocd}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm text-neutral-600 dark:text-neutral-300 bg-neutral-100 dark:bg-neutral-700 hover:bg-neutral-200 dark:hover:bg-neutral-600 rounded-lg transition-colors"
              >
                <ExternalLinkIcon className="w-4 h-4" />
                ArgoCD
              </a>
              <button
                onClick={() => navigate(observabilityPath(status.external_links.grafana))}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm text-neutral-600 dark:text-neutral-300 bg-neutral-100 dark:bg-neutral-700 hover:bg-neutral-200 dark:hover:bg-neutral-600 rounded-lg transition-colors"
              >
                <ExternalLinkIcon className="w-4 h-4" />
                Grafana
              </button>
              <button
                onClick={() => navigate(observabilityPath(status.external_links.prometheus))}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm text-neutral-600 dark:text-neutral-300 bg-neutral-100 dark:bg-neutral-700 hover:bg-neutral-200 dark:hover:bg-neutral-600 rounded-lg transition-colors"
              >
                <ExternalLinkIcon className="w-4 h-4" />
                Prometheus
              </button>
              <button
                onClick={() => navigate(logsPath(status.external_links.logs))}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm text-neutral-600 dark:text-neutral-300 bg-neutral-100 dark:bg-neutral-700 hover:bg-neutral-200 dark:hover:bg-neutral-600 rounded-lg transition-colors"
              >
                <ExternalLinkIcon className="w-4 h-4" />
                Logs
              </button>
            </div>
          </div>
        )}

        {/* Last Updated */}
        {lastUpdated && (
          <div className="mt-4 pt-4 border-t border-neutral-100 dark:border-neutral-700 text-xs text-neutral-400 dark:text-neutral-500 text-right">
            Last updated: {lastUpdated.toLocaleTimeString()}
          </div>
        )}
      </div>
    </div>
  );
}

interface ComponentCardProps {
  component: ComponentStatus;
  onSync: (name: string) => void;
  isSyncing: boolean;
}

const ComponentCard = memo(function ComponentCard({
  component,
  onSync,
  isSyncing,
}: ComponentCardProps) {
  const syncColor = syncStatusColors[component.sync_status] || syncStatusColors.Unknown;
  const healthColor = healthStatusColors[component.health_status] || healthStatusColors.Unknown;
  const isOutOfSync = component.sync_status === 'OutOfSync';

  return (
    <div className="border border-neutral-200 dark:border-neutral-700 rounded-xl p-4 hover:border-neutral-300 dark:hover:border-neutral-600 transition-colors bg-white dark:bg-neutral-800/50">
      <div className="flex items-start justify-between">
        <div>
          <h4 className="font-medium text-neutral-900 dark:text-white">{component.display_name}</h4>
          <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">{component.name}</p>
        </div>
        <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${syncColor}`}>
          {component.sync_status}
        </span>
      </div>

      <div className="mt-3 flex items-center justify-between text-sm">
        <div className="flex items-center gap-1.5">
          <span
            className={`w-2 h-2 rounded-full ${healthColor.replace('text-', 'bg-').replace(/dark:text-\S+/g, '')}`}
          />
          <span className={healthColor}>{component.health_status}</span>
        </div>
        {component.revision && (
          <code className="text-xs text-neutral-500 dark:text-neutral-400 bg-neutral-50 dark:bg-neutral-700 px-1.5 py-0.5 rounded">
            {component.revision.slice(0, 7)}
          </code>
        )}
      </div>

      <div className="mt-3 flex items-center justify-between">
        {component.last_sync && (
          <p className="text-xs text-neutral-400 dark:text-neutral-500">
            {formatRelativeTime(component.last_sync)}
          </p>
        )}
        {isOutOfSync && (
          <button
            onClick={() => onSync(component.name)}
            disabled={isSyncing}
            className="ml-auto px-2 py-1 text-xs font-medium text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSyncing ? (
              <span className="flex items-center gap-1">
                <RefreshIcon className="w-3 h-3 animate-spin" />
                Syncing...
              </span>
            ) : (
              'Sync Now'
            )}
          </button>
        )}
      </div>
    </div>
  );
});

function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSecs < 60) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

export default PlatformStatus;
