// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * PlatformStatus Component (CAB-654)
 *
 * Displays GitOps sync status for platform components via Argo CD.
 * Shows sync status, health, recent deployment events, and external links.
 */
import { useState } from 'react';
import { usePlatformStatus, useSyncComponent } from '../hooks/usePlatformStatus';
import { ComponentStatus } from '../services/api';

// Status color mappings
const syncStatusColors: Record<string, string> = {
  Synced: 'text-green-600 bg-green-50',
  OutOfSync: 'text-yellow-600 bg-yellow-50',
  Unknown: 'text-gray-600 bg-gray-50',
  Error: 'text-red-600 bg-red-50',
  NotFound: 'text-gray-400 bg-gray-50',
};

const healthStatusColors: Record<string, string> = {
  Healthy: 'text-green-600',
  Progressing: 'text-blue-600',
  Degraded: 'text-red-600',
  Suspended: 'text-yellow-600',
  Missing: 'text-gray-400',
  Unknown: 'text-gray-600',
};

const overallStatusConfig: Record<string, { color: string; bg: string; label: string }> = {
  healthy: { color: 'text-green-700', bg: 'bg-green-100', label: 'All Systems Operational' },
  degraded: { color: 'text-red-700', bg: 'bg-red-100', label: 'System Degraded' },
  syncing: { color: 'text-blue-700', bg: 'bg-blue-100', label: 'Sync In Progress' },
  unknown: { color: 'text-gray-700', bg: 'bg-gray-100', label: 'Status Unknown' },
};

// Icons
function CheckCircleIcon({ className = '' }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

function ExclamationCircleIcon({ className = '' }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

function RefreshIcon({ className = '' }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
    </svg>
  );
}

function GitBranchIcon({ className = '' }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122" />
    </svg>
  );
}

function ExternalLinkIcon({ className = '' }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
    </svg>
  );
}

interface PlatformStatusProps {
  compact?: boolean;
  onStatusChange?: (status: string) => void;
}

