import { useState, useCallback, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { apiService } from '../../services/api';
import { GatewayRegistrationForm } from './GatewayRegistrationForm';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import { EmptyState } from '@stoa/shared/components/EmptyState';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import { RefreshCw } from 'lucide-react';
import { Button } from '@stoa/shared/components/Button';
import type { GatewayInstance, GatewayType, GatewayInstanceStatus, GatewayMode } from '../../types';

const statusColors: Record<GatewayInstanceStatus, string> = {
  online: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  offline: 'bg-neutral-100 text-neutral-800 dark:bg-neutral-700 dark:text-neutral-300',
  degraded: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  maintenance: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
};

const modeColors: Record<GatewayMode, string> = {
  'edge-mcp':
    'bg-blue-100 text-blue-800 border-blue-200 dark:bg-blue-900/30 dark:text-blue-400 dark:border-blue-800',
  sidecar:
    'bg-emerald-100 text-emerald-800 border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-400 dark:border-emerald-800',
  proxy:
    'bg-purple-100 text-purple-800 border-purple-200 dark:bg-purple-900/30 dark:text-purple-400 dark:border-purple-800',
  shadow:
    'bg-orange-100 text-orange-800 border-orange-200 dark:bg-orange-900/30 dark:text-orange-400 dark:border-orange-800',
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
  const [searchParams] = useSearchParams();
  const [showForm, setShowForm] = useState(false);
  const [healthChecking, setHealthChecking] = useState<string | null>(null);
  const [modeFilter, setModeFilter] = useState<GatewayMode | ''>('');
  const [selectedGateway, setSelectedGateway] = useState<GatewayInstance | null>(null);

  // Read ?mode= query param
  useEffect(() => {
    const modeParam = searchParams.get('mode');
    if (modeParam && Object.keys(modeLabels).includes(modeParam)) {
      setModeFilter(modeParam as GatewayMode);
    }
  }, [searchParams]);

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

  const gateways: GatewayInstance[] = gatewaysData?.items ?? [];
  const error = queryError
    ? (queryError as any).response?.data?.detail ||
      (queryError as Error).message ||
      'Failed to load gateways'
    : null;

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
    [confirm, toast, refetchGateways, selectedGateway]
  );

  const handleCreated = () => {
    setShowForm(false);
    refetchGateways();
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div className="h-8 w-48 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
          <div className="h-10 w-40 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
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
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Gateway Registry</h1>
          <p className="text-neutral-500 dark:text-neutral-400 mt-1">
            Manage registered gateway instances across all environments
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Mode Filter */}
          {Object.keys(modeCounts).length > 0 && (
            <select
              value={modeFilter}
              onChange={(e) => setModeFilter(e.target.value as GatewayMode | '')}
              className="text-sm border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-200 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
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
          <Button
            variant={showForm ? 'secondary' : 'primary'}
            onClick={() => setShowForm(!showForm)}
          >
            {showForm ? 'Cancel' : '+ Register Gateway'}
          </Button>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 px-4 py-3 rounded-lg flex items-center justify-between">
          <span className="text-sm text-red-700 dark:text-red-400">{error}</span>
          <Button
            variant="secondary"
            size="sm"
            onClick={refetchGateways}
            className="ml-4"
            icon={<RefreshCw className="w-3.5 h-3.5" />}
          >
            Retry
          </Button>
        </div>
      )}

      {/* Registration Form */}
      {showForm && (
        <GatewayRegistrationForm onCreated={handleCreated} onCancel={() => setShowForm(false)} />
      )}

      {/* Gateway Cards */}
      {filteredGateways.length === 0 ? (
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow">
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
              className="bg-white dark:bg-neutral-800 rounded-lg shadow hover:shadow-md transition-shadow cursor-pointer"
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
                            : 'bg-neutral-400'
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
                  <span className="text-xs text-neutral-400 dark:text-neutral-500 font-mono">
                    {typeLabels[gw.gateway_type] || gw.gateway_type}
                  </span>
                </div>

                {/* Name */}
                <h3
                  className="text-lg font-semibold text-neutral-900 dark:text-white truncate"
                  title={gw.name}
                >
                  {gw.display_name}
                </h3>
                <p
                  className="text-sm text-neutral-500 dark:text-neutral-400 font-mono truncate"
                  title={gw.name}
                >
                  {gw.name}
                </p>

                {/* Details */}
                <div className="mt-4 space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-neutral-500 dark:text-neutral-400">Environment</span>
                    <span className="font-medium text-neutral-900 dark:text-white">
                      {gw.environment}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-neutral-500 dark:text-neutral-400">Base URL</span>
                    <span
                      className="font-mono text-xs text-neutral-700 dark:text-neutral-300 truncate ml-2 max-w-[180px]"
                      title={gw.base_url}
                    >
                      {gw.base_url}
                    </span>
                  </div>
                  {gw.tenant_id && (
                    <div className="flex justify-between">
                      <span className="text-neutral-500 dark:text-neutral-400">Tenant</span>
                      <span className="font-medium text-neutral-900 dark:text-white">
                        {gw.tenant_id}
                      </span>
                    </div>
                  )}
                  {gw.capabilities.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {gw.capabilities.map((cap) => (
                        <span
                          key={cap}
                          className="px-1.5 py-0.5 bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300 text-xs rounded"
                        >
                          {cap}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Last health check */}
                {gw.last_health_check && (
                  <p className="text-xs text-neutral-400 dark:text-neutral-500 mt-3">
                    Last check: {new Date(gw.last_health_check).toLocaleString()}
                  </p>
                )}
              </div>

              {/* Actions */}
              <div className="border-t dark:border-neutral-700 px-6 py-3 flex gap-2">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleHealthCheck(gw.id);
                  }}
                  disabled={healthChecking === gw.id}
                  className="text-sm text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 disabled:opacity-50"
                >
                  {healthChecking === gw.id ? 'Checking...' : 'Health Check'}
                </button>
                <span className="text-neutral-300 dark:text-neutral-600">|</span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(gw.id, gw.name);
                  }}
                  className="text-sm text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300"
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
        <GatewayDetailPanel gateway={selectedGateway} onClose={() => setSelectedGateway(null)} />
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
        className="relative w-full max-w-md bg-white dark:bg-neutral-800 shadow-xl overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
        data-testid="gateway-detail-panel"
      >
        {/* Header */}
        <div className="sticky top-0 bg-white dark:bg-neutral-800 border-b dark:border-neutral-700 px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span
              className={`inline-block w-3 h-3 rounded-full ${
                isLive(gw) ? 'bg-green-500 animate-pulse' : 'bg-neutral-400'
              }`}
            />
            <h2 className="text-lg font-semibold text-neutral-900 dark:text-white truncate">
              {gw.display_name}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 text-xl leading-none"
            aria-label="Close detail panel"
          >
            &times;
          </button>
        </div>

        <div className="px-6 py-5 space-y-6">
          {/* Status badges */}
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className={`px-2 py-1 text-xs font-medium rounded-full ${statusColors[gw.status]}`}
            >
              {gw.status}
            </span>
            {isDegraded && (
              <span className="px-2 py-1 text-xs font-medium rounded-full bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400">
                degraded (error rate &gt; 5%)
              </span>
            )}
            {gw.mode && (
              <span
                className={`px-2 py-1 text-xs font-medium rounded-full border ${modeColors[gw.mode]}`}
              >
                {modeLabels[gw.mode]}
              </span>
            )}
          </div>

          {/* Heartbeat metrics */}
          <section>
            <h3 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-3">
              Heartbeat Metrics
            </h3>
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <MetricItem
                label="Uptime"
                value={
                  typeof hd.uptime_seconds === 'number' ? formatUptime(hd.uptime_seconds) : '--'
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
            <h3 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-3">
              Instance Info
            </h3>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-neutral-500 dark:text-neutral-400">Name</dt>
                <dd className="font-mono text-neutral-900 dark:text-white text-xs truncate max-w-[220px]">
                  {gw.name}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-neutral-500 dark:text-neutral-400">Type</dt>
                <dd className="text-neutral-900 dark:text-white">
                  {typeLabels[gw.gateway_type] || gw.gateway_type}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-neutral-500 dark:text-neutral-400">Environment</dt>
                <dd className="text-neutral-900 dark:text-white">{gw.environment}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-neutral-500 dark:text-neutral-400">Base URL</dt>
                <dd className="font-mono text-xs text-neutral-700 dark:text-neutral-300 truncate max-w-[220px]">
                  {gw.base_url}
                </dd>
              </div>
              {gw.version && (
                <div className="flex justify-between">
                  <dt className="text-neutral-500 dark:text-neutral-400">Version</dt>
                  <dd className="font-mono text-neutral-900 dark:text-white">{gw.version}</dd>
                </div>
              )}
              {typeof hd.registered_at === 'string' && (
                <div className="flex justify-between">
                  <dt className="text-neutral-500 dark:text-neutral-400">Registered</dt>
                  <dd className="text-neutral-900 dark:text-white">
                    {new Date(hd.registered_at).toLocaleString()}
                  </dd>
                </div>
              )}
              <div className="flex justify-between">
                <dt className="text-neutral-500 dark:text-neutral-400">Created</dt>
                <dd className="text-neutral-900 dark:text-white">
                  {new Date(gw.created_at).toLocaleString()}
                </dd>
              </div>
            </dl>
          </section>

          {/* Capabilities */}
          {gw.capabilities.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-2">
                Capabilities
              </h3>
              <div className="flex flex-wrap gap-1">
                {gw.capabilities.map((cap) => (
                  <span
                    key={cap}
                    className="px-2 py-1 bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300 text-xs rounded"
                  >
                    {cap}
                  </span>
                ))}
              </div>
            </section>
          )}

          {/* Tags */}
          {gw.tags.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-2">
                Tags
              </h3>
              <div className="flex flex-wrap gap-1">
                {gw.tags.map((tag) => (
                  <span
                    key={tag}
                    className="px-2 py-1 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 text-xs rounded"
                  >
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

function MetricItem({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="bg-neutral-50 dark:bg-neutral-700 rounded-lg p-3">
      <dt className="text-xs text-neutral-500 dark:text-neutral-400">{label}</dt>
      <dd
        className={`text-lg font-semibold ${warn ? 'text-orange-600' : 'text-neutral-900 dark:text-white'}`}
      >
        {value}
      </dd>
    </div>
  );
}
