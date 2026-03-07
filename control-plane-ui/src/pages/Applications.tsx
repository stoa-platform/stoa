import { useState, useEffect, useMemo, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { apiService } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { Plus } from 'lucide-react';
import { useDebounce } from '../hooks/useDebounce';
import { Button } from '@stoa/shared/components/Button';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import { EmptyState } from '@stoa/shared/components/EmptyState';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import type { Application, ApplicationCreate, API, SecurityProfile } from '../types';
import {
  ENV_ORDER,
  ENV_LABELS,
  ENV_COLORS,
  normalizeEnvironment,
  type CanonicalEnvironment,
} from '@stoa/shared/constants/environments';

const PAGE_SIZE = 12;

type EnvFilter = CanonicalEnvironment | 'all';

const TAB_COLORS: Record<
  CanonicalEnvironment,
  { dot: string; bg: string; text: string; border: string }
> = {
  production: {
    dot: ENV_COLORS.production.dot,
    bg: `${ENV_COLORS.production.bg} ${ENV_COLORS.production.bgDark}`,
    text: `${ENV_COLORS.production.text} ${ENV_COLORS.production.textDark}`,
    border: `${ENV_COLORS.production.border} ${ENV_COLORS.production.borderDark}`,
  },
  staging: {
    dot: ENV_COLORS.staging.dot,
    bg: `${ENV_COLORS.staging.bg} ${ENV_COLORS.staging.bgDark}`,
    text: `${ENV_COLORS.staging.text} ${ENV_COLORS.staging.textDark}`,
    border: `${ENV_COLORS.staging.border} ${ENV_COLORS.staging.borderDark}`,
  },
  development: {
    dot: ENV_COLORS.development.dot,
    bg: `${ENV_COLORS.development.bg} ${ENV_COLORS.development.bgDark}`,
    text: `${ENV_COLORS.development.text} ${ENV_COLORS.development.textDark}`,
    border: `${ENV_COLORS.development.border} ${ENV_COLORS.development.borderDark}`,
  },
};

export function Applications() {
  const { isReady } = useAuth();
  const toast = useToastActions();
  const [confirm, ConfirmDialog] = useConfirm();
  const [searchParams, setSearchParams] = useSearchParams();
  const [applications, setApplications] = useState<Application[]>([]);
  const [apis, setApis] = useState<API[]>([]);
  const [selectedTenant, setSelectedTenant] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingApp, setEditingApp] = useState<Application | null>(null);

  // Environment tab filter (like Gateways page)
  const [activeEnv, setActiveEnv] = useState<EnvFilter>(() => {
    const param = searchParams.get('env');
    if (param && (param === 'all' || ENV_ORDER.includes(param as CanonicalEnvironment))) {
      return param as EnvFilter;
    }
    return 'all';
  });

  // Search and pagination state
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string>('');

  // Debounce search for performance (300ms delay)
  const debouncedSearch = useDebounce(searchQuery, 300);

  // Sync env tab to URL
  useEffect(() => {
    const params = new URLSearchParams(searchParams);
    if (activeEnv === 'all') {
      params.delete('env');
    } else {
      params.set('env', activeEnv);
    }
    setSearchParams(params, { replace: true });
  }, [activeEnv, searchParams, setSearchParams]);

  // Fetch tenants via React Query (benefits from prefetch in AuthContext)
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

  // Load apps when tenant changes — NO environment dependency
  useEffect(() => {
    if (selectedTenant) {
      loadTenantData(selectedTenant);
    }
  }, [selectedTenant]);

  // Reset pagination when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [debouncedSearch, statusFilter, selectedTenant, activeEnv]);

  // Load all applications and APIs (no environment filtering)
  async function loadTenantData(tenantId: string) {
    try {
      setLoading(true);
      setError(null);

      const [appsData, apisData] = await Promise.all([
        apiService.getApplications(tenantId).catch((err) => {
          console.error('Failed to load applications:', err);
          return [] as Application[];
        }),
        apiService.getApis(tenantId).catch((err) => {
          console.error('Failed to load APIs:', err);
          return [] as API[];
        }),
      ]);

      setApplications(appsData);
      setApis(apisData);
    } catch (err: any) {
      setError(err.message || 'Failed to load data');
      setApplications([]);
      setApis([]);
    } finally {
      setLoading(false);
    }
  }

  // Normalize app environment
  const normalizeAppEnv = useCallback(
    (app: Application): CanonicalEnvironment =>
      normalizeEnvironment(app.environment || 'development'),
    []
  );

  // Stats per environment
  const envStats = useMemo(() => {
    const stats: Record<
      CanonicalEnvironment,
      { total: number; approved: number; pending: number }
    > = {
      production: { total: 0, approved: 0, pending: 0 },
      staging: { total: 0, approved: 0, pending: 0 },
      development: { total: 0, approved: 0, pending: 0 },
    };
    for (const app of applications) {
      const env = normalizeAppEnv(app);
      stats[env].total++;
      if (app.status === 'approved') stats[env].approved++;
      else if (app.status === 'pending') stats[env].pending++;
    }
    return stats;
  }, [applications, normalizeAppEnv]);

  // Client-side filtering (memoized for performance)
  const filteredApplications = useMemo(() => {
    let result = applications;

    // Apply environment tab filter
    if (activeEnv !== 'all') {
      result = result.filter((app) => normalizeAppEnv(app) === activeEnv);
    }

    // Apply search filter
    if (debouncedSearch) {
      const searchLower = debouncedSearch.toLowerCase();
      result = result.filter(
        (app) =>
          app.name.toLowerCase().includes(searchLower) ||
          (app.display_name || '').toLowerCase().includes(searchLower) ||
          (app.description || '').toLowerCase().includes(searchLower) ||
          app.client_id.toLowerCase().includes(searchLower)
      );
    }

    // Apply status filter
    if (statusFilter) {
      result = result.filter((app) => app.status === statusFilter);
    }

    return result;
  }, [applications, activeEnv, debouncedSearch, statusFilter, normalizeAppEnv]);

  // Paginated results
  const paginatedApplications = useMemo(() => {
    const startIndex = (currentPage - 1) * PAGE_SIZE;
    return filteredApplications.slice(startIndex, startIndex + PAGE_SIZE);
  }, [filteredApplications, currentPage]);

  const totalPages = Math.ceil(filteredApplications.length / PAGE_SIZE);

  async function handleCreate(app: ApplicationCreate) {
    try {
      await apiService.createApplication(selectedTenant, app);
      setShowCreateModal(false);
      loadTenantData(selectedTenant);
    } catch (err: any) {
      setError(err.message || 'Failed to create application');
    }
  }

  async function handleUpdate(appId: string, app: Partial<ApplicationCreate>) {
    try {
      await apiService.updateApplication(selectedTenant, appId, app);
      setEditingApp(null);
      loadTenantData(selectedTenant);
    } catch (err: any) {
      setError(err.message || 'Failed to update application');
    }
  }

  async function handleDelete(appId: string, appName: string) {
    const confirmed = await confirm({
      title: 'Delete Application',
      message: `Are you sure you want to delete "${appName}"? This action cannot be undone.`,
      confirmLabel: 'Delete',
      variant: 'danger',
    });
    if (!confirmed) return;

    try {
      await apiService.deleteApplication(selectedTenant, appId);
      toast.success('Application deleted', `${appName} has been removed`);
      loadTenantData(selectedTenant);
    } catch (err: any) {
      toast.error('Delete failed', err.message || 'Failed to delete application');
    }
  }

  const statusColors: Record<string, string> = {
    pending: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
    approved: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
    suspended: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
    active: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
    disabled: 'bg-neutral-100 text-neutral-600 dark:bg-neutral-700 dark:text-neutral-400',
  };

  if ((tenantsLoading || loading) && tenants.length === 0) {
    return (
      <div className="space-y-6">
        <div className="flex justify-between items-center">
          <div className="h-8 w-48 bg-neutral-200 rounded animate-pulse" />
          <div className="h-10 w-40 bg-neutral-200 rounded animate-pulse" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3].map((i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Applications</h1>
          <p className="text-neutral-500 dark:text-neutral-400 mt-1">
            Manage consumer applications and API subscriptions across all environments
          </p>
        </div>
        <Button
          onClick={() => setShowCreateModal(true)}
          disabled={!selectedTenant}
          icon={<Plus className="w-5 h-5" />}
        >
          Create Application
        </Button>
      </div>

      {/* Environment Tabs (like Gateways page) */}
      <div className="flex gap-2 flex-wrap">
        <button
          onClick={() => setActiveEnv('all')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            activeEnv === 'all'
              ? 'bg-neutral-900 text-white dark:bg-white dark:text-neutral-900'
              : 'bg-neutral-100 text-neutral-600 hover:bg-neutral-200 dark:bg-neutral-800 dark:text-neutral-300 dark:hover:bg-neutral-700'
          }`}
        >
          All Environments
          <span className="ml-2 text-xs opacity-75">({applications.length})</span>
        </button>
        {ENV_ORDER.map((env) => {
          const colors = TAB_COLORS[env];
          const stats = envStats[env];
          return (
            <button
              key={env}
              onClick={() => setActiveEnv(env)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2 ${
                activeEnv === env
                  ? `${colors.bg} ${colors.text} ${colors.border} border`
                  : 'bg-neutral-100 text-neutral-600 hover:bg-neutral-200 dark:bg-neutral-800 dark:text-neutral-300 dark:hover:bg-neutral-700'
              }`}
            >
              <span className={`w-2 h-2 rounded-full ${colors.dot}`} />
              {ENV_LABELS[env]}
              <span className="text-xs opacity-75">({stats.total})</span>
            </button>
          );
        })}
      </div>

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
                placeholder="Search by name, description, client ID..."
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
              <option value="pending">Pending</option>
              <option value="approved">Approved</option>
              <option value="active">Active</option>
              <option value="suspended">Suspended</option>
            </select>
          </div>

          {/* Results count */}
          <div className="text-sm text-neutral-500 dark:text-neutral-400 self-end pb-2">
            {filteredApplications.length} of {applications.length} applications
          </div>
        </div>
      </div>

      {(error || tenantsError) && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg">
          {error || 'Failed to load tenants'}
          <button onClick={() => setError(null)} className="float-right font-bold">
            &times;
          </button>
        </div>
      )}

      {/* Applications Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {loading ? (
          <>
            {[1, 2, 3].map((i) => (
              <CardSkeleton key={i} />
            ))}
          </>
        ) : applications.length === 0 ? (
          <div className="col-span-full bg-white dark:bg-neutral-800 rounded-lg shadow">
            <EmptyState
              variant="default"
              title="No applications found"
              description="No applications found for this tenant. Create your first application to get started."
              action={{ label: 'Create Application', onClick: () => setShowCreateModal(true) }}
            />
          </div>
        ) : filteredApplications.length === 0 ? (
          <div className="col-span-full bg-white dark:bg-neutral-800 rounded-lg shadow">
            <EmptyState
              variant="search"
              action={{
                label: 'Clear filters',
                onClick: () => {
                  setSearchQuery('');
                  setStatusFilter('');
                  setActiveEnv('all');
                },
              }}
            />
          </div>
        ) : (
          paginatedApplications.map((app) => {
            const appEnv = normalizeAppEnv(app);
            const envColor = TAB_COLORS[appEnv];
            return (
              <div
                key={app.id}
                className="bg-white dark:bg-neutral-800 rounded-lg shadow p-6 hover:shadow-md transition-shadow"
              >
                <div className="flex justify-between items-start mb-4">
                  <div className="flex-1 min-w-0">
                    <h3 className="text-lg font-semibold text-neutral-900 dark:text-white truncate">
                      {app.display_name || app.name}
                    </h3>
                    <p className="text-sm text-neutral-500 dark:text-neutral-400">{app.name}</p>
                  </div>
                  <div className="flex items-center gap-2 ml-2 flex-shrink-0">
                    {/* Environment badge */}
                    <span
                      className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full ${envColor.bg} ${envColor.text} ${envColor.border} border`}
                    >
                      <span className={`w-1.5 h-1.5 rounded-full ${envColor.dot}`} />
                      {ENV_LABELS[appEnv]}
                    </span>
                    {/* Status badge */}
                    <span
                      className={`px-2 py-1 text-xs font-medium rounded-full ${statusColors[app.status] || statusColors.active}`}
                    >
                      {app.status}
                    </span>
                  </div>
                </div>

                <p className="text-sm text-neutral-600 dark:text-neutral-300 mb-4 line-clamp-2">
                  {app.description || 'No description'}
                </p>

                <div className="text-sm text-neutral-600 dark:text-neutral-300 mb-4">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-medium">Client ID:</span>
                    <code className="bg-neutral-100 dark:bg-neutral-700 px-2 py-0.5 rounded text-xs truncate max-w-[180px]">
                      {app.client_id}
                    </code>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">Subscriptions:</span>
                    <span>{app.api_subscriptions?.length || 0} APIs</span>
                  </div>
                </div>

                {/* Subscribed APIs */}
                {app.api_subscriptions && app.api_subscriptions.length > 0 && (
                  <div className="mb-4">
                    <p className="text-xs font-medium text-neutral-500 dark:text-neutral-400 mb-2">
                      Subscribed APIs:
                    </p>
                    <div className="flex flex-wrap gap-1">
                      {app.api_subscriptions.slice(0, 3).map((apiId) => (
                        <span
                          key={apiId}
                          className="px-2 py-0.5 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 text-xs rounded"
                        >
                          {apiId}
                        </span>
                      ))}
                      {app.api_subscriptions.length > 3 && (
                        <span className="px-2 py-0.5 bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300 text-xs rounded">
                          +{app.api_subscriptions.length - 3} more
                        </span>
                      )}
                    </div>
                  </div>
                )}

                <div className="flex gap-2 pt-4 border-t dark:border-neutral-700">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setEditingApp(app)}
                    className="flex-1"
                  >
                    Edit
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => handleDelete(app.id, app.display_name || app.name)}
                    className="flex-1"
                  >
                    Delete
                  </Button>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Pagination */}
      {!loading && filteredApplications.length > 0 && totalPages > 1 && (
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow px-6 py-3 flex items-center justify-between">
          <div className="text-sm text-neutral-500 dark:text-neutral-400">
            Showing {(currentPage - 1) * PAGE_SIZE + 1} to{' '}
            {Math.min(currentPage * PAGE_SIZE, filteredApplications.length)} of{' '}
            {filteredApplications.length} results
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

      {/* Create Modal */}
      {showCreateModal && (
        <ApplicationFormModal
          apis={apis}
          onClose={() => setShowCreateModal(false)}
          onSubmit={handleCreate}
          title="Create New Application"
        />
      )}

      {/* Edit Modal */}
      {editingApp && (
        <ApplicationFormModal
          app={editingApp}
          apis={apis}
          onClose={() => setEditingApp(null)}
          onSubmit={(data) => handleUpdate(editingApp.id, data)}
          title="Edit Application"
        />
      )}

      {/* Confirm Dialog */}
      {ConfirmDialog}
    </div>
  );
}

interface ApplicationFormModalProps {
  app?: Application;
  apis: API[];
  onClose: () => void;
  onSubmit: (data: ApplicationCreate) => void;
  title: string;
}

const SECURITY_PROFILES: { value: SecurityProfile; label: string; description: string }[] = [
  {
    value: 'oauth2_public',
    label: 'OAuth2 Public',
    description: 'Public client with PKCE (SPAs, mobile)',
  },
  {
    value: 'oauth2_confidential',
    label: 'OAuth2 Confidential',
    description: 'Server-side with client_secret',
  },
  { value: 'api_key', label: 'API Key', description: 'Simple key-based authentication' },
  {
    value: 'fapi_baseline',
    label: 'FAPI Baseline',
    description: 'Financial-grade security with private_key_jwt',
  },
  {
    value: 'fapi_advanced',
    label: 'FAPI Advanced',
    description: 'FAPI Baseline + DPoP token binding',
  },
];

function ApplicationFormModal({ app, apis, onClose, onSubmit, title }: ApplicationFormModalProps) {
  const [formData, setFormData] = useState<ApplicationCreate>({
    name: app?.name || '',
    display_name: app?.display_name || '',
    description: app?.description || '',
    redirect_uris: [],
    api_subscriptions: app?.api_subscriptions || [],
    security_profile: (app?.security_profile as SecurityProfile) || 'oauth2_public',
  });
  const [redirectUri, setRedirectUri] = useState('');
  const [fapiKeyMode, setFapiKeyMode] = useState<'upload' | 'url'>('upload');

  const isFapi =
    formData.security_profile === 'fapi_baseline' || formData.security_profile === 'fapi_advanced';

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(formData);
  };

  const addRedirectUri = () => {
    if (redirectUri && !formData.redirect_uris.includes(redirectUri)) {
      setFormData({
        ...formData,
        redirect_uris: [...formData.redirect_uris, redirectUri],
      });
      setRedirectUri('');
    }
  };

  const removeRedirectUri = (uri: string) => {
    setFormData({
      ...formData,
      redirect_uris: formData.redirect_uris.filter((u) => u !== uri),
    });
  };

  const toggleApiSubscription = (apiId: string) => {
    if (formData.api_subscriptions.includes(apiId)) {
      setFormData({
        ...formData,
        api_subscriptions: formData.api_subscriptions.filter((id) => id !== apiId),
      });
    } else {
      setFormData({
        ...formData,
        api_subscriptions: [...formData.api_subscriptions, apiId],
      });
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
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
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
                className="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="my-mobile-app"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                Display Name
              </label>
              <input
                type="text"
                value={formData.display_name}
                onChange={(e) => setFormData({ ...formData, display_name: e.target.value })}
                className="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="My Mobile App"
                required
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Description
            </label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              className="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              rows={2}
              placeholder="Application description..."
            />
          </div>

          {/* Security Profile */}
          {!app && (
            <div>
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                Security Profile
              </label>
              <div className="grid grid-cols-1 gap-2">
                {SECURITY_PROFILES.map((profile) => (
                  <label
                    key={profile.value}
                    className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                      formData.security_profile === profile.value
                        ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20 dark:border-blue-400'
                        : 'border-neutral-200 dark:border-neutral-600 hover:bg-neutral-50 dark:hover:bg-neutral-700'
                    }`}
                  >
                    <input
                      type="radio"
                      name="security_profile"
                      value={profile.value}
                      checked={formData.security_profile === profile.value}
                      onChange={() =>
                        setFormData({
                          ...formData,
                          security_profile: profile.value,
                          jwks_uri: undefined,
                          jwks: undefined,
                        })
                      }
                      className="mt-1 w-4 h-4 text-blue-600"
                    />
                    <div>
                      <p className="text-sm font-medium text-neutral-900 dark:text-white">
                        {profile.label}
                      </p>
                      <p className="text-xs text-neutral-500 dark:text-neutral-400">
                        {profile.description}
                      </p>
                    </div>
                  </label>
                ))}
              </div>
            </div>
          )}

          {/* FAPI Key Management */}
          {isFapi && !app && (
            <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-lg p-4">
              <p className="text-sm font-medium text-amber-800 dark:text-amber-300 mb-3">
                FAPI requires a public key for client authentication (private_key_jwt)
              </p>
              <div className="flex gap-2 mb-3">
                <button
                  type="button"
                  onClick={() => {
                    setFapiKeyMode('upload');
                    setFormData({ ...formData, jwks_uri: undefined });
                  }}
                  className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
                    fapiKeyMode === 'upload'
                      ? 'bg-amber-600 text-white'
                      : 'bg-amber-100 text-amber-700 dark:bg-amber-800/50 dark:text-amber-300'
                  }`}
                >
                  Upload PEM / JWK
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setFapiKeyMode('url');
                    setFormData({ ...formData, jwks: undefined });
                  }}
                  className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
                    fapiKeyMode === 'url'
                      ? 'bg-amber-600 text-white'
                      : 'bg-amber-100 text-amber-700 dark:bg-amber-800/50 dark:text-amber-300'
                  }`}
                >
                  JWKS URL
                </button>
              </div>
              {fapiKeyMode === 'upload' ? (
                <div>
                  <label className="block text-xs font-medium text-amber-700 dark:text-amber-400 mb-1">
                    Paste your PEM public key or JWK JSON
                  </label>
                  <textarea
                    value={formData.jwks || ''}
                    onChange={(e) => setFormData({ ...formData, jwks: e.target.value })}
                    className="w-full border border-amber-300 dark:border-amber-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white font-mono text-xs focus:ring-2 focus:ring-amber-500"
                    rows={5}
                    placeholder={`-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhki...\n-----END PUBLIC KEY-----`}
                    required
                  />
                  <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
                    Accepts PEM public key (RSA or EC P-256), single JWK, or JWKS JSON
                  </p>
                </div>
              ) : (
                <div>
                  <label className="block text-xs font-medium text-amber-700 dark:text-amber-400 mb-1">
                    JWKS Endpoint URL
                  </label>
                  <input
                    type="url"
                    value={formData.jwks_uri || ''}
                    onChange={(e) => setFormData({ ...formData, jwks_uri: e.target.value })}
                    className="w-full border border-amber-300 dark:border-amber-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-amber-500"
                    placeholder="https://your-app.example.com/.well-known/jwks.json"
                    required
                  />
                </div>
              )}
            </div>
          )}

          {/* Redirect URIs */}
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Redirect URIs
            </label>
            <div className="flex gap-2 mb-2">
              <input
                type="url"
                value={redirectUri}
                onChange={(e) => setRedirectUri(e.target.value)}
                className="flex-1 border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="https://myapp.example.com/callback"
              />
              <Button type="button" variant="secondary" onClick={addRedirectUri}>
                Add
              </Button>
            </div>
            {formData.redirect_uris.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {formData.redirect_uris.map((uri) => (
                  <span
                    key={uri}
                    className="inline-flex items-center gap-1 px-3 py-1 bg-neutral-100 dark:bg-neutral-700 rounded-lg text-sm dark:text-neutral-300"
                  >
                    {uri}
                    <button
                      type="button"
                      onClick={() => removeRedirectUri(uri)}
                      className="text-neutral-500 hover:text-red-600"
                    >
                      &times;
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* API Subscriptions */}
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
              API Subscriptions
            </label>
            {apis.length === 0 ? (
              <p className="text-sm text-neutral-500 dark:text-neutral-400 italic">
                No APIs available for subscription
              </p>
            ) : (
              <div className="border border-neutral-200 dark:border-neutral-600 rounded-lg divide-y dark:divide-neutral-700 max-h-48 overflow-y-auto">
                {apis.map((api) => (
                  <label
                    key={api.id}
                    className="flex items-center gap-3 px-4 py-3 hover:bg-neutral-50 dark:hover:bg-neutral-700 cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={formData.api_subscriptions.includes(api.id)}
                      onChange={() => toggleApiSubscription(api.id)}
                      className="w-4 h-4 text-blue-600 border-neutral-300 rounded focus:ring-blue-500"
                    />
                    <div className="flex-1">
                      <p className="text-sm font-medium text-neutral-900 dark:text-white">
                        {api.display_name || api.name}
                      </p>
                      <p className="text-xs text-neutral-500 dark:text-neutral-400">
                        v{api.version}
                      </p>
                    </div>
                    <span
                      className={`px-2 py-0.5 text-xs rounded ${
                        api.status === 'published'
                          ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                          : 'bg-neutral-100 text-neutral-600 dark:bg-neutral-700 dark:text-neutral-300'
                      }`}
                    >
                      {api.status}
                    </span>
                  </label>
                ))}
              </div>
            )}
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t dark:border-neutral-700 mt-6">
            <Button variant="secondary" type="button" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit">{app ? 'Update' : 'Create'} Application</Button>
          </div>
        </form>
      </div>
    </div>
  );
}
