import { useState, useEffect } from 'react';
import { apiService } from '../services/api';
import type { Deployment, Tenant, API } from '../types';

export function Deployments() {
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [apis, setApis] = useState<API[]>([]);
  const [selectedTenant, setSelectedTenant] = useState<string>('');
  const [selectedApi, setSelectedApi] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadTenants();
  }, []);

  useEffect(() => {
    if (selectedTenant) {
      loadApis(selectedTenant);
      loadDeployments(selectedTenant);
    }
  }, [selectedTenant]);

  useEffect(() => {
    if (selectedTenant) {
      loadDeployments(selectedTenant, selectedApi || undefined);
    }
  }, [selectedApi]);

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
      const data = await apiService.getApis(tenantId);
      setApis(data);
    } catch (err: any) {
      console.error('Failed to load APIs:', err);
    }
  }

  async function loadDeployments(tenantId: string, apiId?: string) {
    try {
      setLoading(true);
      const data = await apiService.getDeployments(tenantId, apiId);
      setDeployments(data);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to load deployments');
      setDeployments([]);
    } finally {
      setLoading(false);
    }
  }

  async function handleRollback(deploymentId: string) {
    if (!confirm('Are you sure you want to rollback this deployment?')) return;
    try {
      await apiService.rollbackDeployment(selectedTenant, deploymentId);
      loadDeployments(selectedTenant, selectedApi || undefined);
    } catch (err: any) {
      setError(err.message || 'Failed to rollback deployment');
    }
  }

  const statusColors: Record<string, string> = {
    pending: 'bg-yellow-100 text-yellow-800',
    in_progress: 'bg-blue-100 text-blue-800',
    success: 'bg-green-100 text-green-800',
    failed: 'bg-red-100 text-red-800',
    rolled_back: 'bg-gray-100 text-gray-800',
  };

  const statusIcons: Record<string, JSX.Element> = {
    pending: (
      <svg className="w-4 h-4 animate-pulse" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clipRule="evenodd" />
      </svg>
    ),
    in_progress: (
      <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
      </svg>
    ),
    success: (
      <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
      </svg>
    ),
    failed: (
      <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
      </svg>
    ),
    rolled_back: (
      <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clipRule="evenodd" />
      </svg>
    ),
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
          <h1 className="text-2xl font-bold text-gray-900">Deployments</h1>
          <p className="text-gray-500 mt-1">View deployment history and status</p>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-lg shadow p-4">
        <div className="flex flex-wrap gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Tenant</label>
            <select
              value={selectedTenant}
              onChange={(e) => {
                setSelectedTenant(e.target.value);
                setSelectedApi('');
              }}
              className="w-48 border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              {tenants.map((tenant) => (
                <option key={tenant.id} value={tenant.id}>
                  {tenant.display_name || tenant.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">API (optional)</label>
            <select
              value={selectedApi}
              onChange={(e) => setSelectedApi(e.target.value)}
              className="w-48 border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="">All APIs</option>
              {apis.map((api) => (
                <option key={api.id} value={api.id}>
                  {api.display_name || api.name}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error}
          <button onClick={() => setError(null)} className="float-right font-bold">&times;</button>
        </div>
      )}

      {/* Deployments List */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-32">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
          </div>
        ) : deployments.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            <p className="mt-2">No deployments found</p>
            <p className="text-sm text-gray-400">Deploy an API to see it here</p>
          </div>
        ) : (
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">API</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Environment</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Version</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Started</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Deployed By</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {deployments.map((deployment) => (
                <tr key={deployment.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium text-gray-900">{deployment.api_name}</div>
                    <div className="text-xs text-gray-500 font-mono">{deployment.api_id}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`px-2 py-1 text-xs font-medium rounded ${
                      deployment.environment === 'dev' ? 'bg-green-100 text-green-700' : 'bg-blue-100 text-blue-700'
                    }`}>
                      {deployment.environment.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    v{deployment.version}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-full ${statusColors[deployment.status]}`}>
                      {statusIcons[deployment.status]}
                      {deployment.status.replace('_', ' ')}
                    </span>
                    {deployment.error_message && (
                      <p className="text-xs text-red-600 mt-1 max-w-xs truncate" title={deployment.error_message}>
                        {deployment.error_message}
                      </p>
                    )}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {new Date(deployment.started_at).toLocaleString()}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {deployment.deployed_by}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    <div className="flex gap-2">
                      {deployment.awx_job_id && (
                        <a
                          href={`https://awx.apim.cab-i.com/#/jobs/playbook/${deployment.awx_job_id}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:text-blue-800"
                        >
                          View Job
                        </a>
                      )}
                      {deployment.status === 'success' && (
                        <button
                          onClick={() => handleRollback(deployment.id)}
                          className="text-orange-600 hover:text-orange-800"
                        >
                          Rollback
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Legend */}
      <div className="bg-gray-50 rounded-lg p-4">
        <h4 className="text-sm font-medium text-gray-700 mb-2">Status Legend</h4>
        <div className="flex flex-wrap gap-4 text-sm">
          <span className="inline-flex items-center gap-1">
            <span className={`px-2 py-0.5 rounded-full ${statusColors.pending}`}>pending</span>
            <span className="text-gray-500">- Waiting to start</span>
          </span>
          <span className="inline-flex items-center gap-1">
            <span className={`px-2 py-0.5 rounded-full ${statusColors.in_progress}`}>in progress</span>
            <span className="text-gray-500">- Currently deploying</span>
          </span>
          <span className="inline-flex items-center gap-1">
            <span className={`px-2 py-0.5 rounded-full ${statusColors.success}`}>success</span>
            <span className="text-gray-500">- Deployed successfully</span>
          </span>
          <span className="inline-flex items-center gap-1">
            <span className={`px-2 py-0.5 rounded-full ${statusColors.failed}`}>failed</span>
            <span className="text-gray-500">- Deployment failed</span>
          </span>
          <span className="inline-flex items-center gap-1">
            <span className={`px-2 py-0.5 rounded-full ${statusColors.rolled_back}`}>rolled back</span>
            <span className="text-gray-500">- Reverted to previous version</span>
          </span>
        </div>
      </div>
    </div>
  );
}
