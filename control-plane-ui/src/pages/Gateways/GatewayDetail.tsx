import { useState, type ReactNode } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiService } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import { filterProminentOverviewWarnings } from './gatewayOverviewWarnings';
import {
  ArrowLeft,
  ExternalLink,
  Server,
  Zap,
  Globe,
  Activity,
  Layers,
  Shield,
  Route,
  Gauge,
  FileText,
  GitBranch,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Power,
  RefreshCw,
  Heart,
  Eye,
  EyeOff,
  ShieldAlert,
} from 'lucide-react';
import type { GatewayInstance, GatewayOverviewResponse } from '../../types';
import { deploymentLabel, deploymentModeValue, gatewayUrls, topologyLabel } from './gatewayDisplay';

interface DiscoveredAPI {
  name: string;
  description?: string | null;
  version?: string | null;
  backend_url?: string | null;
  inputSchema?: Record<string, unknown> | null;
  annotations?: Record<string, unknown> | null;
  [key: string]: unknown;
}

const STATUS_CONFIG: Record<string, { color: string; icon: typeof CheckCircle2 }> = {
  online: { color: 'text-green-600 bg-green-50', icon: CheckCircle2 },
  offline: { color: 'text-red-600 bg-red-50', icon: XCircle },
  degraded: { color: 'text-amber-600 bg-amber-50', icon: AlertTriangle },
  maintenance: { color: 'text-blue-600 bg-blue-50', icon: Clock },
};

type OverviewTab = 'apis' | 'policies' | 'runtime';

const NATIVE_STOA_RUNTIME_MODES = new Set(['edge-mcp', 'sidecar', 'proxy', 'shadow']);
const NATIVE_STOA_GATEWAY_TYPES = new Set([
  'stoa_edge_mcp',
  'stoa_sidecar',
  'stoa_proxy',
  'stoa_shadow',
]);

function reportsRuntimeTools(gateway: GatewayInstance): boolean {
  return (
    NATIVE_STOA_RUNTIME_MODES.has(gateway.mode ?? '') ||
    NATIVE_STOA_GATEWAY_TYPES.has(gateway.gateway_type ?? '')
  );
}

