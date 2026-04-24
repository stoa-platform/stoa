/**
 * API Deployments Dashboard — Top-level aggregated view (CAB-1888)
 *
 * Shows all gateway deployments across all APIs with environment/status/gateway filters.
 * Replaces the gateway-scoped view with an API-centric deployment view.
 */

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { RefreshCw, Plus, Trash2, RotateCcw } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { useEnvironment } from '../../contexts/EnvironmentContext';
import { apiService } from '../../services/api';
import { SyncStatusBadge } from '../../components/SyncStatusBadge';
import { DeployAPIDialog } from '../GatewayDeployments/DeployAPIDialog';
import { DeploymentDetailDrawer } from './DeploymentDetailDrawer';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import { EmptyState } from '@stoa/shared/components/EmptyState';
import { TableSkeleton } from '@stoa/shared/components/Skeleton';
import { StatCard } from '@stoa/shared/components/StatCard';
import { SubNav } from '../../components/SubNav';
import { apiDeploymentTabs } from '../../components/subNavGroups';
import type { GatewayDeployment } from '../../types';
import type { Schemas } from '@stoa/shared/api-types';
import { getEnvLabel, normalizeEnvironment } from '@stoa/shared/constants/environments';
import type { CanonicalEnvironment } from '@stoa/shared/constants/environments';

const PAGE_SIZE = 20;
const AUTO_REFRESH_INTERVAL = 30_000;
type EnvironmentFilter = '' | 'dev' | 'staging' | 'production';

const statusFilterOptions = [
  { value: '', label: 'All Statuses' },
  { value: 'pending', label: 'Pending' },
  { value: 'syncing', label: 'Syncing' },
  { value: 'synced', label: 'Synced' },
  { value: 'drifted', label: 'Drifted' },
  { value: 'error', label: 'Error' },
  { value: 'deleting', label: 'Deleting' },
];

function toApiEnvironment(env: string): Exclude<EnvironmentFilter, ''> {
  const canonical = normalizeEnvironment(env);
  if (canonical === 'development') return 'dev';
  return canonical;
}

function toContextEnvironment(env: string): 'dev' | 'staging' | 'prod' {
  const canonical = normalizeEnvironment(env);
  if (canonical === 'production') return 'prod';
  if (canonical === 'staging') return 'staging';
  return 'dev';
}

function canonicalSortValue(env: CanonicalEnvironment): number {
  if (env === 'development') return 0;
  if (env === 'staging') return 1;
  return 2;
}

