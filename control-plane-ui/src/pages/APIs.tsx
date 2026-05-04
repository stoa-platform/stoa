import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { apiService, type ApiLifecycleCreateDraftRequest } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { useEnvironment } from '../contexts/EnvironmentContext';
import { useEnvironmentMode } from '../hooks/useEnvironmentMode';
import { useDebounce } from '../hooks/useDebounce';
import { useMediaQuery } from '../hooks/useMediaQuery';
import type { API, APICreate } from '../types';
import yaml from 'js-yaml';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import { EmptyState } from '@stoa/shared/components/EmptyState';
import { TableSkeleton } from '@stoa/shared/components/Skeleton';
import { useCelebration } from '@stoa/shared/components/Celebration';
import { Collapsible } from '@stoa/shared/components/Collapsible';
import { FileText, Server, Code2, Settings, Plus } from 'lucide-react';
import { Button } from '@stoa/shared/components/Button';

const PAGE_SIZE = 20;

// Status colors moved outside component to prevent recreation
const statusColors: Record<string, string> = {
  draft: 'bg-neutral-100 text-neutral-800 dark:bg-neutral-700 dark:text-neutral-300',
  published: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  deprecated: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
};

const ALL_TENANTS = '__all__';
const LEGACY_PORTAL_TAGS = new Set(['portal:published', 'promoted:portal', 'portal-promoted']);

const runtimeStatusColors: Record<string, string> = {
  synced: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
  pending: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
  syncing: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  drifted: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
  error: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  none: 'bg-neutral-100 text-neutral-500 dark:bg-neutral-700 dark:text-neutral-400',
};

function sanitizedApiTags(tags: string[] | undefined): string[] {
  return (tags || []).filter((tag) => !LEGACY_PORTAL_TAGS.has(tag));
}

function RuntimeDeploymentBadges({ api }: { api: API }) {
  const summaries =
    api.runtime_deployments && api.runtime_deployments.length > 0
      ? api.runtime_deployments
      : [
          {
            environment: 'dev',
            status: api.deployed_dev ? 'synced' : 'none',
            gateway_count: api.deployed_dev ? 1 : 0,
            synced_count: api.deployed_dev ? 1 : 0,
            error_count: 0,
            pending_count: 0,
            drifted_count: 0,
            latest_error: null,
            gateway_names: [],
          },
          {
            environment: 'staging',
            status: api.deployed_staging ? 'synced' : 'none',
            gateway_count: api.deployed_staging ? 1 : 0,
            synced_count: api.deployed_staging ? 1 : 0,
            error_count: 0,
            pending_count: 0,
            drifted_count: 0,
            latest_error: null,
            gateway_names: [],
          },
        ];

  return (
    <div className="flex flex-wrap gap-1.5" data-testid="api-runtime-deployments">
      {summaries.map((summary) => {
        const title = [
          `${summary.environment}: ${summary.status}`,
          summary.gateway_count ? `${summary.gateway_count} gateway target(s)` : null,
          summary.gateway_names?.length ? summary.gateway_names.join(', ') : null,
          summary.latest_error ? `Error: ${summary.latest_error}` : null,
        ]
          .filter(Boolean)
          .join(' · ');
        return (
          <span
            key={`${summary.environment}:${summary.status}:${summary.gateway_names?.join(',') || ''}`}
            title={title}
            className={`px-2 py-1 rounded text-xs font-medium ${
              runtimeStatusColors[summary.status] || runtimeStatusColors.none
            }`}
          >
            {summary.environment.toUpperCase()} {summary.status}
          </span>
        );
      })}
    </div>
  );
}

function parseSpecDocument(content: string): Record<string, unknown> {
  let spec: unknown;
  try {
    spec = JSON.parse(content);
  } catch {
    spec = yaml.load(content);
  }
  if (!spec || typeof spec !== 'object' || Array.isArray(spec)) {
    throw new Error('OpenAPI/Swagger spec must be a JSON or YAML object');
  }
  return spec as Record<string, unknown>;
}

