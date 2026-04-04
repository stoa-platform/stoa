import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiService } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import {
  ArrowLeft,
  ExternalLink,
  Server,
  Zap,
  Globe,
  Activity,
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
import type { GatewayInstance } from '../../types';

interface DiscoveredAPI {
  name: string;
  description?: string;
  version?: string;
  backend_url?: string;
  inputSchema?: Record<string, unknown>;
  annotations?: Record<string, unknown>;
}

const MODE_LABELS: Record<string, string> = {
  'edge-mcp': 'Edge MCP',
  sidecar: 'STOA Link',
  proxy: 'Proxy',
  shadow: 'Shadow',
  connect: 'Connect',
};

const STATUS_CONFIG: Record<string, { color: string; icon: typeof CheckCircle2 }> = {
  online: { color: 'text-green-600 bg-green-50', icon: CheckCircle2 },
  offline: { color: 'text-red-600 bg-red-50', icon: XCircle },
  degraded: { color: 'text-amber-600 bg-amber-50', icon: AlertTriangle },
  maintenance: { color: 'text-blue-600 bg-blue-50', icon: Clock },
};

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

  const canWrite = hasPermission('admin:servers');

  const { data: gateway, isLoading } = useQuery<GatewayInstance>({
    queryKey: ['gateway', id],
    queryFn: () => apiService.getGatewayInstance(id!),
    enabled: isReady && !!id,
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
      queryClient.invalidateQueries({ queryKey: ['gateways'] });
      toast.success(enabled ? 'Gateway enabled' : 'Gateway disabled');
    },
    onError: () => toast.error('Failed to update gateway'),
  });

  const healthCheckMutation = useMutation({
    mutationFn: () => apiService.checkGatewayHealth(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['gateway', id] });
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
  const hasVisibilityRestriction =
    gateway.visibility && Array.isArray(gateway.visibility.tenant_ids);

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
            {gateway.mode && (
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-indigo-50 text-indigo-700">
                {MODE_LABELS[gateway.mode] || gateway.mode}
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
          {gateway.public_url && (
            <a
              href={gateway.public_url}
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

      {/* Configuration */}
      <section className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <Server className="h-5 w-5 text-gray-400" />
          Configuration
        </h2>
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4">
          <ConfigItem label="Admin URL" value={gateway.base_url} isLink />
          {gateway.public_url && (
            <ConfigItem label="Public URL" value={gateway.public_url} isLink />
          )}
          {gateway.target_gateway_url && (
            <ConfigItem label="Target Gateway" value={gateway.target_gateway_url} isLink />
          )}
          {gateway.ui_url && <ConfigItem label="Gateway UI" value={gateway.ui_url} isLink />}
          <ConfigItem label="Environment" value={gateway.environment} />
          <ConfigItem label="Type" value={gateway.gateway_type} />
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

      {/* Health & Metrics */}
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
          <MetricCard label="Discovered APIs" value={String(hd.discovered_apis_count ?? '-')} />
          <MetricCard
            label="Error Rate"
            value={hd.error_rate != null ? `${((hd.error_rate as number) * 100).toFixed(1)}%` : '-'}
            alert={(hd.error_rate as number) > 0.05}
          />
        </div>
      </section>

      {/* APIs Deployed */}
      {deployments.length > 0 && (
        <section className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <Zap className="h-5 w-5 text-gray-400" />
            APIs Deployed
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
                {deployments.map((d: Record<string, unknown>) => (
                  <tr key={d.id as string} className="border-b border-gray-50 hover:bg-gray-50">
                    <td className="py-2.5 font-medium text-gray-900">
                      {(d.api_name as string) || (d.api_catalog_id as string)}
                    </td>
                    <td className="py-2.5 text-gray-500">{(d.api_version as string) || '-'}</td>
                    <td className="py-2.5">
                      <SyncBadge status={(d.sync_status as string) || 'pending'} />
                    </td>
                    <td className="py-2.5 text-gray-500">{d.environment as string}</td>
                    {canWrite && (
                      <td className="py-2.5">
                        <ForceSyncButton deploymentId={d.id as string} />
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
      {deployments.length === 0 && discoveredApis.length === 0 && (
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

function SyncBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    synced: 'bg-green-50 text-green-700',
    pending: 'bg-amber-50 text-amber-700',
    syncing: 'bg-blue-50 text-blue-700',
    error: 'bg-red-50 text-red-700',
    drifted: 'bg-orange-50 text-orange-700',
  };
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${colors[status] || 'bg-gray-50 text-gray-700'}`}
    >
      {status}
    </span>
  );
}
