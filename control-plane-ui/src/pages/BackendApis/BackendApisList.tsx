import { useState, useCallback, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, Search } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { backendApisService } from '../../services/backendApisApi';
import { RegisterApiModal } from './RegisterApiModal';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import { EmptyState } from '@stoa/shared/components/EmptyState';
import type { BackendApi, BackendApiStatus } from '../../types';

const statusConfig: Record<BackendApiStatus, { color: string; label: string }> = {
  draft: {
    color: 'bg-gray-100 text-gray-800 dark:bg-neutral-700 dark:text-neutral-300',
    label: 'Draft',
  },
  active: {
    color: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
    label: 'Active',
  },
  disabled: {
    color: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
    label: 'Disabled',
  },
};

const authTypeLabels: Record<string, string> = {
  none: 'None',
  api_key: 'API Key',
  bearer: 'Bearer',
  basic: 'Basic',
  oauth2_cc: 'OAuth2 CC',
};

const PAGE_SIZE = 20;

export function BackendApisList() {
  const { user, hasPermission } = useAuth();
  const toast = useToastActions();
  const queryClient = useQueryClient();
  const [confirm, ConfirmDialog] = useConfirm();
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [page, setPage] = useState(1);

  const tenantId = user?.tenant_id || '';

  const { data, isLoading, error } = useQuery({
    queryKey: ['backend-apis', tenantId],
    queryFn: () => backendApisService.listBackendApis(tenantId),
    enabled: !!tenantId,
  });

  const filteredApis = useMemo(() => {
    let items = data?.items || [];
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      items = items.filter(
        (api) =>
          api.name.toLowerCase().includes(term) ||
          api.display_name?.toLowerCase().includes(term) ||
          api.backend_url.toLowerCase().includes(term)
      );
    }
    if (statusFilter !== 'all') {
      items = items.filter((api) => api.status === statusFilter);
    }
    return items;
  }, [data?.items, searchTerm, statusFilter]);

  const paginatedApis = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return filteredApis.slice(start, start + PAGE_SIZE);
  }, [filteredApis, page]);

  const totalPages = Math.max(1, Math.ceil(filteredApis.length / PAGE_SIZE));

  const handleToggleStatus = useCallback(
    async (api: BackendApi) => {
      const newStatus = api.status === 'active' ? 'disabled' : 'active';
      try {
        await backendApisService.updateBackendApi(tenantId, api.id, { status: newStatus });
        queryClient.invalidateQueries({ queryKey: ['backend-apis', tenantId] });
        toast.success('Status updated', `${api.name} is now ${newStatus}`);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to update status';
        toast.error('Update failed', message);
      }
    },
    [tenantId, queryClient, toast]
  );

  const handleDelete = useCallback(
    async (api: BackendApi) => {
      const confirmed = await confirm({
        title: 'Delete Backend API',
        message: `Are you sure you want to delete "${api.display_name || api.name}"? This will also revoke any associated API keys.`,
        confirmLabel: 'Delete',
        variant: 'danger',
      });
      if (!confirmed) return;

      try {
        await backendApisService.deleteBackendApi(tenantId, api.id);
        queryClient.invalidateQueries({ queryKey: ['backend-apis', tenantId] });
        toast.success('API deleted', `${api.display_name || api.name} has been removed`);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to delete';
        toast.error('Delete failed', message);
      }
    },
    [tenantId, queryClient, toast, confirm]
  );

  const handleCreated = useCallback(() => {
    setShowCreateModal(false);
    queryClient.invalidateQueries({ queryKey: ['backend-apis', tenantId] });
  }, [tenantId, queryClient]);

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
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Backend APIs</h1>
          <p className="text-gray-500 dark:text-neutral-400 mt-1">
            Register backend APIs to expose them as MCP tools through the gateway
          </p>
        </div>
        {hasPermission('apis:create') && (
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            <Plus className="h-4 w-4" />
            Register API
          </button>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg">
          {error instanceof Error ? error.message : 'Failed to load backend APIs'}
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search APIs..."
            value={searchTerm}
            onChange={(e) => {
              setSearchTerm(e.target.value);
              setPage(1);
            }}
            className="w-full pl-10 pr-3 py-2 border border-gray-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
          className="border border-gray-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white"
        >
          <option value="all">All statuses</option>
          <option value="draft">Draft</option>
          <option value="active">Active</option>
          <option value="disabled">Disabled</option>
        </select>
      </div>

      {/* Table */}
      {filteredApis.length === 0 && !isLoading ? (
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow">
          <EmptyState
            variant="apis"
            title={
              searchTerm || statusFilter !== 'all'
                ? 'No matching APIs'
                : 'No backend APIs registered'
            }
            description={
              searchTerm || statusFilter !== 'all'
                ? 'Try adjusting your filters.'
                : 'Register a backend API to expose it as MCP tools through the gateway.'
            }
            action={
              !searchTerm && statusFilter === 'all' && hasPermission('apis:create')
                ? { label: 'Register API', onClick: () => setShowCreateModal(true) }
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
                  Backend URL
                </th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase">
                  Auth
                </th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase">
                  Status
                </th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase">
                  Tools
                </th>
                <th className="text-right px-4 py-3 text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y dark:divide-neutral-700">
              {paginatedApis.map((api) => {
                const status = statusConfig[api.status];
                return (
                  <tr key={api.id} className="hover:bg-gray-50 dark:hover:bg-neutral-750">
                    <td className="px-4 py-3">
                      <div className="font-medium text-gray-900 dark:text-white">
                        {api.display_name || api.name}
                      </div>
                      <div className="text-xs text-gray-500 dark:text-neutral-400 font-mono">
                        {api.name}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-neutral-300 font-mono truncate max-w-xs">
                      {api.backend_url}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-neutral-300">
                      {authTypeLabels[api.auth_type] || api.auth_type}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex px-2 py-0.5 text-xs font-medium rounded-full ${status.color}`}
                      >
                        {status.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-neutral-300">
                      {api.tool_count}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex justify-end gap-2">
                        {hasPermission('apis:update') && api.status !== 'draft' && (
                          <button
                            onClick={() => handleToggleStatus(api)}
                            className="text-xs px-2 py-1 border border-gray-300 dark:border-neutral-600 rounded hover:bg-gray-50 dark:hover:bg-neutral-700 dark:text-neutral-300"
                          >
                            {api.status === 'active' ? 'Disable' : 'Enable'}
                          </button>
                        )}
                        {hasPermission('apis:delete') && (
                          <button
                            onClick={() => handleDelete(api)}
                            className="text-xs px-2 py-1 text-red-600 border border-red-200 dark:border-red-800 rounded hover:bg-red-50 dark:hover:bg-red-900/20"
                          >
                            Delete
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex justify-between items-center px-4 py-3 border-t dark:border-neutral-700">
              <span className="text-sm text-gray-500 dark:text-neutral-400">
                {filteredApis.length} results
              </span>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="px-3 py-1 text-sm border rounded disabled:opacity-50 dark:border-neutral-600 dark:text-neutral-300"
                >
                  Previous
                </button>
                <span className="px-3 py-1 text-sm text-gray-500 dark:text-neutral-400">
                  {page} / {totalPages}
                </span>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="px-3 py-1 text-sm border rounded disabled:opacity-50 dark:border-neutral-600 dark:text-neutral-300"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Modals */}
      {showCreateModal && (
        <RegisterApiModal
          tenantId={tenantId}
          onClose={() => setShowCreateModal(false)}
          onCreated={handleCreated}
        />
      )}

      {ConfirmDialog}
    </div>
  );
}
