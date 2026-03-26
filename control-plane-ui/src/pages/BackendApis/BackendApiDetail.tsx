import { useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  Save,
  Trash2,
  Globe,
  Key,
  Clock,
  FileCode,
  Wrench,
  Pencil,
  X,
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { backendApisService } from '../../services/backendApisApi';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import type { BackendApiStatus, BackendApiAuthType, BackendApiUpdate } from '../../types';

const statusConfig: Record<BackendApiStatus, { color: string; label: string }> = {
  draft: {
    color: 'bg-neutral-100 text-neutral-800 dark:bg-neutral-700 dark:text-neutral-300',
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

const authTypeLabels: Record<BackendApiAuthType, string> = {
  none: 'None',
  api_key: 'API Key',
  bearer: 'Bearer Token',
  basic: 'Basic Auth',
  oauth2_cc: 'OAuth2 Client Credentials',
};

export function BackendApiDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user, hasPermission } = useAuth();
  const toast = useToastActions();
  const queryClient = useQueryClient();
  const [confirm, ConfirmDialog] = useConfirm();

  const tenantId = user?.tenant_id || '';

  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editForm, setEditForm] = useState<BackendApiUpdate>({});

  const {
    data: api,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['backend-api', tenantId, id],
    queryFn: () => backendApisService.getBackendApi(tenantId, id!),
    enabled: !!tenantId && !!id,
  });

  const startEditing = useCallback(() => {
    if (!api) return;
    setEditForm({
      display_name: api.display_name || '',
      description: api.description || '',
      backend_url: api.backend_url,
      openapi_spec_url: api.openapi_spec_url || '',
      auth_type: api.auth_type,
    });
    setEditing(true);
  }, [api]);

  const cancelEditing = useCallback(() => {
    setEditing(false);
    setEditForm({});
  }, []);

  const handleSave = useCallback(async () => {
    if (!id) return;

    setSaving(true);
    try {
      await backendApisService.updateBackendApi(tenantId, id, editForm);
      queryClient.invalidateQueries({ queryKey: ['backend-api', tenantId, id] });
      queryClient.invalidateQueries({ queryKey: ['backend-apis', tenantId] });
      setEditing(false);
      toast.success('API updated', 'Backend API configuration saved');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to update';
      toast.error('Update failed', message);
    } finally {
      setSaving(false);
    }
  }, [id, tenantId, editForm, queryClient, toast]);

  const handleToggleStatus = useCallback(async () => {
    if (!api || !id) return;
    const newStatus = api.status === 'active' ? 'disabled' : 'active';
    try {
      await backendApisService.updateBackendApi(tenantId, id, { status: newStatus });
      queryClient.invalidateQueries({ queryKey: ['backend-api', tenantId, id] });
      queryClient.invalidateQueries({ queryKey: ['backend-apis', tenantId] });
      toast.success('Status updated', `API is now ${newStatus}`);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to update status';
      toast.error('Update failed', message);
    }
  }, [api, id, tenantId, queryClient, toast]);

  const handleDelete = useCallback(async () => {
    if (!api || !id) return;

    const confirmed = await confirm({
      title: 'Delete Backend API',
      message: `Are you sure you want to delete "${api.display_name || api.name}"? This will also revoke any associated API keys.`,
      confirmLabel: 'Delete',
      variant: 'danger',
    });
    if (!confirmed) return;

    try {
      await backendApisService.deleteBackendApi(tenantId, id);
      queryClient.invalidateQueries({ queryKey: ['backend-apis', tenantId] });
      toast.success('API deleted', `${api.display_name || api.name} has been removed`);
      navigate('/apis?tab=backends');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to delete';
      toast.error('Delete failed', message);
    }
  }, [api, id, tenantId, queryClient, toast, navigate, confirm]);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <div className="h-5 w-5 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
          <div className="h-7 w-64 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
        </div>
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-6">
          <div className="space-y-4">
            {[1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className="h-10 bg-neutral-100 dark:bg-neutral-700 rounded animate-pulse"
              />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (error || !api) {
    return (
      <div className="space-y-6">
        <button
          onClick={() => navigate('/apis?tab=backends')}
          className="flex items-center gap-2 text-sm text-neutral-500 hover:text-neutral-700 dark:text-neutral-400 dark:hover:text-neutral-200"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Backend APIs
        </button>
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg">
          {error instanceof Error ? error.message : 'Backend API not found'}
        </div>
      </div>
    );
  }

  const status = statusConfig[api.status];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/apis?tab=backends')}
            className="p-1 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-200 rounded"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div>
            <h1 className="text-xl font-semibold text-neutral-900 dark:text-white">
              {api.display_name || api.name}
            </h1>
            <p className="text-sm text-neutral-500 dark:text-neutral-400 font-mono">{api.name}</p>
          </div>
          <span
            className={`inline-flex px-2 py-0.5 text-xs font-medium rounded-full ${status.color}`}
          >
            {status.label}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {hasPermission('apis:update') && !editing && (
            <button
              onClick={startEditing}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 dark:text-neutral-300"
            >
              <Pencil className="h-3.5 w-3.5" />
              Edit
            </button>
          )}
          {hasPermission('apis:update') && api.status !== 'draft' && (
            <button
              onClick={handleToggleStatus}
              className="text-sm px-3 py-1.5 border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 dark:text-neutral-300"
            >
              {api.status === 'active' ? 'Disable' : 'Enable'}
            </button>
          )}
          {hasPermission('apis:delete') && (
            <button
              onClick={handleDelete}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-red-600 border border-red-200 dark:border-red-800 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Delete
            </button>
          )}
        </div>
      </div>

      {/* Detail / Edit */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow">
        {editing ? (
          /* Edit Form */
          <div className="p-6 space-y-4">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-lg font-medium text-neutral-900 dark:text-white">
                Edit Configuration
              </h2>
              <button
                onClick={cancelEditing}
                className="p-1 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-200"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div>
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                Display Name
              </label>
              <input
                type="text"
                value={editForm.display_name || ''}
                onChange={(e) => setEditForm((f) => ({ ...f, display_name: e.target.value }))}
                className="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                Description
              </label>
              <textarea
                value={editForm.description || ''}
                onChange={(e) => setEditForm((f) => ({ ...f, description: e.target.value }))}
                rows={3}
                className="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                Backend URL
              </label>
              <input
                type="url"
                value={editForm.backend_url || ''}
                onChange={(e) => setEditForm((f) => ({ ...f, backend_url: e.target.value }))}
                className="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 font-mono"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                OpenAPI Spec URL
              </label>
              <input
                type="url"
                value={editForm.openapi_spec_url || ''}
                onChange={(e) => setEditForm((f) => ({ ...f, openapi_spec_url: e.target.value }))}
                placeholder="https://example.com/openapi.json"
                className="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 font-mono"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                Auth Type
              </label>
              <select
                value={editForm.auth_type || 'none'}
                onChange={(e) =>
                  setEditForm((f) => ({
                    ...f,
                    auth_type: e.target.value as BackendApiAuthType,
                  }))
                }
                className="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500"
              >
                {Object.entries(authTypeLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex justify-end gap-3 pt-2 border-t dark:border-neutral-700">
              <button
                onClick={cancelEditing}
                className="px-4 py-2 text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 dark:text-neutral-300"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex items-center gap-1.5 px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                <Save className="h-3.5 w-3.5" />
                {saving ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        ) : (
          /* Detail View */
          <div className="divide-y dark:divide-neutral-700">
            {api.description && (
              <div className="px-6 py-4">
                <p className="text-sm text-neutral-600 dark:text-neutral-300">{api.description}</p>
              </div>
            )}

            <div className="px-6 py-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="flex items-start gap-3">
                <Globe className="h-4 w-4 text-neutral-400 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                    Backend URL
                  </p>
                  <p className="text-sm text-neutral-900 dark:text-white font-mono break-all">
                    {api.backend_url}
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-3">
                <Key className="h-4 w-4 text-neutral-400 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                    Authentication
                  </p>
                  <p className="text-sm text-neutral-900 dark:text-white">
                    {authTypeLabels[api.auth_type] || api.auth_type}
                    {api.has_credentials && (
                      <span className="ml-2 text-xs text-green-600 dark:text-green-400">
                        credentials configured
                      </span>
                    )}
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-3">
                <Wrench className="h-4 w-4 text-neutral-400 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                    MCP Tools
                  </p>
                  <p className="text-sm text-neutral-900 dark:text-white">
                    {api.tool_count} tool{api.tool_count !== 1 ? 's' : ''} generated
                  </p>
                </div>
              </div>

              {api.openapi_spec_url && (
                <div className="flex items-start gap-3">
                  <FileCode className="h-4 w-4 text-neutral-400 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                      OpenAPI Spec
                    </p>
                    <p className="text-sm text-neutral-900 dark:text-white font-mono break-all">
                      {api.openapi_spec_url}
                    </p>
                    {api.spec_hash && (
                      <p className="text-xs text-neutral-400 mt-0.5">
                        Hash: {api.spec_hash.slice(0, 12)}...
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>

            <div className="px-6 py-4">
              <div className="flex items-center gap-6 text-xs text-neutral-500 dark:text-neutral-400">
                <span className="flex items-center gap-1.5">
                  <Clock className="h-3.5 w-3.5" />
                  Created {new Date(api.created_at).toLocaleDateString()}
                </span>
                <span>Updated {new Date(api.updated_at).toLocaleDateString()}</span>
                {api.last_synced_at && (
                  <span>Last synced {new Date(api.last_synced_at).toLocaleDateString()}</span>
                )}
                {api.created_by && <span>By {api.created_by}</span>}
              </div>
            </div>
          </div>
        )}
      </div>

      {ConfirmDialog}
    </div>
  );
}
