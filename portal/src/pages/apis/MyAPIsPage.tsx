/**
 * My APIs Page (CAB-1634)
 *
 * Self-service management page for tenant-owned APIs.
 * Allows tenant-admins to register, update, delete their APIs.
 * Devops users can view. Viewers can only view.
 */

import { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Search,
  Plus,
  RefreshCw,
  AlertCircle,
  BookOpen,
  Trash2,
  CheckCircle,
  XCircle,
  Clock,
  ChevronDown,
  ChevronUp,
  Globe,
  Tag,
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import {
  tenantApisService,
  type TenantAPI,
  type TenantAPICreatePayload,
} from '../../services/tenantApis';

const statusColors: Record<string, { bg: string; text: string; icon: React.ElementType }> = {
  published: {
    bg: 'bg-green-100 dark:bg-green-900/30',
    text: 'text-green-700 dark:text-green-400',
    icon: CheckCircle,
  },
  draft: {
    bg: 'bg-amber-100 dark:bg-amber-900/30',
    text: 'text-amber-700 dark:text-amber-400',
    icon: Clock,
  },
  deprecated: {
    bg: 'bg-red-100 dark:bg-red-900/30',
    text: 'text-red-700 dark:text-red-400',
    icon: XCircle,
  },
};

interface RegisterAPIModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: TenantAPICreatePayload) => void;
  isLoading: boolean;
  error: string | null;
}

