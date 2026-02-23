import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, RefreshCw, Server, CheckCircle, XCircle, AlertCircle, Clock } from 'lucide-react';
import { externalMcpServersService } from '../../services/externalMcpServersApi';
import { useAuth } from '../../contexts/AuthContext';
import { ExternalMCPServerModal } from './ExternalMCPServerModal';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import { EmptyState } from '@stoa/shared/components/EmptyState';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import type {
  ExternalMCPServer,
  ExternalMCPServerCreate,
  ExternalMCPServerUpdate,
  ExternalMCPHealthStatus,
} from '../../types';

const healthStatusConfig: Record<
  ExternalMCPHealthStatus,
  { color: string; icon: typeof CheckCircle; label: string }
> = {
  unknown: {
    color: 'bg-neutral-100 text-neutral-800 dark:bg-neutral-700 dark:text-neutral-300',
    icon: Clock,
    label: 'Unknown',
  },
  healthy: {
    color: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
    icon: CheckCircle,
    label: 'Healthy',
  },
  degraded: {
    color: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
    icon: AlertCircle,
    label: 'Degraded',
  },
  unhealthy: {
    color: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
    icon: XCircle,
    label: 'Unhealthy',
  },
};

const transportLabels: Record<string, string> = {
  sse: 'SSE',
  http: 'HTTP',
  websocket: 'WebSocket',
};

