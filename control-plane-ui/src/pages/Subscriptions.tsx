import { useState, useEffect, useMemo, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiService } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { useEnvironmentMode } from '../hooks/useEnvironmentMode';
import { useDebounce } from '../hooks/useDebounce';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import { EmptyState } from '@stoa/shared/components/EmptyState';
import { TableSkeleton, StatCardSkeletonRow } from '@stoa/shared/components/Skeleton';
import { Button } from '@stoa/shared/components/Button';
import { Clock, TrendingUp, Users, Timer } from 'lucide-react';
import type { Subscription, SubscriptionStatus, SubscriptionStats } from '../types';
import { SubNav } from '../components/SubNav';
import { apiCatalogTabs } from '../components/subNavGroups';

const PAGE_SIZE = 20;

const STATUS_TABS: { key: SubscriptionStatus | 'all'; label: string }[] = [
  { key: 'pending', label: 'Pending' },
  { key: 'active', label: 'Active' },
  { key: 'suspended', label: 'Suspended' },
  { key: 'revoked', label: 'Revoked' },
  { key: 'rejected', label: 'Rejected' },
  { key: 'all', label: 'All' },
];

const statusColors: Record<SubscriptionStatus, string> = {
  pending: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  active: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  suspended: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  revoked: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  expired: 'bg-neutral-100 text-neutral-800 dark:bg-neutral-700/30 dark:text-neutral-400',
  rejected: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
};

const provisioningColors: Record<string, string> = {
  none: 'bg-neutral-100 text-neutral-700 dark:bg-neutral-700/30 dark:text-neutral-300',
  pending: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  provisioning: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  ready: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  failed: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  deprovisioning: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  deprovisioned: 'bg-neutral-100 text-neutral-700 dark:bg-neutral-700/30 dark:text-neutral-300',
};

