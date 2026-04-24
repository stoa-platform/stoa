import { useState, useEffect, useCallback } from 'react';
import {
  RefreshCw,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Activity,
  Server,
  RotateCcw,
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';

import { apiService } from '../../services/api';
import { SyncStatusBadge } from '../../components/SyncStatusBadge';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import { EmptyState } from '@stoa/shared/components/EmptyState';
import { TableSkeleton } from '@stoa/shared/components/Skeleton';
import type { GatewayInstance, GatewayInstanceStatus, GatewayDeployment } from '../../types';
import type { Schemas } from '@stoa/shared/api-types';
import { SubNav } from '../../components/SubNav';
import { gatewayTabs } from '../../components/subNavGroups';

const AUTO_REFRESH_INTERVAL = 30_000;

const gatewayStatusConfig: Record<
  GatewayInstanceStatus,
  { icon: typeof CheckCircle2; color: string; bg: string; label: string }
> = {
  online: {
    icon: CheckCircle2,
    color: 'text-green-600 dark:text-green-400',
    bg: 'bg-green-100 dark:bg-green-900/30',
    label: 'Online',
  },
  offline: {
    icon: XCircle,
    color: 'text-red-600 dark:text-red-400',
    bg: 'bg-red-100 dark:bg-red-900/30',
    label: 'Offline',
  },
  degraded: {
    icon: AlertTriangle,
    color: 'text-orange-600 dark:text-orange-400',
    bg: 'bg-orange-100 dark:bg-orange-900/30',
    label: 'Degraded',
  },
  maintenance: {
    icon: Activity,
    color: 'text-blue-600 dark:text-blue-400',
    bg: 'bg-blue-100 dark:bg-blue-900/30',
    label: 'Maintenance',
  },
};

const fallbackStatus = {
  icon: AlertTriangle,
  color: 'text-neutral-600 dark:text-neutral-400',
  bg: 'bg-neutral-100 dark:bg-neutral-700',
  label: 'Unknown',
};

function SummaryCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 px-4 py-3">
      <p className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
        {label}
      </p>
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
    </div>
  );
}