export function PlatformStatus({ compact = false, onStatusChange }: PlatformStatusProps) {
  const { data: status, isLoading, error, refetch } = usePlatformStatus({
    refetchInterval: 30000, // Refresh every 30 seconds
  });
  const syncMutation = useSyncComponent();
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  // Update lastUpdated when data changes
  if (status && !lastUpdated) {
    setLastUpdated(new Date());
  }

  // Notify parent of status changes
  if (status && onStatusChange) {
    onStatusChange(status.gitops.status);
  }

  const handleRefresh = () => {
    refetch();
    setLastUpdated(new Date());
  };

  const handleSync = async (componentName: string) => {
    try {
      await syncMutation.mutateAsync(componentName);
      setLastUpdated(new Date());
    } catch (err) {
      console.error('Failed to sync component:', err);
    }
  };

  if (isLoading && !status) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center justify-center">
          <RefreshIcon className="w-5 h-5 animate-spin text-gray-400" />
          <span className="ml-2 text-gray-500">Loading platform status...</span>
        </div>
      </div>
    );
  }

  if (error && !status) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center gap-2 text-red-600">
          <ExclamationCircleIcon className="w-5 h-5" />
          <span>Failed to load platform status</span>
          <button
            onClick={handleRefresh}
            className="ml-auto text-sm text-blue-600 hover:text-blue-800"
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
      <div className={`rounded-lg p-3 ${overallConfig.bg}`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {status.gitops.status === 'healthy' ? (
              <CheckCircleIcon className={`w-5 h-5 ${overallConfig.color}`} />
            ) : (
              <ExclamationCircleIcon className={`w-5 h-5 ${overallConfig.color}`} />
            )}
            <span className={`font-medium ${overallConfig.color}`}>
              {overallConfig.label}
            </span>
          </div>
          <button
            onClick={handleRefresh}
            disabled={isLoading}
            className="p-1 hover:bg-white/50 rounded transition-colors"
            title="Refresh status"
          >
            <RefreshIcon className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-gray-900">Platform Status</h3>
            <p className="text-sm text-gray-500">GitOps sync status via Argo CD</p>
          </div>
          <div className="flex items-center gap-3">
            <span className={`px-3 py-1 rounded-full text-sm font-medium ${overallConfig.bg} ${overallConfig.color}`}>
              {overallConfig.label}
            </span>
            <button
              onClick={handleRefresh}
              disabled={isLoading}
              className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
              title="Refresh status"
            >
              <RefreshIcon className={`w-5 h-5 text-gray-600 ${isLoading ? 'animate-spin' : ''}`} />
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

        {/* Recent Events */}
        {status.events.length > 0 && (
          <div className="mt-6 pt-6 border-t border-gray-200">
            <h4 className="text-sm font-medium text-gray-700 mb-3">Recent Deployments</h4>
            <div className="space-y-2">
              {status.events.slice(0, 5).map((event, idx) => (
                <div
                  key={`${event.component}-${event.timestamp}-${idx}`}
                  className="flex items-center justify-between text-sm"
                >
                  <div className="flex items-center gap-2">
                    <GitBranchIcon className="w-4 h-4 text-gray-400" />
                    <span className="text-gray-900">{event.component}</span>
                    <code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">
                      {event.revision}
                    </code>
                  </div>
                  <span className="text-gray-500 text-xs">
                    {formatRelativeTime(event.timestamp)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* External Links */}
        {status.external_links && (
          <div className="mt-6 pt-6 border-t border-gray-200">
            <h4 className="text-sm font-medium text-gray-700 mb-3">Quick Links</h4>
            <div className="flex flex-wrap gap-2">
              <a
                href={status.external_links.argocd}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
              >
                <ExternalLinkIcon className="w-4 h-4" />
                ArgoCD
              </a>
              <a
                href={status.external_links.grafana}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
              >
                <ExternalLinkIcon className="w-4 h-4" />
                Grafana
              </a>
              <a
                href={status.external_links.prometheus}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
              >
                <ExternalLinkIcon className="w-4 h-4" />
                Prometheus
              </a>
              <a
                href={status.external_links.logs}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
              >
                <ExternalLinkIcon className="w-4 h-4" />
                Logs
              </a>
            </div>
          </div>
        )}

        {/* Last Updated */}
        {lastUpdated && (
          <div className="mt-4 pt-4 border-t border-gray-100 text-xs text-gray-400 text-right">
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

function ComponentCard({ component, onSync, isSyncing }: ComponentCardProps) {
  const syncColor = syncStatusColors[component.sync_status] || syncStatusColors.Unknown;
  const healthColor = healthStatusColors[component.health_status] || healthStatusColors.Unknown;
  const isOutOfSync = component.sync_status === 'OutOfSync';

  return (
    <div className="border border-gray-200 rounded-lg p-4 hover:border-gray-300 transition-colors">
      <div className="flex items-start justify-between">
        <div>
          <h4 className="font-medium text-gray-900">{component.display_name}</h4>
          <p className="text-xs text-gray-500 mt-0.5">{component.name}</p>
        </div>
        <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${syncColor}`}>
          {component.sync_status}
        </span>
      </div>

      <div className="mt-3 flex items-center justify-between text-sm">
        <div className="flex items-center gap-1.5">
          <span className={`w-2 h-2 rounded-full ${healthColor.replace('text-', 'bg-')}`} />
          <span className={healthColor}>{component.health_status}</span>
        </div>
        {component.revision && (
          <code className="text-xs text-gray-500 bg-gray-50 px-1.5 py-0.5 rounded">
            {component.revision}
          </code>
        )}
      </div>

      {component.message && (
        <p className="mt-2 text-xs text-red-600 bg-red-50 rounded p-2">
          {component.message}
        </p>
      )}

      <div className="mt-3 flex items-center justify-between">
        {component.last_sync && (
          <p className="text-xs text-gray-400">
            Last sync: {formatRelativeTime(component.last_sync)}
          </p>
        )}
        {isOutOfSync && (
          <button
            onClick={() => onSync(component.name)}
            disabled={isSyncing}
            className="ml-auto px-2 py-1 text-xs font-medium text-blue-600 hover:text-blue-800 hover:bg-blue-50 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
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
}

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
