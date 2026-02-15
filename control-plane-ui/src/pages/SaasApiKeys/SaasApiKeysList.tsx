import { useState, useCallback, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, Copy, Check } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { backendApisService } from '../../services/backendApisApi';
import { CreateKeyModal } from './CreateKeyModal';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import { EmptyState } from '@stoa/shared/components/EmptyState';
import type { SaasApiKeyStatus, SaasApiKeyCreatedResponse } from '../../types';

const statusConfig: Record<SaasApiKeyStatus, { color: string; label: string }> = {
  active: {
    color: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
    label: 'Active',
  },
  revoked: {
    color: 'bg-gray-100 text-gray-800 dark:bg-neutral-700 dark:text-neutral-300',
    label: 'Revoked',
  },
  expired: {
    color: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
    label: 'Expired',
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

export function SaasApiKeysList() {
  const { user, hasPermission } = useAuth();
  const toast = useToastActions();
  const queryClient = useQueryClient();
  const [confirm, ConfirmDialog] = useConfirm();
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [revealedKey, setRevealedKey] = useState<SaasApiKeyCreatedResponse | null>(null);
  const [copied, setCopied] = useState(false);

  const tenantId = user?.tenant_id || '';

  const { data, isLoading, error } = useQuery({
    queryKey: ['saas-keys', tenantId],
    queryFn: () => backendApisService.listSaasKeys(tenantId),
    enabled: !!tenantId,
  });

  const { data: backendApis } = useQuery({
    queryKey: ['backend-apis', tenantId],
    queryFn: () => backendApisService.listBackendApis(tenantId),
    enabled: !!tenantId,
  });

  const apiNameMap = useMemo(() => {
    const map: Record<string, string> = {};
    for (const api of backendApis?.items || []) {
      map[api.id] = api.display_name || api.name;
    }
    return map;
  }, [backendApis?.items]);

  const handleRevoke = useCallback(
    async (keyId: string, keyName: string) => {
      const confirmed = await confirm({
        title: 'Revoke API Key',
        message: `Are you sure you want to revoke "${keyName}"? This action cannot be undone.`,
        confirmLabel: 'Revoke',
        variant: 'danger',
      });
      if (!confirmed) return;

      try {
        await backendApisService.revokeSaasKey(tenantId, keyId);
        queryClient.invalidateQueries({ queryKey: ['saas-keys', tenantId] });
        toast.success('Key revoked', `${keyName} has been revoked`);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to revoke key';
        toast.error('Revoke failed', message);
      }
    },
    [tenantId, queryClient, toast, confirm]
  );

  const handleKeyCreated = useCallback(
    (result: SaasApiKeyCreatedResponse) => {
      setShowCreateModal(false);
      setRevealedKey(result);
      setCopied(false);
      queryClient.invalidateQueries({ queryKey: ['saas-keys', tenantId] });
    },
    [tenantId, queryClient]
  );

  const handleCopyKey = useCallback(async () => {
    if (!revealedKey) return;
    await navigator.clipboard.writeText(revealedKey.key);
    setCopied(true);
    toast.success('Copied!', 'API key copied to clipboard');
    setTimeout(() => setCopied(false), 2000);
  }, [revealedKey, toast]);

  const keys = data?.items || [];

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex justify-between items-center">
          <div className="h-8 w-48 bg-gray-200 dark:bg-neutral-700 rounded animate-pulse" />
          <div className="h-10 w-32 bg-gray-200 dark:bg-neutral-700 rounded animate-pulse" />
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
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">API Keys</h1>
          <p className="text-gray-500 dark:text-neutral-400 mt-1">
            Create scoped API keys to access backend APIs through the gateway
          </p>
        </div>
        {hasPermission('apis:create') && (
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            <Plus className="h-4 w-4" />
            Create Key
          </button>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg">
          {error instanceof Error ? error.message : 'Failed to load API keys'}
        </div>
      )}

      {/* Table */}
      {keys.length === 0 ? (
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow">
          <EmptyState
            variant="default"
            title="No API keys created"
            description="Create a scoped API key to authenticate requests to your backend APIs through the gateway."
            action={
              hasPermission('apis:create')
                ? { label: 'Create Key', onClick: () => setShowCreateModal(true) }
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
                  Key
                </th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase">
                  Name
                </th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase">
                  Allowed APIs
                </th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase">
                  RPM
                </th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase">
                  Status
                </th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase">
                  Expires
                </th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase">
                  Last Used
                </th>
                <th className="text-right px-4 py-3 text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y dark:divide-neutral-700">
              {keys.map((key) => {
                const status = statusConfig[key.status];
                return (
                  <tr key={key.id} className="hover:bg-gray-50 dark:hover:bg-neutral-750">
                    <td className="px-4 py-3 text-sm font-mono text-gray-600 dark:text-neutral-300">
                      {key.key_prefix}...
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-medium text-gray-900 dark:text-white text-sm">
                        {key.name}
                      </div>
                      {key.description && (
                        <div className="text-xs text-gray-500 dark:text-neutral-400 truncate max-w-xs">
                          {key.description}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-neutral-300">
                      {key.allowed_backend_api_ids.length === 0 ? (
                        '-'
                      ) : (
                        <span
                          title={key.allowed_backend_api_ids
                            .map((id) => apiNameMap[id] || id)
                            .join(', ')}
                        >
                          {key.allowed_backend_api_ids.length} API
                          {key.allowed_backend_api_ids.length !== 1 ? 's' : ''}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-neutral-300">
                      {key.rate_limit_rpm ?? '-'}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex px-2 py-0.5 text-xs font-medium rounded-full ${status.color}`}
                      >
                        {status.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-neutral-300">
                      {formatDate(key.expires_at)}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-neutral-300">
                      {formatDate(key.last_used_at)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {key.status === 'active' && hasPermission('apis:delete') && (
                        <button
                          onClick={() => handleRevoke(key.id, key.name)}
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

      {/* Key reveal dialog */}
      {revealedKey && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-xl w-full max-w-lg p-6 space-y-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">API Key Created</h2>
            <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 text-yellow-800 dark:text-yellow-300 px-4 py-3 rounded-lg text-sm">
              Copy this key now. It will not be shown again.
            </div>
            <div className="flex items-center gap-2">
              <code className="flex-1 bg-gray-100 dark:bg-neutral-700 px-4 py-3 rounded-lg text-sm font-mono text-gray-900 dark:text-white break-all select-all">
                {revealedKey.key}
              </code>
              <button
                onClick={handleCopyKey}
                className="flex-shrink-0 p-2 border border-gray-300 dark:border-neutral-600 rounded-lg hover:bg-gray-50 dark:hover:bg-neutral-700"
                title="Copy to clipboard"
              >
                {copied ? (
                  <Check className="h-5 w-5 text-green-500" />
                ) : (
                  <Copy className="h-5 w-5 text-gray-500 dark:text-neutral-400" />
                )}
              </button>
            </div>
            <div className="text-sm text-gray-500 dark:text-neutral-400">
              <strong>Name:</strong> {revealedKey.name}
              <br />
              <strong>Prefix:</strong> {revealedKey.key_prefix}
            </div>
            <div className="flex justify-end">
              <button
                onClick={() => setRevealedKey(null)}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modals */}
      {showCreateModal && (
        <CreateKeyModal
          tenantId={tenantId}
          onClose={() => setShowCreateModal(false)}
          onCreated={handleKeyCreated}
        />
      )}

      {ConfirmDialog}
    </div>
  );
}
