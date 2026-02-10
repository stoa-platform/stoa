import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiService } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { useDebounce } from '../hooks/useDebounce';
import type { API, APICreate } from '../types';
import yaml from 'js-yaml';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import { EmptyState } from '@stoa/shared/components/EmptyState';
import { TableSkeleton } from '@stoa/shared/components/Skeleton';
import { useCelebration } from '@stoa/shared/components/Celebration';
import { Collapsible } from '@stoa/shared/components/Collapsible';
import { FileText, Server, Code2, Settings } from 'lucide-react';

const PAGE_SIZE = 20;

// Status colors moved outside component to prevent recreation
const statusColors: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-800 dark:bg-neutral-700 dark:text-neutral-300',
  published: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  deprecated: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
};

export function APIs() {
  const { isReady } = useAuth();
  const toast = useToastActions();
  const queryClient = useQueryClient();
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

  // Auto-select first tenant when tenants load
  useEffect(() => {
    if (tenants.length > 0 && !selectedTenant) {
      setSelectedTenant(tenants[0].id);
    }
  }, [tenants, selectedTenant]);

  // Fetch APIs for selected tenant via React Query
  const {
    data: apis = [],
    isLoading: apisLoading,
    error: apisError,
  } = useQuery({
    queryKey: ['apis', selectedTenant],
    queryFn: () => apiService.getApis(selectedTenant),
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
    queryClient.invalidateQueries({ queryKey: ['apis', selectedTenant] });
  }, [queryClient, selectedTenant]);

  // Memoized handlers to prevent unnecessary re-renders
  const handleCreate = useCallback(
    async (api: APICreate, deployToDev: boolean) => {
      try {
        const wasFirstApi = isFirstApi;
        const created = await apiService.createApi(selectedTenant, api);

        // Auto-deploy to DEV if requested
        if (deployToDev) {
          await apiService.createDeployment(selectedTenant, {
            api_id: created.id,
            environment: 'dev',
            version: api.version,
          });
        }

        setShowCreateModal(false);
        invalidateApis();

        // Celebrate first API creation
        if (wasFirstApi) {
          celebrate();
          toast.success('Welcome!', 'You created your first API. Explore the Deploy options next.');
        } else {
          toast.success('API created', `${api.display_name || api.name} has been created`);
        }
      } catch (err: any) {
        toast.error('Creation failed', err.message || 'Failed to create API');
      }
    },
    [selectedTenant, isFirstApi, celebrate, toast, invalidateApis]
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

  const handleDeploy = useCallback(
    async (api: API, environment: 'dev' | 'staging') => {
      try {
        await apiService.createDeployment(selectedTenant, {
          api_id: api.id,
          environment,
          version: api.version,
        });
        toast.success(
          `Deployment started`,
          `${api.name} is being deployed to ${environment.toUpperCase()}`
        );
        invalidateApis();
      } catch (err: any) {
        toast.error('Deployment failed', err.message || 'Failed to deploy API');
      }
    },
    [selectedTenant, toast, invalidateApis]
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
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">APIs</h1>
          <p className="text-gray-500 dark:text-neutral-400 mt-1">
            Manage API definitions and deployments
          </p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          disabled={!selectedTenant}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Create API
        </button>
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
              value={selectedTenant}
              onChange={(e) => setSelectedTenant(e.target.value)}
              className="w-48 border border-gray-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              {tenants.map((tenant) => (
                <option key={tenant.id} value={tenant.id}>
                  {tenant.display_name || tenant.name}
                </option>
              ))}
            </select>
          </div>

          {/* Search Input */}
          <div className="flex-1 min-w-[200px]">
            <label className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-2">
              Search
            </label>
            <div className="relative">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search by name, description, URL..."
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
                  onClick={() => setSearchQuery('')}
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
              onChange={(e) => setStatusFilter(e.target.value)}
              className="w-36 border border-gray-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="">All Status</option>
              <option value="draft">Draft</option>
              <option value="published">Published</option>
              <option value="deprecated">Deprecated</option>
            </select>
          </div>

          {/* Results count */}
          <div className="text-sm text-gray-500 dark:text-neutral-400 self-end pb-2">
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
        ) : (
          <table className="min-w-full divide-y divide-gray-200 dark:divide-neutral-700">
            <thead className="bg-gray-50 dark:bg-neutral-700">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase tracking-wider">
                  Name
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase tracking-wider">
                  Version
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase tracking-wider">
                  Portal
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase tracking-wider">
                  Deployed
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-neutral-800 divide-y divide-gray-200 dark:divide-neutral-700">
              {paginatedApis.map((api) => (
                <tr key={api.id} className="hover:bg-gray-50 dark:hover:bg-neutral-700">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div>
                      <div className="text-sm font-medium text-gray-900 dark:text-white">
                        {api.display_name || api.name}
                      </div>
                      <div className="text-sm text-gray-500 dark:text-neutral-400">
                        {api.backend_url}
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-neutral-400">
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
                    {api.portal_promoted || api.tags?.includes('portal:published') ? (
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
                      <span className="text-gray-400 dark:text-neutral-500 text-xs">
                        Not promoted
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    <div className="flex gap-2">
                      <span
                        className={`px-2 py-1 rounded text-xs ${api.deployed_dev ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' : 'bg-gray-100 text-gray-500 dark:bg-neutral-700 dark:text-neutral-400'}`}
                      >
                        DEV
                      </span>
                      <span
                        className={`px-2 py-1 rounded text-xs ${api.deployed_staging ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' : 'bg-gray-100 text-gray-500 dark:bg-neutral-700 dark:text-neutral-400'}`}
                      >
                        STG
                      </span>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleDeploy(api, 'dev')}
                        className="text-green-600 hover:text-green-800 dark:text-green-400 dark:hover:text-green-300"
                        title="Deploy to DEV"
                      >
                        Deploy DEV
                      </button>
                      <button
                        onClick={() => handleDeploy(api, 'staging')}
                        className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300"
                        title="Deploy to Staging"
                      >
                        Deploy STG
                      </button>
                      <button
                        onClick={() => setEditingApi(api)}
                        className="text-gray-600 hover:text-gray-800 dark:text-neutral-400 dark:hover:text-white"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleDelete(api.id, api.display_name || api.name)}
                        className="text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300"
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* Pagination */}
        {!loading && filteredApis.length > 0 && totalPages > 1 && (
          <div className="bg-gray-50 dark:bg-neutral-700 px-6 py-3 flex items-center justify-between border-t border-gray-200 dark:border-neutral-600">
            <div className="text-sm text-gray-500 dark:text-neutral-400">
              Showing {(currentPage - 1) * PAGE_SIZE + 1} to{' '}
              {Math.min(currentPage * PAGE_SIZE, filteredApis.length)} of {filteredApis.length}{' '}
              results
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="px-3 py-1 text-sm border border-gray-300 dark:border-neutral-600 rounded-lg hover:bg-gray-100 dark:hover:bg-neutral-600 dark:text-neutral-300 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Previous
              </button>
              <span className="px-3 py-1 text-sm text-gray-700 dark:text-neutral-300">
                Page {currentPage} of {totalPages}
              </span>
              <button
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="px-3 py-1 text-sm border border-gray-300 dark:border-neutral-600 rounded-lg hover:bg-gray-100 dark:hover:bg-neutral-600 dark:text-neutral-300 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Create Modal */}
      {showCreateModal && (
        <APIFormModal
          onClose={() => setShowCreateModal(false)}
          onSubmit={handleCreate}
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
  onSubmit: (data: APICreate, deployToDev: boolean) => void;
  title: string;
  isEdit?: boolean;
}

type CreateMode = 'manual' | 'openapi';

function APIFormModal({ api, onClose, onSubmit, title, isEdit }: APIFormModalProps) {
  const [mode, setMode] = useState<CreateMode>('manual');
  const [deployToDev, setDeployToDev] = useState(!isEdit);
  const [formData, setFormData] = useState<APICreate>({
    name: api?.name || '',
    display_name: api?.display_name || '',
    version: api?.version || '1.0.0',
    description: api?.description || '',
    backend_url: api?.backend_url || '',
    openapi_spec: '',
    tags: api?.tags || [],
    portal_promoted: api?.portal_promoted || api?.tags?.includes('portal:published') || false,
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
      let spec: any;

      // Try to parse as JSON first, then YAML
      try {
        spec = JSON.parse(content);
      } catch {
        spec = yaml.load(content);
      }

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
      });
    } catch (err: any) {
      setParseError(err.message || 'Failed to parse OpenAPI specification');
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    // Build tags array based on portal_promoted flag
    const tags = [...(formData.tags || [])].filter((tag) => tag !== 'portal:published');
    if (formData.portal_promoted) {
      tags.push('portal:published');
    }

    const submitData: APICreate = {
      ...formData,
      tags,
    };

    onSubmit(submitData, deployToDev);
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        <div className="flex justify-between items-center px-6 py-4 border-b dark:border-neutral-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-neutral-300"
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
            <div className="flex rounded-lg bg-gray-100 dark:bg-neutral-700 p-1">
              <button
                type="button"
                onClick={() => setMode('manual')}
                className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
                  mode === 'manual'
                    ? 'bg-white dark:bg-neutral-600 text-gray-900 dark:text-white shadow'
                    : 'text-gray-500 dark:text-neutral-400 hover:text-gray-700 dark:hover:text-neutral-300'
                }`}
              >
                Manual Entry
              </button>
              <button
                type="button"
                onClick={() => setMode('openapi')}
                className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
                  mode === 'openapi'
                    ? 'bg-white dark:bg-neutral-600 text-gray-900 dark:text-white shadow'
                    : 'text-gray-500 dark:text-neutral-400 hover:text-gray-700 dark:hover:text-neutral-300'
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
                <label className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-2">
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
                    className="flex items-center gap-2 px-4 py-2 border-2 border-dashed border-gray-300 dark:border-neutral-600 rounded-lg hover:border-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors dark:text-neutral-300"
                  >
                    <svg
                      className="w-5 h-5 text-gray-400"
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
                <label className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-2">
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
                  className="w-full border border-gray-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
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
                  <label className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1">
                    Name (slug)
                  </label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        name: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-'),
                      })
                    }
                    className="w-full border border-gray-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    placeholder="payment-api"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1">
                    Version
                  </label>
                  <input
                    type="text"
                    value={formData.version}
                    onChange={(e) => setFormData({ ...formData, version: e.target.value })}
                    className="w-full border border-gray-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    placeholder="1.0.0"
                    required
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Display Name</label>
                <input
                  type="text"
                  value={formData.display_name}
                  onChange={(e) => setFormData({ ...formData, display_name: e.target.value })}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  placeholder="Payment API"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                <textarea
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
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
              <label className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1">
                Backend URL
              </label>
              <input
                type="url"
                value={formData.backend_url}
                onChange={(e) => setFormData({ ...formData, backend_url: e.target.value })}
                className="w-full border border-gray-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="https://backend.internal/api/v1"
                required
              />
              <p className="text-xs text-gray-500 dark:text-neutral-400 mt-1">
                The backend service URL that the Gateway will proxy requests to
              </p>
            </div>
          </Collapsible>

          {/* OpenAPI Spec for manual mode */}
          {mode === 'manual' && (
            <Collapsible
              title="OpenAPI Specification"
              icon={<Code2 className="h-4 w-4" />}
              badge="Optional"
              defaultExpanded={false}
              variant="bordered"
            >
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1">
                  OpenAPI Spec
                </label>
                <textarea
                  value={formData.openapi_spec}
                  onChange={(e) => setFormData({ ...formData, openapi_spec: e.target.value })}
                  className="w-full border border-gray-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
                  rows={6}
                  placeholder="Paste OpenAPI/Swagger spec here (YAML or JSON)..."
                />
                <p className="text-xs text-gray-500 dark:text-neutral-400 mt-1">
                  Adding an OpenAPI spec enables API documentation and validation
                </p>
              </div>
            </Collapsible>
          )}

          {/* Portal & Deployment Settings */}
          <Collapsible
            title="Portal & Deployment"
            icon={<Settings className="h-4 w-4" />}
            defaultExpanded={!isEdit}
            variant="bordered"
          >
            <div className="space-y-4">
              {/* Portal Promotion Toggle */}
              <div className="flex items-start gap-3">
                <div className="flex items-center h-5">
                  <input
                    type="checkbox"
                    id="portalPromoted"
                    checked={formData.portal_promoted}
                    onChange={(e) =>
                      setFormData({ ...formData, portal_promoted: e.target.checked })
                    }
                    className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                  />
                </div>
                <div className="flex-1">
                  <label
                    htmlFor="portalPromoted"
                    className="text-sm font-medium text-gray-700 dark:text-neutral-300"
                  >
                    Promote to Developer Portal
                  </label>
                  <p className="text-xs text-gray-500 dark:text-neutral-400 mt-1">
                    When enabled, this API will be visible in the Developer Portal for consumers to
                    discover and subscribe.
                  </p>
                </div>
              </div>

              {/* Deploy to DEV checkbox */}
              {!isEdit && (
                <div className="flex items-start gap-3 pt-3 border-t dark:border-neutral-700">
                  <div className="flex items-center h-5">
                    <input
                      type="checkbox"
                      id="deployToDev"
                      checked={deployToDev}
                      onChange={(e) => setDeployToDev(e.target.checked)}
                      className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                    />
                  </div>
                  <div className="flex-1">
                    <label
                      htmlFor="deployToDev"
                      className="text-sm font-medium text-gray-700 dark:text-neutral-300"
                    >
                      Deploy to DEV environment
                    </label>
                    <p className="text-xs text-gray-500 dark:text-neutral-400 mt-1">
                      Automatically deploy this API to the DEV environment after creation.
                    </p>
                  </div>
                </div>
              )}
            </div>
          </Collapsible>

          <div className="flex justify-end gap-3 pt-4 border-t dark:border-neutral-700 mt-6">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 border border-gray-300 dark:border-neutral-600 rounded-lg text-gray-700 dark:text-neutral-300 hover:bg-gray-50 dark:hover:bg-neutral-700"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center gap-2"
            >
              {!isEdit && deployToDev && (
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M13 10V3L4 14h7v7l9-11h-7z"
                  />
                </svg>
              )}
              {isEdit ? 'Update API' : deployToDev ? 'Create & Deploy' : 'Create API'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
