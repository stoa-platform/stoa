import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiService } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
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
  online: {
    color: 'text-green-600 bg-green-50 dark:bg-green-950 dark:text-green-400',
    icon: CheckCircle2,
  },
  offline: { color: 'text-red-600 bg-red-50 dark:bg-red-950 dark:text-red-400', icon: XCircle },
  degraded: {
    color: 'text-amber-600 bg-amber-50 dark:bg-amber-950 dark:text-amber-400',
    icon: AlertTriangle,
  },
  maintenance: {
    color: 'text-blue-600 bg-blue-50 dark:bg-blue-950 dark:text-blue-400',
    icon: Clock,
  },
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
  const { isReady } = useAuth();

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

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button
          onClick={() => navigate('/gateways')}
          className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
        >
          <ArrowLeft className="h-5 w-5 text-gray-500" />
        </button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">
              {gateway.display_name}
            </h1>
            <span
              className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium ${statusCfg.color}`}
            >
              <StatusIcon className="h-3 w-3" />
              {gateway.status}
            </span>
            {gateway.mode && (
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
                {MODE_LABELS[gateway.mode] || gateway.mode}
              </span>
            )}
            {gateway.source === 'argocd' && (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-teal-50 text-teal-700 dark:bg-teal-950 dark:text-teal-300">
                <GitBranch className="h-3 w-3" />
                GitOps
              </span>
            )}
          </div>
          <p className="text-sm text-gray-500 dark:text-gray-400 font-mono mt-1">{gateway.name}</p>
        </div>
        {gateway.public_url && (
          <a
            href={gateway.public_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-200 dark:border-gray-700 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          >
            <Globe className="h-4 w-4" />
            Open Gateway
            <ExternalLink className="h-3 w-3" />
          </a>
        )}
      </div>

      {/* Configuration */}
      <section className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4 flex items-center gap-2">
          <Server className="h-5 w-5 text-gray-400 dark:text-gray-500" />
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
          <div className="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800">
            <dt className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">
              Capabilities
            </dt>
            <div className="flex flex-wrap gap-2">
              {gateway.capabilities.map((cap) => (
                <span
                  key={cap}
                  className="px-2 py-1 rounded-md bg-gray-100 dark:bg-gray-800 text-xs font-medium text-gray-600 dark:text-gray-300"
                >
                  {cap}
                </span>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* Health & Metrics */}
      <section className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4 flex items-center gap-2">
          <Activity className="h-5 w-5 text-gray-400 dark:text-gray-500" />
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
        <section className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4 flex items-center gap-2">
            <Zap className="h-5 w-5 text-gray-400 dark:text-gray-500" />
            APIs Deployed
            <span className="ml-auto text-sm font-normal text-gray-400">
              {deployments.length} API{deployments.length !== 1 ? 's' : ''}
            </span>
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 dark:text-gray-400 border-b border-gray-100 dark:border-gray-800">
                  <th className="pb-2 font-medium">API Name</th>
                  <th className="pb-2 font-medium">Version</th>
                  <th className="pb-2 font-medium">Sync Status</th>
                  <th className="pb-2 font-medium">Environment</th>
                </tr>
              </thead>
              <tbody>
                {deployments.map((d: Record<string, unknown>) => (
                  <tr
                    key={d.id as string}
                    className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800"
                  >
                    <td className="py-2.5 font-medium text-gray-900 dark:text-gray-100">
                      {(d.api_name as string) || (d.api_catalog_id as string)}
                    </td>
                    <td className="py-2.5 text-gray-500 dark:text-gray-400">
                      {(d.api_version as string) || '-'}
                    </td>
                    <td className="py-2.5">
                      <SyncBadge status={(d.sync_status as string) || 'pending'} />
                    </td>
                    <td className="py-2.5 text-gray-500 dark:text-gray-400">
                      {d.environment as string}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* MCP Tools (live from gateway) */}
      {discoveredApis.length > 0 && (
        <section className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4 flex items-center gap-2">
            <Zap className="h-5 w-5 text-gray-400 dark:text-gray-500" />
            MCP Tools
            <span className="ml-auto text-sm font-normal text-gray-400">
              {discoveredApis.length} tool{discoveredApis.length !== 1 ? 's' : ''}
            </span>
          </h2>
          <p className="text-xs text-gray-400 dark:text-gray-500 mb-3">
            Live tools from the gateway&apos;s MCP tool registry.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 dark:text-gray-400 border-b border-gray-100 dark:border-gray-800">
                  <th className="pb-2 font-medium">API Name</th>
                  <th className="pb-2 font-medium">Description</th>
                </tr>
              </thead>
              <tbody>
                {discoveredApis.map((api) => (
                  <tr
                    key={api.name}
                    className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800"
                  >
                    <td className="py-2.5 font-medium text-gray-900 dark:text-gray-100 font-mono text-xs">
                      {api.name}
                    </td>
                    <td className="py-2.5 text-gray-500 dark:text-gray-400 max-w-md truncate">
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
        <section className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4 flex items-center gap-2">
            <Zap className="h-5 w-5 text-gray-400 dark:text-gray-500" />
            APIs
          </h2>
          <p className="text-sm text-gray-400 dark:text-gray-500 text-center py-8">
            No APIs deployed and no MCP tools registered on this gateway
          </p>
        </section>
      )}
    </div>
  );
}

function ConfigItem({ label, value, isLink }: { label: string; value: string; isLink?: boolean }) {
  return (
    <div>
      <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">{label}</dt>
      <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">
        {isLink ? (
          <a
            href={value}
            target="_blank"
            rel="noopener noreferrer"
            className="font-mono text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300 inline-flex items-center gap-1"
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
    <div className="rounded-lg border border-gray-100 dark:border-gray-800 p-3">
      <dt className="text-xs font-medium text-gray-500 dark:text-gray-400">{label}</dt>
      <dd
        className={`mt-1 text-lg font-semibold ${alert ? 'text-red-600' : 'text-gray-900 dark:text-gray-100'}`}
      >
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
