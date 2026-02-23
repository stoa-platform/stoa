import { useState, useEffect, useCallback } from 'react';
import { Server, RefreshCw, Activity, Loader2 } from 'lucide-react';
import { gatewaysService } from '../../services/gateways';
import type { GatewayInstance, GatewayStatus, GatewayType } from '../../types';

const statusConfig: Record<GatewayStatus, { bg: string; text: string; label: string }> = {
  online: {
    bg: 'bg-green-100 dark:bg-green-900/30',
    text: 'text-green-800 dark:text-green-400',
    label: 'Online',
  },
  offline: {
    bg: 'bg-red-100 dark:bg-red-900/30',
    text: 'text-red-800 dark:text-red-400',
    label: 'Offline',
  },
  degraded: {
    bg: 'bg-yellow-100 dark:bg-yellow-900/30',
    text: 'text-yellow-800 dark:text-yellow-400',
    label: 'Degraded',
  },
  maintenance: {
    bg: 'bg-neutral-100 dark:bg-neutral-700',
    text: 'text-neutral-800 dark:text-neutral-300',
    label: 'Maintenance',
  },
};

const gatewayTypeLabels: Partial<Record<GatewayType, string>> = {
  stoa: 'STOA',
  stoa_edge_mcp: 'STOA Edge-MCP',
  stoa_sidecar: 'STOA Sidecar',
  stoa_proxy: 'STOA Proxy',
  stoa_shadow: 'STOA Shadow',
  kong: 'Kong',
  gravitee: 'Gravitee',
  webmethods: 'webMethods',
  apigee: 'Apigee',
  aws_apigateway: 'AWS API GW',
};

function StatusBadge({ status }: { status: GatewayStatus }) {
  const cfg = statusConfig[status] || statusConfig.offline;
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${cfg.bg} ${cfg.text}`}
    >
      {cfg.label}
    </span>
  );
}

function ModeBadge({ mode }: { mode: string }) {
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-100 dark:bg-indigo-900/30 text-indigo-800 dark:text-indigo-400">
      {mode}
    </span>
  );
}

export function GatewaysPage() {
  const [gateways, setGateways] = useState<GatewayInstance[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState('');
  const [envFilter, setEnvFilter] = useState('');
  const [healthCheckingId, setHealthCheckingId] = useState<string | null>(null);

  const fetchGateways = useCallback(async () => {
    setIsLoading(true);
    const data = await gatewaysService.listGateways({
      gateway_type: typeFilter || undefined,
      environment: envFilter || undefined,
    });
    setGateways(data.items);
    setTotal(data.total);
    setIsLoading(false);
  }, [typeFilter, envFilter]);

  useEffect(() => {
    fetchGateways();
  }, [fetchGateways]);

  const handleHealthCheck = async (id: string) => {
    setHealthCheckingId(id);
    await gatewaysService.triggerHealthCheck(id);
    await fetchGateways();
    setHealthCheckingId(null);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Gateway Instances</h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            {total} gateway{total !== 1 ? 's' : ''} registered
          </p>
        </div>
        <button
          onClick={fetchGateways}
          className="inline-flex items-center px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-md text-sm font-medium text-neutral-700 dark:text-neutral-300 bg-white dark:bg-neutral-800 hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors"
        >
          <RefreshCw className={`w-4 h-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-3">
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-md text-sm bg-white dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300"
        >
          <option value="">All Types</option>
          <option value="stoa">STOA</option>
          <option value="kong">Kong</option>
          <option value="gravitee">Gravitee</option>
          <option value="webmethods">webMethods</option>
        </select>
        <select
          value={envFilter}
          onChange={(e) => setEnvFilter(e.target.value)}
          className="px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-md text-sm bg-white dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300"
        >
          <option value="">All Environments</option>
          <option value="dev">Development</option>
          <option value="staging">Staging</option>
          <option value="prod">Production</option>
        </select>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-neutral-400" />
        </div>
      ) : gateways.length === 0 ? (
        <div className="text-center py-12 bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700">
          <Server className="w-12 h-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-3" />
          <p className="text-neutral-500 dark:text-neutral-400 font-medium">
            No gateways registered
          </p>
          <p className="text-sm text-neutral-400 dark:text-neutral-500 mt-1">
            Gateway instances will appear here once registered via the Control Plane API.
          </p>
        </div>
      ) : (
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 overflow-hidden">
          <table className="min-w-full divide-y divide-neutral-200 dark:divide-neutral-700">
            <thead className="bg-neutral-50 dark:bg-neutral-900">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                  Name
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                  Type
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                  Environment
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                  Mode
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                  Last Health Check
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-200 dark:divide-neutral-700">
              {gateways.map((gw) => (
                <tr
                  key={gw.id}
                  className="hover:bg-neutral-50 dark:hover:bg-neutral-700/50 transition-colors"
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center">
                      <Server className="w-4 h-4 text-neutral-400 dark:text-neutral-500 mr-2" />
                      <div>
                        <p className="text-sm font-medium text-neutral-900 dark:text-white">
                          {gw.display_name}
                        </p>
                        <p className="text-xs text-neutral-500 dark:text-neutral-400">{gw.name}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm text-neutral-700 dark:text-neutral-300">
                    {gatewayTypeLabels[gw.gateway_type] || gw.gateway_type}
                  </td>
                  <td className="px-4 py-3 text-sm text-neutral-700 dark:text-neutral-300 capitalize">
                    {gw.environment}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={gw.status} />
                  </td>
                  <td className="px-4 py-3">
                    {gw.mode ? (
                      <ModeBadge mode={gw.mode} />
                    ) : (
                      <span className="text-neutral-400 dark:text-neutral-500 text-sm">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-sm text-neutral-500 dark:text-neutral-400">
                    {gw.last_health_check
                      ? new Date(gw.last_health_check).toLocaleString()
                      : 'Never'}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => handleHealthCheck(gw.id)}
                      disabled={healthCheckingId === gw.id}
                      className="inline-flex items-center px-2 py-1 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 rounded transition-colors disabled:opacity-50"
                      title="Trigger health check"
                    >
                      {healthCheckingId === gw.id ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Activity className="w-3.5 h-3.5" />
                      )}
                      <span className="ml-1">Check</span>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