export function Subscriptions() {
  const { isReady } = useAuth();
  const { canEdit } = useEnvironmentMode();
  const toast = useToastActions();
  const [confirm, ConfirmDialog] = useConfirm();

  // State
  const [selectedTenant, setSelectedTenant] = useState<string>('');
  const [activeTab, setActiveTab] = useState<SubscriptionStatus | 'all'>('pending');
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [rejectModalOpen, setRejectModalOpen] = useState(false);
  const [rejectTarget, setRejectTarget] = useState<Subscription | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [bulkRejectOpen, setBulkRejectOpen] = useState(false);
  const [bulkRejectReason, setBulkRejectReason] = useState('');
  const [actionLoading, setActionLoading] = useState(false);

  const debouncedSearch = useDebounce(searchQuery, 300);

  // Fetch tenants
  const { data: tenants = [], isLoading: tenantsLoading } = useQuery({
    queryKey: ['tenants'],
    queryFn: () => apiService.getTenants(),
    enabled: isReady,
    staleTime: 5 * 60 * 1000,
  });

  // Auto-select first tenant
  useEffect(() => {
    if (tenants.length > 0 && !selectedTenant) {
      setSelectedTenant(tenants[0].id);
    }
  }, [tenants, selectedTenant]);

  // Load subscriptions
  const loadSubscriptions = useCallback(
    async (tenantId: string, status: SubscriptionStatus | 'all', page: number) => {
      try {
        setLoading(true);
        setError(null);
        const statusParam = status === 'all' ? undefined : status;
        const data = await apiService.getSubscriptions(tenantId, statusParam, page, PAGE_SIZE);
        setSubscriptions(data.items);
        setTotal(data.total);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load subscriptions');
        setSubscriptions([]);
        setTotal(0);
      } finally {
        setLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    if (selectedTenant) {
      loadSubscriptions(selectedTenant, activeTab, currentPage);
    }
  }, [selectedTenant, activeTab, currentPage, loadSubscriptions]);

  // Fetch stats
  const { data: stats } = useQuery({
    queryKey: ['subscription-stats', selectedTenant],
    queryFn: () => apiService.getSubscriptionStats(selectedTenant),
    enabled: isReady && !!selectedTenant,
    staleTime: 30 * 1000,
  });

  // Reset page on tab/search change
  useEffect(() => {
    setCurrentPage(1);
    setSelectedIds(new Set());
  }, [activeTab, debouncedSearch, selectedTenant]);

  // Client-side search filter
  const filteredSubscriptions = useMemo(() => {
    if (!debouncedSearch) return subscriptions;
    const q = debouncedSearch.toLowerCase();
    return subscriptions.filter(
      (s) =>
        s.application_name.toLowerCase().includes(q) ||
        s.subscriber_email.toLowerCase().includes(q) ||
        s.api_name.toLowerCase().includes(q)
    );
  }, [subscriptions, debouncedSearch]);

  const totalPages = Math.ceil(total / PAGE_SIZE);

  // Actions
  const reload = () => loadSubscriptions(selectedTenant, activeTab, currentPage);

  async function handleApprove(sub: Subscription) {
    const ok = await confirm({
      title: 'Approve Subscription',
      message: `Approve ${sub.application_name}'s subscription to ${sub.api_name}?`,
      confirmLabel: 'Approve',
    });
    if (!ok) return;
    try {
      setActionLoading(true);
      await apiService.approveSubscription(sub.id);
      toast.success('Subscription approved');
      reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to approve subscription');
    } finally {
      setActionLoading(false);
    }
  }

  function openRejectModal(sub: Subscription) {
    setRejectTarget(sub);
    setRejectReason('');
    setRejectModalOpen(true);
  }

  async function handleReject() {
    if (!rejectTarget || !rejectReason.trim()) return;
    try {
      setActionLoading(true);
      await apiService.rejectSubscription(rejectTarget.id, rejectReason.trim());
      toast.success('Subscription rejected');
      setRejectModalOpen(false);
      setRejectTarget(null);
      reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to reject subscription');
    } finally {
      setActionLoading(false);
    }
  }

  async function handleSuspend(sub: Subscription) {
    const ok = await confirm({
      title: 'Suspend Subscription',
      message: `Suspend ${sub.application_name}'s subscription to ${sub.api_name}?`,
      confirmLabel: 'Suspend',
    });
    if (!ok) return;
    try {
      setActionLoading(true);
      await apiService.suspendSubscription(sub.id);
      toast.success('Subscription suspended');
      reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to suspend subscription');
    } finally {
      setActionLoading(false);
    }
  }

  async function handleReactivate(sub: Subscription) {
    const ok = await confirm({
      title: 'Reactivate Subscription',
      message: `Reactivate ${sub.application_name}'s subscription to ${sub.api_name}?`,
      confirmLabel: 'Reactivate',
    });
    if (!ok) return;
    try {
      setActionLoading(true);
      await apiService.reactivateSubscription(sub.id);
      toast.success('Subscription reactivated');
      reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to reactivate subscription');
    } finally {
      setActionLoading(false);
    }
  }

  async function handleRevoke(sub: Subscription) {
    const reason = window.prompt(
      `Reason for revoking ${sub.application_name}'s subscription to ${sub.api_name}:`
    );
    if (!reason?.trim()) return;

    const ok = await confirm({
      title: 'Revoke Subscription',
      message: `Permanently revoke ${sub.application_name}'s subscription to ${sub.api_name}?`,
      confirmLabel: 'Revoke',
    });
    if (!ok) return;

    try {
      setActionLoading(true);
      await apiService.revokeSubscription(sub.id, reason.trim());
      toast.success('Subscription revoked');
      reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to revoke subscription');
    } finally {
      setActionLoading(false);
    }
  }

  async function handleBulkApprove() {
    if (selectedIds.size === 0) return;
    const ok = await confirm({
      title: 'Bulk Approve',
      message: `Approve ${selectedIds.size} subscription(s)?`,
      confirmLabel: 'Approve All',
    });
    if (!ok) return;
    try {
      setActionLoading(true);
      const result = await apiService.bulkSubscriptionAction({
        ids: Array.from(selectedIds),
        action: 'approve',
      });
      toast.success(
        `${result.succeeded} approved${result.failed.length ? `, ${result.failed.length} failed` : ''}`
      );
      setSelectedIds(new Set());
      reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Bulk approve failed');
    } finally {
      setActionLoading(false);
    }
  }

  async function handleBulkReject() {
    if (selectedIds.size === 0 || !bulkRejectReason.trim()) return;
    try {
      setActionLoading(true);
      const result = await apiService.bulkSubscriptionAction({
        ids: Array.from(selectedIds),
        action: 'reject',
        reason: bulkRejectReason.trim(),
      });
      toast.success(
        `${result.succeeded} rejected${result.failed.length ? `, ${result.failed.length} failed` : ''}`
      );
      setSelectedIds(new Set());
      setBulkRejectOpen(false);
      setBulkRejectReason('');
      reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Bulk reject failed');
    } finally {
      setActionLoading(false);
    }
  }

  function toggleSelect(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    if (selectedIds.size === filteredSubscriptions.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filteredSubscriptions.map((s) => s.id)));
    }
  }

  if (tenantsLoading) {
    return (
      <div className="space-y-6">
        <StatCardSkeletonRow count={4} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {ConfirmDialog}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Subscriptions</h1>
          <p className="text-neutral-500 dark:text-neutral-400 mt-1">
            Manage API subscription requests and approvals
          </p>
        </div>
        {/* Tenant Selector */}
        <select
          value={selectedTenant}
          onChange={(e) => setSelectedTenant(e.target.value)}
          className="px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-sm"
        >
          {tenants.map((t) => (
            <option key={t.id} value={t.id}>
              {t.display_name || t.name}
            </option>
          ))}
        </select>
      </div>

      {/* Contextual sub-navigation (CAB-1785) */}
      <SubNav tabs={apiCatalogTabs} />

      {/* Stats Cards */}
      {stats && <StatsCards stats={stats} />}

      {/* Search + Bulk Actions Bar */}
      <div className="flex items-center gap-4">
        <input
          type="text"
          placeholder="Search by application, email, or API..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="flex-1 px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-sm placeholder-neutral-400"
        />
        {selectedIds.size > 0 && activeTab === 'pending' && (
          <div className="flex items-center gap-2">
            <span className="text-sm text-neutral-500 dark:text-neutral-400">
              {selectedIds.size} selected
            </span>
            <Button
              size="sm"
              onClick={handleBulkApprove}
              disabled={actionLoading || !canEdit}
              title={!canEdit ? 'Read-only environment' : undefined}
            >
              Approve ({selectedIds.size})
            </Button>
            <Button
              size="sm"
              variant="danger"
              onClick={() => {
                setBulkRejectReason('');
                setBulkRejectOpen(true);
              }}
              disabled={actionLoading || !canEdit}
              title={!canEdit ? 'Read-only environment' : undefined}
            >
              Reject ({selectedIds.size})
            </Button>
          </div>
        )}
      </div>

      {/* Status Tabs */}
      <div className="border-b border-neutral-200 dark:border-neutral-700">
        <nav className="-mb-px flex gap-6">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.key
                  ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                  : 'border-transparent text-neutral-500 hover:text-neutral-700 dark:text-neutral-400 dark:hover:text-neutral-300'
              }`}
            >
              {tab.label}
              {stats && tab.key !== 'all' && stats.by_status[tab.key] !== undefined && (
                <span className="ml-1.5 text-xs text-neutral-400">
                  ({stats.by_status[tab.key]})
                </span>
              )}
              {stats && tab.key === 'all' && (
                <span className="ml-1.5 text-xs text-neutral-400">({stats.total})</span>
              )}
            </button>
          ))}
        </nav>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 text-red-700 dark:text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Table */}
      {loading ? (
        <TableSkeleton rows={5} columns={8} />
      ) : filteredSubscriptions.length === 0 ? (
        <EmptyState
          title="No subscriptions"
          description={
            activeTab === 'pending'
              ? 'No pending subscription requests.'
              : `No ${activeTab === 'all' ? '' : activeTab} subscriptions found.`
          }
        />
      ) : (
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none overflow-hidden">
          <table className="min-w-full divide-y divide-neutral-200 dark:divide-neutral-700">
            <thead className="bg-neutral-50 dark:bg-neutral-900/50">
              <tr>
                {activeTab === 'pending' && (
                  <th className="px-4 py-3 w-10">
                    <input
                      type="checkbox"
                      checked={
                        selectedIds.size > 0 && selectedIds.size === filteredSubscriptions.length
                      }
                      onChange={toggleSelectAll}
                      className="rounded border-neutral-300 dark:border-neutral-600"
                    />
                  </th>
                )}
                <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                  Application
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                  API
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                  Subscriber
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                  Plan
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                  Provisioning
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                  Created
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-200 dark:divide-neutral-700">
              {filteredSubscriptions.map((sub) => (
                <tr key={sub.id} className="hover:bg-neutral-50 dark:hover:bg-neutral-700/50">
                  {activeTab === 'pending' && (
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(sub.id)}
                        onChange={() => toggleSelect(sub.id)}
                        className="rounded border-neutral-300 dark:border-neutral-600"
                      />
                    </td>
                  )}
                  <td className="px-4 py-3 text-sm text-neutral-900 dark:text-white font-medium">
                    {sub.application_name}
                  </td>
                  <td className="px-4 py-3 text-sm text-neutral-600 dark:text-neutral-300">
                    {sub.api_name}
                    <span className="text-xs text-neutral-400 ml-1">v{sub.api_version}</span>
                  </td>
                  <td className="px-4 py-3 text-sm text-neutral-600 dark:text-neutral-300">
                    {sub.subscriber_email}
                  </td>
                  <td className="px-4 py-3 text-sm text-neutral-500 dark:text-neutral-400">
                    {sub.plan_name || '—'}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${statusColors[sub.status]}`}
                    >
                      {sub.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-neutral-500 dark:text-neutral-400">
                    <div className="flex flex-col gap-1">
                      <span
                        title={sub.provisioning_error || undefined}
                        className={`w-fit inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                          provisioningColors[sub.provisioning_status || 'none'] ||
                          provisioningColors.none
                        }`}
                      >
                        {sub.provisioning_status || 'none'}
                      </span>
                      {sub.gateway_app_id && (
                        <span
                          title={sub.gateway_app_id}
                          className="max-w-[12rem] truncate text-xs text-neutral-400 dark:text-neutral-500 font-mono"
                        >
                          {sub.gateway_app_id}
                        </span>
                      )}
                      {sub.provisioning_error && (
                        <span
                          title={sub.provisioning_error}
                          className="max-w-[12rem] truncate text-xs text-red-600 dark:text-red-400"
                        >
                          {sub.provisioning_error}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm text-neutral-500 dark:text-neutral-400">
                    {new Date(sub.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      {sub.status === 'pending' && (
                        <>
                          <button
                            onClick={() => handleApprove(sub)}
                            disabled={actionLoading || !canEdit}
                            title={!canEdit ? 'Read-only environment' : undefined}
                            className="text-green-600 hover:text-green-800 dark:text-green-400 dark:hover:text-green-300 text-sm font-medium disabled:opacity-50"
                          >
                            Approve
                          </button>
                          <button
                            onClick={() => openRejectModal(sub)}
                            disabled={actionLoading || !canEdit}
                            title={!canEdit ? 'Read-only environment' : undefined}
                            className="text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300 text-sm font-medium disabled:opacity-50"
                          >
                            Reject
                          </button>
                        </>
                      )}
                      {sub.status === 'active' && (
                        <>
                          <button
                            onClick={() => handleSuspend(sub)}
                            disabled={actionLoading || !canEdit}
                            title={!canEdit ? 'Read-only environment' : undefined}
                            className="text-orange-600 hover:text-orange-800 dark:text-orange-400 dark:hover:text-orange-300 text-sm font-medium disabled:opacity-50"
                          >
                            Suspend
                          </button>
                          <button
                            onClick={() => handleRevoke(sub)}
                            disabled={actionLoading || !canEdit}
                            title={!canEdit ? 'Read-only environment' : undefined}
                            className="text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300 text-sm font-medium disabled:opacity-50"
                          >
                            Revoke
                          </button>
                        </>
                      )}
                      {sub.status === 'suspended' && (
                        <>
                          <button
                            onClick={() => handleReactivate(sub)}
                            disabled={actionLoading || !canEdit}
                            title={!canEdit ? 'Read-only environment' : undefined}
                            className="text-green-600 hover:text-green-800 dark:text-green-400 dark:hover:text-green-300 text-sm font-medium disabled:opacity-50"
                          >
                            Reactivate
                          </button>
                          <button
                            onClick={() => handleRevoke(sub)}
                            disabled={actionLoading || !canEdit}
                            title={!canEdit ? 'Read-only environment' : undefined}
                            className="text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300 text-sm font-medium disabled:opacity-50"
                          >
                            Revoke
                          </button>
                        </>
                      )}
                      {sub.status_reason && (
                        <span
                          title={sub.status_reason}
                          className="text-neutral-400 cursor-help text-xs"
                        >
                          (reason)
                        </span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="px-4 py-3 border-t border-neutral-200 dark:border-neutral-700 flex items-center justify-between">
              <p className="text-sm text-neutral-500 dark:text-neutral-400">
                Showing {(currentPage - 1) * PAGE_SIZE + 1} to{' '}
                {Math.min(currentPage * PAGE_SIZE, total)} of {total}
              </p>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                >
                  Previous
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                >
                  Next
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Reject Modal */}
      {rejectModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-xl p-6 w-full max-w-md">
            <h3 className="text-lg font-semibold text-neutral-900 dark:text-white mb-2">
              Reject Subscription
            </h3>
            <p className="text-sm text-neutral-500 dark:text-neutral-400 mb-4">
              Reject {rejectTarget?.application_name}&apos;s subscription to{' '}
              {rejectTarget?.api_name}?
            </p>
            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Reason for rejection (required)"
              rows={3}
              className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-900 text-neutral-900 dark:text-white text-sm resize-none"
            />
            <div className="flex justify-end gap-3 mt-4">
              <Button
                variant="secondary"
                onClick={() => {
                  setRejectModalOpen(false);
                  setRejectTarget(null);
                }}
              >
                Cancel
              </Button>
              <Button
                variant="danger"
                onClick={handleReject}
                disabled={!rejectReason.trim() || actionLoading}
              >
                Reject
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Bulk Reject Modal */}
      {bulkRejectOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-xl p-6 w-full max-w-md">
            <h3 className="text-lg font-semibold text-neutral-900 dark:text-white mb-2">
              Reject {selectedIds.size} Subscription(s)
            </h3>
            <textarea
              value={bulkRejectReason}
              onChange={(e) => setBulkRejectReason(e.target.value)}
              placeholder="Reason for rejection (required)"
              rows={3}
              className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-900 text-neutral-900 dark:text-white text-sm resize-none"
            />
            <div className="flex justify-end gap-3 mt-4">
              <Button variant="secondary" onClick={() => setBulkRejectOpen(false)}>
                Cancel
              </Button>
              <Button
                variant="danger"
                onClick={handleBulkReject}
                disabled={!bulkRejectReason.trim() || actionLoading}
              >
                Reject All
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Stats Cards Component
function StatsCards({ stats }: { stats: SubscriptionStats }) {
  const approvalRate =
    stats.total > 0 ? Math.round(((stats.by_status['active'] || 0) / stats.total) * 100) : 0;

  const cards = [
    {
      label: 'Total Subscribers',
      value: stats.total,
      icon: Users,
      color: 'text-blue-600 dark:text-blue-400',
      bg: 'bg-blue-50 dark:bg-blue-900/20',
    },
    {
      label: 'Pending Requests',
      value: stats.by_status['pending'] || 0,
      icon: Clock,
      color: 'text-yellow-600 dark:text-yellow-400',
      bg: 'bg-yellow-50 dark:bg-yellow-900/20',
    },
    {
      label: 'Approval Rate',
      value: `${approvalRate}%`,
      icon: TrendingUp,
      color: 'text-green-600 dark:text-green-400',
      bg: 'bg-green-50 dark:bg-green-900/20',
    },
    {
      label: 'Avg Time to Approve',
      value:
        stats.avg_approval_time_hours != null
          ? `${stats.avg_approval_time_hours.toFixed(1)}h`
          : '—',
      icon: Timer,
      color: 'text-purple-600 dark:text-purple-400',
      bg: 'bg-purple-50 dark:bg-purple-900/20',
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((card) => (
        <div
          key={card.label}
          className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none p-4 flex items-center gap-4"
        >
          <div className={`p-2.5 rounded-lg ${card.bg}`}>
            <card.icon className={`w-5 h-5 ${card.color}`} />
          </div>
          <div>
            <p className="text-sm text-neutral-500 dark:text-neutral-400">{card.label}</p>
            <p className="text-xl font-semibold text-neutral-900 dark:text-white">{card.value}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
