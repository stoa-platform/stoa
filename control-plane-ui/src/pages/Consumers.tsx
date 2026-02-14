import { useState, useMemo, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiService } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { useEnvironmentMode } from '../hooks/useEnvironmentMode';
import { useDebounce } from '../hooks/useDebounce';
import { useMediaQuery } from '../hooks/useMediaQuery';
import type { Consumer, CertificateStatus } from '../types';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import { EmptyState } from '@stoa/shared/components/EmptyState';
import { TableSkeleton } from '@stoa/shared/components/Skeleton';
import { ConsumerDetailModal } from '../components/ConsumerDetailModal';
import { CertificateHealthBadge } from '../components/CertificateHealthBadge';

const PAGE_SIZE = 20;

const statusColors: Record<string, string> = {
  active: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  suspended: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  blocked: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
};

export function Consumers() {
  const { isReady } = useAuth();
  const { canEdit, canDelete } = useEnvironmentMode();
  const isMobile = useMediaQuery('(max-width: 767px)');
  const toast = useToastActions();
  const queryClient = useQueryClient();
  const [confirm, ConfirmDialog] = useConfirm();
  const [selectedTenant, setSelectedTenant] = useState<string>('');

  // Search and pagination state
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [selectedConsumer, setSelectedConsumer] = useState<Consumer | null>(null);
  const [certFilter, setCertFilter] = useState<string>('');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkRevoking, setBulkRevoking] = useState(false);

  const debouncedSearch = useDebounce(searchQuery, 300);

  // Fetch tenants
  const {
    data: tenants = [],
    isLoading: tenantsLoading,
    error: tenantsError,
  } = useQuery({
    queryKey: ['tenants'],
    queryFn: () => apiService.getTenants(),
    enabled: isReady,
    staleTime: 5 * 60 * 1000,
  });

  // Auto-select first tenant (derived state — no useEffect needed)
  const activeTenant = selectedTenant || (tenants.length > 0 ? tenants[0].id : '');

  // Fetch consumers for selected tenant
  const {
    data: consumers = [],
    isLoading: consumersLoading,
    error: consumersError,
  } = useQuery({
    queryKey: ['consumers', activeTenant],
    queryFn: () => apiService.getConsumers(activeTenant),
    enabled: !!activeTenant,
  });

  const loading = tenantsLoading || consumersLoading;
  const error = tenantsError || consumersError;

  // Handlers that reset pagination
  const handleSearchChange = useCallback((value: string) => {
    setSearchQuery(value);
    setCurrentPage(1);
  }, []);

  const handleStatusChange = useCallback((value: string) => {
    setStatusFilter(value);
    setCurrentPage(1);
  }, []);

  const handleTenantChange = useCallback((value: string) => {
    setSelectedTenant(value);
    setCurrentPage(1);
  }, []);

  // Client-side filtering
  const filteredConsumers = useMemo(() => {
    let result = consumers;

    if (debouncedSearch) {
      const searchLower = debouncedSearch.toLowerCase();
      result = result.filter(
        (c) =>
          c.external_id.toLowerCase().includes(searchLower) ||
          c.name.toLowerCase().includes(searchLower) ||
          c.email.toLowerCase().includes(searchLower) ||
          (c.company || '').toLowerCase().includes(searchLower)
      );
    }

    if (statusFilter) {
      result = result.filter((c) => c.status === statusFilter);
    }

    if (certFilter === 'expiring') {
      result = result.filter((c) => {
        if (!c.certificate_not_after || c.certificate_status !== 'active') return false;
        const days = Math.floor(
          (new Date(c.certificate_not_after).getTime() - Date.now()) / (1000 * 60 * 60 * 24)
        );
        return days > 0 && days <= 90;
      });
    } else if (certFilter === 'no-cert') {
      result = result.filter((c) => !c.certificate_fingerprint);
    }

    return result;
  }, [consumers, debouncedSearch, statusFilter, certFilter, activeTenant]);

  // Pagination
  const paginatedConsumers = useMemo(() => {
    const startIndex = (currentPage - 1) * PAGE_SIZE;
    return filteredConsumers.slice(startIndex, startIndex + PAGE_SIZE);
  }, [filteredConsumers, currentPage]);

  const totalPages = Math.ceil(filteredConsumers.length / PAGE_SIZE);

  const invalidateConsumers = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['consumers', activeTenant] });
  }, [queryClient, activeTenant]);

  const handleSuspend = useCallback(
    async (consumer: Consumer) => {
      const confirmed = await confirm({
        title: 'Suspend Consumer',
        message: `Suspend "${consumer.name}" (${consumer.external_id})? They will lose API access.`,
        confirmLabel: 'Suspend',
        cancelLabel: 'Cancel',
        variant: 'danger',
      });
      if (!confirmed) return;

      try {
        await apiService.suspendConsumer(activeTenant, consumer.id);
        toast.success('Consumer suspended', `${consumer.name} has been suspended`);
        invalidateConsumers();
      } catch (err: any) {
        toast.error('Suspend failed', err.message || 'Failed to suspend consumer');
      }
    },
    [activeTenant, confirm, toast, invalidateConsumers]
  );

  const handleActivate = useCallback(
    async (consumer: Consumer) => {
      try {
        await apiService.activateConsumer(activeTenant, consumer.id);
        toast.success('Consumer activated', `${consumer.name} has been activated`);
        invalidateConsumers();
      } catch (err: any) {
        toast.error('Activation failed', err.message || 'Failed to activate consumer');
      }
    },
    [activeTenant, toast, invalidateConsumers]
  );

  const handleDelete = useCallback(
    async (consumer: Consumer) => {
      const confirmed = await confirm({
        title: 'Delete Consumer',
        message: `Delete "${consumer.name}" (${consumer.external_id})? This cannot be undone.`,
        confirmLabel: 'Delete',
        cancelLabel: 'Cancel',
        variant: 'danger',
      });
      if (!confirmed) return;

      try {
        await apiService.deleteConsumer(activeTenant, consumer.id);
        toast.success('Consumer deleted', `${consumer.name} has been removed`);
        invalidateConsumers();
      } catch (err: any) {
        toast.error('Delete failed', err.message || 'Failed to delete consumer');
      }
    },
    [activeTenant, confirm, toast, invalidateConsumers]
  );

  const toggleSelection = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleAll = useCallback(() => {
    if (selectedIds.size === paginatedConsumers.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(paginatedConsumers.map((c) => c.id)));
    }
  }, [selectedIds.size, paginatedConsumers]);

  const handleBulkRevoke = useCallback(async () => {
    const ids = Array.from(selectedIds);
    const confirmed = await confirm({
      title: 'Bulk Revoke Certificates',
      message: `Revoke certificates for ${ids.length} selected consumer${ids.length > 1 ? 's' : ''}? This will disable their API access immediately.`,
      confirmLabel: `Revoke ${ids.length}`,
      cancelLabel: 'Cancel',
      variant: 'danger',
    });
    if (!confirmed) return;

    setBulkRevoking(true);
    try {
      const result = await apiService.bulkRevokeCertificates(activeTenant, ids);
      toast.success(
        'Bulk revoke complete',
        `${result.success} revoked, ${result.skipped} skipped, ${result.failed} failed`
      );
      setSelectedIds(new Set());
      invalidateConsumers();
    } catch (err: unknown) {
      toast.error(
        'Bulk revoke failed',
        err instanceof Error ? err.message : 'Failed to bulk revoke certificates'
      );
    } finally {
      setBulkRevoking(false);
    }
  }, [selectedIds, activeTenant, confirm, toast, invalidateConsumers]);

  if (loading && tenants.length === 0) {
    return (
      <div className="space-y-6">
        <TableSkeleton
          rows={5}
          columns={6}
          headers={['External ID', 'Name', 'Email', 'Company', 'Status', 'Actions']}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Consumers</h1>
        <p className="text-gray-500 dark:text-neutral-400 mt-1">
          API consumers with mTLS certificate bindings
        </p>
      </div>

      {/* Filters */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
        <div className="flex flex-wrap gap-4 items-end">
          {/* Tenant Selector */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-2">
              Tenant
            </label>
            <select
              value={activeTenant}
              onChange={(e) => handleTenantChange(e.target.value)}
              className="w-48 border border-gray-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              {tenants.map((tenant) => (
                <option key={tenant.id} value={tenant.id}>
                  {tenant.display_name || tenant.name}
                </option>
              ))}
            </select>
          </div>

          {/* Search */}
          <div className="flex-1 min-w-[200px]">
            <label className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-2">
              Search
            </label>
            <div className="relative">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => handleSearchChange(e.target.value)}
                placeholder="Search by ID, name, email, company..."
                className="w-full border border-gray-300 dark:border-neutral-600 rounded-lg px-3 py-2 pl-10 bg-white dark:bg-neutral-700 dark:text-white dark:placeholder-neutral-400 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
              <svg
                className="absolute left-3 top-2.5 h-5 w-5 text-gray-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                />
              </svg>
              {searchQuery && (
                <button
                  onClick={() => handleSearchChange('')}
                  className="absolute right-3 top-2.5 text-gray-400 hover:text-gray-600"
                >
                  <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M6 18L18 6M6 6l12 12"
                    />
                  </svg>
                </button>
              )}
            </div>
          </div>

          {/* Status Filter */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-2">
              Status
            </label>
            <select
              value={statusFilter}
              onChange={(e) => handleStatusChange(e.target.value)}
              className="w-36 border border-gray-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="">All Status</option>
              <option value="active">Active</option>
              <option value="suspended">Suspended</option>
              <option value="blocked">Blocked</option>
            </select>
          </div>

          {/* Certificate Filter */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-2">
              Certificate
            </label>
            <select
              value={certFilter}
              onChange={(e) => {
                setCertFilter(e.target.value);
                setCurrentPage(1);
              }}
              className="w-40 border border-gray-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="">All Certs</option>
              <option value="expiring">Expiring Soon</option>
              <option value="no-cert">No Certificate</option>
            </select>
          </div>

          {/* Results count */}
          <div className="text-sm text-gray-500 dark:text-neutral-400 self-end pb-2">
            {filteredConsumers.length} of {consumers.length} consumers
          </div>
        </div>

        {/* Bulk Actions Toolbar */}
        {canEdit && selectedIds.size > 0 && (
          <div className="mt-3 flex items-center gap-3 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
            <span className="text-sm font-medium text-blue-800 dark:text-blue-300">
              {selectedIds.size} selected
            </span>
            <button
              onClick={handleBulkRevoke}
              disabled={bulkRevoking}
              className="px-3 py-1.5 bg-red-600 text-white text-sm rounded-lg hover:bg-red-700 disabled:opacity-50"
            >
              {bulkRevoking ? 'Revoking...' : `Revoke Selected (${selectedIds.size})`}
            </button>
            <button
              onClick={() => setSelectedIds(new Set())}
              className="text-sm text-blue-600 hover:text-blue-800 dark:text-blue-400"
            >
              Clear selection
            </button>
          </div>
        )}
      </div>

      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg">
          {error.message || 'Failed to load data'}
        </div>
      )}

      {/* Empty State */}
      {!loading && filteredConsumers.length === 0 && (
        <EmptyState
          title={consumers.length === 0 ? 'No consumers yet' : 'No matching consumers'}
          description={
            consumers.length === 0
              ? 'Consumers self-register via the Developer Portal or are bulk-onboarded via the API.'
              : 'Try adjusting your search or filter criteria.'
          }
          action={
            consumers.length > 0
              ? {
                  label: 'Clear filters',
                  onClick: () => {
                    handleSearchChange('');
                    handleStatusChange('');
                  },
                }
              : undefined
          }
        />
      )}

      {/* Desktop Table */}
      {!isMobile && paginatedConsumers.length > 0 && (
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-neutral-700">
            <thead className="bg-gray-50 dark:bg-neutral-900">
              <tr>
                {canEdit && (
                  <th className="px-3 py-3 w-10">
                    <input
                      type="checkbox"
                      checked={
                        paginatedConsumers.length > 0 &&
                        selectedIds.size === paginatedConsumers.length
                      }
                      onChange={toggleAll}
                      className="rounded border-gray-300 dark:border-neutral-600"
                    />
                  </th>
                )}
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase tracking-wider">
                  External ID
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase tracking-wider">
                  Name
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase tracking-wider">
                  Email
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase tracking-wider">
                  Company
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase tracking-wider">
                  Certificate
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-neutral-700">
              {paginatedConsumers.map((consumer) => (
                <tr
                  key={consumer.id}
                  onClick={() => setSelectedConsumer(consumer)}
                  className="hover:bg-gray-50 dark:hover:bg-neutral-700/50 transition-colors cursor-pointer"
                >
                  {canEdit && (
                    <td className="px-3 py-4 w-10" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selectedIds.has(consumer.id)}
                        onChange={() => toggleSelection(consumer.id)}
                        className="rounded border-gray-300 dark:border-neutral-600"
                      />
                    </td>
                  )}
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-900 dark:text-white">
                    {consumer.external_id}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white">
                    {consumer.name}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-neutral-400">
                    {consumer.email}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-neutral-400">
                    {consumer.company || '—'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span
                      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${statusColors[consumer.status] || ''}`}
                    >
                      {consumer.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    {consumer.certificate_fingerprint ? (
                      <div className="flex items-center gap-2">
                        <CertificateHealthBadge
                          status={consumer.certificate_status as CertificateStatus}
                          notAfter={consumer.certificate_not_after}
                        />
                        <span className="font-mono text-xs text-gray-400 dark:text-neutral-500">
                          {consumer.certificate_fingerprint.substring(0, 12)}...
                        </span>
                      </div>
                    ) : (
                      <span className="text-gray-400 dark:text-neutral-500">—</span>
                    )}
                  </td>
                  <td
                    className="px-6 py-4 whitespace-nowrap text-right text-sm"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className="flex justify-end gap-2">
                      {canEdit && consumer.status === 'active' && (
                        <button
                          onClick={() => handleSuspend(consumer)}
                          className="text-yellow-600 hover:text-yellow-800 dark:text-yellow-400 dark:hover:text-yellow-300"
                          title="Suspend consumer"
                        >
                          Suspend
                        </button>
                      )}
                      {canEdit && consumer.status === 'suspended' && (
                        <button
                          onClick={() => handleActivate(consumer)}
                          className="text-green-600 hover:text-green-800 dark:text-green-400 dark:hover:text-green-300"
                          title="Activate consumer"
                        >
                          Activate
                        </button>
                      )}
                      {canDelete && (
                        <button
                          onClick={() => handleDelete(consumer)}
                          className="text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300"
                          title="Delete consumer"
                        >
                          Delete
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Mobile Card View */}
      {isMobile && paginatedConsumers.length > 0 && (
        <div className="space-y-3">
          {paginatedConsumers.map((consumer) => (
            <div
              key={consumer.id}
              onClick={() => setSelectedConsumer(consumer)}
              className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4 space-y-2 cursor-pointer"
            >
              <div className="flex justify-between items-start">
                <div>
                  <p className="font-medium text-gray-900 dark:text-white">{consumer.name}</p>
                  <p className="text-sm font-mono text-gray-500 dark:text-neutral-400">
                    {consumer.external_id}
                  </p>
                </div>
                <span
                  className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${statusColors[consumer.status] || ''}`}
                >
                  {consumer.status}
                </span>
              </div>
              <p className="text-sm text-gray-500 dark:text-neutral-400">{consumer.email}</p>
              {consumer.company && (
                <p className="text-sm text-gray-500 dark:text-neutral-400">{consumer.company}</p>
              )}
              {consumer.certificate_fingerprint && (
                <div className="flex items-center gap-2">
                  <CertificateHealthBadge
                    status={consumer.certificate_status as CertificateStatus}
                    notAfter={consumer.certificate_not_after}
                  />
                  <span className="text-xs font-mono text-gray-400 dark:text-neutral-500 truncate">
                    {consumer.certificate_fingerprint.substring(0, 20)}...
                  </span>
                </div>
              )}
              <div
                className="flex gap-2 pt-2 border-t border-gray-100 dark:border-neutral-700"
                onClick={(e) => e.stopPropagation()}
              >
                {canEdit && consumer.status === 'active' && (
                  <button
                    onClick={() => handleSuspend(consumer)}
                    className="text-sm text-yellow-600 dark:text-yellow-400"
                  >
                    Suspend
                  </button>
                )}
                {canEdit && consumer.status === 'suspended' && (
                  <button
                    onClick={() => handleActivate(consumer)}
                    className="text-sm text-green-600 dark:text-green-400"
                  >
                    Activate
                  </button>
                )}
                {canDelete && (
                  <button
                    onClick={() => handleDelete(consumer)}
                    className="text-sm text-red-600 dark:text-red-400"
                  >
                    Delete
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-between items-center">
          <p className="text-sm text-gray-500 dark:text-neutral-400">
            Page {currentPage} of {totalPages}
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage === 1}
              className="px-3 py-1 border border-gray-300 dark:border-neutral-600 rounded-lg text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50 dark:hover:bg-neutral-700 dark:text-white"
            >
              Previous
            </button>
            <button
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage === totalPages}
              className="px-3 py-1 border border-gray-300 dark:border-neutral-600 rounded-lg text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50 dark:hover:bg-neutral-700 dark:text-white"
            >
              Next
            </button>
          </div>
        </div>
      )}

      {selectedConsumer && (
        <ConsumerDetailModal
          consumer={selectedConsumer}
          tenantId={activeTenant}
          onClose={() => setSelectedConsumer(null)}
        />
      )}

      {ConfirmDialog}
    </div>
  );
}
