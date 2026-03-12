/**
 * Certificates — Certificate management dashboard (CAB-1786)
 *
 * Dedicated page for managing mTLS certificates across all consumers.
 * Features: dashboard cards, sortable/filterable table, bulk revoke, expiry alerts.
 */

import { useState, useMemo, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiService } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { useEnvironmentMode } from '../hooks/useEnvironmentMode';
import type { Consumer, CertificateStatus } from '../types';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import { EmptyState } from '@stoa/shared/components/EmptyState';
import { TableSkeleton } from '@stoa/shared/components/Skeleton';
import { CertificateHealthBadge } from '../components/CertificateHealthBadge';
import { ConsumerDetailModal } from '../components/ConsumerDetailModal';
import { Button } from '@stoa/shared/components/Button';
import { SubNav } from '../components/SubNav';
import { consumersTabs } from '../components/subNavGroups';
import { ShieldCheck, AlertTriangle, ShieldOff, Clock, ArrowUpDown } from 'lucide-react';

type SortField = 'name' | 'status' | 'expiry' | 'fingerprint';
type SortDir = 'asc' | 'desc';

interface CertConsumer extends Consumer {
  _daysUntilExpiry: number;
}

function getDaysUntilExpiry(notAfter?: string): number {
  if (!notAfter) return Infinity;
  return Math.floor((new Date(notAfter).getTime() - Date.now()) / (1000 * 60 * 60 * 24));
}