export function DriftDetection() {
  const { isReady, hasRole } = useAuth();
  const toast = useToastActions();
  const [confirm, ConfirmDialog] = useConfirm();

  const [gateways, setGateways] = useState<GatewayInstance[]>([]);
  const [driftedDeployments, setDriftedDeployments] = useState<GatewayDeployment[]>([]);
  const [summary, setSummary] = useState<Schemas['DeploymentStatusSummary'] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [gatewayTypeFilter, setGatewayTypeFilter] = useState<string>('');

  const isAdmin = hasRole('cpi-admin');

  const loadData = useCallback(async () => {
    // Fetch all gateways regardless of environment (consistent with Registry/Overview)
    const typeParam = gatewayTypeFilter ? { gateway_type: gatewayTypeFilter } : {};
    // P1-1: allSettled across 4 slices — we merge drifted+error lists but each
    // one's failure must not wipe the other displayed data.
    const [gatewaysResult, driftedResult, errorResult, summaryResult] = await Promise.allSettled([
      apiService.getGatewayInstances({ page_size: 100 }),
      apiService.getGatewayDeployments({
        sync_status: 'drifted',
        page_size: 100,
        ...typeParam,
      }),
      apiService.getGatewayDeployments({
        sync_status: 'error',
        page_size: 100,
        ...typeParam,
      }),
      apiService.getDeploymentStatusSummary(),
    ]);

    if (gatewaysResult.status === 'fulfilled') {
      setGateways(gatewaysResult.value.items);
    } else {
      console.error('Failed to load gateway instances:', gatewaysResult.reason);
    }
    // Merge drifted + error only if at least one succeeded; preserve prior
    // list otherwise.
    if (driftedResult.status === 'fulfilled' || errorResult.status === 'fulfilled') {
      const drifted = driftedResult.status === 'fulfilled' ? driftedResult.value.items : [];
      const errored = errorResult.status === 'fulfilled' ? errorResult.value.items : [];
      setDriftedDeployments([...drifted, ...errored]);
    }
    if (summaryResult.status === 'fulfilled') {
      setSummary(summaryResult.value);
    } else {
      console.error('Failed to load drift summary:', summaryResult.reason);
    }

    const allFailed = [gatewaysResult, driftedResult, errorResult, summaryResult].every(
      (r) => r.status === 'rejected'
    );
    if (allFailed) {
      const err = gatewaysResult.status === 'rejected' ? gatewaysResult.reason : undefined;
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to load drift data';
      setError(msg);
    } else {
      setError(null);
    }
    setLoading(false);
  }, [gatewayTypeFilter]);

  useEffect(() => {
    if (isReady) loadData();
  }, [isReady, loadData]);

  useEffect(() => {
    if (!isReady) return;
    const interval = setInterval(loadData, AUTO_REFRESH_INTERVAL);
    return () => clearInterval(interval);
  }, [isReady, loadData]);

  const handleHealthCheck = async (id: string, name: string) => {
    setActionLoading(id);
    try {
      await apiService.checkGatewayHealth(id);
      toast.success(`Health check triggered for ${name}`);
      await loadData();
    } catch {
      toast.error(`Failed to check health for ${name}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleForceSync = async (id: string) => {
    const confirmed = await confirm({
      title: 'Force Sync Deployment',
      message: 'This will force re-sync the deployment to the gateway. Continue?',
      confirmLabel: 'Force Sync',
      variant: 'warning',
    });
    if (!confirmed) return;

    setActionLoading(id);
    try {
      await apiService.forceSyncDeployment(id);
      toast.success('Force sync triggered successfully');
      await loadData();
    } catch {
      toast.error('Failed to force sync deployment');
    } finally {
      setActionLoading(null);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="h-8 bg-neutral-200 dark:bg-neutral-700 rounded w-1/4 animate-pulse" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div
              key={i}
              className="h-20 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse"
            />
          ))}
        </div>
        <TableSkeleton />
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6">
        <div className="flex items-center mb-2">
          <XCircle className="w-5 h-5 text-red-500 dark:text-red-400 mr-2" />
          <span className="text-red-800 dark:text-red-300 font-medium">
            Failed to load drift data
          </span>
        </div>
        <p className="text-sm text-red-600 dark:text-red-400 mb-3">{error}</p>
        <button
          onClick={() => {
            setLoading(true);
            loadData();
          }}
          className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-red-700 dark:text-red-300 bg-white dark:bg-neutral-800 border border-red-300 dark:border-red-700 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          Retry
        </button>
      </div>
    );
  }

  const filteredGateways = gatewayTypeFilter
    ? gateways.filter((g) => g.gateway_type === gatewayTypeFilter)
    : gateways;
  const healthyGateways = filteredGateways.filter((g) => g.status === 'online').length;
  const unhealthyGateways = filteredGateways.filter(
    (g) => g.status === 'offline' || g.status === 'degraded'
  ).length;
  const driftedCount = summary?.drifted ?? 0;
  const errorCount = summary?.error ?? 0;

  // Global status: combine gateway health + deployment drift
  const hasHealthIssues = unhealthyGateways > 0;
  const hasDriftIssues = driftedCount > 0 || errorCount > 0;
  const allClear = !hasHealthIssues && !hasDriftIssues;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Drift Detection</h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            Gateway health and deployment sync status
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={gatewayTypeFilter}
            onChange={(e) => {
              setGatewayTypeFilter(e.target.value);
              setLoading(true);
            }}
            className="px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-md text-sm text-neutral-700 dark:text-neutral-300 bg-white dark:bg-neutral-800"
          >
            <option value="">All gateway types</option>
            <option value="stoa_edge_mcp">STOA Edge MCP</option>
            <option value="stoa_sidecar">STOA Link</option>
            <option value="stoa_proxy">STOA Proxy</option>
            <option value="kong">Kong</option>
            <option value="gravitee">Gravitee</option>
            <option value="webmethods">webMethods</option>
            <option value="apigee">Apigee</option>
            <option value="aws_apigateway">AWS API GW</option>
            <option value="azure_apim">Azure APIM</option>
          </select>
          <button
            onClick={loadData}
            className="inline-flex items-center px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-md text-sm font-medium text-neutral-700 dark:text-neutral-300 bg-white dark:bg-neutral-800 hover:bg-neutral-50 dark:hover:bg-neutral-700"
          >
            <RefreshCw className="w-4 h-4 mr-2" />
            Refresh
          </button>
        </div>
      </div>

      <SubNav tabs={gatewayTabs} />

      {/* Global Status Banner */}
      {allClear ? (
        <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg px-4 py-3 flex items-center gap-3">
          <CheckCircle2 className="w-5 h-5 text-green-500 flex-shrink-0" />
          <div>
            <p className="text-sm font-medium text-green-800 dark:text-green-300">
              All systems healthy
            </p>
            <p className="text-xs text-green-600 dark:text-green-400">
              {filteredGateways.length} gateways online, no deployment drift detected
            </p>
          </div>
        </div>
      ) : (
        <div
          className={`border rounded-lg px-4 py-3 flex items-center gap-3 ${
            hasHealthIssues
              ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
              : 'bg-orange-50 dark:bg-orange-900/20 border-orange-200 dark:border-orange-800'
          }`}
        >
          <AlertTriangle
            className={`w-5 h-5 flex-shrink-0 ${hasHealthIssues ? 'text-red-500' : 'text-orange-500'}`}
          />
          <div>
            <p
              className={`text-sm font-medium ${hasHealthIssues ? 'text-red-800 dark:text-red-300' : 'text-orange-800 dark:text-orange-300'}`}
            >
              {hasHealthIssues && hasDriftIssues
                ? 'Gateway health issues and deployment drift detected'
                : hasHealthIssues
                  ? 'Gateway health issues detected'
                  : 'Deployment drift detected'}
            </p>
            <p
              className={`text-xs ${hasHealthIssues ? 'text-red-600 dark:text-red-400' : 'text-orange-600 dark:text-orange-400'}`}
            >
              {hasHealthIssues &&
                `${unhealthyGateways} gateway${unhealthyGateways > 1 ? 's' : ''} degraded or offline`}
              {hasHealthIssues && hasDriftIssues && ' — '}
              {hasDriftIssues &&
                `${driftedCount + errorCount} deployment${driftedCount + errorCount > 1 ? 's' : ''} drifted or errored`}
            </p>
          </div>
        </div>
      )}

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <SummaryCard
          label="Total Gateways"
          value={filteredGateways.length}
          color="text-neutral-900 dark:text-white"
        />
        <SummaryCard
          label="Healthy"
          value={healthyGateways}
          color={
            healthyGateways === filteredGateways.length
              ? 'text-green-600'
              : 'text-neutral-900 dark:text-white'
          }
        />
        <SummaryCard
          label="Degraded / Offline"
          value={unhealthyGateways}
          color={unhealthyGateways > 0 ? 'text-red-600' : 'text-neutral-900 dark:text-white'}
        />
        <SummaryCard
          label="Drifted Deployments"
          value={driftedCount + errorCount}
          color={
            driftedCount + errorCount > 0 ? 'text-orange-600' : 'text-neutral-900 dark:text-white'
          }
        />
      </div>

      {/* Section 1: Gateway Health */}
      <div>
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-white mb-1">
          Gateway Health
        </h2>
        <p className="text-xs text-neutral-500 dark:text-neutral-400 mb-3">
          Process-level health — is each gateway responding to health checks?
        </p>
        {filteredGateways.length === 0 ? (
          <EmptyState
            title={gatewayTypeFilter ? 'No gateways of this type' : 'No gateways registered'}
            description={
              gatewayTypeFilter
                ? 'Clear the filter to see all gateways.'
                : 'Register a gateway to start monitoring.'
            }
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredGateways.map((gw) => {
              const cfg = gatewayStatusConfig[gw.status] || fallbackStatus;
              const StatusIcon = cfg.icon;
              return (
                <div
                  key={gw.id}
                  className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4"
                >
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2 min-w-0">
                      <Server className="w-4 h-4 text-neutral-400 flex-shrink-0" />
                      <span className="font-medium text-neutral-900 dark:text-white text-sm truncate">
                        {gw.display_name || gw.name}
                      </span>
                    </div>
                    <span
                      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium flex-shrink-0 ${cfg.bg} ${cfg.color}`}
                    >
                      <StatusIcon className="w-3 h-3" />
                      {cfg.label}
                    </span>
                  </div>
                  <div className="text-xs text-neutral-500 dark:text-neutral-400 space-y-1">
                    <p>Type: {gw.gateway_type}</p>
                    {gw.last_health_check && (
                      <p>Last check: {new Date(gw.last_health_check).toLocaleString()}</p>
                    )}
                  </div>
                  {isAdmin && (
                    <button
                      onClick={() => handleHealthCheck(gw.id, gw.display_name || gw.name)}
                      disabled={actionLoading === gw.id}
                      className="mt-3 inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-900/20 rounded-md hover:bg-indigo-100 dark:hover:bg-indigo-900/40 disabled:opacity-50 transition-colors"
                    >
                      <Activity className="w-3 h-3" />
                      {actionLoading === gw.id ? 'Checking...' : 'Check Health'}
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Section 2: Deployment Sync */}
      <div>
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-white mb-1">
          Deployment Sync
        </h2>
        <p className="text-xs text-neutral-500 dark:text-neutral-400 mb-3">
          Config-level sync — are API configurations on gateways matching the desired state?
        </p>
        {driftedDeployments.length === 0 ? (
          <div className="bg-neutral-50 dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-6 text-center">
            <CheckCircle2 className="w-6 h-6 text-green-500 mx-auto mb-2" />
            <p className="text-sm text-neutral-700 dark:text-neutral-300">
              No deployment drift detected
            </p>
            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
              All API configurations are in sync with their desired state.
            </p>
          </div>
        ) : (
          <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 overflow-hidden">
            <table className="min-w-full divide-y divide-neutral-200 dark:divide-neutral-700">
              <thead className="bg-neutral-50 dark:bg-neutral-900">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                    API
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                    Gateway
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                    Status
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                    Error
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                    Last Sync
                  </th>
                  {isAdmin && (
                    <th className="px-4 py-3 text-right text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                      Actions
                    </th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-200 dark:divide-neutral-700">
                {driftedDeployments.map((dep) => (
                  <tr key={dep.id}>
                    <td className="px-4 py-3 text-sm text-neutral-900 dark:text-white">
                      {String(dep.desired_state?.['api_name'] ?? dep.api_catalog_id)}
                    </td>
                    <td className="px-4 py-3 text-sm text-neutral-500 dark:text-neutral-400">
                      {dep.gateway_instance_id}
                    </td>
                    <td className="px-4 py-3">
                      <SyncStatusBadge status={dep.sync_status} />
                    </td>
                    <td className="px-4 py-3 text-sm text-red-600 dark:text-red-400 max-w-xs truncate">
                      {dep.sync_error || '\u2014'}
                    </td>
                    <td className="px-4 py-3 text-sm text-neutral-500 dark:text-neutral-400">
                      {dep.last_sync_attempt
                        ? new Date(dep.last_sync_attempt).toLocaleString()
                        : '\u2014'}
                    </td>
                    {isAdmin && (
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => handleForceSync(dep.id)}
                          disabled={actionLoading === dep.id}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-orange-700 dark:text-orange-400 bg-orange-50 dark:bg-orange-900/20 rounded-md hover:bg-orange-100 dark:hover:bg-orange-900/40 disabled:opacity-50 transition-colors"
                        >
                          <RotateCcw className="w-3 h-3" />
                          {actionLoading === dep.id ? 'Syncing...' : 'Force Sync'}
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {ConfirmDialog}
    </div>
  );
}