export function APIs() {
  const { isReady, hasRole } = useAuth();
  const isAdmin = hasRole('cpi-admin');
  const { activeEnvironment } = useEnvironment();
  const { canCreate, canEdit, canDelete, isReadOnly } = useEnvironmentMode();
  const isMobile = useMediaQuery('(max-width: 767px)');
  const toast = useToastActions();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [confirm, ConfirmDialog] = useConfirm();
  const { celebrate } = useCelebration();
  const [selectedTenant, setSelectedTenant] = useState<string>('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingApi, setEditingApi] = useState<API | null>(null);

  // Search and pagination state
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string>('');

  // Debounce search for performance (300ms delay)
  const debouncedSearch = useDebounce(searchQuery, 300);

  // Fetch tenants via React Query (long staleTime — tenants rarely change)
  const {
    data: tenants = [],
    isLoading: tenantsLoading,
    error: tenantsError,
  } = useQuery({
    queryKey: ['tenants'],
    queryFn: () => apiService.getTenants(),
    enabled: isReady,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  // Auto-select: admin defaults to "All tenants", others get first tenant
  useEffect(() => {
    if (!selectedTenant) {
      if (isAdmin) {
        setSelectedTenant(ALL_TENANTS);
      } else if (tenants.length > 0) {
        setSelectedTenant(tenants[0].id);
      }
    }
  }, [tenants, selectedTenant, isAdmin]);

  // Fetch APIs for selected tenant via React Query
  const {
    data: apis = [],
    isLoading: apisLoading,
    error: apisError,
  } = useQuery({
    queryKey: ['apis', selectedTenant, activeEnvironment],
    queryFn: () =>
      selectedTenant === ALL_TENANTS
        ? apiService.getAdminApis()
        : apiService.getApis(selectedTenant, activeEnvironment),
    enabled: !!selectedTenant,
  });

  const isFirstApi = apis.length === 0 && !apisLoading;
  const loading = tenantsLoading || apisLoading;
  const error = tenantsError || apisError;

  // Reset pagination when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [debouncedSearch, statusFilter, selectedTenant]);

  // Client-side filtering and pagination (memoized for performance)
  const filteredApis = useMemo(() => {
    let result = apis;

    // Apply search filter
    if (debouncedSearch) {
      const searchLower = debouncedSearch.toLowerCase();
      result = result.filter(
        (api) =>
          api.name.toLowerCase().includes(searchLower) ||
          (api.display_name || '').toLowerCase().includes(searchLower) ||
          (api.description || '').toLowerCase().includes(searchLower) ||
          (api.backend_url || '').toLowerCase().includes(searchLower)
      );
    }

    // Apply status filter
    if (statusFilter) {
      result = result.filter((api) => api.status === statusFilter);
    }

    return result;
  }, [apis, debouncedSearch, statusFilter]);

  // Paginated results
  const paginatedApis = useMemo(() => {
    const startIndex = (currentPage - 1) * PAGE_SIZE;
    return filteredApis.slice(startIndex, startIndex + PAGE_SIZE);
  }, [filteredApis, currentPage]);

  const totalPages = Math.ceil(filteredApis.length / PAGE_SIZE);

  const invalidateApis = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['apis', selectedTenant, activeEnvironment] });
  }, [queryClient, selectedTenant, activeEnvironment]);

  const getApiDetailHref = useCallback(
    (api: { id: string; name: string; tenant_id?: string }) => {
      const tenantId = api.tenant_id || (selectedTenant !== ALL_TENANTS ? selectedTenant : '');
      return tenantId ? `/apis/${tenantId}/${api.name}` : `/apis/${api.id}`;
    },
    [selectedTenant]
  );

  // Memoized handlers to prevent unnecessary re-renders
  const handleCreate = useCallback(
    async (api: APICreate, _openDeploymentWorkflow: boolean) => {
      try {
        const wasFirstApi = isFirstApi;
        await apiService.createApi(selectedTenant, api);

        setShowCreateModal(false);
        invalidateApis();

        // Celebrate first API creation
        if (wasFirstApi) {
          celebrate();
          toast.success('Welcome!', 'You created your first API. Open its lifecycle to continue.');
        } else {
          toast.success('API created', `${api.display_name || api.name} has been created`);
        }
      } catch (err: any) {
        toast.error('Creation failed', err.message || 'Failed to create API');
      }
    },
    [selectedTenant, isFirstApi, celebrate, toast, invalidateApis]
  );

  const handleCreateLifecycleDraft = useCallback(
    async (draft: ApiLifecycleCreateDraftRequest) => {
      try {
        if (selectedTenant === ALL_TENANTS) {
          throw new Error('Select a concrete tenant before creating a lifecycle draft');
        }
        const state = await apiService.createLifecycleDraft(selectedTenant, draft);
        setShowCreateModal(false);
        invalidateApis();
        toast.success('Lifecycle draft created', `${state.display_name} is ready for validation`);
        navigate(`/apis/${state.tenant_id}/${state.api_id}`);
      } catch (err: any) {
        toast.error('Draft creation failed', err.message || 'Failed to create lifecycle draft');
        throw err;
      }
    },
    [selectedTenant, invalidateApis, toast, navigate]
  );

  const handleUpdate = useCallback(
    async (apiId: string, api: Partial<APICreate>) => {
      try {
        await apiService.updateApi(selectedTenant, apiId, api);
        setEditingApi(null);
        invalidateApis();
      } catch (err: any) {
        toast.error('Update failed', err.message || 'Failed to update API');
      }
    },
    [selectedTenant, invalidateApis, toast]
  );

  const handleDelete = useCallback(
    async (apiId: string, apiName: string) => {
      const confirmed = await confirm({
        title: 'Delete API',
        message: `Are you sure you want to delete "${apiName}"? This action cannot be undone.`,
        confirmLabel: 'Delete',
        cancelLabel: 'Cancel',
        variant: 'danger',
      });
      if (!confirmed) return;

      try {
        await apiService.deleteApi(selectedTenant, apiId);
        toast.success('API deleted', `${apiName} has been removed`);
        invalidateApis();
      } catch (err: any) {
        toast.error('Delete failed', err.message || 'Failed to delete API');
      }
    },
    [selectedTenant, confirm, toast, invalidateApis]
  );

  // Memoized filter clear handler
  const clearFilters = useCallback(() => {
    setSearchQuery('');
    setStatusFilter('');
  }, []);

  if (loading && tenants.length === 0) {
    return (
      <div className="space-y-6">
        <TableSkeleton
          rows={5}
          columns={6}
          headers={['Name', 'Version', 'Status', 'Portal', 'Deployed', 'Actions']}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {canCreate && (
        <div className="flex justify-end">
          <Button
            onClick={() => setShowCreateModal(true)}
            disabled={!selectedTenant}
            icon={<Plus className="w-5 h-5" />}
          >
            Create API
          </Button>
        </div>
      )}

      {isReadOnly && (
        <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-400 px-4 py-3 rounded-lg text-sm flex items-center gap-2">
          <svg
            className="w-5 h-5 flex-shrink-0"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
            />
          </svg>
          Production environment — read-only. Use Promote from staging to deploy changes.
        </div>
      )}

      {/* Filters */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
        <div className="flex flex-wrap gap-4 items-end">
          {/* Tenant Selector */}
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
              Tenant
            </label>
            <select
              value={selectedTenant}
              onChange={(e) => setSelectedTenant(e.target.value)}
              className="w-48 border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              {isAdmin && <option value={ALL_TENANTS}>All tenants</option>}
              {tenants.map((tenant) => (
                <option key={tenant.id} value={tenant.id}>
                  {tenant.display_name || tenant.name}
                </option>
              ))}
            </select>
          </div>

          {/* Search Input */}
          <div className="flex-1 min-w-[200px]">
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
              Search
            </label>
            <div className="relative">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search by name, description, URL..."
                className="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 pl-10 bg-white dark:bg-neutral-700 dark:text-white dark:placeholder-neutral-400 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
              <svg
                className="absolute left-3 top-2.5 h-5 w-5 text-neutral-400"
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
                  onClick={() => setSearchQuery('')}
                  className="absolute right-3 top-2.5 text-neutral-400 hover:text-neutral-600"
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
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
              Status
            </label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="w-36 border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="">All Status</option>
              <option value="draft">Draft</option>
              <option value="published">Published</option>
              <option value="deprecated">Deprecated</option>
            </select>
          </div>

          {/* Results count */}
          <div className="text-sm text-neutral-500 dark:text-neutral-400 self-end pb-2">
            {filteredApis.length} of {apis.length} APIs
          </div>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg">
          {error.message || 'Failed to load data'}
        </div>
      )}

      {/* APIs List */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow overflow-hidden">
        {loading ? (
          <TableSkeleton
            rows={5}
            columns={6}
            headers={['Name', 'Version', 'Status', 'Portal', 'Deployed', 'Actions']}
          />
        ) : apis.length === 0 ? (
          <EmptyState
            variant="apis"
            action={{
              label: 'Create your first API',
              onClick: () => setShowCreateModal(true),
            }}
          />
        ) : filteredApis.length === 0 ? (
          <EmptyState
            variant="search"
            action={{
              label: 'Clear filters',
              onClick: clearFilters,
            }}
          />
        ) : isMobile ? (
          <div className="divide-y divide-neutral-200 dark:divide-neutral-700">
            {paginatedApis.map((api) => (
              <div key={api.id} className="p-4 space-y-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-neutral-900 dark:text-white truncate">
                      {api.display_name || api.name}
                    </p>
                    <p className="text-xs text-neutral-500 dark:text-neutral-400 truncate">
                      {api.backend_url}
                    </p>
                  </div>
                  <span className="text-xs text-neutral-500 dark:text-neutral-400 flex-shrink-0">
                    v{api.version}
                  </span>
                </div>

                <div className="flex flex-wrap gap-1.5">
                  <span
                    className={`px-2 py-1 text-xs font-medium rounded-full ${statusColors[api.status]}`}
                  >
                    {api.status}
                  </span>
                  {api.portal_promoted && (
                    <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400">
                      Portal
                    </span>
                  )}
                  <RuntimeDeploymentBadges api={api} />
                </div>

                <div className="flex flex-wrap gap-3 pt-1">
                  <a
                    href={getApiDetailHref(api)}
                    className="text-green-600 hover:text-green-800 dark:text-green-400 dark:hover:text-green-300 text-sm py-1"
                  >
                    Open Lifecycle
                  </a>
                  {canEdit && (
                    <button
                      onClick={() => setEditingApi(api)}
                      className="text-neutral-600 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-white text-sm py-1"
                    >
                      Edit
                    </button>
                  )}
                  {canDelete && (
                    <button
                      onClick={() => handleDelete(api.id, api.display_name || api.name)}
                      className="text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300 text-sm py-1"
                    >
                      Delete
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-neutral-200 dark:divide-neutral-700">
              <thead className="bg-neutral-50 dark:bg-neutral-700">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                    Name
                  </th>
                  {selectedTenant === ALL_TENANTS && (
                    <th className="px-6 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                      Tenant
                    </th>
                  )}
                  <th className="px-6 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                    Version
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                    Portal
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                    Deployed
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-neutral-800 divide-y divide-neutral-200 dark:divide-neutral-700">
                {paginatedApis.map((api) => (
                  <tr
                    key={api.id}
                    className="hover:bg-neutral-50 dark:hover:bg-neutral-700 cursor-pointer"
                    onClick={() => navigate(`/apis/${api.tenant_id || selectedTenant}/${api.name}`)}
                  >
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div>
                        <div className="text-sm font-medium text-neutral-900 dark:text-white">
                          {api.display_name || api.name}
                        </div>
                        <div className="text-sm text-neutral-500 dark:text-neutral-400">
                          {api.backend_url}
                        </div>
                      </div>
                    </td>
                    {selectedTenant === ALL_TENANTS && (
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-neutral-600 dark:text-neutral-300">
                        {api.tenant_id}
                      </td>
                    )}
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-neutral-500 dark:text-neutral-400">
                      v{api.version}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span
                        className={`px-2 py-1 text-xs font-medium rounded-full ${statusColors[api.status]}`}
                      >
                        {api.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      {api.portal_promoted ? (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400">
                          <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                            <path
                              fillRule="evenodd"
                              d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                              clipRule="evenodd"
                            />
                          </svg>
                          Published
                        </span>
                      ) : (
                        <span className="text-neutral-400 dark:text-neutral-500 text-xs">
                          Not promoted
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      <RuntimeDeploymentBadges api={api} />
                    </td>
                    <td
                      className="px-6 py-4 whitespace-nowrap text-sm"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <div className="flex gap-2">
                        <a
                          href={getApiDetailHref(api)}
                          className="text-green-600 hover:text-green-800 dark:text-green-400 dark:hover:text-green-300"
                          title="Open lifecycle"
                        >
                          Open Lifecycle
                        </a>
                        {canEdit && (
                          <button
                            onClick={() => setEditingApi(api)}
                            className="text-neutral-600 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-white"
                          >
                            Edit
                          </button>
                        )}
                        {canDelete && (
                          <button
                            onClick={() => handleDelete(api.id, api.display_name || api.name)}
                            className="text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300"
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

        {/* Pagination */}
        {!loading && filteredApis.length > 0 && totalPages > 1 && (
          <div className="bg-neutral-50 dark:bg-neutral-700 px-6 py-3 flex items-center justify-between border-t border-neutral-200 dark:border-neutral-600">
            <div className="text-sm text-neutral-500 dark:text-neutral-400">
              Showing {(currentPage - 1) * PAGE_SIZE + 1} to{' '}
              {Math.min(currentPage * PAGE_SIZE, filteredApis.length)} of {filteredApis.length}{' '}
              results
            </div>
            <div className="flex gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
              >
                Previous
              </Button>
              <span className="px-3 py-1 text-sm text-neutral-700 dark:text-neutral-300">
                Page {currentPage} of {totalPages}
              </span>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Create Modal */}
      {showCreateModal && (
        <APIFormModal
          onClose={() => setShowCreateModal(false)}
          onSubmit={handleCreate}
          onLifecycleSubmit={handleCreateLifecycleDraft}
          title="Create New API"
        />
      )}

      {/* Edit Modal */}
      {editingApi && (
        <APIFormModal
          api={editingApi}
          onClose={() => setEditingApi(null)}
          onSubmit={(data) => handleUpdate(editingApi.id, data)}
          title="Edit API"
          isEdit
        />
      )}

      {/* Confirm Dialog */}
      {ConfirmDialog}
    </div>
  );
}

interface APIFormModalProps {
  api?: API;
  onClose: () => void;
  onSubmit: (data: APICreate, openDeploymentWorkflow: boolean) => Promise<void>;
  onLifecycleSubmit?: (data: ApiLifecycleCreateDraftRequest) => Promise<void>;
  title: string;
  isEdit?: boolean;
}

type CreateMode = 'lifecycle' | 'manual' | 'openapi';

function APIFormModal({
  api,
  onClose,
  onSubmit,
  onLifecycleSubmit,
  title,
  isEdit,
}: APIFormModalProps) {
  const [mode, setMode] = useState<CreateMode>(isEdit ? 'manual' : 'lifecycle');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [specReference, setSpecReference] = useState('');
  const [formData, setFormData] = useState<APICreate>({
    name: api?.name || '',
    display_name: api?.display_name || '',
    version: api?.version || '1.0.0',
    description: api?.description || '',
    backend_url: api?.backend_url || '',
    openapi_spec:
      api?.openapi_spec && typeof api.openapi_spec === 'object'
        ? JSON.stringify(api.openapi_spec, null, 2)
        : (api?.openapi_spec as string) || '',
    tags: api?.tags || [],
    portal_promoted: api?.portal_promoted || false,
  });
  const [parseError, setParseError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      const content = await file.text();
      parseOpenApiSpec(content, file.name);
    } catch (err: any) {
      setParseError(`Failed to read file: ${err.message}`);
    }
  };

  const parseOpenApiSpec = (content: string, _filename?: string) => {
    try {
      setParseError(null);
      const spec: any = parseSpecDocument(content);

      if (!spec) {
        throw new Error('Could not parse OpenAPI/Swagger specification');
      }

      // Validate it's an OpenAPI/Swagger spec
      const isOpenApi3 = spec.openapi && spec.openapi.startsWith('3.');
      const isSwagger2 = spec.swagger && spec.swagger.startsWith('2.');

      if (!isOpenApi3 && !isSwagger2) {
        throw new Error('File must be a valid OpenAPI 3.x or Swagger 2.x specification');
      }

      // Extract info from spec
      const info = spec.info || {};
      const apiName =
        info.title
          ?.toLowerCase()
          .replace(/[^a-z0-9]+/g, '-')
          .replace(/(^-|-$)/g, '') || 'new-api';
      const version = info.version || '1.0.0';
      const description = info.description || '';

      // Try to find backend URL from servers (OpenAPI 3) or host (Swagger 2)
      let backendUrl = '';
      if (isOpenApi3 && spec.servers && spec.servers.length > 0) {
        backendUrl = spec.servers[0].url || '';
      } else if (isSwagger2) {
        const scheme = spec.schemes?.[0] || 'https';
        const host = spec.host || '';
        const basePath = spec.basePath || '';
        if (host) {
          backendUrl = `${scheme}://${host}${basePath}`;
        }
      }

      setFormData({
        name: apiName,
        display_name: info.title || 'New API',
        version,
        description,
        backend_url: backendUrl,
        openapi_spec: content,
        tags: sanitizedApiTags(formData.tags),
        portal_promoted: false,
      });
    } catch (err: any) {
      setParseError(err.message || 'Failed to parse OpenAPI specification');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSubmitting) return;

    const tags = sanitizedApiTags(formData.tags);

    if (mode === 'lifecycle' && !isEdit && onLifecycleSubmit) {
      setParseError(null);
      let openapiSpec: Record<string, unknown> | undefined;
      const specContent = formData.openapi_spec?.trim();
      if (specContent) {
        try {
          openapiSpec = parseSpecDocument(specContent);
        } catch (err: any) {
          setParseError(err.message || 'Failed to parse OpenAPI specification');
          return;
        }
      }

      const reference = specReference.trim();
      if (!openapiSpec && !reference) {
        setParseError(
          'Lifecycle drafts require an inline OpenAPI/Swagger spec or a spec reference'
        );
        return;
      }

      const draft: ApiLifecycleCreateDraftRequest = {
        name: formData.name,
        display_name: formData.display_name,
        version: formData.version,
        description: formData.description,
        backend_url: formData.backend_url,
        openapi_spec: openapiSpec,
        spec_reference: reference || null,
        tags,
      };

      setIsSubmitting(true);
      try {
        await onLifecycleSubmit(draft);
      } finally {
        setIsSubmitting(false);
      }
      return;
    }

    const submitData: APICreate = {
      ...formData,
      tags,
      portal_promoted: false,
    };

    setIsSubmitting(true);
    try {
      await onSubmit(submitData, false);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        <div className="flex justify-between items-center px-6 py-4 border-b dark:border-neutral-700">
          <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">{title}</h2>
          <button
            onClick={onClose}
            className="text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Mode Selector (only for create) */}
        {!isEdit && (
          <div className="px-6 pt-4">
            <div className="flex rounded-lg bg-neutral-100 dark:bg-neutral-700 p-1">
              <button
                type="button"
                onClick={() => setMode('lifecycle')}
                className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
                  mode === 'lifecycle'
                    ? 'bg-white dark:bg-neutral-600 text-neutral-900 dark:text-white shadow'
                    : 'text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300'
                }`}
              >
                Lifecycle Draft
              </button>
              <button
                type="button"
                onClick={() => setMode('manual')}
                className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
                  mode === 'manual'
                    ? 'bg-white dark:bg-neutral-600 text-neutral-900 dark:text-white shadow'
                    : 'text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300'
                }`}
              >
                Manual Entry
              </button>
              <button
                type="button"
                onClick={() => setMode('openapi')}
                className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
                  mode === 'openapi'
                    ? 'bg-white dark:bg-neutral-600 text-neutral-900 dark:text-white shadow'
                    : 'text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300'
                }`}
              >
                Import OpenAPI/Swagger
              </button>
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-4">
          {/* OpenAPI Import Section */}
          {mode === 'openapi' && !isEdit && (
            <div className="space-y-4 pb-4 border-b dark:border-neutral-700">
              <div>
                <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                  Upload OpenAPI/Swagger File
                </label>
                <div className="flex gap-2">
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".json,.yaml,.yml"
                    onChange={handleFileUpload}
                    className="hidden"
                  />
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="flex items-center gap-2 px-4 py-2 border-2 border-dashed border-neutral-300 dark:border-neutral-600 rounded-lg hover:border-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors dark:text-neutral-300"
                  >
                    <svg
                      className="w-5 h-5 text-neutral-400"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                      />
                    </svg>
                    Choose File (.json, .yaml, .yml)
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                  Or Paste OpenAPI/Swagger Content
                </label>
                <textarea
                  value={formData.openapi_spec}
                  onChange={(e) => {
                    setFormData({ ...formData, openapi_spec: e.target.value });
                    if (e.target.value.trim()) {
                      parseOpenApiSpec(e.target.value);
                    }
                  }}
                  className="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
                  rows={8}
                  placeholder={`openapi: "3.0.0"
info:
  title: My API
  version: "1.0.0"
  description: API description
servers:
  - url: https://api.example.com/v1
paths:
  /health:
    get:
      summary: Health check`}
                />
              </div>

              {parseError && (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg text-sm">
                  {parseError}
                </div>
              )}

              {formData.name && !parseError && formData.openapi_spec && (
                <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 text-green-700 dark:text-green-400 px-4 py-3 rounded-lg text-sm">
                  <strong>Parsed successfully!</strong> Found API: {formData.display_name} v
                  {formData.version}
                </div>
              )}
            </div>
          )}

          {/* Basic Information Section */}
          <Collapsible
            title="Basic Information"
            icon={<FileText className="h-4 w-4" />}
            defaultExpanded={true}
            variant="bordered"
          >
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                    Name (slug)
                  </label>
                  <input
                    data-testid="api-form-name"
                    type="text"
                    value={formData.name}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        name: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-'),
                      })
                    }
                    className="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    placeholder="payment-api"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                    Version
                  </label>
                  <input
                    type="text"
                    value={formData.version}
                    onChange={(e) => setFormData({ ...formData, version: e.target.value })}
                    className="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    placeholder="1.0.0"
                    required
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-neutral-700 mb-1">
                  Display Name
                </label>
                <input
                  data-testid="api-form-display-name"
                  type="text"
                  value={formData.display_name}
                  onChange={(e) => setFormData({ ...formData, display_name: e.target.value })}
                  className="w-full border border-neutral-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  placeholder="Payment API"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-neutral-700 mb-1">
                  Description
                </label>
                <textarea
                  data-testid="api-form-description"
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  className="w-full border border-neutral-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  rows={2}
                  placeholder="API for handling payments..."
                />
              </div>
            </div>
          </Collapsible>

          {/* Endpoint Configuration Section */}
          <Collapsible
            title="Endpoint Configuration"
            icon={<Server className="h-4 w-4" />}
            defaultExpanded={true}
            variant="bordered"
          >
            <div>
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                Backend URL
              </label>
              <input
                data-testid="api-form-backend-url"
                type="url"
                value={formData.backend_url}
                onChange={(e) => setFormData({ ...formData, backend_url: e.target.value })}
                className="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="https://backend.internal/api/v1"
                required
              />
              <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                The backend service URL that the Gateway will proxy requests to
              </p>
            </div>
          </Collapsible>

          {/* OpenAPI Spec for manual/lifecycle modes */}
          {(mode === 'manual' || mode === 'lifecycle') && (
            <Collapsible
              title={mode === 'lifecycle' ? 'Lifecycle Contract' : 'OpenAPI Specification'}
              icon={<Code2 className="h-4 w-4" />}
              badge={mode === 'lifecycle' ? 'Required' : 'Optional'}
              defaultExpanded={mode === 'lifecycle'}
              variant="bordered"
            >
              <div className="space-y-3">
                <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                  OpenAPI Spec
                </label>
                <textarea
                  data-testid="api-form-openapi-spec"
                  value={formData.openapi_spec}
                  onChange={(e) => setFormData({ ...formData, openapi_spec: e.target.value })}
                  className="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
                  rows={6}
                  placeholder="Paste OpenAPI/Swagger spec here (YAML or JSON)..."
                />
                {mode === 'lifecycle' && (
                  <label className="block text-sm">
                    <span className="mb-1 block font-medium text-neutral-700 dark:text-neutral-300">
                      Spec reference
                    </span>
                    <input
                      data-testid="lifecycle-spec-reference"
                      type="text"
                      value={specReference}
                      onChange={(e) => setSpecReference(e.target.value)}
                      className="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                      placeholder="optional Git/catalog reference"
                    />
                  </label>
                )}
                <p className="text-xs text-neutral-500 dark:text-neutral-400">
                  {mode === 'lifecycle'
                    ? 'Validation uses this persisted contract. A reference-only draft may fail validation until the backend can resolve it.'
                    : 'Adding an OpenAPI spec enables API documentation and validation.'}
                </p>
                {parseError && mode === 'lifecycle' && (
                  <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg text-sm">
                    {parseError}
                  </div>
                )}
              </div>
            </Collapsible>
          )}

          {!isEdit && mode !== 'lifecycle' && (
            <Collapsible
              title="Lifecycle"
              icon={<Settings className="h-4 w-4" />}
              defaultExpanded={false}
              variant="bordered"
            >
              <p className="text-sm text-neutral-600 dark:text-neutral-400">
                Portal publication and gateway deployment are controlled from the API lifecycle
                panel after creation.
              </p>
            </Collapsible>
          )}

          <div className="flex justify-end gap-3 pt-4 border-t dark:border-neutral-700 mt-6">
            <Button variant="secondary" type="button" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={isSubmitting}>
              {isEdit
                ? 'Update API'
                : mode === 'lifecycle'
                  ? 'Create lifecycle draft'
                  : 'Create API'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