export function Certificates() {
  const { isReady } = useAuth();
  const { canEdit } = useEnvironmentMode();
  const toast = useToastActions();
  const queryClient = useQueryClient();
  const [confirm, ConfirmDialog] = useConfirm();

  const [selectedTenant, setSelectedTenant] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkRevoking, setBulkRevoking] = useState(false);
  const [selectedConsumer, setSelectedConsumer] = useState<Consumer | null>(null);
  const [sortField, setSortField] = useState<SortField>('expiry');
  const [sortDir, setSortDir] = useState<SortDir>('asc');

  // Fetch tenants
  const { data: tenants = [], isLoading: tenantsLoading } = useQuery({
    queryKey: ['tenants'],
    queryFn: () => apiService.getTenants(),
    enabled: isReady,
    staleTime: 5 * 60 * 1000,
  });

  const activeTenant = selectedTenant || (tenants.length > 0 ? tenants[0].id : '');

  // Fetch all consumers for the tenant (certificates are fields on Consumer)
  const {
    data: consumers = [],
    isLoading: consumersLoading,
    error,
  } = useQuery({
    queryKey: ['consumers', activeTenant],
    queryFn: () => apiService.getConsumers(activeTenant),
    enabled: !!activeTenant,
  });

  const loading = tenantsLoading || consumersLoading;

  // Only consumers with certificates
  const certConsumers: CertConsumer[] = useMemo(() => {
    return consumers
      .filter((c) => c.certificate_fingerprint)
      .map((c) => ({
        ...c,
        _daysUntilExpiry: getDaysUntilExpiry(c.certificate_not_after),
      }));
  }, [consumers]);

  // Dashboard counts
  const counts = useMemo(() => {
    let active = 0;
    let expiring = 0;
    let critical = 0;
    let revoked = 0;
    for (const c of certConsumers) {
      const status = c.certificate_status;
      if (status === 'revoked') {
        revoked++;
      } else if (status === 'expired' || c._daysUntilExpiry <= 0) {
        critical++;
      } else if (c._daysUntilExpiry <= 30) {
        critical++;
      } else if (c._daysUntilExpiry <= 90) {
        expiring++;
      } else {
        active++;
      }
    }
    return { active, expiring, critical, revoked, total: certConsumers.length };
  }, [certConsumers]);

  // Filter by certificate status
  const filtered = useMemo(() => {
    if (!statusFilter) return certConsumers;
    return certConsumers.filter((c) => {
      if (statusFilter === 'active') {
        return c.certificate_status === 'active' && c._daysUntilExpiry > 90;
      }
      if (statusFilter === 'expiring') {
        return (
          c.certificate_status === 'active' && c._daysUntilExpiry > 30 && c._daysUntilExpiry <= 90
        );
      }
      if (statusFilter === 'critical') {
        return (
          c.certificate_status === 'expired' ||
          (c.certificate_status === 'active' && c._daysUntilExpiry <= 30)
        );
      }
      if (statusFilter === 'revoked') {
        return c.certificate_status === 'revoked';
      }
      return true;
    });
  }, [certConsumers, statusFilter]);

  // Sort
  const sorted = useMemo(() => {
    const items = [...filtered];
    items.sort((a, b) => {
      let cmp = 0;
      switch (sortField) {
        case 'name':
          cmp = a.name.localeCompare(b.name);
          break;
        case 'status':
          cmp = (a.certificate_status || '').localeCompare(b.certificate_status || '');
          break;
        case 'expiry':
          cmp = a._daysUntilExpiry - b._daysUntilExpiry;
          break;
        case 'fingerprint':
          cmp = (a.certificate_fingerprint || '').localeCompare(b.certificate_fingerprint || '');
          break;
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return items;
  }, [filtered, sortField, sortDir]);

  const handleSort = useCallback(
    (field: SortField) => {
      if (sortField === field) {
        setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
      } else {
        setSortField(field);
        setSortDir('asc');
      }
    },
    [sortField]
  );

  const invalidateConsumers = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['consumers', activeTenant] });
  }, [queryClient, activeTenant]);

  const toggleSelection = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleAll = useCallback(() => {
    if (selectedIds.size === sorted.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(sorted.map((c) => c.id)));
    }
  }, [selectedIds.size, sorted]);

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

  const handleRevokeSingle = useCallback(
    async (consumer: Consumer) => {
      const confirmed = await confirm({
        title: 'Revoke Certificate',
        message: `Revoke certificate for "${consumer.name}" (${consumer.external_id})? This will disable their API access immediately.`,
        confirmLabel: 'Revoke',
        cancelLabel: 'Cancel',
        variant: 'danger',
      });
      if (!confirmed) return;

      try {
        await apiService.revokeCertificate(activeTenant, consumer.id);
        toast.success('Certificate revoked', `${consumer.name}'s certificate has been revoked`);
        invalidateConsumers();
      } catch (err: unknown) {
        toast.error(
          'Revoke failed',
          err instanceof Error ? err.message : 'Failed to revoke certificate'
        );
      }
    },
    [activeTenant, confirm, toast, invalidateConsumers]
  );

  if (loading && tenants.length === 0) {
    return (
      <div className="space-y-6">
        <TableSkeleton
          rows={5}
          columns={5}
          headers={['Consumer', 'Status', 'Fingerprint', 'Expires', 'Actions']}
        />
      </div>
    );
  }

  const SortButton = ({ field, children }: { field: SortField; children: React.ReactNode }) => (
    <button
      onClick={() => handleSort(field)}
      className="flex items-center gap-1 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider hover:text-neutral-700 dark:hover:text-neutral-300"
    >
      {children}
      <ArrowUpDown
        className={`h-3 w-3 ${sortField === field ? 'text-primary-600 dark:text-primary-400' : 'opacity-40'}`}
      />
    </button>
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Certificates</h1>
        <p className="text-neutral-500 dark:text-neutral-400 mt-1">
          mTLS certificate lifecycle management across all consumers
        </p>
      </div>

      <SubNav tabs={consumersTabs} />

      {/* Expiry Alert Banner */}
      {counts.critical > 0 && (
        <div className="flex items-center gap-3 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
          <AlertTriangle className="h-5 w-5 text-red-600 dark:text-red-400 flex-shrink-0" />
          <div>
            <p className="text-sm font-medium text-red-800 dark:text-red-300">
              {counts.critical} certificate{counts.critical > 1 ? 's' : ''} expiring within 30 days
              or already expired
            </p>
            <p className="text-xs text-red-600 dark:text-red-400 mt-0.5">
              Review and rotate affected certificates to prevent API access disruption.
            </p>
          </div>
          <Button
            variant="danger"
            size="sm"
            className="ml-auto flex-shrink-0"
            onClick={() => setStatusFilter('critical')}
          >
            View Critical
          </Button>
        </div>
      )}

      {/* Dashboard Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <DashboardCard
          label="Active"
          count={counts.active}
          icon={<ShieldCheck className="h-5 w-5 text-green-600 dark:text-green-400" />}
          color="green"
          active={statusFilter === 'active'}
          onClick={() => setStatusFilter(statusFilter === 'active' ? '' : 'active')}
        />
        <DashboardCard
          label="Expiring Soon"
          count={counts.expiring}
          icon={<Clock className="h-5 w-5 text-yellow-600 dark:text-yellow-400" />}
          color="yellow"
          active={statusFilter === 'expiring'}
          onClick={() => setStatusFilter(statusFilter === 'expiring' ? '' : 'expiring')}
        />
        <DashboardCard
          label="Critical"
          count={counts.critical}
          icon={<AlertTriangle className="h-5 w-5 text-red-600 dark:text-red-400" />}
          color="red"
          active={statusFilter === 'critical'}
          onClick={() => setStatusFilter(statusFilter === 'critical' ? '' : 'critical')}
        />
        <DashboardCard
          label="Revoked"
          count={counts.revoked}
          icon={<ShieldOff className="h-5 w-5 text-neutral-600 dark:text-neutral-400" />}
          color="neutral"
          active={statusFilter === 'revoked'}
          onClick={() => setStatusFilter(statusFilter === 'revoked' ? '' : 'revoked')}
        />
      </div>

      {/* Filters Bar */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
        <div className="flex flex-wrap gap-4 items-end">
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
              Tenant
            </label>
            <select
              value={activeTenant}
              onChange={(e) => {
                setSelectedTenant(e.target.value);
                setSelectedIds(new Set());
              }}
              className="w-48 border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              {tenants.map((tenant) => (
                <option key={tenant.id} value={tenant.id}>
                  {tenant.display_name || tenant.name}
                </option>
              ))}
            </select>
          </div>

          <div className="text-sm text-neutral-500 dark:text-neutral-400 self-end pb-2">
            {filtered.length} of {counts.total} certificates
            {statusFilter && (
              <button
                onClick={() => setStatusFilter('')}
                className="ml-2 text-primary-600 dark:text-primary-400 hover:underline"
              >
                Clear filter
              </button>
            )}
          </div>
        </div>

        {/* Bulk Actions */}
        {canEdit && selectedIds.size > 0 && (
          <div className="mt-3 flex items-center gap-3 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
            <span className="text-sm font-medium text-blue-800 dark:text-blue-300">
              {selectedIds.size} selected
            </span>
            <Button variant="danger" size="sm" onClick={handleBulkRevoke} loading={bulkRevoking}>
              {bulkRevoking ? 'Revoking...' : `Revoke Selected (${selectedIds.size})`}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setSelectedIds(new Set())}>
              Clear selection
            </Button>
          </div>
        )}
      </div>

      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg">
          {error.message || 'Failed to load data'}
        </div>
      )}

      {/* Empty State */}
      {!loading && certConsumers.length === 0 && (
        <EmptyState
          title="No certificates bound"
          description="Consumers can bind mTLS certificates via the Developer Portal or API. Once bound, certificates appear here for lifecycle management."
        />
      )}

      {!loading && certConsumers.length > 0 && filtered.length === 0 && (
        <EmptyState
          title="No matching certificates"
          description="No certificates match the current filter."
          action={{
            label: 'Clear filter',
            onClick: () => setStatusFilter(''),
          }}
        />
      )}

      {/* Certificate Table */}
      {sorted.length > 0 && (
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow overflow-hidden">
          <table className="min-w-full divide-y divide-neutral-200 dark:divide-neutral-700">
            <thead className="bg-neutral-50 dark:bg-neutral-900">
              <tr>
                {canEdit && (
                  <th className="px-3 py-3 w-10">
                    <input
                      type="checkbox"
                      checked={sorted.length > 0 && selectedIds.size === sorted.length}
                      onChange={toggleAll}
                      className="rounded border-neutral-300 dark:border-neutral-600"
                    />
                  </th>
                )}
                <th className="px-6 py-3 text-left">
                  <SortButton field="name">Consumer</SortButton>
                </th>
                <th className="px-6 py-3 text-left">
                  <SortButton field="status">Status</SortButton>
                </th>
                <th className="px-6 py-3 text-left">
                  <SortButton field="fingerprint">Fingerprint</SortButton>
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                  Subject DN
                </th>
                <th className="px-6 py-3 text-left">
                  <SortButton field="expiry">Expires</SortButton>
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-200 dark:divide-neutral-700">
              {sorted.map((consumer) => (
                <tr
                  key={consumer.id}
                  onClick={() => setSelectedConsumer(consumer)}
                  className="hover:bg-neutral-50 dark:hover:bg-neutral-700/50 transition-colors cursor-pointer"
                >
                  {canEdit && (
                    <td className="px-3 py-4 w-10" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selectedIds.has(consumer.id)}
                        onChange={() => toggleSelection(consumer.id)}
                        className="rounded border-neutral-300 dark:border-neutral-600"
                      />
                    </td>
                  )}
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div>
                      <p className="text-sm font-medium text-neutral-900 dark:text-white">
                        {consumer.name}
                      </p>
                      <p className="text-xs text-neutral-500 dark:text-neutral-400 font-mono">
                        {consumer.external_id}
                      </p>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <CertificateHealthBadge
                      status={consumer.certificate_status as CertificateStatus}
                      notAfter={consumer.certificate_not_after}
                    />
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className="text-xs font-mono text-neutral-500 dark:text-neutral-400">
                      {consumer.certificate_fingerprint
                        ? consumer.certificate_fingerprint.substring(0, 16) + '...'
                        : '—'}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span
                      className="text-xs text-neutral-500 dark:text-neutral-400 max-w-[200px] truncate block"
                      title={consumer.certificate_subject_dn || undefined}
                    >
                      {consumer.certificate_subject_dn || '—'}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    {consumer.certificate_not_after ? (
                      <div>
                        <p className="text-sm text-neutral-900 dark:text-white">
                          {new Date(consumer.certificate_not_after).toLocaleDateString()}
                        </p>
                        <p
                          className={`text-xs ${
                            consumer._daysUntilExpiry <= 7
                              ? 'text-red-600 dark:text-red-400 font-medium'
                              : consumer._daysUntilExpiry <= 30
                                ? 'text-orange-600 dark:text-orange-400'
                                : 'text-neutral-500 dark:text-neutral-400'
                          }`}
                        >
                          {consumer._daysUntilExpiry <= 0
                            ? 'Expired'
                            : `${consumer._daysUntilExpiry}d remaining`}
                        </p>
                      </div>
                    ) : (
                      <span className="text-neutral-400">—</span>
                    )}
                  </td>
                  <td
                    className="px-6 py-4 whitespace-nowrap text-right text-sm"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {canEdit &&
                      consumer.certificate_status !== 'revoked' &&
                      consumer.certificate_status !== 'expired' && (
                        <button
                          onClick={() => handleRevokeSingle(consumer)}
                          className="text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300"
                        >
                          Revoke
                        </button>
                      )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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

function DashboardCard({
  label,
  count,
  icon,
  color,
  active,
  onClick,
}: {
  label: string;
  count: number;
  icon: React.ReactNode;
  color: string;
  active: boolean;
  onClick: () => void;
}) {
  const borderColor = active
    ? `border-${color}-500 dark:border-${color}-400`
    : 'border-transparent';

  return (
    <button
      onClick={onClick}
      className={`bg-white dark:bg-neutral-800 rounded-lg shadow p-4 text-left border-2 transition-colors hover:shadow-md ${borderColor}`}
    >
      <div className="flex items-center justify-between">
        {icon}
        <span className="text-2xl font-bold text-neutral-900 dark:text-white">{count}</span>
      </div>
      <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-2">{label}</p>
    </button>
  );
}
