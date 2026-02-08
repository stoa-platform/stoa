import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { apiService } from '../../services/api';
import { GatewayRegistrationForm } from './GatewayRegistrationForm';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import { EmptyState } from '@stoa/shared/components/EmptyState';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import type { GatewayInstance, GatewayType, GatewayInstanceStatus, GatewayMode } from '../../types';

const statusColors: Record<GatewayInstanceStatus, string> = {
  online: 'bg-green-100 text-green-800',
  offline: 'bg-gray-100 text-gray-800',
  degraded: 'bg-yellow-100 text-yellow-800',
  maintenance: 'bg-blue-100 text-blue-800',
};

const modeColors: Record<GatewayMode, string> = {
  'edge-mcp': 'bg-blue-100 text-blue-800 border-blue-200',
  sidecar: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  proxy: 'bg-purple-100 text-purple-800 border-purple-200',
  shadow: 'bg-orange-100 text-orange-800 border-orange-200',
};

const modeLabels: Record<GatewayMode, string> = {
  'edge-mcp': 'Edge MCP',
  sidecar: 'Sidecar',
  proxy: 'Proxy',
  shadow: 'Shadow',
};

const typeLabels: Record<GatewayType, string> = {
  webmethods: 'webMethods',
  kong: 'Kong',
  apigee: 'Apigee',
  aws_apigateway: 'AWS API Gateway',
  stoa: 'STOA',
  stoa_edge_mcp: 'STOA Edge MCP',
  stoa_sidecar: 'STOA Sidecar',
  stoa_proxy: 'STOA Proxy',
  stoa_shadow: 'STOA Shadow',
};

export function GatewayList() {
  const { isReady } = useAuth();
  const toast = useToastActions();
  const [confirm, ConfirmDialog] = useConfirm();
  const [gateways, setGateways] = useState<GatewayInstance[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [healthChecking, setHealthChecking] = useState<string | null>(null);
  const [modeFilter, setModeFilter] = useState<GatewayMode | ''>('');

  // Filter gateways by mode
  const filteredGateways = modeFilter ? gateways.filter((gw) => gw.mode === modeFilter) : gateways;

  // Count STOA gateways by mode for the filter dropdown
  const modeCounts = gateways.reduce(
    (acc, gw) => {
      if (gw.mode) {
        acc[gw.mode] = (acc[gw.mode] || 0) + 1;
      }
      return acc;
    },
    {} as Record<string, number>
  );

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

  const handleDelete = useCallback(
    async (id: string, name: string) => {
      const confirmed = await confirm({
        title: 'Delete Gateway',
        message: `Are you sure you want to delete "${name}"? This cannot be undone.`,
        confirmLabel: 'Delete',
        variant: 'danger',
      });
      if (!confirmed) return;

      try {
        await apiService.deleteGatewayInstance(id);
        toast.success(`Gateway "${name}" deleted successfully`);
        await loadGateways();
      } catch (err: any) {
        toast.error(err.response?.data?.detail || 'Failed to delete gateway');
      }
    },
    [confirm, toast, loadGateways]
  );

  const handleCreated = () => {
    setShowForm(false);
    loadGateways();
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div className="h-8 w-48 bg-gray-200 rounded animate-pulse" />
          <div className="h-10 w-40 bg-gray-200 rounded animate-pulse" />
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
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Gateway Registry</h1>
          <p className="text-gray-500 mt-1">
            Manage registered gateway instances across all environments
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Mode Filter */}
          {Object.keys(modeCounts).length > 0 && (
            <select
              value={modeFilter}
              onChange={(e) => setModeFilter(e.target.value as GatewayMode | '')}
              className="text-sm border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="">All Modes ({gateways.length})</option>
              {(['edge-mcp', 'sidecar', 'proxy', 'shadow'] as GatewayMode[]).map((mode) =>
                modeCounts[mode] ? (
                  <option key={mode} value={mode}>
                    {modeLabels[mode]} ({modeCounts[mode]})
                  </option>
                ) : null
              )}
            </select>
          )}
          <button
            onClick={() => setShowForm(!showForm)}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
          >
            {showForm ? 'Cancel' : '+ Register Gateway'}
          </button>
        </div>
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
        <GatewayRegistrationForm onCreated={handleCreated} onCancel={() => setShowForm(false)} />
      )}

      {/* Gateway Cards */}
      {filteredGateways.length === 0 ? (
        <div className="bg-white rounded-lg shadow">
          <EmptyState
            variant="servers"
            title={modeFilter ? `No ${modeLabels[modeFilter]} gateways` : 'No gateways registered'}
            description={
              modeFilter
                ? 'Try clearing the filter or register a new gateway.'
                : 'Register your first gateway instance to start multi-gateway orchestration.'
            }
            action={{ label: 'Register Gateway', onClick: () => setShowForm(true) }}
          />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredGateways.map((gw) => (
            <div
              key={gw.id}
              className="bg-white rounded-lg shadow hover:shadow-md transition-shadow"
            >
              <div className="p-6">
                {/* Header row */}
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span
                      className={`px-2 py-1 text-xs font-medium rounded-full ${statusColors[gw.status]}`}
                    >
                      {gw.status}
                    </span>
                    {gw.mode && (
                      <span
                        className={`px-2 py-1 text-xs font-medium rounded-full border ${modeColors[gw.mode]}`}
                      >
                        {modeLabels[gw.mode]}
                      </span>
                    )}
                  </div>
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
                    <span
                      className="font-mono text-xs text-gray-700 truncate ml-2 max-w-[180px]"
                      title={gw.base_url}
                    >
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
                        <span
                          key={cap}
                          className="px-1.5 py-0.5 bg-gray-100 text-gray-600 text-xs rounded"
                        >
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

      {ConfirmDialog}
    </div>
  );
}
