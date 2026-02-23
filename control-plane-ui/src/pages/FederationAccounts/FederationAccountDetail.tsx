import { useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Plus, Users, Clock, Wrench, BarChart3, Ban } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { federationService } from '../../services/federationApi';
import { SubAccountModal } from './SubAccountModal';
import { ToolAllowListModal } from './ToolAllowListModal';
import { ApiKeyRevealDialog } from './ApiKeyRevealDialog';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import { EmptyState } from '@stoa/shared/components/EmptyState';
import type {
  FederationAccountStatus,
  MasterAccountUpdate,
  SubAccountCreatedResponse,
} from '../../types';

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

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export function FederationAccountDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user, hasRole } = useAuth();
  const toast = useToastActions();
  const queryClient = useQueryClient();
  const [confirm, ConfirmDialog] = useConfirm();
  const [showSubAccountModal, setShowSubAccountModal] = useState(false);
  const [revealedKey, setRevealedKey] = useState<SubAccountCreatedResponse | null>(null);
  const [toolEditSub, setToolEditSub] = useState<{ id: string; name: string } | null>(null);
  const [usageDays, setUsageDays] = useState<7 | 30 | 90>(7);

  const tenantId = user?.tenant_id || '';
  const isAdmin = hasRole('cpi-admin') || hasRole('tenant-admin');

  const { data: account, isLoading: accountLoading } = useQuery({
    queryKey: ['federation-account', tenantId, id],
    queryFn: () => federationService.getMasterAccount(tenantId, id!),
    enabled: !!tenantId && !!id,
  });

  const { data: subAccountsData, isLoading: subAccountsLoading } = useQuery({
    queryKey: ['federation-sub-accounts', tenantId, id],
    queryFn: () => federationService.listSubAccounts(tenantId, id!),
    enabled: !!tenantId && !!id,
  });

  const { data: usageData } = useQuery({
    queryKey: ['federation-usage', tenantId, id, usageDays],
    queryFn: () => federationService.getUsage(tenantId, id!, usageDays),
    enabled: !!tenantId && !!id,
  });

  const subAccounts = subAccountsData?.items || [];

  const bulkRevokeMutation = useMutation({
    mutationFn: () => federationService.bulkRevoke(tenantId, id!),
    onSuccess: (result) => {
      queryClient.invalidateQueries({
        queryKey: ['federation-sub-accounts', tenantId, id],
      });
      queryClient.invalidateQueries({ queryKey: ['federation-account', tenantId, id] });
      queryClient.invalidateQueries({ queryKey: ['federation-usage', tenantId, id] });
      toast.success('Bulk revoke complete', `${result.revoked_count} sub-account(s) revoked`);
    },
    onError: (err: unknown) => {
      const message = err instanceof Error ? err.message : 'Failed to bulk revoke';
      toast.error('Bulk revoke failed', message);
    },
  });

  const handleBulkRevoke = useCallback(async () => {
    if (!id) return;
    const items = subAccountsData?.items || [];
    const activeCount = items.filter((s) => s.status === 'active').length;
    if (activeCount === 0) {
      toast.info('No active sub-accounts', 'All sub-accounts are already revoked');
      return;
    }

    const confirmed = await confirm({
      title: 'Revoke All Sub-Accounts',
      message: `Are you sure you want to revoke all ${activeCount} active sub-account(s)? All API keys will stop working immediately.`,
      confirmLabel: 'Revoke All',
      variant: 'danger',
    });
    if (!confirmed) return;

    bulkRevokeMutation.mutate();
  }, [id, subAccountsData, toast, confirm, bulkRevokeMutation]);

  const handleSuspendToggle = useCallback(async () => {
    if (!account || !id) return;
    const newStatus = account.status === 'active' ? 'suspended' : 'active';
    const action = newStatus === 'suspended' ? 'suspend' : 'reactivate';

    const confirmed = await confirm({
      title: `${action.charAt(0).toUpperCase() + action.slice(1)} Account`,
      message: `Are you sure you want to ${action} "${account.name}"?`,
      confirmLabel: action.charAt(0).toUpperCase() + action.slice(1),
      variant: newStatus === 'suspended' ? 'danger' : 'default',
    });
    if (!confirmed) return;

    try {
      const update: MasterAccountUpdate = { status: newStatus };
      await federationService.updateMasterAccount(tenantId, id, update);
      queryClient.invalidateQueries({ queryKey: ['federation-account', tenantId, id] });
      toast.success('Account updated', `${account.name} has been ${action}ed`);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : `Failed to ${action} account`;
      toast.error('Update failed', message);
    }
  }, [account, id, tenantId, queryClient, toast, confirm]);

  const handleDelete = useCallback(async () => {
    if (!account || !id) return;

    const confirmed = await confirm({
      title: 'Delete Master Account',
      message: `Are you sure you want to delete "${account.name}"? All sub-accounts will be revoked. This action cannot be undone.`,
      confirmLabel: 'Delete',
      variant: 'danger',
    });
    if (!confirmed) return;

    try {
      await federationService.deleteMasterAccount(tenantId, id);
      toast.success('Account deleted', `${account.name} has been deleted`);
      navigate('/federation/accounts');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to delete account';
      toast.error('Delete failed', message);
    }
  }, [account, id, tenantId, toast, confirm, navigate]);

  const handleRevokeSubAccount = useCallback(
    async (subId: string, subName: string) => {
      if (!id) return;

      const confirmed = await confirm({
        title: 'Revoke Sub-Account',
        message: `Are you sure you want to revoke "${subName}"? The API key will stop working immediately.`,
        confirmLabel: 'Revoke',
        variant: 'danger',
      });
      if (!confirmed) return;

      try {
        await federationService.revokeSubAccount(tenantId, id, subId);
        queryClient.invalidateQueries({
          queryKey: ['federation-sub-accounts', tenantId, id],
        });
        toast.success('Sub-account revoked', `${subName} has been revoked`);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to revoke sub-account';
        toast.error('Revoke failed', message);
      }
    },
    [id, tenantId, queryClient, toast, confirm]
  );

  const handleSubAccountCreated = useCallback(
    (result: SubAccountCreatedResponse) => {
      setShowSubAccountModal(false);
      setRevealedKey(result);
      queryClient.invalidateQueries({
        queryKey: ['federation-sub-accounts', tenantId, id],
      });
      queryClient.invalidateQueries({ queryKey: ['federation-account', tenantId, id] });
    },
    [tenantId, id, queryClient]
  );

  const isLoading = accountLoading || subAccountsLoading;

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-64 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-6 space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-6 bg-neutral-100 dark:bg-neutral-700 rounded animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (!account) {
    return (
      <div className="space-y-6">
        <button
          onClick={() => navigate('/federation/accounts')}
          className="flex items-center gap-1 text-sm text-neutral-500 hover:text-neutral-700 dark:text-neutral-400 dark:hover:text-neutral-200"
        >
          <ArrowLeft className="h-4 w-4" /> Back to Federation
        </button>
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg">
          Account not found
        </div>
      </div>
    );
  }

  const status = statusConfig[account.status];

  return (
    <div className="space-y-6">
      {/* Back link */}
      <button
        onClick={() => navigate('/federation/accounts')}
        className="flex items-center gap-1 text-sm text-neutral-500 hover:text-neutral-700 dark:text-neutral-400 dark:hover:text-neutral-200"
      >
        <ArrowLeft className="h-4 w-4" /> Back to Federation
      </button>

      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">{account.name}</h1>
            <span
              className={`inline-flex px-2 py-0.5 text-xs font-medium rounded-full ${status.color}`}
            >
              {status.label}
            </span>
          </div>
          {account.description && (
            <p className="text-neutral-500 dark:text-neutral-400 mt-1">{account.description}</p>
          )}
        </div>
        {isAdmin && account.status !== 'revoked' && (
          <div className="flex gap-2">
            <button
              onClick={handleSuspendToggle}
              className="px-3 py-1.5 text-sm border border-yellow-300 dark:border-yellow-700 text-yellow-700 dark:text-yellow-400 rounded-lg hover:bg-yellow-50 dark:hover:bg-yellow-900/20"
            >
              {account.status === 'active' ? 'Suspend' : 'Reactivate'}
            </button>
            <button
              onClick={handleBulkRevoke}
              disabled={bulkRevokeMutation.isPending}
              className="flex items-center gap-1 px-3 py-1.5 text-sm border border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50"
            >
              <Ban className="h-3.5 w-3.5" />
              Revoke All
            </button>
            <button
              onClick={handleDelete}
              className="px-3 py-1.5 text-sm border border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20"
            >
              Delete
            </button>
          </div>
        )}
      </div>

      {/* Info card */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <div className="text-xs text-neutral-500 dark:text-neutral-400 uppercase font-medium">
              Sub-accounts
            </div>
            <div className="mt-1 flex items-center gap-1 text-lg font-semibold text-neutral-900 dark:text-white">
              <Users className="h-4 w-4 text-neutral-400" />
              {account.sub_account_count} / {account.max_sub_accounts}
            </div>
          </div>
          <div>
            <div className="text-xs text-neutral-500 dark:text-neutral-400 uppercase font-medium">
              Created
            </div>
            <div className="mt-1 flex items-center gap-1 text-sm text-neutral-900 dark:text-white">
              <Clock className="h-4 w-4 text-neutral-400" />
              {formatDate(account.created_at)}
            </div>
          </div>
          <div>
            <div className="text-xs text-neutral-500 dark:text-neutral-400 uppercase font-medium">
              Updated
            </div>
            <div className="mt-1 text-sm text-neutral-900 dark:text-white">
              {formatDate(account.updated_at)}
            </div>
          </div>
          <div>
            <div className="text-xs text-neutral-500 dark:text-neutral-400 uppercase font-medium">
              Requests ({usageDays}d)
            </div>
            <div className="mt-1 flex items-center gap-1 text-lg font-semibold text-neutral-900 dark:text-white">
              <BarChart3 className="h-4 w-4 text-neutral-400" />
              {usageData ? usageData.total_requests.toLocaleString() : '-'}
            </div>
          </div>
        </div>
      </div>

      {/* Usage breakdown */}
      {usageData && usageData.sub_accounts.length > 0 && (
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow overflow-hidden">
          <div className="px-4 py-3 border-b dark:border-neutral-700 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-neutral-900 dark:text-white">
              Usage Breakdown (last {usageData.period_days} days)
            </h2>
            <select
              value={usageDays}
              onChange={(e) => setUsageDays(Number(e.target.value) as 7 | 30 | 90)}
              aria-label="Usage period"
              className="text-xs border border-neutral-300 dark:border-neutral-600 rounded-md bg-white dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300 px-2 py-1 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value={7}>7 days</option>
              <option value={30}>30 days</option>
              <option value={90}>90 days</option>
            </select>
          </div>
          <table className="w-full">
            <thead>
              <tr className="bg-neutral-50 dark:bg-neutral-800 border-b dark:border-neutral-700">
                <th className="text-left px-4 py-2 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                  Sub-account
                </th>
                <th className="text-right px-4 py-2 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                  Requests
                </th>
                <th className="text-right px-4 py-2 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                  Tokens
                </th>
                <th className="text-right px-4 py-2 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                  Avg Latency
                </th>
                <th className="text-right px-4 py-2 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                  Errors
                </th>
              </tr>
            </thead>
            <tbody className="divide-y dark:divide-neutral-700">
              {usageData.sub_accounts.map((stat) => (
                <tr key={stat.sub_account_id}>
                  <td className="px-4 py-2 text-sm text-neutral-900 dark:text-white">
                    {stat.sub_account_name}
                  </td>
                  <td className="px-4 py-2 text-sm text-right text-neutral-600 dark:text-neutral-300">
                    {stat.total_requests.toLocaleString()}
                  </td>
                  <td className="px-4 py-2 text-sm text-right text-neutral-600 dark:text-neutral-300">
                    {stat.total_tokens.toLocaleString()}
                  </td>
                  <td className="px-4 py-2 text-sm text-right text-neutral-600 dark:text-neutral-300">
                    {stat.avg_latency_ms}ms
                  </td>
                  <td className="px-4 py-2 text-sm text-right">
                    <span
                      className={
                        stat.error_count > 0
                          ? 'text-red-600 dark:text-red-400 font-medium'
                          : 'text-neutral-600 dark:text-neutral-300'
                      }
                    >
                      {stat.error_count}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Sub-accounts section */}
      <div className="space-y-4">
        <div className="flex justify-between items-center">
          <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">Sub-accounts</h2>
          {isAdmin && account.status === 'active' && (
            <button
              onClick={() => setShowSubAccountModal(true)}
              className="flex items-center gap-2 px-3 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              <Plus className="h-3.5 w-3.5" />
              Add Sub-Account
            </button>
          )}
        </div>

        {subAccounts.length === 0 ? (
          <div className="bg-white dark:bg-neutral-800 rounded-lg shadow">
            <EmptyState
              variant="default"
              title="No sub-accounts"
              description="Create a sub-account to delegate API access with scoped permissions."
              action={
                isAdmin && account.status === 'active'
                  ? {
                      label: 'Add Sub-Account',
                      onClick: () => setShowSubAccountModal(true),
                    }
                  : undefined
              }
            />
          </div>
        ) : (
          <div className="bg-white dark:bg-neutral-800 rounded-lg shadow overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800">
                  <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                    Name
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                    Status
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                    API Key
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                    Tools
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                    Last Used
                  </th>
                  <th className="text-right px-4 py-3 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y dark:divide-neutral-700">
                {subAccounts.map((sub) => {
                  const subStatus = statusConfig[sub.status];
                  return (
                    <tr key={sub.id} className="hover:bg-neutral-50 dark:hover:bg-neutral-750">
                      <td className="px-4 py-3">
                        <div className="font-medium text-neutral-900 dark:text-white text-sm">
                          {sub.name}
                        </div>
                        {sub.description && (
                          <div className="text-xs text-neutral-500 dark:text-neutral-400 truncate max-w-xs">
                            {sub.description}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex px-2 py-0.5 text-xs font-medium rounded-full ${subStatus.color}`}
                        >
                          {subStatus.label}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm font-mono text-neutral-600 dark:text-neutral-300">
                        {sub.api_key_prefix}...
                      </td>
                      <td className="px-4 py-3 text-sm text-neutral-600 dark:text-neutral-300">
                        {isAdmin ? (
                          <button
                            onClick={() => setToolEditSub({ id: sub.id, name: sub.name })}
                            className="inline-flex items-center gap-1 text-blue-600 dark:text-blue-400 hover:underline"
                            data-testid={`tools-btn-${sub.id}`}
                          >
                            <Wrench className="h-3.5 w-3.5" />
                            {sub.allowed_tools.length}
                          </button>
                        ) : (
                          <span className="inline-flex items-center gap-1">
                            <Wrench className="h-3.5 w-3.5" />
                            {sub.allowed_tools.length}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm text-neutral-600 dark:text-neutral-300">
                        {formatDate(sub.last_used_at)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {sub.status === 'active' && isAdmin && (
                          <button
                            onClick={() => handleRevokeSubAccount(sub.id, sub.name)}
                            className="text-xs px-2 py-1 text-red-600 border border-red-200 dark:border-red-800 rounded hover:bg-red-50 dark:hover:bg-red-900/20"
                          >
                            Revoke
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
      </div>

      {/* Modals */}
      {showSubAccountModal && id && (
        <SubAccountModal
          tenantId={tenantId}
          masterId={id}
          onClose={() => setShowSubAccountModal(false)}
          onCreated={handleSubAccountCreated}
        />
      )}

      {toolEditSub && id && (
        <ToolAllowListModal
          tenantId={tenantId}
          masterId={id}
          subAccountId={toolEditSub.id}
          subAccountName={toolEditSub.name}
          isAdmin={isAdmin}
          onClose={() => setToolEditSub(null)}
          onSaved={() => {
            setToolEditSub(null);
            queryClient.invalidateQueries({
              queryKey: ['federation-sub-accounts', tenantId, id],
            });
          }}
        />
      )}

      {revealedKey && (
        <ApiKeyRevealDialog
          apiKey={revealedKey.api_key}
          name={revealedKey.name}
          onClose={() => setRevealedKey(null)}
        />
      )}

      {ConfirmDialog}
    </div>
  );
}
