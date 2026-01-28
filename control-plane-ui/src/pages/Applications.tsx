// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
import { useState, useEffect, useMemo } from 'react';
import { apiService } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import type { Application, ApplicationCreate, Tenant, API } from '../types';

// Debounce hook for search optimization
function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(handler);
    };
  }, [value, delay]);

  return debouncedValue;
}

const PAGE_SIZE = 12;

export function Applications() {
  const { isReady } = useAuth();
  const [applications, setApplications] = useState<Application[]>([]);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [apis, setApis] = useState<API[]>([]);
  const [selectedTenant, setSelectedTenant] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingApp, setEditingApp] = useState<Application | null>(null);

  // Search and pagination state
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string>('');

  // Debounce search for performance (300ms delay)
  const debouncedSearch = useDebounce(searchQuery, 300);

  useEffect(() => {
    if (isReady) {
      loadTenants();
    }
  }, [isReady]);

  useEffect(() => {
    if (selectedTenant) {
      // Parallel loading for better performance
      loadTenantData(selectedTenant);
    }
  }, [selectedTenant]);

  // Reset pagination when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [debouncedSearch, statusFilter, selectedTenant]);

  async function loadTenants() {
    try {
      const data = await apiService.getTenants();
      setTenants(data);
      if (data.length > 0) {
        setSelectedTenant(data[0].id);
      }
      setLoading(false);
    } catch (err: any) {
      setError(err.message || 'Failed to load tenants');
      setLoading(false);
    }
  }

  // Parallel loading of applications and APIs
  async function loadTenantData(tenantId: string) {
    try {
      setLoading(true);
      setError(null);

      // Load applications and APIs in parallel for faster performance
      const [appsData, apisData] = await Promise.all([
        apiService.getApplications(tenantId).catch(err => {
          console.error('Failed to load applications:', err);
          return [] as Application[];
        }),
        apiService.getApis(tenantId).catch(err => {
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

  // Client-side filtering (memoized for performance)
  const filteredApplications = useMemo(() => {
    let result = applications;

    // Apply search filter
    if (debouncedSearch) {
      const searchLower = debouncedSearch.toLowerCase();
      result = result.filter(app =>
        app.name.toLowerCase().includes(searchLower) ||
        (app.display_name || '').toLowerCase().includes(searchLower) ||
        (app.description || '').toLowerCase().includes(searchLower) ||
        app.client_id.toLowerCase().includes(searchLower)
      );
    }

    // Apply status filter
    if (statusFilter) {
      result = result.filter(app => app.status === statusFilter);
    }

    return result;
  }, [applications, debouncedSearch, statusFilter]);

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

  async function handleDelete(appId: string) {
    if (!confirm('Are you sure you want to delete this application?')) return;
    try {
      await apiService.deleteApplication(selectedTenant, appId);
      loadTenantData(selectedTenant);
    } catch (err: any) {
      setError(err.message || 'Failed to delete application');
    }
  }

  const statusColors: Record<string, string> = {
    pending: 'bg-yellow-100 text-yellow-800',
    approved: 'bg-green-100 text-green-800',
    suspended: 'bg-red-100 text-red-800',
  };

  if (loading && tenants.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Applications</h1>
          <p className="text-gray-500 mt-1">Manage consumer applications and API subscriptions</p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          disabled={!selectedTenant}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Create Application
        </button>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-lg shadow p-4">
        <div className="flex flex-wrap gap-4 items-end">
          {/* Tenant Selector */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Tenant</label>
            <select
              value={selectedTenant}
              onChange={(e) => setSelectedTenant(e.target.value)}
              className="w-48 border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
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
            <label className="block text-sm font-medium text-gray-700 mb-2">Search</label>
            <div className="relative">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search by name, description, client ID..."
                className="w-full border border-gray-300 rounded-lg px-3 py-2 pl-10 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
              <svg className="absolute left-3 top-2.5 h-5 w-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="absolute right-3 top-2.5 text-gray-400 hover:text-gray-600"
                >
                  <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              )}
            </div>
          </div>

          {/* Status Filter */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Status</label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="w-36 border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="">All Status</option>
              <option value="pending">Pending</option>
              <option value="approved">Approved</option>
              <option value="suspended">Suspended</option>
            </select>
          </div>

          {/* Results count */}
          <div className="text-sm text-gray-500 self-end pb-2">
            {filteredApplications.length} of {applications.length} applications
          </div>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error}
          <button onClick={() => setError(null)} className="float-right font-bold">&times;</button>
        </div>
      )}

      {/* Applications Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {loading ? (
          <div className="col-span-full flex items-center justify-center h-32">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
          </div>
        ) : applications.length === 0 ? (
          <div className="col-span-full text-center py-12 text-gray-500 bg-white rounded-lg shadow">
            <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
            </svg>
            <p className="mt-2">No applications found for this tenant</p>
            <button
              onClick={() => setShowCreateModal(true)}
              className="mt-4 text-blue-600 hover:text-blue-700"
            >
              Create your first application
            </button>
          </div>
        ) : filteredApplications.length === 0 ? (
          <div className="col-span-full text-center py-12 text-gray-500 bg-white rounded-lg shadow">
            <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <p className="mt-2">No applications match your search criteria</p>
            <button
              onClick={() => { setSearchQuery(''); setStatusFilter(''); }}
              className="mt-4 text-blue-600 hover:text-blue-700"
            >
              Clear filters
            </button>
          </div>
        ) : (
          paginatedApplications.map((app) => (
            <div key={app.id} className="bg-white rounded-lg shadow p-6 hover:shadow-md transition-shadow">
              <div className="flex justify-between items-start mb-4">
                <div>
                  <h3 className="text-lg font-semibold text-gray-900">{app.display_name || app.name}</h3>
                  <p className="text-sm text-gray-500">{app.name}</p>
                </div>
                <span className={`px-2 py-1 text-xs font-medium rounded-full ${statusColors[app.status]}`}>
                  {app.status}
                </span>
              </div>

              <p className="text-sm text-gray-600 mb-4 line-clamp-2">{app.description || 'No description'}</p>

              <div className="text-sm text-gray-600 mb-4">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-medium">Client ID:</span>
                  <code className="bg-gray-100 px-2 py-0.5 rounded text-xs">{app.client_id}</code>
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-medium">Subscriptions:</span>
                  <span>{app.api_subscriptions?.length || 0} APIs</span>
                </div>
              </div>

              {/* Subscribed APIs */}
              {app.api_subscriptions && app.api_subscriptions.length > 0 && (
                <div className="mb-4">
                  <p className="text-xs font-medium text-gray-500 mb-2">Subscribed APIs:</p>
                  <div className="flex flex-wrap gap-1">
                    {app.api_subscriptions.slice(0, 3).map((apiId) => (
                      <span key={apiId} className="px-2 py-0.5 bg-blue-50 text-blue-700 text-xs rounded">
                        {apiId}
                      </span>
                    ))}
                    {app.api_subscriptions.length > 3 && (
                      <span className="px-2 py-0.5 bg-gray-100 text-gray-600 text-xs rounded">
                        +{app.api_subscriptions.length - 3} more
                      </span>
                    )}
                  </div>
                </div>
              )}

              <div className="flex gap-2 pt-4 border-t">
                <button
                  onClick={() => setEditingApp(app)}
                  className="flex-1 px-3 py-2 text-sm text-gray-600 hover:text-gray-800 hover:bg-gray-100 rounded-lg"
                >
                  Edit
                </button>
                <button
                  onClick={() => handleDelete(app.id)}
                  className="flex-1 px-3 py-2 text-sm text-red-600 hover:text-red-800 hover:bg-red-50 rounded-lg"
                >
                  Delete
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Pagination */}
      {!loading && filteredApplications.length > 0 && totalPages > 1 && (
        <div className="bg-white rounded-lg shadow px-6 py-3 flex items-center justify-between">
          <div className="text-sm text-gray-500">
            Showing {((currentPage - 1) * PAGE_SIZE) + 1} to {Math.min(currentPage * PAGE_SIZE, filteredApplications.length)} of {filteredApplications.length} results
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
              disabled={currentPage === 1}
              className="px-3 py-1 text-sm border border-gray-300 rounded-lg hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Previous
            </button>
            <span className="px-3 py-1 text-sm text-gray-700">
              Page {currentPage} of {totalPages}
            </span>
            <button
              onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
              disabled={currentPage === totalPages}
              className="px-3 py-1 text-sm border border-gray-300 rounded-lg hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Next
            </button>
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

function ApplicationFormModal({ app, apis, onClose, onSubmit, title }: ApplicationFormModalProps) {
  const [formData, setFormData] = useState<ApplicationCreate>({
    name: app?.name || '',
    display_name: app?.display_name || '',
    description: app?.description || '',
    redirect_uris: [],
    api_subscriptions: app?.api_subscriptions || [],
  });
  const [redirectUri, setRedirectUri] = useState('');

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
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        <div className="flex justify-between items-center px-6 py-4 border-b">
          <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Name (slug)</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-') })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="my-mobile-app"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Display Name</label>
              <input
                type="text"
                value={formData.display_name}
                onChange={(e) => setFormData({ ...formData, display_name: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="My Mobile App"
                required
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              rows={2}
              placeholder="Application description..."
            />
          </div>

          {/* Redirect URIs */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Redirect URIs</label>
            <div className="flex gap-2 mb-2">
              <input
                type="url"
                value={redirectUri}
                onChange={(e) => setRedirectUri(e.target.value)}
                className="flex-1 border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="https://myapp.example.com/callback"
              />
              <button
                type="button"
                onClick={addRedirectUri}
                className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
              >
                Add
              </button>
            </div>
            {formData.redirect_uris.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {formData.redirect_uris.map((uri) => (
                  <span
                    key={uri}
                    className="inline-flex items-center gap-1 px-3 py-1 bg-gray-100 rounded-lg text-sm"
                  >
                    {uri}
                    <button
                      type="button"
                      onClick={() => removeRedirectUri(uri)}
                      className="text-gray-500 hover:text-red-600"
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
            <label className="block text-sm font-medium text-gray-700 mb-2">API Subscriptions</label>
            {apis.length === 0 ? (
              <p className="text-sm text-gray-500 italic">No APIs available for subscription</p>
            ) : (
              <div className="border border-gray-200 rounded-lg divide-y max-h-48 overflow-y-auto">
                {apis.map((api) => (
                  <label
                    key={api.id}
                    className="flex items-center gap-3 px-4 py-3 hover:bg-gray-50 cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={formData.api_subscriptions.includes(api.id)}
                      onChange={() => toggleApiSubscription(api.id)}
                      className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                    />
                    <div className="flex-1">
                      <p className="text-sm font-medium text-gray-900">{api.display_name || api.name}</p>
                      <p className="text-xs text-gray-500">v{api.version}</p>
                    </div>
                    <span className={`px-2 py-0.5 text-xs rounded ${
                      api.status === 'published' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'
                    }`}>
                      {api.status}
                    </span>
                  </label>
                ))}
              </div>
            )}
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t mt-6">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              {app ? 'Update' : 'Create'} Application
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
