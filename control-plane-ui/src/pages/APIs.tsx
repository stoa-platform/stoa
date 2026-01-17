import { useState, useEffect, useRef } from 'react';
import { apiService } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import type { API, APICreate, Tenant } from '../types';
import yaml from 'js-yaml';

export function APIs() {
  const { isReady } = useAuth();
  const [apis, setApis] = useState<API[]>([]);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [selectedTenant, setSelectedTenant] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingApi, setEditingApi] = useState<API | null>(null);

  useEffect(() => {
    if (isReady) {
      loadTenants();
    }
  }, [isReady]);

  useEffect(() => {
    if (selectedTenant) {
      loadApis(selectedTenant);
    }
  }, [selectedTenant]);

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

  async function loadApis(tenantId: string) {
    try {
      setLoading(true);
      const data = await apiService.getApis(tenantId);
      setApis(data);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to load APIs');
      setApis([]);
    } finally {
      setLoading(false);
    }
  }

  async function handleCreate(api: APICreate, deployToDev: boolean) {
    try {
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
      loadApis(selectedTenant);
    } catch (err: any) {
      setError(err.message || 'Failed to create API');
    }
  }

  async function handleUpdate(apiId: string, api: Partial<APICreate>) {
    try {
      await apiService.updateApi(selectedTenant, apiId, api);
      setEditingApi(null);
      loadApis(selectedTenant);
    } catch (err: any) {
      setError(err.message || 'Failed to update API');
    }
  }

  async function handleDelete(apiId: string) {
    if (!confirm('Are you sure you want to delete this API?')) return;
    try {
      await apiService.deleteApi(selectedTenant, apiId);
      loadApis(selectedTenant);
    } catch (err: any) {
      setError(err.message || 'Failed to delete API');
    }
  }

  async function handleDeploy(api: API, environment: 'dev' | 'staging') {
    try {
      await apiService.createDeployment(selectedTenant, {
        api_id: api.id,
        environment,
        version: api.version,
      });
      alert(`Deployment to ${environment.toUpperCase()} started!`);
      loadApis(selectedTenant);
    } catch (err: any) {
      setError(err.message || 'Failed to deploy API');
    }
  }

  const statusColors: Record<string, string> = {
    draft: 'bg-gray-100 text-gray-800',
    published: 'bg-green-100 text-green-800',
    deprecated: 'bg-yellow-100 text-yellow-800',
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
          <h1 className="text-2xl font-bold text-gray-900">APIs</h1>
          <p className="text-gray-500 mt-1">Manage API definitions and deployments</p>
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

      {/* Tenant Selector */}
      <div className="bg-white rounded-lg shadow p-4">
        <label className="block text-sm font-medium text-gray-700 mb-2">Select Tenant</label>
        <select
          value={selectedTenant}
          onChange={(e) => setSelectedTenant(e.target.value)}
          className="w-full md:w-64 border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        >
          {tenants.map((tenant) => (
            <option key={tenant.id} value={tenant.id}>
              {tenant.display_name || tenant.name}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error}
          <button onClick={() => setError(null)} className="float-right font-bold">&times;</button>
        </div>
      )}

      {/* APIs List */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-32">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
          </div>
        ) : apis.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <p className="mt-2">No APIs found for this tenant</p>
            <button
              onClick={() => setShowCreateModal(true)}
              className="mt-4 text-blue-600 hover:text-blue-700"
            >
              Create your first API
            </button>
          </div>
        ) : (
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Version</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Portal</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Deployed</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {apis.map((api) => (
                <tr key={api.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div>
                      <div className="text-sm font-medium text-gray-900">{api.display_name || api.name}</div>
                      <div className="text-sm text-gray-500">{api.backend_url}</div>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    v{api.version}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`px-2 py-1 text-xs font-medium rounded-full ${statusColors[api.status]}`}>
                      {api.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    {api.portal_promoted || api.tags?.includes('portal:published') ? (
                      <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-purple-100 text-purple-700">
                        <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                        </svg>
                        Published
                      </span>
                    ) : (
                      <span className="text-gray-400 text-xs">Not promoted</span>
                    )}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    <div className="flex gap-2">
                      <span className={`px-2 py-1 rounded text-xs ${api.deployed_dev ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                        DEV
                      </span>
                      <span className={`px-2 py-1 rounded text-xs ${api.deployed_staging ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-500'}`}>
                        STG
                      </span>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleDeploy(api, 'dev')}
                        className="text-green-600 hover:text-green-800"
                        title="Deploy to DEV"
                      >
                        Deploy DEV
                      </button>
                      <button
                        onClick={() => handleDeploy(api, 'staging')}
                        className="text-blue-600 hover:text-blue-800"
                        title="Deploy to Staging"
                      >
                        Deploy STG
                      </button>
                      <button
                        onClick={() => setEditingApi(api)}
                        className="text-gray-600 hover:text-gray-800"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleDelete(api.id)}
                        className="text-red-600 hover:text-red-800"
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
      const apiName = info.title?.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '') || 'new-api';
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
    const tags = [...(formData.tags || [])].filter(tag => tag !== 'portal:published');
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
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        <div className="flex justify-between items-center px-6 py-4 border-b">
          <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Mode Selector (only for create) */}
        {!isEdit && (
          <div className="px-6 pt-4">
            <div className="flex rounded-lg bg-gray-100 p-1">
              <button
                type="button"
                onClick={() => setMode('manual')}
                className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
                  mode === 'manual'
                    ? 'bg-white text-gray-900 shadow'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                Manual Entry
              </button>
              <button
                type="button"
                onClick={() => setMode('openapi')}
                className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
                  mode === 'openapi'
                    ? 'bg-white text-gray-900 shadow'
                    : 'text-gray-500 hover:text-gray-700'
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
            <div className="space-y-4 pb-4 border-b">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
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
                    className="flex items-center gap-2 px-4 py-2 border-2 border-dashed border-gray-300 rounded-lg hover:border-blue-400 hover:bg-blue-50 transition-colors"
                  >
                    <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                    </svg>
                    Choose File (.json, .yaml, .yml)
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
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
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
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
                <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
                  {parseError}
                </div>
              )}

              {formData.name && !parseError && formData.openapi_spec && (
                <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg text-sm">
                  <strong>Parsed successfully!</strong> Found API: {formData.display_name} v{formData.version}
                </div>
              )}
            </div>
          )}

          {/* Form Fields */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Name (slug)</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-') })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="payment-api"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Version</label>
              <input
                type="text"
                value={formData.version}
                onChange={(e) => setFormData({ ...formData, version: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
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

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Backend URL</label>
            <input
              type="url"
              value={formData.backend_url}
              onChange={(e) => setFormData({ ...formData, backend_url: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              placeholder="https://backend.internal/api/v1"
              required
            />
            <p className="text-xs text-gray-500 mt-1">The backend service URL that the Gateway will proxy requests to</p>
          </div>

          {/* OpenAPI Spec for manual mode */}
          {mode === 'manual' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">OpenAPI Spec (optional)</label>
              <textarea
                value={formData.openapi_spec}
                onChange={(e) => setFormData({ ...formData, openapi_spec: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
                rows={4}
                placeholder="Paste OpenAPI/Swagger spec here (YAML or JSON)..."
              />
            </div>
          )}

          {/* Portal Promotion Toggle */}
          <div className="pt-4 border-t">
            <div className="flex items-start gap-3">
              <div className="flex items-center h-5">
                <input
                  type="checkbox"
                  id="portalPromoted"
                  checked={formData.portal_promoted}
                  onChange={(e) => setFormData({ ...formData, portal_promoted: e.target.checked })}
                  className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                />
              </div>
              <div className="flex-1">
                <label htmlFor="portalPromoted" className="text-sm font-medium text-gray-700">
                  Promote to Developer Portal
                </label>
                <p className="text-xs text-gray-500 mt-1">
                  When enabled, this API will be visible in the Developer Portal for consumers to discover and subscribe.
                  This adds the <code className="bg-gray-100 px-1 rounded">portal:published</code> tag.
                </p>
              </div>
            </div>
          </div>

          {/* Deploy to DEV checkbox */}
          {!isEdit && (
            <div className="flex items-center gap-2 pt-2">
              <input
                type="checkbox"
                id="deployToDev"
                checked={deployToDev}
                onChange={(e) => setDeployToDev(e.target.checked)}
                className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
              />
              <label htmlFor="deployToDev" className="text-sm text-gray-700">
                Deploy to DEV environment after creation
              </label>
            </div>
          )}

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
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center gap-2"
            >
              {!isEdit && deployToDev && (
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              )}
              {isEdit ? 'Update API' : (deployToDev ? 'Create & Deploy' : 'Create API')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
