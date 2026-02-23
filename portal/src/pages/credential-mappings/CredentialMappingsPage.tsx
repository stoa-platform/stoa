/**
 * Credential Mappings Page (CAB-1432)
 *
 * Manages consumer→API backend credential mappings.
 * tenant-admin: full CRUD. devops/viewer: read-only list.
 */

import { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Search,
  Plus,
  RefreshCw,
  AlertCircle,
  Key,
  Trash2,
  Pencil,
  X,
  Shield,
  Eye,
  EyeOff,
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import {
  credentialMappingsService,
  type CredentialMapping,
  type CredentialMappingCreate,
  type CredentialMappingUpdate,
  type CredentialAuthType,
} from '../../services/credentialMappings';

const AUTH_TYPE_LABELS: Record<CredentialAuthType, string> = {
  api_key: 'API Key',
  bearer: 'Bearer Token',
  basic: 'Basic Auth',
};

const DEFAULT_HEADERS: Record<CredentialAuthType, string> = {
  api_key: 'X-API-Key',
  bearer: 'Authorization',
  basic: 'Authorization',
};

interface ModalState {
  open: boolean;
  mode: 'create' | 'edit';
  editId?: string;
}

export function CredentialMappingsPage() {
  const { user, isAuthenticated, accessToken } = useAuth();
  const [searchQuery, setSearchQuery] = useState('');
  const [mappings, setMappings] = useState<CredentialMapping[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  // Modal state
  const [modal, setModal] = useState<ModalState>({ open: false, mode: 'create' });
  const [formData, setFormData] = useState<{
    consumer_id: string;
    api_id: string;
    auth_type: CredentialAuthType;
    header_name: string;
    credential_value: string;
    description: string;
  }>({
    consumer_id: '',
    api_id: '',
    auth_type: 'api_key',
    header_name: 'X-API-Key',
    credential_value: '',
    description: '',
  });
  const [showCredential, setShowCredential] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formLoading, setFormLoading] = useState(false);

  const tenantId = user?.tenant_id;

  const isWriteUser = useMemo(() => {
    const roles = user?.roles || [];
    return roles.includes('cpi-admin') || roles.includes('tenant-admin');
  }, [user?.roles]);

  // Load mappings
  useEffect(() => {
    if (!isAuthenticated || !accessToken || !tenantId) return;

    async function loadMappings() {
      setIsLoading(true);
      setError(null);
      try {
        const result = await credentialMappingsService.list(tenantId!);
        setMappings(result.items);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load credential mappings');
      } finally {
        setIsLoading(false);
      }
    }

    loadMappings();
  }, [isAuthenticated, accessToken, tenantId, refreshKey]);

  const filteredMappings = useMemo(() => {
    if (!searchQuery.trim()) return mappings;
    const query = searchQuery.toLowerCase();
    return mappings.filter(
      (m) =>
        m.api_id.toLowerCase().includes(query) ||
        m.consumer_id.toLowerCase().includes(query) ||
        m.header_name.toLowerCase().includes(query) ||
        (m.description && m.description.toLowerCase().includes(query))
    );
  }, [mappings, searchQuery]);

  const handleRefresh = () => setRefreshKey((k) => k + 1);

  const openCreateModal = useCallback(() => {
    setFormData({
      consumer_id: '',
      api_id: '',
      auth_type: 'api_key',
      header_name: 'X-API-Key',
      credential_value: '',
      description: '',
    });
    setFormError(null);
    setShowCredential(false);
    setModal({ open: true, mode: 'create' });
  }, []);

  const openEditModal = useCallback((mapping: CredentialMapping) => {
    setFormData({
      consumer_id: mapping.consumer_id,
      api_id: mapping.api_id,
      auth_type: mapping.auth_type,
      header_name: mapping.header_name,
      credential_value: '',
      description: mapping.description || '',
    });
    setFormError(null);
    setShowCredential(false);
    setModal({ open: true, mode: 'edit', editId: mapping.id });
  }, []);

  const closeModal = useCallback(() => {
    setModal({ open: false, mode: 'create' });
    setFormError(null);
  }, []);

  const handleAuthTypeChange = useCallback((authType: CredentialAuthType) => {
    setFormData((prev) => ({
      ...prev,
      auth_type: authType,
      header_name: DEFAULT_HEADERS[authType],
    }));
  }, []);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!tenantId) return;

      setFormLoading(true);
      setFormError(null);

      try {
        if (modal.mode === 'create') {
          const payload: CredentialMappingCreate = {
            consumer_id: formData.consumer_id,
            api_id: formData.api_id,
            auth_type: formData.auth_type,
            header_name: formData.header_name,
            credential_value: formData.credential_value,
            description: formData.description || undefined,
          };
          await credentialMappingsService.create(tenantId, payload);
        } else if (modal.editId) {
          const payload: CredentialMappingUpdate = {
            auth_type: formData.auth_type,
            header_name: formData.header_name,
            description: formData.description || undefined,
          };
          if (formData.credential_value) {
            payload.credential_value = formData.credential_value;
          }
          await credentialMappingsService.update(tenantId, modal.editId, payload);
        }
        closeModal();
        handleRefresh();
      } catch (err) {
        setFormError(err instanceof Error ? err.message : 'Operation failed');
      } finally {
        setFormLoading(false);
      }
    },
    [tenantId, modal, formData, closeModal]
  );

  const handleDelete = useCallback(
    async (id: string, apiId: string) => {
      if (!tenantId) return;
      if (!window.confirm(`Delete credential mapping for "${apiId}"? This cannot be undone.`))
        return;

      setActionLoading(`delete-${id}`);
      try {
        await credentialMappingsService.delete(tenantId, id);
        setMappings((prev) => prev.filter((m) => m.id !== id));
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Delete failed');
      } finally {
        setActionLoading(null);
      }
    },
    [tenantId]
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white flex items-center gap-2">
            <Key className="h-6 w-6 text-primary-600 dark:text-primary-400" />
            Credential Mappings
          </h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            Map backend API credentials to consumers for automatic injection at the gateway.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleRefresh}
            disabled={isLoading}
            className="p-2 rounded-lg text-neutral-500 hover:text-neutral-700 dark:text-neutral-400 dark:hover:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-700 disabled:opacity-50 transition-colors"
            title="Refresh"
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
          {isWriteUser && (
            <button
              onClick={openCreateModal}
              className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-sm font-medium"
            >
              <Plus className="h-4 w-4" />
              Add Mapping
            </button>
          )}
        </div>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-neutral-400" />
        <input
          type="text"
          placeholder="Search by API, consumer, or header..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full pl-10 pr-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white placeholder-neutral-400 dark:placeholder-neutral-500 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
        />
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 flex items-start gap-3">
          <AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm text-red-700 dark:text-red-400">{error}</p>
            <button
              onClick={() => {
                setError(null);
                handleRefresh();
              }}
              className="text-sm text-red-600 dark:text-red-400 hover:underline mt-1"
            >
              Try again
            </button>
          </div>
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-16 bg-neutral-100 dark:bg-neutral-800 rounded-lg animate-pulse"
            />
          ))}
        </div>
      )}

      {/* Empty state */}
      {!isLoading && !error && filteredMappings.length === 0 && (
        <div className="text-center py-12">
          <Shield className="h-12 w-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-4" />
          <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">
            {searchQuery ? 'No matching credentials' : 'No credential mappings yet'}
          </h2>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            {searchQuery
              ? 'Try adjusting your search terms.'
              : 'Add a mapping to inject backend API credentials automatically.'}
          </p>
          {!searchQuery && isWriteUser && (
            <button
              onClick={openCreateModal}
              className="mt-4 inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-sm font-medium"
            >
              <Plus className="h-4 w-4" />
              Add Mapping
            </button>
          )}
        </div>
      )}

      {/* Table */}
      {!isLoading && filteredMappings.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-neutral-200 dark:border-neutral-700">
                <th className="text-left py-3 px-4 text-neutral-500 dark:text-neutral-400 font-medium">
                  API
                </th>
                <th className="text-left py-3 px-4 text-neutral-500 dark:text-neutral-400 font-medium">
                  Consumer
                </th>
                <th className="text-left py-3 px-4 text-neutral-500 dark:text-neutral-400 font-medium">
                  Auth Type
                </th>
                <th className="text-left py-3 px-4 text-neutral-500 dark:text-neutral-400 font-medium">
                  Header
                </th>
                <th className="text-left py-3 px-4 text-neutral-500 dark:text-neutral-400 font-medium">
                  Status
                </th>
                {isWriteUser && (
                  <th className="text-right py-3 px-4 text-neutral-500 dark:text-neutral-400 font-medium">
                    Actions
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {filteredMappings.map((mapping) => (
                <tr
                  key={mapping.id}
                  className="border-b border-neutral-100 dark:border-neutral-800 hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition-colors"
                >
                  <td className="py-3 px-4">
                    <span className="font-mono text-xs text-neutral-900 dark:text-white">
                      {mapping.api_id}
                    </span>
                  </td>
                  <td className="py-3 px-4">
                    <span className="font-mono text-xs text-neutral-600 dark:text-neutral-400">
                      {mapping.consumer_id.slice(0, 8)}...
                    </span>
                  </td>
                  <td className="py-3 px-4">
                    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-400">
                      <Key className="h-3 w-3" />
                      {AUTH_TYPE_LABELS[mapping.auth_type]}
                    </span>
                  </td>
                  <td className="py-3 px-4">
                    <code className="text-xs bg-neutral-100 dark:bg-neutral-700 px-1.5 py-0.5 rounded">
                      {mapping.header_name}
                    </code>
                  </td>
                  <td className="py-3 px-4">
                    {mapping.is_active ? (
                      <span className="inline-flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
                        <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
                        Active
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-xs text-neutral-500">
                        <span className="h-1.5 w-1.5 rounded-full bg-neutral-400" />
                        Inactive
                      </span>
                    )}
                  </td>
                  {isWriteUser && (
                    <td className="py-3 px-4 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => openEditModal(mapping)}
                          disabled={actionLoading !== null}
                          className="p-1.5 rounded text-neutral-400 hover:text-primary-600 dark:hover:text-primary-400 hover:bg-neutral-100 dark:hover:bg-neutral-700 disabled:opacity-50 transition-colors"
                          title="Edit"
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => handleDelete(mapping.id, mapping.api_id)}
                          disabled={actionLoading === `delete-${mapping.id}`}
                          className="p-1.5 rounded text-neutral-400 hover:text-red-600 dark:hover:text-red-400 hover:bg-neutral-100 dark:hover:bg-neutral-700 disabled:opacity-50 transition-colors"
                          title="Delete"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create/Edit Modal */}
      {modal.open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
          <div className="bg-white dark:bg-neutral-800 rounded-xl shadow-2xl max-w-lg w-full max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between p-6 border-b border-neutral-200 dark:border-neutral-700">
              <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">
                {modal.mode === 'create' ? 'Add Credential Mapping' : 'Edit Credential Mapping'}
              </h2>
              <button
                onClick={closeModal}
                className="p-1.5 rounded-lg text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700 transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="p-6 space-y-4">
              {formError && (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3 text-sm text-red-700 dark:text-red-400">
                  {formError}
                </div>
              )}

              {modal.mode === 'create' && (
                <>
                  <div>
                    <label
                      htmlFor="consumer_id"
                      className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1"
                    >
                      Consumer ID *
                    </label>
                    <input
                      id="consumer_id"
                      type="text"
                      required
                      value={formData.consumer_id}
                      onChange={(e) =>
                        setFormData((prev) => ({ ...prev, consumer_id: e.target.value }))
                      }
                      placeholder="550e8400-e29b-41d4-a716-446655440000"
                      className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white placeholder-neutral-400 dark:placeholder-neutral-500 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none font-mono text-sm"
                    />
                  </div>

                  <div>
                    <label
                      htmlFor="api_id"
                      className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1"
                    >
                      API ID *
                    </label>
                    <input
                      id="api_id"
                      type="text"
                      required
                      value={formData.api_id}
                      onChange={(e) => setFormData((prev) => ({ ...prev, api_id: e.target.value }))}
                      placeholder="weather-api-v1"
                      className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white placeholder-neutral-400 dark:placeholder-neutral-500 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
                    />
                  </div>
                </>
              )}

              <div>
                <label
                  htmlFor="auth_type"
                  className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1"
                >
                  Auth Type *
                </label>
                <select
                  id="auth_type"
                  value={formData.auth_type}
                  onChange={(e) => handleAuthTypeChange(e.target.value as CredentialAuthType)}
                  className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
                >
                  <option value="api_key">API Key</option>
                  <option value="bearer">Bearer Token</option>
                  <option value="basic">Basic Auth</option>
                </select>
              </div>

              <div>
                <label
                  htmlFor="header_name"
                  className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1"
                >
                  Header Name *
                </label>
                <input
                  id="header_name"
                  type="text"
                  required
                  value={formData.header_name}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, header_name: e.target.value }))
                  }
                  placeholder="X-API-Key"
                  className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white placeholder-neutral-400 dark:placeholder-neutral-500 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none font-mono text-sm"
                />
              </div>

              <div>
                <label
                  htmlFor="credential_value"
                  className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1"
                >
                  Credential Value {modal.mode === 'create' ? '*' : '(leave empty to keep current)'}
                </label>
                <div className="relative">
                  <input
                    id="credential_value"
                    type={showCredential ? 'text' : 'password'}
                    required={modal.mode === 'create'}
                    value={formData.credential_value}
                    onChange={(e) =>
                      setFormData((prev) => ({ ...prev, credential_value: e.target.value }))
                    }
                    placeholder={
                      modal.mode === 'edit' ? 'Enter new value to update...' : 'sk-live-abc123...'
                    }
                    className="w-full pl-3 pr-10 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white placeholder-neutral-400 dark:placeholder-neutral-500 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none font-mono text-sm"
                  />
                  <button
                    type="button"
                    onClick={() => setShowCredential((v) => !v)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300"
                  >
                    {showCredential ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              <div>
                <label
                  htmlFor="description"
                  className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1"
                >
                  Description
                </label>
                <input
                  id="description"
                  type="text"
                  value={formData.description}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, description: e.target.value }))
                  }
                  placeholder="ACME Corp production API key"
                  maxLength={500}
                  className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white placeholder-neutral-400 dark:placeholder-neutral-500 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
                />
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={closeModal}
                  className="px-4 py-2 text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={formLoading}
                  className="px-4 py-2 text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 rounded-lg disabled:opacity-50 transition-colors"
                >
                  {formLoading
                    ? 'Saving...'
                    : modal.mode === 'create'
                      ? 'Create Mapping'
                      : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
