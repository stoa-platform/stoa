import { useState, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../contexts/AuthContext';
import { apiService } from '../../services/api';
import { GatewayRegistrationForm } from './GatewayRegistrationForm';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import { EmptyState } from '@stoa/shared/components/EmptyState';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import type {
  GatewayInstance,
  GatewayType,
  GatewayInstanceStatus,
  GatewayMode,
} from '../../types';

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

/** Returns true if the gateway heartbeat is recent (< 90s). */
function isLive(gw: GatewayInstance): boolean {
  if (!gw.last_health_check) return false;
  const elapsed = Date.now() - new Date(gw.last_health_check).getTime();
  return elapsed < 90_000;
}

/** Format seconds into a human-readable uptime string. */
function formatUptime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

export function GatewayList() {
  const { isReady } = useAuth();
  const queryClient = useQueryClient();
  const toast = useToastActions();
  const [confirm, ConfirmDialog] = useConfirm();
  const [showForm, setShowForm] = useState(false);
  const [healthChecking, setHealthChecking] = useState<string | null>(null);
  const [modeFilter, setModeFilter] = useState<GatewayMode | ''>('');
  const [selectedGateway, setSelectedGateway] = useState<GatewayInstance | null>(null);

  // Auto-refresh gateway list every 30s via useQuery
  const {
    data: gatewaysData,
    isLoading,
    error: queryError,
  } = useQuery({
    queryKey: ['gateways'],
    queryFn: () => apiService.getGatewayInstances(),
    enabled: isReady,
    refetchInterval: 30_000,
    staleTime: 10_000,
  });

  const gateways = gatewaysData?.items ?? [];
  const error = queryError
    ? (queryError as any).response?.data?.detail ||
      (queryError as Error).message ||
      'Failed to load gateways'
    : null;

  // Filter gateways by mode
  const filteredGateways = modeFilter
    ? gateways.filter((gw) => gw.mode === modeFilter)
    : gateways;

  // Count STOA gateways by mode for the filter dropdown
  const modeCounts = gateways.reduce(
    (acc, gw) => {
      if (gw.mode) {
        acc[gw.mode] = (acc[gw.mode] || 0) + 1;
      }
      return acc;
    },
    {} as Record<string, number>,
  );

  const refetchGateways = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['gateways'] });
  }, [queryClient]);

  const handleHealthCheck = async (id: string) => {
    setHealthChecking(id);
    try {
      await apiService.checkGatewayHealth(id);
      refetchGateways();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Health check failed');
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
        if (selectedGateway?.id === id) setSelectedGateway(null);
        refetchGateways();
      } catch (err: any) {
        toast.error(err.response?.data?.detail || 'Failed to delete gateway');
      }
    },
    [confirm, toast, refetchGateways, selectedGateway],
  );

  const handleCreated = () => {
    setShowForm(false);
    refetchGateways();
  };

  if (isLoading) {
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
                ) : null,
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
          <button onClick={() => void 0} className="text-red-500 hover:text-red-700">
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
              className="bg-white rounded-lg shadow hover:shadow-md transition-shadow cursor-pointer"
              onClick={() => setSelectedGateway(gw)}
            >
              <div className="p-6">
                {/* Header row */}
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    {/* Live indicator */}
                    <span
                      className={`inline-block w-2.5 h-2.5 rounded-full ${
                        isLive(gw)
                          ? 'bg-green-500 animate-pulse'
                          : gw.status === 'degraded'
                            ? 'bg-yellow-500'
                            : 'bg-gray-400'
                      }`}
                      title={isLive(gw) ? 'Live (heartbeat active)' : 'No recent heartbeat'}
                    />
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
                  onClick={(e) => {
                    e.stopPropagation();
                    handleHealthCheck(gw.id);
                  }}
                  disabled={healthChecking === gw.id}
                  className="text-sm text-blue-600 hover:text-blue-800 disabled:opacity-50"
                >
                  {healthChecking === gw.id ? 'Checking...' : 'Health Check'}
                </button>
                <span className="text-gray-300">|</span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(gw.id, gw.name);
                  }}
                  className="text-sm text-red-600 hover:text-red-800"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Gateway Detail Panel */}
      {selectedGateway && (
        <GatewayDetailPanel
          gateway={selectedGateway}
          onClose={() => setSelectedGateway(null)}
        />
      )}

      {ConfirmDialog}
    </div>
  );
}

// --- Gateway Detail Panel (slide-over) ---