function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${mins}m`;
  return `${mins}m`;
}

export function GatewayDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { isReady, hasPermission } = useAuth();
  const toast = useToastActions();
  const queryClient = useQueryClient();
  const [confirm, ConfirmDialog] = useConfirm();
  const [overviewTab, setOverviewTab] = useState<OverviewTab>('apis');

  const canWrite = hasPermission('admin:servers');

  const { data: gateway, isLoading } = useQuery<GatewayInstance>({
    queryKey: ['gateway', id],
    queryFn: () => apiService.getGatewayInstance(id!),
    enabled: isReady && !!id,
  });

  const {
    data: overview,
    isLoading: overviewLoading,
    isError: overviewError,
  } = useQuery<GatewayOverviewResponse>({
    queryKey: ['gateway-overview', id],
    queryFn: () => apiService.getGatewayOverview(id!),
    enabled: isReady && !!id,
    retry: false,
  });

  const { data: deploymentsData } = useQuery({
    queryKey: ['gateway-deployments', id],
    queryFn: () =>
      apiService.getGatewayDeployments({
        gateway_instance_id: id,
        page_size: 100,
      }),
    enabled: isReady && !!id,
  });

  const { data: toolsData } = useQuery<DiscoveredAPI[]>({
    queryKey: ['gateway-tools', id],
    queryFn: () => apiService.getGatewayTools(id!),
    enabled: isReady && !!id && gateway?.status === 'online',
    retry: false,
  });

  const toggleEnabledMutation = useMutation({
    mutationFn: async (enabled: boolean) => apiService.updateGatewayInstance(id!, { enabled }),
    onSuccess: (_data, enabled) => {
      queryClient.invalidateQueries({ queryKey: ['gateway', id] });
      queryClient.invalidateQueries({ queryKey: ['gateway-overview', id] });
      queryClient.invalidateQueries({ queryKey: ['gateways'] });
      toast.success(enabled ? 'Gateway enabled' : 'Gateway disabled');
    },
    onError: () => toast.error('Failed to update gateway'),
  });

  const healthCheckMutation = useMutation({
    mutationFn: () => apiService.checkGatewayHealth(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['gateway', id] });
      queryClient.invalidateQueries({ queryKey: ['gateway-overview', id] });
      toast.success('Health check completed');
    },
    onError: () => toast.error('Health check failed'),
  });

  const handleToggleEnabled = async () => {
    if (!gateway) return;
    if (gateway.enabled) {
      const confirmed = await confirm({
        title: 'Disable Gateway',
        message: `Disabling "${gateway.display_name}" will prevent new deployments and tool syncs to this gateway. Existing deployments will remain active.`,
        confirmLabel: 'Disable',
        variant: 'danger',
      });
      if (confirmed) toggleEnabledMutation.mutate(false);
    } else {
      toggleEnabledMutation.mutate(true);
    }
  };

  if (isLoading || !gateway) {
    return (
      <div className="p-6 space-y-4">
        <CardSkeleton />
        <CardSkeleton />
      </div>
    );
  }

  const hd = (gateway.health_details || {}) as Record<string, unknown>;
  const statusCfg = STATUS_CONFIG[gateway.status] || STATUS_CONFIG.offline;
  const StatusIcon = statusCfg.icon;
  const deployments = deploymentsData?.items || [];
  const discoveredApis = toolsData || [];
  const usesDeploymentMetric = reportsRuntimeTools(gateway);
  const syncedDeployments = deployments.filter((deployment) => deployment.sync_status === 'synced');
  const discoveryMetricLabel = usesDeploymentMetric ? 'Deployed APIs' : 'Discovered APIs';
  const discoveryMetricValue = usesDeploymentMetric
    ? deploymentsData
      ? String(syncedDeployments.length)
      : '-'
    : String(hd.discovered_apis_count ?? '-');
  const urls = gatewayUrls(gateway);
  const modeLabel = deploymentLabel(gateway);
  const configDeploymentMode = deploymentModeValue(gateway);
  const topologyText = topologyLabel(gateway);
  const hasVisibilityRestriction =
    gateway.visibility && Array.isArray(gateway.visibility.tenant_ids);
  const hasOverview = Boolean(overview);
  const showLegacyGatewayData = !overviewLoading && !hasOverview;
  const overviewWarnings = overview?.data_quality.warnings ?? [];
  const prominentOverviewWarnings = filterProminentOverviewWarnings(overviewWarnings);

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button
          onClick={() => navigate('/gateways')}
          className="p-2 rounded-lg hover:bg-gray-100 transition-colors"
        >
          <ArrowLeft className="h-5 w-5 text-gray-500" />
        </button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold text-gray-900">{gateway.display_name}</h1>
            <span
              className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium ${statusCfg.color}`}
            >
              <StatusIcon className="h-3 w-3" />
              {gateway.status}
            </span>
            {!gateway.enabled && (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
                <Power className="h-3 w-3" />
                Disabled
              </span>
            )}
            {modeLabel && (
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-indigo-50 text-indigo-700">
                {modeLabel}
              </span>
            )}
            {topologyText && (
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-50 text-slate-700">
                {topologyText}
              </span>
            )}
            {gateway.source === 'argocd' && (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-teal-50 text-teal-700">
                <GitBranch className="h-3 w-3" />
                GitOps
              </span>
            )}
          </div>
          <p className="text-sm text-gray-500 font-mono mt-1">{gateway.name}</p>
        </div>
        <div className="flex items-center gap-2">
          {canWrite && (
            <>
              <button
                onClick={() => healthCheckMutation.mutate()}
                disabled={healthCheckMutation.isPending}
                className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-gray-200 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50"
              >
                <Heart
                  className={`h-4 w-4 ${healthCheckMutation.isPending ? 'animate-pulse' : ''}`}
                />
                Health Check
              </button>
              <button
                onClick={handleToggleEnabled}
                disabled={toggleEnabledMutation.isPending}
                className={`inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 ${
                  gateway.enabled
                    ? 'border border-red-200 text-red-700 hover:bg-red-50'
                    : 'border border-green-200 text-green-700 hover:bg-green-50'
                }`}
              >
                <Power className="h-4 w-4" />
                {gateway.enabled ? 'Disable' : 'Enable'}
              </button>
            </>
          )}
          {urls.publicUrl && (
            <a
              href={urls.publicUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-gray-200 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
            >
              <Globe className="h-4 w-4" />
              Open Gateway
              <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </div>
      </div>

      {/* Disabled banner */}
      {!gateway.enabled && (
        <div className="flex items-center gap-3 p-4 bg-amber-50 border border-amber-200 rounded-xl">
          <ShieldAlert className="h-5 w-5 text-amber-600 flex-shrink-0" />
          <div>
            <p className="text-sm font-medium text-amber-800">Gateway disabled</p>
            <p className="text-sm text-amber-700">
              This gateway will not accept new deployments or tool syncs. Existing deployments
              remain active.
            </p>
          </div>
        </div>
      )}

      {overviewLoading && (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
          <CardSkeleton className="h-24" />
          <CardSkeleton className="h-24" />
          <CardSkeleton className="h-24" />
          <CardSkeleton className="h-24" />
        </div>
      )}

      {overview && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
            <OverviewSummaryCard
              icon={<GitBranch className="h-4 w-4" />}
              label="Config"
              value={formatStatusLabel(overview.summary.sync_status)}
              detail={`${formatNullableNumber(overview.sync.desired_generation)} desired / ${formatNullableNumber(overview.sync.applied_generation)} applied`}
              status={overview.summary.sync_status}
            />
            <OverviewSummaryCard
              icon={<Activity className="h-4 w-4" />}
              label="Runtime"
              value={formatStatusLabel(overview.summary.runtime_status)}
              detail={`Heartbeat ${formatAge(overview.runtime.heartbeat_age_seconds)}`}
              status={overview.summary.runtime_status}
            />
            <OverviewSummaryCard
              icon={<Layers className="h-4 w-4" />}
              label="APIs"
              value={`${overview.summary.apis_count} deployed`}
              detail={`Routes ${overview.summary.expected_routes_count} expected / ${formatNullableNumber(overview.summary.reported_routes_count)} reported`}
            />
            <OverviewSummaryCard
              icon={<Shield className="h-4 w-4" />}
              label="Policies"
              value={`${overview.summary.effective_policies_count} effective`}
              detail={`${overview.summary.failed_policies_count} failed`}
              status={overview.summary.failed_policies_count > 0 ? 'failed' : 'in_sync'}
            />
          </div>

          {(overview.visibility.filtered || prominentOverviewWarnings.length > 0) && (
            <div className="space-y-2">
              {overview.visibility.filtered && (
                <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                  <EyeOff className="h-4 w-4" />
                  Vue filtrée selon vos permissions.
                </div>
              )}
              {prominentOverviewWarnings.map((warning) => (
                <div
                  key={warning.code}
                  className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700"
                >
                  <AlertTriangle className="h-4 w-4 text-amber-500" />
                  {warning.message}
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {overviewError && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          <AlertTriangle className="h-4 w-4" />
          Gateway overview unavailable. Showing legacy gateway data.
        </div>
      )}

      {/* Configuration */}
      <section className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <Server className="h-5 w-5 text-gray-400" />
          Configuration
        </h2>
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4">
          <ConfigItem label="Admin URL" value={urls.baseUrl ?? '--'} isLink={!!urls.baseUrl} />
          {urls.publicUrl && <ConfigItem label="STOA Runtime" value={urls.publicUrl} isLink />}
          {urls.targetUrl && <ConfigItem label="Target Gateway" value={urls.targetUrl} isLink />}
          {urls.uiUrl && <ConfigItem label="Third-party UI" value={urls.uiUrl} isLink />}
          <ConfigItem label="Environment" value={gateway.environment} />
          <ConfigItem label="Type" value={gateway.gateway_type} />
          {gateway.target_gateway_type && (
            <ConfigItem label="Target Type" value={gateway.target_gateway_type} />
          )}
          {configDeploymentMode && (
            <ConfigItem label="Deployment Mode" value={configDeploymentMode} />
          )}
          {gateway.topology && <ConfigItem label="Topology" value={gateway.topology} />}
          {gateway.version && <ConfigItem label="Version" value={gateway.version} />}
          <ConfigItem label="Source" value={gateway.source || 'manual'} />
          {gateway.tenant_id && <ConfigItem label="Tenant" value={gateway.tenant_id} />}
        </dl>
        {gateway.capabilities.length > 0 && (
          <div className="mt-4 pt-4 border-t border-gray-100">
            <dt className="text-sm font-medium text-gray-500 mb-2">Capabilities</dt>
            <div className="flex flex-wrap gap-2">
              {gateway.capabilities.map((cap) => (
                <span
                  key={cap}
                  className="px-2 py-1 rounded-md bg-gray-100 text-xs font-medium text-gray-600"
                >
                  {cap}
                </span>
              ))}
            </div>
          </div>
        )}
        {/* Visibility */}
        <div className="mt-4 pt-4 border-t border-gray-100">
          <dt className="text-sm font-medium text-gray-500 mb-2 flex items-center gap-1.5">
            {hasVisibilityRestriction ? (
              <EyeOff className="h-3.5 w-3.5" />
            ) : (
              <Eye className="h-3.5 w-3.5" />
            )}
            Visibility
          </dt>
          {hasVisibilityRestriction ? (
            <div className="flex flex-wrap gap-2">
              {gateway.visibility!.tenant_ids.map((tid) => (
                <span
                  key={tid}
                  className="px-2 py-1 rounded-md bg-amber-50 text-xs font-medium text-amber-700"
                >
                  {tid}
                </span>
              ))}
            </div>
          ) : (
            <span className="text-sm text-gray-600">All tenants</span>
          )}
        </div>
      </section>

      {overview && (
        <section className="bg-white rounded-xl border border-gray-200">
          <div className="border-b border-gray-100 px-4 pt-4">
            <div className="flex flex-wrap gap-1">
              <OverviewTabButton
                active={overviewTab === 'apis'}
                icon={<Layers className="h-4 w-4" />}
                label="APIs"
                onClick={() => setOverviewTab('apis')}
              />
              <OverviewTabButton
                active={overviewTab === 'policies'}
                icon={<Shield className="h-4 w-4" />}
                label="Policies"
                onClick={() => setOverviewTab('policies')}
              />
              <OverviewTabButton
                active={overviewTab === 'runtime'}
                icon={<Gauge className="h-4 w-4" />}
                label="Runtime"
                onClick={() => setOverviewTab('runtime')}
              />
            </div>
          </div>
          <div className="p-4">
            {overviewTab === 'apis' && <GatewayOverviewApis overview={overview} />}
            {overviewTab === 'policies' && <GatewayOverviewPolicies overview={overview} />}
            {overviewTab === 'runtime' && <GatewayOverviewRuntime overview={overview} />}
          </div>
        </section>
      )}

      {/* Health & Metrics */}
      {showLegacyGatewayData && (
        <section className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <Activity className="h-5 w-5 text-gray-400" />
            Health &amp; Metrics
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <MetricCard
              label="Uptime"
              value={hd.uptime_seconds ? formatUptime(hd.uptime_seconds as number) : '-'}
            />
            <MetricCard label="Routes" value={String(hd.routes_count ?? '-')} />
            <MetricCard label={discoveryMetricLabel} value={discoveryMetricValue} />
            <MetricCard
              label="Error Rate"
              value={
                hd.error_rate != null ? `${((hd.error_rate as number) * 100).toFixed(1)}%` : '-'
              }
              alert={(hd.error_rate as number) > 0.05}
            />
          </div>
        </section>
      )}

      {/* API Deployments */}
      {showLegacyGatewayData && deployments.length > 0 && (
        <section className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <Zap className="h-5 w-5 text-gray-400" />
            API Deployments
            <span className="ml-auto text-sm font-normal text-gray-400">
              {deployments.length} API{deployments.length !== 1 ? 's' : ''}
            </span>
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b border-gray-100">
                  <th className="pb-2 font-medium">API Name</th>
                  <th className="pb-2 font-medium">Version</th>
                  <th className="pb-2 font-medium">Sync Status</th>
                  <th className="pb-2 font-medium">Environment</th>
                  {canWrite && <th className="pb-2 font-medium">Actions</th>}
                </tr>
              </thead>
              <tbody>
                {deployments.map((d) => (
                  <tr key={d.id} className="border-b border-gray-50 hover:bg-gray-50">
                    <td className="py-2.5 font-medium text-gray-900">
                      {(d.desired_state?.api_name as string | undefined) || d.api_catalog_id}
                    </td>
                    <td className="py-2.5 text-gray-500">
                      {(d.desired_state?.api_version as string | undefined) || '-'}
                    </td>
                    <td className="py-2.5">
                      <SyncBadge status={d.sync_status || 'pending'} />
                    </td>
                    <td className="py-2.5 text-gray-500">{d.gateway_environment || '-'}</td>
                    {canWrite && (
                      <td className="py-2.5">
                        <ForceSyncButton deploymentId={d.id} />
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* MCP Tools (live from gateway) */}
      {discoveredApis.length > 0 && (
        <section className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <Zap className="h-5 w-5 text-gray-400" />
            MCP Tools
            <span className="ml-auto text-sm font-normal text-gray-400">
              {discoveredApis.length} tool{discoveredApis.length !== 1 ? 's' : ''}
            </span>
          </h2>
          <p className="text-xs text-gray-400 mb-3">
            Live tools from the gateway&apos;s MCP tool registry.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b border-gray-100">
                  <th className="pb-2 font-medium">API Name</th>
                  <th className="pb-2 font-medium">Description</th>
                </tr>
              </thead>
              <tbody>
                {discoveredApis.map((api) => (
                  <tr key={api.name} className="border-b border-gray-50 hover:bg-gray-50">
                    <td className="py-2.5 font-medium text-gray-900 font-mono text-xs">
                      {api.name}
                    </td>
                    <td className="py-2.5 text-gray-500 max-w-md truncate">
                      {api.description || '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Empty state: no deployments and no discovered APIs */}
      {showLegacyGatewayData && deployments.length === 0 && discoveredApis.length === 0 && (
        <section className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <Zap className="h-5 w-5 text-gray-400" />
            APIs
          </h2>
          <p className="text-sm text-gray-400 text-center py-8">
            No APIs deployed and no MCP tools registered on this gateway
          </p>
        </section>
      )}

      {ConfirmDialog}
    </div>
  );
}

function ForceSyncButton({ deploymentId }: { deploymentId: string }) {
  const toast = useToastActions();
  const queryClient = useQueryClient();

  const syncMutation = useMutation({
    mutationFn: () => apiService.forceSyncDeployment(deploymentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['gateway-deployments'] });
      queryClient.invalidateQueries({ queryKey: ['gateway-overview'] });
      toast.success('Sync triggered');
    },
    onError: () => toast.error('Sync failed'),
  });

  return (
    <button
      onClick={() => syncMutation.mutate()}
      disabled={syncMutation.isPending}
      className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium text-indigo-700 hover:bg-indigo-50 transition-colors disabled:opacity-50"
    >
      <RefreshCw className={`h-3 w-3 ${syncMutation.isPending ? 'animate-spin' : ''}`} />
      Sync
    </button>
  );
}

function OverviewTabButton({
  active,
  icon,
  label,
  onClick,
}: {
  active: boolean;
  icon: ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-2 border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
        active
          ? 'border-indigo-600 text-indigo-700'
          : 'border-transparent text-gray-500 hover:text-gray-800'
      }`}
    >
      {icon}
      {label}
    </button>
  );
}

function OverviewSummaryCard({
  icon,
  label,
  value,
  detail,
  status,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  detail: string;
  status?: string;
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-medium text-gray-500">
          <span className="text-gray-400">{icon}</span>
          {label}
        </div>
        {status && <StatusDot status={status} />}
      </div>
      <div className="mt-3 text-xl font-semibold text-gray-900">{value}</div>
      <div className="mt-1 text-sm text-gray-500">{detail}</div>
    </div>
  );
}

function GatewayOverviewApis({ overview }: { overview: GatewayOverviewResponse }) {
  const apis = overview.resolved_config.apis;
  if (apis.length === 0) {
    return (
      <div className="py-10 text-center text-sm text-gray-400">
        No APIs are deployed on this gateway.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100 text-left text-gray-500">
            <th className="pb-2 font-medium">API</th>
            <th className="pb-2 font-medium">Tenant</th>
            <th className="pb-2 font-medium">Version</th>
            <th className="pb-2 font-medium">Routes</th>
            <th className="pb-2 font-medium">Backend</th>
            <th className="pb-2 font-medium">Policies</th>
            <th className="pb-2 font-medium">Sync</th>
            <th className="pb-2 font-medium">Last sync</th>
          </tr>
        </thead>
        <tbody>
          {apis.map((api) => (
            <tr
              key={api.api_catalog_id}
              className="border-b border-gray-50 align-top hover:bg-gray-50"
            >
              <td className="py-3 pr-4">
                <Link
                  to={`/apis/${encodeURIComponent(api.tenant_id)}/${encodeURIComponent(api.api_id)}`}
                  className="inline-flex items-center gap-1 font-medium text-indigo-700 hover:text-indigo-900"
                >
                  {api.name}
                  <ExternalLink className="h-3 w-3" />
                </Link>
                <div className="mt-1 font-mono text-xs text-gray-400">{api.api_id}</div>
              </td>
              <td className="py-3 pr-4 font-mono text-xs text-gray-500">{api.tenant_id}</td>
              <td className="py-3 pr-4 text-gray-600">{api.version}</td>
              <td className="py-3 pr-4">
                <div className="font-medium text-gray-900">{api.routes_count}</div>
                <div className="mt-1 space-y-1">
                  {api.routes_preview.map((route) => (
                    <div
                      key={`${route.method}-${route.path}`}
                      className="whitespace-nowrap font-mono text-xs text-gray-500"
                    >
                      <span className="mr-2 rounded bg-gray-100 px-1.5 py-0.5 text-[11px] font-semibold text-gray-700">
                        {route.method}
                      </span>
                      {route.path}
                    </div>
                  ))}
                  {api.routes_count > api.routes_preview.length && (
                    <div className="text-xs text-gray-400">
                      + {api.routes_count - api.routes_preview.length} routes
                    </div>
                  )}
                </div>
              </td>
              <td className="max-w-xs py-3 pr-4">
                {api.backend ? (
                  <span
                    className="block truncate font-mono text-xs text-gray-600"
                    title={api.backend}
                  >
                    {api.backend}
                  </span>
                ) : (
                  <span className="text-gray-400">-</span>
                )}
              </td>
              <td className="py-3 pr-4 text-gray-600">{api.policies_count}</td>
              <td className="py-3 pr-4">
                <SyncBadge status={api.sync_status} />
                {api.last_error && (
                  <div
                    className="mt-1 max-w-xs truncate text-xs text-red-600"
                    title={api.last_error}
                  >
                    {api.last_error}
                  </div>
                )}
              </td>
              <td className="py-3 pr-4 text-xs text-gray-500">
                {formatDateTime(api.last_sync_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GatewayOverviewPolicies({ overview }: { overview: GatewayOverviewResponse }) {
  const policies = overview.resolved_config.policies;
  if (policies.length === 0) {
    return (
      <div className="py-10 text-center text-sm text-gray-400">
        No effective policies are applied to this gateway.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100 text-left text-gray-500">
            <th className="pb-2 font-medium">Name</th>
            <th className="pb-2 font-medium">Type</th>
            <th className="pb-2 font-medium">Scope</th>
            <th className="pb-2 font-medium">Target</th>
            <th className="pb-2 font-medium">Priority</th>
            <th className="pb-2 font-medium">Status</th>
            <th className="pb-2 font-medium">Summary</th>
          </tr>
        </thead>
        <tbody>
          {policies.map((policy) => (
            <tr key={policy.id} className="border-b border-gray-50 align-top hover:bg-gray-50">
              <td className="py-3 pr-4 font-medium text-gray-900">{policy.name}</td>
              <td className="py-3 pr-4 font-mono text-xs text-gray-600">{policy.type}</td>
              <td className="py-3 pr-4">
                <span className="rounded bg-gray-100 px-2 py-1 text-xs font-medium text-gray-700">
                  {policy.scope}
                </span>
              </td>
              <td className="py-3 pr-4">
                <div className="text-gray-700">{policy.target.name || policy.target.id || '-'}</div>
                <div className="font-mono text-xs text-gray-400">{policy.target.type}</div>
              </td>
              <td className="py-3 pr-4 text-gray-600">{policy.priority}</td>
              <td className="py-3 pr-4">
                <SyncBadge status={policy.sync_status} />
              </td>
              <td className="max-w-md py-3 pr-4 text-gray-600">{policy.summary}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GatewayOverviewRuntime({ overview }: { overview: GatewayOverviewResponse }) {
  const runtime = overview.runtime;
  const sync = overview.sync;
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <div>
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-gray-900">
          <Activity className="h-4 w-4 text-gray-400" />
          Runtime
        </h3>
        <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <RuntimeItem label="Status" value={formatStatusLabel(runtime.status)} />
          <RuntimeItem label="Heartbeat" value={formatAge(runtime.heartbeat_age_seconds)} />
          <RuntimeItem label="Version" value={runtime.version || '-'} />
          <RuntimeItem label="Mode" value={runtime.mode || '-'} />
          <RuntimeItem
            label="Uptime"
            value={runtime.uptime_seconds != null ? formatUptime(runtime.uptime_seconds) : '-'}
          />
          <RuntimeItem label="MCP tools" value={formatNullableNumber(runtime.mcp_tools_count)} />
          <RuntimeItem label="Requests" value={formatNullableNumber(runtime.requests_total)} />
          <RuntimeItem label="Error rate" value={formatPercent(runtime.error_rate)} />
          <RuntimeItem label="Memory" value={formatBytes(runtime.memory_usage_bytes)} />
          <RuntimeItem
            label="Metrics"
            value={`${formatStatusLabel(overview.summary.metrics_status)} / ${overview.data_quality.metrics_window_seconds ?? '-'}s`}
          />
        </dl>
      </div>

      <div>
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-gray-900">
          <Route className="h-4 w-4 text-gray-400" />
          Sync / drift
        </h3>
        <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <RuntimeItem label="Sync status" value={formatStatusLabel(sync.status)} />
          <RuntimeItem
            label="Generation"
            value={`${formatNullableNumber(sync.desired_generation)} desired / ${formatNullableNumber(sync.applied_generation)} applied`}
          />
          <RuntimeItem
            label="Routes"
            value={`${overview.summary.expected_routes_count} expected / ${formatNullableNumber(overview.summary.reported_routes_count)} reported`}
          />
          <RuntimeItem
            label="Policies"
            value={`${overview.summary.effective_policies_count} expected / ${formatNullableNumber(overview.summary.reported_policies_count)} reported`}
          />
          <RuntimeItem label="Last reconciled" value={formatDateTime(sync.last_reconciled_at)} />
          <RuntimeItem label="Last error" value={sync.last_error || '-'} />
        </dl>
        {sync.steps.length > 0 && (
          <div className="mt-4 rounded-lg border border-gray-100">
            <div className="border-b border-gray-100 px-3 py-2 text-xs font-medium text-gray-500">
              Sync steps
            </div>
            <div className="max-h-48 overflow-auto p-3">
              <pre className="text-xs text-gray-600">{JSON.stringify(sync.steps, null, 2)}</pre>
            </div>
          </div>
        )}
        {overview.source.control_plane_revision && (
          <div className="mt-4 flex items-center gap-2 text-xs text-gray-500">
            <FileText className="h-3.5 w-3.5" />
            Revision {overview.source.control_plane_revision}
          </div>
        )}
        {overview.data_quality.warnings.length > 0 && (
          <div className="mt-4 rounded-lg border border-gray-100">
            <div className="border-b border-gray-100 px-3 py-2 text-xs font-medium text-gray-500">
              Data quality
            </div>
            <div className="space-y-2 p-3">
              {overview.data_quality.warnings.map((warning) => (
                <div key={warning.code} className="text-xs text-gray-600">
                  <span className="font-medium text-gray-800">
                    {formatStatusLabel(warning.severity)}:
                  </span>{' '}
                  {warning.message}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function RuntimeItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-gray-100 p-3">
      <dt className="text-xs font-medium text-gray-500">{label}</dt>
      <dd className="mt-1 break-words text-sm font-medium text-gray-900">{value}</dd>
    </div>
  );
}

function ConfigItem({ label, value, isLink }: { label: string; value: string; isLink?: boolean }) {
  return (
    <div>
      <dt className="text-sm font-medium text-gray-500">{label}</dt>
      <dd className="mt-1 text-sm text-gray-900">
        {isLink ? (
          <a
            href={value}
            target="_blank"
            rel="noopener noreferrer"
            className="font-mono text-indigo-600 hover:text-indigo-800 inline-flex items-center gap-1"
          >
            {value}
            <ExternalLink className="h-3 w-3" />
          </a>
        ) : (
          <span className="font-mono">{value}</span>
        )}
      </dd>
    </div>
  );
}

function MetricCard({ label, value, alert }: { label: string; value: string; alert?: boolean }) {
  return (
    <div className="rounded-lg border border-gray-100 p-3">
      <dt className="text-xs font-medium text-gray-500">{label}</dt>
      <dd className={`mt-1 text-lg font-semibold ${alert ? 'text-red-600' : 'text-gray-900'}`}>
        {value}
      </dd>
    </div>
  );
}

function StatusDot({ status }: { status: string }) {
  const color =
    {
      in_sync: 'bg-green-500',
      healthy: 'bg-green-500',
      available: 'bg-green-500',
      pending: 'bg-amber-500',
      stale: 'bg-amber-500',
      partial: 'bg-amber-500',
      drift: 'bg-orange-500',
      degraded: 'bg-orange-500',
      failed: 'bg-red-500',
      offline: 'bg-red-500',
      unavailable: 'bg-red-500',
    }[status] ?? 'bg-gray-400';

  return <span className={`h-2.5 w-2.5 rounded-full ${color}`} aria-hidden="true" />;
}

function SyncBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    in_sync: 'bg-green-50 text-green-700',
    synced: 'bg-green-50 text-green-700',
    pending: 'bg-amber-50 text-amber-700',
    syncing: 'bg-blue-50 text-blue-700',
    failed: 'bg-red-50 text-red-700',
    error: 'bg-red-50 text-red-700',
    drift: 'bg-orange-50 text-orange-700',
    drifted: 'bg-orange-50 text-orange-700',
    unknown: 'bg-gray-50 text-gray-700',
  };
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${colors[status] || 'bg-gray-50 text-gray-700'}`}
    >
      {formatStatusLabel(status)}
    </span>
  );
}

function formatStatusLabel(status: string): string {
  return status.replace(/_/g, ' ');
}

function formatNullableNumber(value: number | null | undefined): string {
  return value == null ? '-' : String(value);
}

function formatAge(seconds: number | null | undefined): string {
  if (seconds == null) return '-';
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleString(undefined, {
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatPercent(value: number | null | undefined): string {
  if (value == null) return '-';
  return `${(value * 100).toFixed(1)}%`;
}

function formatBytes(value: number | null | undefined): string {
  if (value == null) return '-';
  if (value < 1024) return `${value} B`;
  const units = ['KB', 'MB', 'GB'];
  let amount = value / 1024;
  for (const unit of units) {
    if (amount < 1024) return `${amount.toFixed(1)} ${unit}`;
    amount /= 1024;
  }
  return `${amount.toFixed(1)} TB`;
}