function RegisterAPIModal({ isOpen, onClose, onSubmit, isLoading, error }: RegisterAPIModalProps) {
  const [name, setName] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [version, setVersion] = useState('1.0.0');
  const [description, setDescription] = useState('');
  const [backendUrl, setBackendUrl] = useState('');
  const [tags, setTags] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      name: name.trim(),
      display_name: displayName.trim(),
      version: version.trim() || '1.0.0',
      description: description.trim(),
      backend_url: backendUrl.trim(),
      tags: tags
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean),
    });
  };

  const resetForm = () => {
    setName('');
    setDisplayName('');
    setVersion('1.0.0');
    setDescription('');
    setBackendUrl('');
    setTags('');
  };

  useEffect(() => {
    if (!isOpen) resetForm();
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="fixed inset-0 bg-black/50"
        onClick={onClose}
        onKeyDown={(e) => e.key === 'Escape' && onClose()}
        role="button"
        tabIndex={-1}
        aria-label="Close modal"
      />
      <div className="relative bg-white dark:bg-neutral-800 rounded-xl shadow-xl max-w-lg w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div className="p-6">
          <h2 className="text-xl font-semibold text-neutral-900 dark:text-white mb-4">
            Register API
          </h2>

          {error && (
            <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
              <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="api-name" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                Name (slug)
              </label>
              <input
                id="api-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                placeholder="my-api"
                pattern="[a-z0-9][a-z0-9-]*[a-z0-9]"
                title="Lowercase letters, numbers, and hyphens only"
                className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              />
            </div>

            <div>
              <label htmlFor="api-display-name" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                Display Name
              </label>
              <input
                id="api-display-name"
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                required
                placeholder="My API"
                className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label htmlFor="api-version" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                  Version
                </label>
                <input
                  id="api-version"
                  type="text"
                  value={version}
                  onChange={(e) => setVersion(e.target.value)}
                  placeholder="1.0.0"
                  className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                />
              </div>
              <div>
                <label htmlFor="api-tags" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                  Tags
                </label>
                <input
                  id="api-tags"
                  type="text"
                  value={tags}
                  onChange={(e) => setTags(e.target.value)}
                  placeholder="rest, internal"
                  className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                />
              </div>
            </div>

            <div>
              <label htmlFor="api-backend-url" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                Backend URL
              </label>
              <input
                id="api-backend-url"
                type="url"
                value={backendUrl}
                onChange={(e) => setBackendUrl(e.target.value)}
                required
                placeholder="https://api.example.com"
                className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              />
            </div>

            <div>
              <label htmlFor="api-description" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                Description
              </label>
              <textarea
                id="api-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Describe your API..."
                rows={3}
                className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 resize-none"
              />
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 border border-neutral-300 dark:border-neutral-600 text-neutral-700 dark:text-neutral-200 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isLoading || !name.trim() || !displayName.trim() || !backendUrl.trim()}
                className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50"
              >
                {isLoading ? 'Registering...' : 'Register API'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

export function MyAPIsPage() {
  const { user, isAuthenticated, accessToken } = useAuth();
  const [searchQuery, setSearchQuery] = useState('');
  const [apis, setApis] = useState<TenantAPI[]>([]);
  const [expandedApi, setExpandedApi] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [isRegisterOpen, setIsRegisterOpen] = useState(false);
  const [registerLoading, setRegisterLoading] = useState(false);
  const [registerError, setRegisterError] = useState<string | null>(null);

  const tenantId = user?.tenant_id;

  const isWriteUser = useMemo(() => {
    const roles = user?.roles || [];
    return roles.includes('cpi-admin') || roles.includes('tenant-admin');
  }, [user?.roles]);

  // Load APIs
  useEffect(() => {
    if (!isAuthenticated || !accessToken || !tenantId) return;

    async function loadApis() {
      setIsLoading(true);
      setError(null);
      try {
        const result = await tenantApisService.list(tenantId!);
        setApis(result.items);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load APIs');
      } finally {
        setIsLoading(false);
      }
    }

    loadApis();
  }, [isAuthenticated, accessToken, tenantId, refreshKey]);

  const filteredApis = useMemo(() => {
    if (!searchQuery.trim()) return apis;
    const query = searchQuery.toLowerCase();
    return apis.filter(
      (a) =>
        a.display_name.toLowerCase().includes(query) ||
        a.name.toLowerCase().includes(query) ||
        a.description.toLowerCase().includes(query)
    );
  }, [apis, searchQuery]);

  const handleRefresh = () => setRefreshKey((k) => k + 1);

  const handleExpandApi = useCallback(
    (apiId: string) => {
      setExpandedApi(expandedApi === apiId ? null : apiId);
    },
    [expandedApi]
  );

  const handleDeleteApi = useCallback(
    async (apiId: string, displayName: string) => {
      if (!tenantId) return;
      if (!window.confirm(`Delete API "${displayName}"? This cannot be undone.`)) return;

      setActionLoading(`delete-${apiId}`);
      try {
        await tenantApisService.delete(tenantId, apiId);
        setApis((prev) => prev.filter((a) => a.id !== apiId));
        if (expandedApi === apiId) {
          setExpandedApi(null);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Delete failed');
      } finally {
        setActionLoading(null);
      }
    },
    [tenantId, expandedApi]
  );

  const handleRegister = useCallback(
    async (payload: TenantAPICreatePayload) => {
      if (!tenantId) return;
      setRegisterLoading(true);
      setRegisterError(null);
      try {
        await tenantApisService.create(tenantId, payload);
        setIsRegisterOpen(false);
        handleRefresh();
      } catch (err) {
        setRegisterError(err instanceof Error ? err.message : 'Registration failed');
      } finally {
        setRegisterLoading(false);
      }
    },
    [tenantId]
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">My APIs</h1>
          <p className="text-neutral-500 dark:text-neutral-400 mt-1">
            Register and manage your tenant APIs
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleRefresh}
            disabled={isLoading}
            className="inline-flex items-center gap-2 px-4 py-2 border border-neutral-300 dark:border-neutral-600 text-neutral-700 dark:text-neutral-200 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          {isWriteUser && (
            <button
              data-testid="register-api-btn"
              onClick={() => setIsRegisterOpen(true)}
              className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
            >
              <Plus className="h-4 w-4" />
              Register API
            </button>
          )}
        </div>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-neutral-400" />
        <input
          type="text"
          placeholder="Search APIs..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full pl-10 pr-4 py-2 border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white placeholder-neutral-500 dark:placeholder-neutral-400 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
        />
      </div>

      {/* Error banner */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-red-500 dark:text-red-400 mt-0.5 flex-shrink-0" />
            <div className="flex-1">
              <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
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
            <button
              onClick={() => setError(null)}
              className="text-red-400 hover:text-red-600 dark:hover:text-red-300 flex-shrink-0"
              aria-label="Dismiss error"
            >
              <XCircle className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="grid grid-cols-1 gap-4">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-5 animate-pulse"
            >
              <div className="h-5 bg-neutral-200 dark:bg-neutral-700 rounded w-1/3 mb-3" />
              <div className="h-4 bg-neutral-100 dark:bg-neutral-700 rounded w-2/3" />
            </div>
          ))}
        </div>
      )}

      {/* API List */}
      {!isLoading && filteredApis.length > 0 && (
        <div className="space-y-3">
          {filteredApis.map((api) => {
            const status = statusColors[api.status] || statusColors.draft;
            const StatusIcon = status.icon;
            const isExpanded = expandedApi === api.id;

            return (
              <div
                key={api.id}
                className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700"
              >
                {/* API Row */}
                <div
                  className="p-5 cursor-pointer hover:bg-neutral-50 dark:hover:bg-neutral-750 transition-colors"
                  onClick={() => handleExpandApi(api.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') handleExpandApi(api.id);
                  }}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="p-2 bg-primary-50 dark:bg-primary-900/30 rounded-lg flex-shrink-0">
                        <BookOpen className="h-5 w-5 text-primary-600 dark:text-primary-400" />
                      </div>
                      <div className="min-w-0">
                        <h3 className="font-semibold text-neutral-900 dark:text-white truncate">
                          {api.display_name}
                        </h3>
                        <p className="text-sm text-neutral-500 dark:text-neutral-400 truncate">
                          {api.name} v{api.version}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 flex-shrink-0 ml-4">
                      {/* Status Badge */}
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded ${status.bg} ${status.text}`}
                      >
                        <StatusIcon className="h-3 w-3" />
                        {api.status}
                      </span>
                      {/* Portal promoted badge */}
                      {api.portal_promoted && (
                        <span className="px-2 py-1 text-xs font-medium bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 rounded">
                          Portal
                        </span>
                      )}
                      {/* Tags count */}
                      {api.tags.length > 0 && (
                        <span className="inline-flex items-center gap-1 text-sm text-neutral-500 dark:text-neutral-400">
                          <Tag className="h-4 w-4" />
                          {api.tags.length}
                        </span>
                      )}
                      {/* Expand icon */}
                      {isExpanded ? (
                        <ChevronUp className="h-5 w-5 text-neutral-400" />
                      ) : (
                        <ChevronDown className="h-5 w-5 text-neutral-400" />
                      )}
                    </div>
                  </div>
                  {api.description && (
                    <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-2 line-clamp-1 pl-12">
                      {api.description}
                    </p>
                  )}
                </div>

                {/* Expanded Detail */}
                {isExpanded && (
                  <div className="border-t border-neutral-200 dark:border-neutral-700 p-5 space-y-4">
                    {/* Detail fields */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div>
                        <dt className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                          Backend URL
                        </dt>
                        <dd className="mt-1 flex items-center gap-2 text-sm text-neutral-900 dark:text-white">
                          <Globe className="h-4 w-4 text-neutral-400 flex-shrink-0" />
                          <span className="truncate">{api.backend_url}</span>
                        </dd>
                      </div>
                      <div>
                        <dt className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                          Version
                        </dt>
                        <dd className="mt-1 text-sm text-neutral-900 dark:text-white">
                          {api.version}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                          Deployment
                        </dt>
                        <dd className="mt-1 flex items-center gap-2">
                          <span
                            className={`px-2 py-0.5 text-xs rounded ${api.deployed_dev ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400' : 'bg-neutral-100 dark:bg-neutral-700 text-neutral-500 dark:text-neutral-400'}`}
                          >
                            Dev {api.deployed_dev ? 'Live' : 'Off'}
                          </span>
                          <span
                            className={`px-2 py-0.5 text-xs rounded ${api.deployed_staging ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400' : 'bg-neutral-100 dark:bg-neutral-700 text-neutral-500 dark:text-neutral-400'}`}
                          >
                            Staging {api.deployed_staging ? 'Live' : 'Off'}
                          </span>
                        </dd>
                      </div>
                      {api.tags.length > 0 && (
                        <div>
                          <dt className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                            Tags
                          </dt>
                          <dd className="mt-1 flex flex-wrap gap-1">
                            {api.tags.map((tag) => (
                              <span
                                key={tag}
                                className="px-2 py-0.5 text-xs bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300 rounded"
                              >
                                {tag}
                              </span>
                            ))}
                          </dd>
                        </div>
                      )}
                    </div>

                    {/* Actions */}
                    {isWriteUser && (
                      <div className="flex flex-wrap gap-2 pt-2 border-t border-neutral-100 dark:border-neutral-700">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteApi(api.id, api.display_name);
                          }}
                          disabled={actionLoading === `delete-${api.id}`}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm border border-red-300 dark:border-red-800 text-red-600 dark:text-red-400 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors disabled:opacity-50"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          {actionLoading === `delete-${api.id}` ? 'Deleting...' : 'Delete'}
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Empty state */}
      {!isLoading && filteredApis.length === 0 && (
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-12 text-center">
          <BookOpen className="h-12 w-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-neutral-900 dark:text-white mb-2">
            {searchQuery ? 'No APIs match your search' : 'No APIs registered yet'}
          </h3>
          <p className="text-neutral-500 dark:text-neutral-400 mb-6">
            {searchQuery
              ? 'Try adjusting your search terms.'
              : 'Register your first API to get started with the catalog.'}
          </p>
          {!searchQuery && isWriteUser && (
            <button
              onClick={() => setIsRegisterOpen(true)}
              className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
            >
              <Plus className="h-4 w-4" />
              Register API
            </button>
          )}
        </div>
      )}

      {/* Register Modal */}
      <RegisterAPIModal
        isOpen={isRegisterOpen}
        onClose={() => {
          setIsRegisterOpen(false);
          setRegisterError(null);
        }}
        onSubmit={handleRegister}
        isLoading={registerLoading}
        error={registerError}
      />
    </div>
  );
}