export function ApiDeploymentsDashboard() {
  const { isReady } = useAuth();
  const { activeEnvironment, environments, switchEnvironment } = useEnvironment();
  const toast = useToastActions();
  const [confirm, ConfirmDialog] = useConfirm();
  const [deployments, setDeployments] = useState<GatewayDeployment[]>([]);
  const [summary, setSummary] = useState<Schemas['DeploymentStatusSummary'] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [envFilter, setEnvFilter] = useState<EnvironmentFilter>(
    toApiEnvironment(activeEnvironment)
  );
  const [currentPage, setCurrentPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [showDeployDialog, setShowDeployDialog] = useState(false);
  const [selectedDeployment, setSelectedDeployment] = useState<GatewayDeployment | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const latestLoadRef = useRef(0);

  const envFilterOptions = useMemo(() => {
    const seen = new Set<CanonicalEnvironment>();
    const options = environments
      .map((env) => normalizeEnvironment(env.name))
      .filter((env) => {
        if (seen.has(env)) return false;
        seen.add(env);
        return true;
      })
      .sort((a, b) => canonicalSortValue(a) - canonicalSortValue(b))
      .map((env) => ({
        value: toApiEnvironment(env),
        label: getEnvLabel(env),
      }));

    return [{ value: '', label: 'All Environments' }, ...options];
  }, [environments]);

  useEffect(() => {
    setEnvFilter(toApiEnvironment(activeEnvironment));
    setCurrentPage(1);
  }, [activeEnvironment]);

  const loadData = useCallback(async () => {
    const requestId = latestLoadRef.current + 1;
    latestLoadRef.current = requestId;
    const params: Record<string, string | number> = { page: currentPage, page_size: PAGE_SIZE };
    if (statusFilter) params.sync_status = statusFilter;
    if (envFilter) params.environment = envFilter;

    // P1-1: allSettled — partial failure preserves the other slice.
    const [deploymentsResult, summaryResult] = await Promise.allSettled([
      apiService.getGatewayDeployments(params),
      apiService.getDeploymentStatusSummary(),
    ]);

    if (requestId !== latestLoadRef.current) return;

    if (deploymentsResult.status === 'fulfilled') {
      setDeployments(deploymentsResult.value.items);
      setTotal(deploymentsResult.value.total);
    } else {
      console.error('Failed to load API deployments:', deploymentsResult.reason);
    }
    if (summaryResult.status === 'fulfilled') {
      setSummary(summaryResult.value);
    } else {
      console.error('Failed to load deployment summary:', summaryResult.reason);
    }

    if (deploymentsResult.status === 'rejected' && summaryResult.status === 'rejected') {
      const err = deploymentsResult.reason;
      const message = err instanceof Error ? err.message : 'Failed to load deployments';
      setError(message);
    } else {
      setError(null);
    }
    setLoading(false);
  }, [currentPage, statusFilter, envFilter]);

  useEffect(() => {
    if (isReady) loadData();
  }, [isReady, loadData]);

  // Auto-refresh
  useEffect(() => {
    if (!isReady) return;
    const interval = setInterval(loadData, AUTO_REFRESH_INTERVAL);
    return () => clearInterval(interval);
  }, [isReady, loadData]);

  const handleForceSync = async (id: string) => {
    setActionLoading(id);
    try {
      await apiService.forceSyncDeployment(id);
      toast.success('Re-sync triggered');
      await loadData();
    } catch {
      toast.error('Failed to trigger re-sync');
    } finally {
      setActionLoading(null);
    }
  };

  const handleUndeploy = async (id: string) => {
    const confirmed = await confirm({
      title: 'Undeploy API',
      message: 'Remove this API from the gateway? The gateway will stop proxying this API.',
      confirmLabel: 'Undeploy',
      variant: 'danger',
    });
    if (!confirmed) return;

    setActionLoading(id);
    try {
      await apiService.undeployFromGateway(id);
      toast.success('Undeploy initiated');
      await loadData();
    } catch {
      toast.error('Failed to undeploy');
    } finally {
      setActionLoading(null);
    }
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="space-y-6">
      {ConfirmDialog}
      <SubNav tabs={apiDeploymentTabs} />

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">API Deployments</h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            All API deployments across gateways and environments
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadData}
            className="p-2 rounded-lg border border-neutral-300 dark:border-neutral-600 text-neutral-600 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-700"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
          <button
            onClick={() => setShowDeployDialog(true)}
            className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700"
          >
            <Plus className="h-4 w-4" />
            Deploy API
          </button>
        </div>
      </div>

      {/* Status Summary Cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
          <StatCard label="Total" value={summary.total} />
          <StatCard label="Synced" value={summary.synced} colorClass="text-green-600" />
          <StatCard label="Pending" value={summary.pending} colorClass="text-yellow-600" />
          <StatCard label="Syncing" value={summary.syncing} colorClass="text-blue-600" />
          <StatCard label="Drifted" value={summary.drifted} colorClass="text-orange-600" />
          <StatCard label="Error" value={summary.error} colorClass="text-red-600" />
          <StatCard label="Deleting" value={summary.deleting} />
        </div>
      )}

      {/* Filters */}
      <div className="flex items-center gap-3">
        <select
          value={envFilter}
          onChange={(e) => {
            const nextEnv = e.target.value as EnvironmentFilter;
            setEnvFilter(nextEnv);
            setCurrentPage(1);
            if (nextEnv) switchEnvironment(toContextEnvironment(nextEnv));
          }}
          className="border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-neutral-700 dark:text-white"
        >
          {envFilterOptions.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setCurrentPage(1);
          }}
          className="border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-neutral-700 dark:text-white"
        >
          {statusFilterOptions.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg text-sm">
          {error}
        </div>
      )}

      {/* Table */}
      {loading ? (
        <TableSkeleton rows={5} columns={5} />
      ) : deployments.length === 0 ? (
        <EmptyState
          title="No deployments found"
          description="Deploy an API to get started"
          action={{
            label: 'Deploy API',
            onClick: () => setShowDeployDialog(true),
          }}
        />
      ) : (
        <>
          <div className="overflow-x-auto border border-neutral-200 dark:border-neutral-700 rounded-lg">
            <table className="w-full text-sm">
              <thead className="bg-neutral-50 dark:bg-neutral-800/50">
                <tr>
                  <th className="text-left px-4 py-3 text-neutral-500 dark:text-neutral-400 font-medium">
                    API
                  </th>
                  <th className="text-left px-4 py-3 text-neutral-500 dark:text-neutral-400 font-medium">
                    Gateway
                  </th>
                  <th className="text-left px-4 py-3 text-neutral-500 dark:text-neutral-400 font-medium">
                    Environment
                  </th>
                  <th className="text-left px-4 py-3 text-neutral-500 dark:text-neutral-400 font-medium">
                    Status
                  </th>
                  <th className="text-left px-4 py-3 text-neutral-500 dark:text-neutral-400 font-medium">
                    Last Sync
                  </th>
                  <th className="text-right px-4 py-3 text-neutral-500 dark:text-neutral-400 font-medium">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
                {deployments.map((d) => (
                  <tr
                    key={d.id}
                    onClick={() => setSelectedDeployment(d)}
                    className="hover:bg-neutral-50 dark:hover:bg-neutral-800/30 cursor-pointer"
                  >
                    <td className="px-4 py-3 text-neutral-900 dark:text-white font-medium">
                      {(d.desired_state?.api_name as string) || d.api_catalog_id?.slice(0, 8)}
                    </td>
                    <td className="px-4 py-3 text-neutral-600 dark:text-neutral-300">
                      {d.gateway_name || d.gateway_instance_id?.slice(0, 8)}
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-xs font-semibold uppercase px-2 py-0.5 rounded bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400">
                        {d.gateway_environment || '—'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <SyncStatusBadge status={d.sync_status} />
                    </td>
                    <td className="px-4 py-3 text-xs text-neutral-500 dark:text-neutral-400">
                      {d.last_sync_success ? new Date(d.last_sync_success).toLocaleString() : '—'}
                    </td>
                    <td className="px-4 py-3 text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center justify-end gap-1">
                        {(d.sync_status === 'drifted' || d.sync_status === 'error') && (
                          <button
                            onClick={() => handleForceSync(d.id)}
                            disabled={actionLoading === d.id}
                            className="p-1.5 rounded text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20"
                            title="Re-sync"
                          >
                            <RotateCcw className="h-4 w-4" />
                          </button>
                        )}
                        <button
                          onClick={() => handleUndeploy(d.id)}
                          disabled={actionLoading === d.id}
                          className="p-1.5 rounded text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20"
                          title="Undeploy"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between">
              <span className="text-sm text-neutral-500 dark:text-neutral-400">
                Page {currentPage} of {totalPages} ({total} total)
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="px-3 py-1.5 text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg disabled:opacity-50"
                >
                  Previous
                </button>
                <button
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className="px-3 py-1.5 text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg disabled:opacity-50"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* Deploy Dialog */}
      {showDeployDialog && (
        <DeployAPIDialog
          onClose={() => setShowDeployDialog(false)}
          onDeployed={() => {
            setShowDeployDialog(false);
            loadData();
            toast.success('Deployment initiated');
          }}
        />
      )}

      {/* Detail Drawer */}
      {selectedDeployment && (
        <DeploymentDetailDrawer
          deployment={selectedDeployment}
          onClose={() => setSelectedDeployment(null)}
          onAction={() => {
            setSelectedDeployment(null);
            loadData();
          }}
        />
      )}
    </div>
  );
}