export function ExternalMCPServersList() {
  const navigate = useNavigate();
  const { isReady } = useAuth();
  const toast = useToastActions();
  const [confirm, ConfirmDialog] = useConfirm();
  const [servers, setServers] = useState<ExternalMCPServer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [testingServerId, setTestingServerId] = useState<string | null>(null);
  const [syncingServerId, setSyncingServerId] = useState<string | null>(null);

  useEffect(() => {
    if (isReady) {
      loadServers();
    }
  }, [isReady]);

  async function loadServers() {
    try {
      setLoading(true);
      const response = await externalMcpServersService.listServers();
      setServers(response.servers);
      setError(null);
    } catch (err: any) {
      console.error('Failed to load external MCP servers:', err);
      setError(err.message || 'Failed to load servers');
    } finally {
      setLoading(false);
    }
  }

  const handleCreate = useCallback(
    async (data: ExternalMCPServerCreate | ExternalMCPServerUpdate) => {
      try {
        await externalMcpServersService.createServer(data as ExternalMCPServerCreate);
        setShowCreateModal(false);
        await loadServers();
      } catch (err: any) {
        throw new Error(err.response?.data?.detail || err.message || 'Failed to create server');
      }
    },
    []
  );

  const handleTestConnection = useCallback(
    async (serverId: string) => {
      try {
        setTestingServerId(serverId);
        const result = await externalMcpServersService.testConnection(serverId);
        await loadServers(); // Refresh to get updated health status

        if (result.success) {
          toast.success(
            'Connection successful',
            `${result.tools_discovered !== undefined ? `Found ${result.tools_discovered} tools. ` : ''}Latency: ${result.latency_ms}ms`
          );
        } else {
          toast.error('Connection failed', result.error);
        }
      } catch (err: any) {
        toast.error('Test failed', err.message);
      } finally {
        setTestingServerId(null);
      }
    },
    [toast]
  );

  const handleSyncTools = useCallback(
    async (serverId: string) => {
      try {
        setSyncingServerId(serverId);
        const result = await externalMcpServersService.syncTools(serverId);
        await loadServers(); // Refresh to get updated tool count
        toast.success(
          'Tools synchronized',
          `Synced ${result.synced_count} tools${result.removed_count > 0 ? `. Removed ${result.removed_count} obsolete.` : ''}`
        );
      } catch (err: any) {
        toast.error('Sync failed', err.message);
      } finally {
        setSyncingServerId(null);
      }
    },
    [toast]
  );

  const handleDelete = useCallback(
    async (server: ExternalMCPServer) => {
      const confirmed = await confirm({
        title: 'Delete MCP Server',
        message: `Are you sure you want to delete "${server.display_name}"? This will also delete all synced tools.`,
        confirmLabel: 'Delete',
        variant: 'danger',
      });
      if (!confirmed) return;

      try {
        await externalMcpServersService.deleteServer(server.id);
        toast.success('Server deleted', `${server.display_name} has been removed`);
        await loadServers();
      } catch (err: any) {
        toast.error('Delete failed', err.message);
      }
    },
    [toast, confirm]
  );

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex justify-between items-center">
          <div className="h-8 w-64 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
          <div className="flex gap-3">
            <div className="h-10 w-24 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
            <div className="h-10 w-28 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
          </div>
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
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">
            External MCP Servers
          </h1>
          <p className="text-neutral-500 dark:text-neutral-400 mt-1">
            Register external MCP servers (Linear, GitHub, etc.) to proxy through STOA with
            governance
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={loadServers}
            className="flex items-center gap-2 px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 dark:text-neutral-300"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            <Plus className="h-4 w-4" />
            Add Server
          </button>
        </div>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg">
          {error}
          <button onClick={() => setError(null)} className="float-right font-bold">
            &times;
          </button>
        </div>
      )}

      {/* Servers Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {servers.length === 0 ? (
          <div className="col-span-full bg-white dark:bg-neutral-800 rounded-lg shadow">
            <EmptyState
              variant="servers"
              title="No external MCP servers registered"
              description="Register external MCP servers like Linear or GitHub to proxy through STOA with governance."
              action={{ label: 'Add Server', onClick: () => setShowCreateModal(true) }}
            />
          </div>
        ) : (
          servers.map((server) => {
            const healthConfig = healthStatusConfig[server.health_status];
            const HealthIcon = healthConfig.icon;

            return (
              <div
                key={server.id}
                className="bg-white dark:bg-neutral-800 rounded-lg shadow p-6 hover:shadow-md transition-shadow"
              >
                {/* Header */}
                <div className="flex justify-between items-start mb-4">
                  <div className="flex items-center gap-3">
                    {server.icon ? (
                      <img src={server.icon} alt="" className="w-10 h-10 rounded" />
                    ) : (
                      <div className="w-10 h-10 bg-neutral-100 dark:bg-neutral-700 rounded flex items-center justify-center">
                        <Server className="h-5 w-5 text-neutral-500 dark:text-neutral-400" />
                      </div>
                    )}
                    <div>
                      <h3 className="text-lg font-semibold text-neutral-900 dark:text-white">
                        {server.display_name}
                      </h3>
                      <p className="text-sm text-neutral-500 dark:text-neutral-400 font-mono">
                        {server.name}
                      </p>
                    </div>
                  </div>
                  <span
                    className={`px-2 py-1 text-xs font-medium rounded-full flex items-center gap-1 ${healthConfig.color}`}
                  >
                    <HealthIcon className="h-3 w-3" />
                    {healthConfig.label}
                  </span>
                </div>

                {/* Info */}
                <div className="space-y-2 text-sm text-neutral-600 dark:text-neutral-300 mb-4">
                  <div className="flex justify-between">
                    <span className="text-neutral-500 dark:text-neutral-400">Transport:</span>
                    <span className="font-mono">
                      {transportLabels[server.transport] || server.transport}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-neutral-500 dark:text-neutral-400">Auth:</span>
                    <span>{server.auth_type.replace('_', ' ')}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-neutral-500 dark:text-neutral-400">Tools:</span>
                    <span>{server.tools_count}</span>
                  </div>
                  {server.tool_prefix && (
                    <div className="flex justify-between">
                      <span className="text-neutral-500 dark:text-neutral-400">Prefix:</span>
                      <span className="font-mono">{server.tool_prefix}__</span>
                    </div>
                  )}
                  <div className="flex justify-between items-center">
                    <span className="text-neutral-500 dark:text-neutral-400">Status:</span>
                    <span
                      className={`px-2 py-0.5 text-xs rounded ${server.enabled ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400' : 'bg-neutral-100 text-neutral-800 dark:bg-neutral-700 dark:text-neutral-300'}`}
                    >
                      {server.enabled ? 'Enabled' : 'Disabled'}
                    </span>
                  </div>
                </div>

                {/* Sync Error */}
                {server.sync_error && (
                  <div
                    className="mb-4 p-2 bg-red-50 dark:bg-red-900/20 border border-red-100 dark:border-red-800 rounded text-xs text-red-700 dark:text-red-400 truncate"
                    title={server.sync_error}
                  >
                    {server.sync_error}
                  </div>
                )}

                {/* Actions */}
                <div className="flex gap-2 pt-4 border-t dark:border-neutral-700">
                  <button
                    onClick={() => handleTestConnection(server.id)}
                    disabled={testingServerId === server.id}
                    className="flex-1 px-3 py-2 text-sm border border-neutral-300 dark:border-neutral-600 rounded hover:bg-neutral-50 dark:hover:bg-neutral-700 dark:text-neutral-300 disabled:opacity-50"
                  >
                    {testingServerId === server.id ? 'Testing...' : 'Test'}
                  </button>
                  <button
                    onClick={() => handleSyncTools(server.id)}
                    disabled={syncingServerId === server.id}
                    className="flex-1 px-3 py-2 text-sm border border-neutral-300 dark:border-neutral-600 rounded hover:bg-neutral-50 dark:hover:bg-neutral-700 dark:text-neutral-300 disabled:opacity-50"
                  >
                    {syncingServerId === server.id ? 'Syncing...' : 'Sync'}
                  </button>
                  <button
                    onClick={() => navigate(`/external-mcp-servers/${server.id}`)}
                    className="flex-1 px-3 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
                  >
                    View
                  </button>
                </div>

                {/* Quick Delete (hover only) */}
                <button
                  onClick={() => handleDelete(server)}
                  className="mt-2 w-full px-3 py-1.5 text-xs text-red-600 hover:bg-red-50 rounded opacity-0 hover:opacity-100 transition-opacity"
                >
                  Delete Server
                </button>
              </div>
            );
          })
        )}
      </div>

      {/* Create Modal */}
      {showCreateModal && (
        <ExternalMCPServerModal onClose={() => setShowCreateModal(false)} onSubmit={handleCreate} />
      )}

      {ConfirmDialog}
    </div>
  );
}
