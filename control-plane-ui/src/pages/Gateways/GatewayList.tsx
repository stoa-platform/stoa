import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { apiService } from '../../services/api';
import { GatewayRegistrationForm } from './GatewayRegistrationForm';
import type {
  GatewayInstance,
  GatewayType,
  GatewayInstanceStatus,
} from '../../types';

const statusColors: Record<GatewayInstanceStatus, string> = {
  online: 'bg-green-100 text-green-800',
  offline: 'bg-gray-100 text-gray-800',
  degraded: 'bg-yellow-100 text-yellow-800',
  maintenance: 'bg-blue-100 text-blue-800',
};

const typeLabels: Record<GatewayType, string> = {
  webmethods: 'webMethods',
  kong: 'Kong',
  apigee: 'Apigee',
  aws_apigateway: 'AWS API Gateway',
  stoa: 'STOA',
};

export function GatewayList() {
  const { isReady } = useAuth();
  const [gateways, setGateways] = useState<GatewayInstance[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [healthChecking, setHealthChecking] = useState<string | null>(null);

  const loadGateways = useCallback(async () => {
    try {
      setLoading(true);
      const result = await apiService.getGatewayInstances();
      setGateways(result.items);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load gateways');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isReady) {
      loadGateways();
    }
  }, [isReady, loadGateways]);

  const handleHealthCheck = async (id: string) => {
    setHealthChecking(id);
    try {
      await apiService.checkGatewayHealth(id);
      await loadGateways();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Health check failed');
    } finally {
      setHealthChecking(null);
    }
  };

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`Delete gateway "${name}"? This cannot be undone.`)) return;
    try {
      await apiService.deleteGatewayInstance(id);
      await loadGateways();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to delete gateway');
    }
  };

  const handleCreated = () => {
    setShowForm(false);
    loadGateways();
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Gateway Registry</h1>
          <p className="text-gray-500 mt-1">
            Manage registered gateway instances across all environments
          </p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
        >
          {showForm ? 'Cancel' : '+ Register Gateway'}
        </button>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-red-500 hover:text-red-700">
            &times;
          </button>
        </div>
      )}

      {/* Registration Form */}
      {showForm && (
        <GatewayRegistrationForm
          onCreated={handleCreated}
          onCancel={() => setShowForm(false)}
        />
      )}

      {/* Gateway Cards */}
      {gateways.length === 0 ? (
        <div className="bg-white rounded-lg shadow p-12 text-center">
          <svg className="w-16 h-16 text-gray-300 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M5 12h14M12 5l7 7-7 7" />
          </svg>
          <h3 className="text-lg font-medium text-gray-900 mb-2">No gateways registered</h3>
          <p className="text-gray-500">
            Register your first gateway instance to start multi-gateway orchestration.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {gateways.map((gw) => (
            <div key={gw.id} className="bg-white rounded-lg shadow hover:shadow-md transition-shadow">
              <div className="p-6">
                {/* Header row */}
                <div className="flex items-center justify-between mb-3">
                  <span className={`px-2 py-1 text-xs font-medium rounded-full ${statusColors[gw.status]}`}>
                    {gw.status}
                  </span>
                  <span className="text-xs text-gray-400 font-mono">
                    {typeLabels[gw.gateway_type] || gw.gateway_type}
                  </span>
                </div>

                {/* Name */}
                <h3 className="text-lg font-semibold text-gray-900 truncate" title={gw.name}>
                  {gw.display_name}
                </h3>
                <p className="text-sm text-gray-500 font-mono truncate" title={gw.name}>
                  {gw.name}
                </p>

                {/* Details */}
                <div className="mt-4 space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Environment</span>
                    <span className="font-medium text-gray-900">{gw.environment}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Base URL</span>
                    <span className="font-mono text-xs text-gray-700 truncate ml-2 max-w-[180px]" title={gw.base_url}>
                      {gw.base_url}
                    </span>
                  </div>
                  {gw.tenant_id && (
                    <div className="flex justify-between">
                      <span className="text-gray-500">Tenant</span>
                      <span className="font-medium text-gray-900">{gw.tenant_id}</span>
                    </div>
                  )}
                  {gw.capabilities.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {gw.capabilities.map((cap) => (
                        <span key={cap} className="px-1.5 py-0.5 bg-gray-100 text-gray-600 text-xs rounded">
                          {cap}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Last health check */}
                {gw.last_health_check && (
                  <p className="text-xs text-gray-400 mt-3">
                    Last check: {new Date(gw.last_health_check).toLocaleString()}
                  </p>
                )}
              </div>

              {/* Actions */}
              <div className="border-t px-6 py-3 flex gap-2">
                <button
                  onClick={() => handleHealthCheck(gw.id)}
                  disabled={healthChecking === gw.id}
                  className="text-sm text-blue-600 hover:text-blue-800 disabled:opacity-50"
                >
                  {healthChecking === gw.id ? 'Checking...' : 'Health Check'}
                </button>
                <span className="text-gray-300">|</span>
                <button
                  onClick={() => handleDelete(gw.id, gw.name)}
                  className="text-sm text-red-600 hover:text-red-800"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