function GatewayDetailPanel({
  gateway: gw,
  onClose,
}: {
  gateway: GatewayInstance;
  onClose: () => void;
}) {
  const hd = (gw.health_details ?? {}) as Record<string, unknown>;
  const errorRate = typeof hd.error_rate === 'number' ? hd.error_rate : null;
  const isDegraded = errorRate !== null && errorRate > 0.05;

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      onClick={onClose}
      data-testid="gateway-detail-overlay"
    >
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/30" />

      {/* Panel */}
      <div
        className="relative w-full max-w-md bg-white shadow-xl overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
        data-testid="gateway-detail-panel"
      >
        {/* Header */}
        <div className="sticky top-0 bg-white border-b px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span
              className={`inline-block w-3 h-3 rounded-full ${
                isLive(gw) ? 'bg-green-500 animate-pulse' : 'bg-gray-400'
              }`}
            />
            <h2 className="text-lg font-semibold text-gray-900 truncate">{gw.display_name}</h2>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl leading-none"
            aria-label="Close detail panel"
          >
            &times;
          </button>
        </div>

        <div className="px-6 py-5 space-y-6">
          {/* Status badges */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`px-2 py-1 text-xs font-medium rounded-full ${statusColors[gw.status]}`}>
              {gw.status}
            </span>
            {isDegraded && (
              <span className="px-2 py-1 text-xs font-medium rounded-full bg-orange-100 text-orange-800">
                degraded (error rate &gt; 5%)
              </span>
            )}
            {gw.mode && (
              <span className={`px-2 py-1 text-xs font-medium rounded-full border ${modeColors[gw.mode]}`}>
                {modeLabels[gw.mode]}
              </span>
            )}
          </div>

          {/* Heartbeat metrics */}
          <section>
            <h3 className="text-sm font-semibold text-gray-700 mb-3">Heartbeat Metrics</h3>
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <MetricItem
                label="Uptime"
                value={
                  typeof hd.uptime_seconds === 'number'
                    ? formatUptime(hd.uptime_seconds)
                    : '--'
                }
              />
              <MetricItem
                label="Routes"
                value={hd.routes_count != null ? String(hd.routes_count) : '--'}
              />
              <MetricItem
                label="Policies"
                value={hd.policies_count != null ? String(hd.policies_count) : '--'}
              />
              <MetricItem
                label="Requests"
                value={hd.requests_total != null ? String(hd.requests_total) : '--'}
              />
              <MetricItem
                label="Error Rate"
                value={errorRate !== null ? `${(errorRate * 100).toFixed(1)}%` : '--'}
                warn={isDegraded}
              />
              <MetricItem
                label="Last Heartbeat"
                value={
                  typeof hd.last_heartbeat === 'string'
                    ? new Date(hd.last_heartbeat).toLocaleTimeString()
                    : gw.last_health_check
                      ? new Date(gw.last_health_check).toLocaleTimeString()
                      : '--'
                }
              />
            </dl>
          </section>

          {/* Instance info */}
          <section>
            <h3 className="text-sm font-semibold text-gray-700 mb-3">Instance Info</h3>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-gray-500">Name</dt>
                <dd className="font-mono text-gray-900 text-xs truncate max-w-[220px]">{gw.name}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Type</dt>
                <dd className="text-gray-900">{typeLabels[gw.gateway_type] || gw.gateway_type}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Environment</dt>
                <dd className="text-gray-900">{gw.environment}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Base URL</dt>
                <dd className="font-mono text-xs text-gray-700 truncate max-w-[220px]">{gw.base_url}</dd>
              </div>
              {gw.version && (
                <div className="flex justify-between">
                  <dt className="text-gray-500">Version</dt>
                  <dd className="font-mono text-gray-900">{gw.version}</dd>
                </div>
              )}
              {typeof hd.registered_at === 'string' && (
                <div className="flex justify-between">
                  <dt className="text-gray-500">Registered</dt>
                  <dd className="text-gray-900">{new Date(hd.registered_at).toLocaleString()}</dd>
                </div>
              )}
              <div className="flex justify-between">
                <dt className="text-gray-500">Created</dt>
                <dd className="text-gray-900">{new Date(gw.created_at).toLocaleString()}</dd>
              </div>
            </dl>
          </section>

          {/* Capabilities */}
          {gw.capabilities.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold text-gray-700 mb-2">Capabilities</h3>
              <div className="flex flex-wrap gap-1">
                {gw.capabilities.map((cap) => (
                  <span key={cap} className="px-2 py-1 bg-gray-100 text-gray-600 text-xs rounded">
                    {cap}
                  </span>
                ))}
              </div>
            </section>
          )}

          {/* Tags */}
          {gw.tags.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold text-gray-700 mb-2">Tags</h3>
              <div className="flex flex-wrap gap-1">
                {gw.tags.map((tag) => (
                  <span key={tag} className="px-2 py-1 bg-blue-50 text-blue-700 text-xs rounded">
                    {tag}
                  </span>
                ))}
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

function MetricItem({
  label,
  value,
  warn,
}: {
  label: string;
  value: string;
  warn?: boolean;
}) {
  return (
    <div className="bg-gray-50 rounded-lg p-3">
      <dt className="text-xs text-gray-500">{label}</dt>
      <dd className={`text-lg font-semibold ${warn ? 'text-orange-600' : 'text-gray-900'}`}>
        {value}
      </dd>
    </div>
  );
}
