import { useState, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Plus, Users, AlertTriangle } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { federationService } from '../../services/federationApi';
import { MasterAccountModal } from './MasterAccountModal';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import { EmptyState } from '@stoa/shared/components/EmptyState';
import type { FederationAccountStatus } from '../../types';

const statusConfig: Record<FederationAccountStatus, { color: string; label: string }> = {
  active: {
    color: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
    label: 'Active',
  },
  suspended: {
    color: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
    label: 'Suspended',
  },
  revoked: {
    color: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
    label: 'Revoked',
  },
};

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export function FederationAccountsList() {
  const { user, hasRole } = useAuth();
  const navigate = useNavigate();
  const toast = useToastActions();
  const queryClient = useQueryClient();
  const [confirm, ConfirmDialog] = useConfirm();
  const [showCreateModal, setShowCreateModal] = useState(false);

  const tenantId = user?.tenant_id || '';

  const { data, isLoading, error } = useQuery({
    queryKey: ['federation-accounts', tenantId],
    queryFn: () => federationService.listMasterAccounts(tenantId),
    enabled: !!tenantId,
  });

  const handleDelete = useCallback(
    async (accountId: string, accountName: string) => {
      const confirmed = await confirm({
        title: 'Delete Master Account',
        message: `Are you sure you want to delete "${accountName}"? All sub-accounts will be revoked. This action cannot be undone.`,
        confirmLabel: 'Delete',
        variant: 'danger',
      });
      if (!confirmed) return;

      try {
        await federationService.deleteMasterAccount(tenantId, accountId);
        queryClient.invalidateQueries({ queryKey: ['federation-accounts', tenantId] });
        toast.success('Account deleted', `${accountName} has been deleted`);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to delete account';
        toast.error('Delete failed', message);
      }
    },
    [tenantId, queryClient, toast, confirm]
  );

  const accounts = data?.items || [];
  const isAdmin = hasRole('cpi-admin') || hasRole('tenant-admin');
  const canCreate = isAdmin;

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex justify-between items-center">
          <div className="h-8 w-64 bg-gray-200 dark:bg-neutral-700 rounded animate-pulse" />
          <div className="h-10 w-40 bg-gray-200 dark:bg-neutral-700 rounded animate-pulse" />
        </div>
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow">
          <div className="p-6 space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-12 bg-gray-100 dark:bg-neutral-700 rounded animate-pulse" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Federation</h1>
          <p className="text-gray-500 dark:text-neutral-400 mt-1">
            Manage master accounts and delegated sub-accounts for MCP federation
          </p>
        </div>
        {canCreate && (
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            <Plus className="h-4 w-4" />
            Create Account
          </button>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 flex-shrink-0" />
          {error instanceof Error ? error.message : 'Failed to load federation accounts'}
        </div>
      )}

      {/* Table */}
      {accounts.length === 0 ? (
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow">
          <EmptyState
            variant="default"
            title="No federation accounts"
            description="Create a master account to start delegating API access to sub-accounts."
            action={
              canCreate
                ? { label: 'Create Account', onClick: () => setShowCreateModal(true) }
                : undefined
            }
          />
        </div>
      ) : (
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b dark:border-neutral-700 bg-gray-50 dark:bg-neutral-800">
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase">
                  Name
                </th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase">
                  Status
                </th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase">
                  Sub-accounts
                </th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase">
                  Created
                </th>
                <th className="text-right px-4 py-3 text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y dark:divide-neutral-700">
              {accounts.map((account) => {
                const status = statusConfig[account.status];
                return (
                  <tr
                    key={account.id}
                    className="hover:bg-gray-50 dark:hover:bg-neutral-750 cursor-pointer"
                    onClick={() => navigate(`/federation/accounts/${account.id}`)}
                  >
                    <td className="px-4 py-3">
                      <div className="font-medium text-gray-900 dark:text-white text-sm">
                        {account.name}
                      </div>
                      {account.description && (
                        <div className="text-xs text-gray-500 dark:text-neutral-400 truncate max-w-xs">
                          {account.description}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex px-2 py-0.5 text-xs font-medium rounded-full ${status.color}`}
                      >
                        {status.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-neutral-300">
                      <span className="inline-flex items-center gap-1">
                        <Users className="h-3.5 w-3.5" />
                        {account.sub_account_count} / {account.max_sub_accounts}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-neutral-300">
                      {formatDate(account.created_at)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {account.status === 'active' && isAdmin && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDelete(account.id, account.name);
                          }}
                          className="text-xs px-2 py-1 text-red-600 border border-red-200 dark:border-red-800 rounded hover:bg-red-50 dark:hover:bg-red-900/20"
                        >
                          Delete
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Modals */}
      {showCreateModal && (
        <MasterAccountModal
          tenantId={tenantId}
          onClose={() => setShowCreateModal(false)}
          onCreated={() => {
            setShowCreateModal(false);
            queryClient.invalidateQueries({ queryKey: ['federation-accounts', tenantId] });
          }}
        />
      )}

      {ConfirmDialog}
    </div>
  );
}
