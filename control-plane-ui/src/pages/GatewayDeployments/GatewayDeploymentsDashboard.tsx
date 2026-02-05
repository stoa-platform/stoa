import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Plus, Trash2, RotateCcw } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { apiService } from '../../services/api';
import { SyncStatusBadge } from '../../components/SyncStatusBadge';
import { DeployAPIDialog } from './DeployAPIDialog';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import { EmptyState } from '@stoa/shared/components/EmptyState';
import { TableSkeleton } from '@stoa/shared/components/Skeleton';
import type { GatewayDeployment, DeploymentStatusSummary } from '../../types';

const PAGE_SIZE = 20;
const AUTO_REFRESH_INTERVAL = 30_000;

const statusFilterOptions: { value: string; label: string }[] = [
  { value: '', label: 'All Statuses' },
  { value: 'pending', label: 'Pending' },
  { value: 'syncing', label: 'Syncing' },
  { value: 'synced', label: 'Synced' },
  { value: 'drifted', label: 'Drifted' },
  { value: 'error', label: 'Error' },
  { value: 'deleting', label: 'Deleting' },
];

function StatCard({
  label,
  count,
  color,
}: {
  label: string;
  count: number;
  color: string;
}) {
  return (
    <div className="bg-white rounded-lg shadow px-4 py-3">
      <p className="text-xs font-medium text-gray-500 uppercase">{label}</p>
      <p className={`text-2xl font-bold ${color}`}>{count}</p>
    </div>
  );
}

export function GatewayDeploymentsDashboard() {
  const { isReady } = useAuth();
  const toast = useToastActions();
  const [confirm, ConfirmDialog] = useConfirm();
  const [deployments, setDeployments] = useState<GatewayDeployment[]>([]);
  const [summary, setSummary] = useState<DeploymentStatusSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [showDeployDialog, setShowDeployDialog] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const params: Record<string, any> = { page: currentPage, page_size: PAGE_SIZE };
      if (statusFilter) params.sync_status = statusFilter;

      const [deploymentsResult, summaryResult] = await Promise.all([
        apiService.getGatewayDeployments(params),
        apiService.getDeploymentStatusSummary(),
      ]);

      setDeployments(deploymentsResult.items);
      setTotal(deploymentsResult.total);
      setSummary(summaryResult);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load deployments');
    } finally {
      setLoading(false);
    }
  }, [currentPage, statusFilter]);

  useEffect(() => {
    if (isReady) loadData();
  }, [isReady, loadData]);

  // Auto-refresh
  useEffect(() => {
    if (!isReady) return;
    const interval = setInterval(loadData, AUTO_REFRESH_INTERVAL);
    return () => clearInterval(interval);
  }, [isReady, loadData]);

  // Reset page on filter change
  useEffect(() => {
    setCurrentPage(1);
  }, [statusFilter]);

  const handleForceSync = async (id: string) => {
    setActionLoading(id);
    try {
      await apiService.forceSyncDeployment(id);
      await loadData();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Force sync failed');
    } finally {
      setActionLoading(null);
    }
  };

  const handleUndeploy = useCallback(async (id: string, apiName?: string) => {
    const confirmed = await confirm({
      title: 'Undeploy API',
      message: `Are you sure you want to undeploy "${apiName || 'this API'}"? This will remove it from the gateway.`,
      confirmLabel: 'Undeploy',
      variant: 'danger',
    });
    if (!confirmed) return;

    setActionLoading(id);
    try {
      await apiService.undeployFromGateway(id);
      toast.success(`${apiName || 'API'} undeployed successfully`);
      await loadData();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Undeploy failed');
    } finally {
      setActionLoading(null);
    }
  }, [confirm, toast, loadData]);

  const handleDeployed = () => {
    setShowDeployDialog(false);
    loadData();
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  const formatTime = (iso?: string) => {
    if (!iso) return '-';
    const d = new Date(iso);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return 'just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    return d.toLocaleDateString();
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Gateway Deployments</h1>
          <p className="text-sm text-gray-500 mt-1">
            Manage API deployments across gateway instances
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={loadData}
            className="flex items-center gap-2 border border-gray-300 text-gray-700 px-3 py-2 rounded-lg text-sm hover:bg-gray-50"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
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
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
          <StatCard label="Synced" count={summary.synced} color="text-green-600" />
          <StatCard label="Pending" count={summary.pending} color="text-yellow-600" />
          <StatCard label="Drifted" count={summary.drifted} color="text-orange-600" />
          <StatCard label="Error" count={summary.error} color="text-red-600" />
          <StatCard label="Syncing" count={summary.syncing} color="text-blue-600" />
          <StatCard label="Total" count={summary.total} color="text-gray-900" />
        </div>
      )}

      {/* Filter */}
      <div className="flex items-center gap-4">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500"
        >
          {statusFilterOptions.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <span className="text-sm text-gray-500">
          {total} deployment{total !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center justify-between">
          <span className="text-sm">{error}</span>
          <button onClick={() => setError(null)} className="text-red-500 hover:text-red-700">
            &times;
          </button>
        </div>
      )}

      {/* Table */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        {loading ? (
          <TableSkeleton rows={5} columns={6} />
        ) : deployments.length === 0 ? (
          <EmptyState
            variant="deployments"
            title="No deployments found"
            description="Deploy an API to a gateway to get started."
            action={{ label: 'Deploy API', onClick: () => setShowDeployDialog(true) }}
          />
        ) : (
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  API
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Gateway Resource
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Last Sync
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Attempts
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {deployments.map((dep) => (
                <tr key={dep.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4">
                    <div>
                      <p className="text-sm font-medium text-gray-900">
                        {(dep.desired_state as any)?.api_name || dep.api_catalog_id.slice(0, 8)}
                      </p>
                      <p className="text-xs text-gray-500">
                        {(dep.desired_state as any)?.tenant_id || '-'}
                      </p>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <SyncStatusBadge status={dep.sync_status} />
                    {dep.sync_error && (
                      <p className="text-xs text-red-500 mt-1 max-w-xs truncate" title={dep.sync_error}>
                        {dep.sync_error}
                      </p>
                    )}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500 font-mono">
                    {dep.gateway_resource_id || '-'}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">
                    {formatTime(dep.last_sync_attempt)}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">{dep.sync_attempts}</td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => handleForceSync(dep.id)}
                        disabled={actionLoading === dep.id}
                        className="inline-flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800 disabled:opacity-50"
                        title="Force sync"
                      >
                        <RotateCcw className="h-4 w-4" />
                        Sync
                      </button>
                      <button
                        onClick={() => handleUndeploy(dep.id, (dep.desired_state as any)?.api_name)}
                        disabled={actionLoading === dep.id}
                        className="inline-flex items-center gap-1 text-sm text-red-600 hover:text-red-800 disabled:opacity-50"
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
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between border-t px-6 py-3">
            <p className="text-sm text-gray-500">
              Page {currentPage} of {totalPages}
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage <= 1}
                className="border border-gray-300 text-gray-700 px-3 py-1 rounded text-sm disabled:opacity-50 hover:bg-gray-50"
              >
                Previous
              </button>
              <button
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage >= totalPages}
                className="border border-gray-300 text-gray-700 px-3 py-1 rounded text-sm disabled:opacity-50 hover:bg-gray-50"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Deploy Dialog */}
      {showDeployDialog && (
        <DeployAPIDialog
          onClose={() => setShowDeployDialog(false)}
          onDeployed={handleDeployed}
        />
      )}

      {ConfirmDialog}
    </div>
  );
}
