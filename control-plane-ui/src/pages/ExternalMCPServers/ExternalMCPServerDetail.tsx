import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  RefreshCw,
  Server,
  CheckCircle,
  XCircle,
  AlertCircle,
  Clock,
  Settings,
  Trash2,
  Play,
  ExternalLink,
} from 'lucide-react';
import { externalMcpServersService } from '../../services/externalMcpServersApi';
import { useAuth } from '../../contexts/AuthContext';
import { ExternalMCPServerModal } from './ExternalMCPServerModal';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import { EmptyState } from '@stoa/shared/components/EmptyState';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import type {
  ExternalMCPServerDetail as ServerDetail,
  ExternalMCPServerUpdate,
  ExternalMCPHealthStatus,
} from '../../types';

const healthStatusConfig: Record<
  ExternalMCPHealthStatus,
  { color: string; bgColor: string; icon: typeof CheckCircle; label: string }
> = {
  unknown: {
    color: 'text-neutral-600 dark:text-neutral-400',
    bgColor: 'bg-neutral-100 dark:bg-neutral-700',
    icon: Clock,
    label: 'Unknown',
  },
  healthy: {
    color: 'text-green-600 dark:text-green-400',
    bgColor: 'bg-green-100 dark:bg-green-900/30',
    icon: CheckCircle,
    label: 'Healthy',
  },
  degraded: {
    color: 'text-yellow-600 dark:text-yellow-400',
    bgColor: 'bg-yellow-100 dark:bg-yellow-900/30',
    icon: AlertCircle,
    label: 'Degraded',
  },
  unhealthy: {
    color: 'text-red-600 dark:text-red-400',
    bgColor: 'bg-red-100 dark:bg-red-900/30',
    icon: XCircle,
    label: 'Unhealthy',
  },
};

export function ExternalMCPServerDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { isReady } = useAuth();
  const toast = useToastActions();
  const [confirm, ConfirmDialog] = useConfirm();

  const [server, setServer] = useState<ServerDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showEditModal, setShowEditModal] = useState(false);
  const [testing, setTesting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [togglingTool, setTogglingTool] = useState<string | null>(null);

  useEffect(() => {
    if (isReady && id) {
      loadServer();
    }
  }, [isReady, id]);

  async function loadServer() {
    if (!id) return;

    try {
      setLoading(true);
      const data = await externalMcpServersService.getServer(id);
      setServer(data);
      setError(null);
    } catch (err: any) {
      console.error('Failed to load server:', err);
      setError(err.message || 'Failed to load server');
    } finally {
      setLoading(false);
    }
  }

  const handleUpdate = useCallback(
    async (data: ExternalMCPServerUpdate) => {
      if (!id) return;

      try {
        await externalMcpServersService.updateServer(id, data);
        setShowEditModal(false);
        await loadServer();
      } catch (err: any) {
        throw new Error(err.response?.data?.detail || err.message || 'Failed to update server');
      }
    },
    [id]
  );

  const handleTestConnection = useCallback(async () => {
    if (!id) return;

    try {
      setTesting(true);
      const result = await externalMcpServersService.testConnection(id);
      await loadServer();

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
      setTesting(false);
    }
  }, [id, toast]);

  const handleSyncTools = useCallback(async () => {
    if (!id) return;

    try {
      setSyncing(true);
      const result = await externalMcpServersService.syncTools(id);
      await loadServer();
      toast.success(
        'Tools synchronized',
        `Synced ${result.synced_count} tools${result.removed_count > 0 ? `. Removed ${result.removed_count} obsolete.` : ''}`
      );
    } catch (err: any) {
      toast.error('Sync failed', err.message);
    } finally {
      setSyncing(false);
    }
  }, [id, toast]);

  const handleToggleTool = useCallback(
    async (toolId: string, enabled: boolean) => {
      if (!id) return;

      try {
        setTogglingTool(toolId);
        await externalMcpServersService.updateTool(id, toolId, { enabled });
        await loadServer();
        toast.success(enabled ? 'Tool enabled' : 'Tool disabled');
      } catch (err: any) {
        toast.error('Failed to update tool', err.message);
      } finally {
        setTogglingTool(null);
      }
    },
    [id, toast]
  );

  const handleDelete = useCallback(async () => {
    if (!id || !server) return;

    const confirmed = await confirm({
      title: 'Delete MCP Server',
      message: `Are you sure you want to delete "${server.display_name}"? This will also delete all synced tools and cannot be undone.`,
      confirmLabel: 'Delete',
      variant: 'danger',
    });
    if (!confirmed) return;

    try {
      await externalMcpServersService.deleteServer(id);
      toast.success('Server deleted', `${server.display_name} has been removed`);
      navigate('/external-mcp-servers');
    } catch (err: any) {
      toast.error('Delete failed', err.message);
    }
  }, [id, server, navigate, toast, confirm]);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-4">
          <div className="h-6 w-6 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
          <div className="h-12 w-12 bg-neutral-200 dark:bg-neutral-700 rounded-lg animate-pulse" />
          <div className="space-y-2">
            <div className="h-6 w-48 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
            <div className="h-4 w-32 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
          </div>
        </div>
        <CardSkeleton className="h-48" />
        <CardSkeleton className="h-64" />
      </div>
    );
  }

  if (error || !server) {
    return (
      <div className="space-y-4">
        <button
          onClick={() => navigate('/external-mcp-servers')}
          className="flex items-center gap-2 text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-white"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Servers
        </button>
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg">
          {error || 'Server not found'}
        </div>
      </div>
    );
  }

  const healthConfig = healthStatusConfig[server.health_status];
  const HealthIcon = healthConfig.icon;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/external-mcp-servers')}
            className="flex items-center gap-2 text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-white"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div className="flex items-center gap-3">
            {server.icon ? (
              <img src={server.icon} alt="" className="w-12 h-12 rounded-lg" />
            ) : (
              <div className="w-12 h-12 bg-neutral-100 dark:bg-neutral-700 rounded-lg flex items-center justify-center">
                <Server className="h-6 w-6 text-neutral-500 dark:text-neutral-400" />
              </div>
            )}
            <div>
              <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">
                {server.display_name}
              </h1>
              <p className="text-sm text-neutral-500 dark:text-neutral-400 font-mono">
                {server.name}
              </p>
            </div>
          </div>
        </div>

        <div className="flex gap-3">
          <button
            onClick={handleTestConnection}
            disabled={testing}
            className="flex items-center gap-2 px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 dark:text-neutral-300 disabled:opacity-50"
          >
            <Play className="h-4 w-4" />
            {testing ? 'Testing...' : 'Test Connection'}
          </button>
          <button
            onClick={handleSyncTools}
            disabled={syncing}
            className="flex items-center gap-2 px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 dark:text-neutral-300 disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${syncing ? 'animate-spin' : ''}`} />
            {syncing ? 'Syncing...' : 'Sync Tools'}
          </button>
          <button
            onClick={() => setShowEditModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            <Settings className="h-4 w-4" />
            Edit
          </button>
        </div>
      </div>

      {/* Server Info Card */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {/* Health Status */}
          <div>
            <label className="block text-sm font-medium text-neutral-500 dark:text-neutral-400 mb-1">
              Health Status
            </label>
            <div
              className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full ${healthConfig.bgColor}`}
            >
              <HealthIcon className={`h-4 w-4 ${healthConfig.color}`} />
              <span className={`text-sm font-medium ${healthConfig.color}`}>
                {healthConfig.label}
              </span>
            </div>
            {server.last_health_check && (
              <p className="text-xs text-neutral-500 dark:text-neutral-500 mt-1">
                Last checked: {new Date(server.last_health_check).toLocaleString()}
              </p>
            )}
          </div>

          {/* Base URL */}
          <div>
            <label className="block text-sm font-medium text-neutral-500 dark:text-neutral-400 mb-1">
              Base URL
            </label>
            <a
              href={server.base_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-blue-600 hover:text-blue-800 text-sm"
            >
              {server.base_url}
              <ExternalLink className="h-3 w-3" />
            </a>
          </div>

          {/* Transport & Auth */}
          <div>
            <label className="block text-sm font-medium text-neutral-500 dark:text-neutral-400 mb-1">
              Transport / Auth
            </label>
            <p className="text-sm text-neutral-900 dark:text-white">
              {server.transport.toUpperCase()} / {server.auth_type.replace('_', ' ')}
            </p>
          </div>

          {/* Status */}
          <div>
            <label className="block text-sm font-medium text-neutral-500 dark:text-neutral-400 mb-1">
              Status
            </label>
            <span
              className={`inline-flex px-2 py-1 text-xs rounded-full ${server.enabled ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400' : 'bg-neutral-100 text-neutral-800 dark:bg-neutral-700 dark:text-neutral-300'}`}
            >
              {server.enabled ? 'Enabled' : 'Disabled'}
            </span>
          </div>
        </div>

        {/* Description */}
        {server.description && (
          <div className="mt-6 pt-6 border-t dark:border-neutral-700">
            <label className="block text-sm font-medium text-neutral-500 dark:text-neutral-400 mb-1">
              Description
            </label>
            <p className="text-sm text-neutral-700 dark:text-neutral-300">{server.description}</p>
          </div>
        )}

        {/* Sync Error */}
        {server.sync_error && (
          <div className="mt-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-100 dark:border-red-800 rounded-lg">
            <h4 className="text-sm font-medium text-red-800 dark:text-red-400 mb-1">Sync Error</h4>
            <p className="text-sm text-red-700 dark:text-red-400">{server.sync_error}</p>
          </div>
        )}

        {/* Metadata */}
        <div className="mt-6 pt-6 border-t dark:border-neutral-700 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm dark:text-neutral-300">
          <div>
            <span className="text-neutral-500 dark:text-neutral-400">Tool Prefix:</span>{' '}
            <code className="bg-neutral-100 dark:bg-neutral-700 px-1 rounded">
              {server.tool_prefix || server.name}__
            </code>
          </div>
          <div>
            <span className="text-neutral-500 dark:text-neutral-400">Tools Count:</span>{' '}
            {server.tools.length}
          </div>
          <div>
            <span className="text-neutral-500 dark:text-neutral-400">Last Synced:</span>{' '}
            {server.last_sync_at ? new Date(server.last_sync_at).toLocaleString() : 'Never'}
          </div>
          <div>
            <span className="text-neutral-500 dark:text-neutral-400">Created:</span>{' '}
            {new Date(server.created_at).toLocaleString()}
          </div>
        </div>
      </div>

      {/* Tools List */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow">
        <div className="px-6 py-4 border-b dark:border-neutral-700 flex justify-between items-center">
          <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">
            Tools ({server.tools.length})
          </h2>
          <p className="text-sm text-neutral-500 dark:text-neutral-400">
            Enable/disable tools to control which are exposed via STOA
          </p>
        </div>

        {server.tools.length === 0 ? (
          <EmptyState
            variant="tools"
            title="No tools synced yet"
            description="Click 'Sync Tools' to discover available tools from this server."
            action={{ label: 'Sync Tools', onClick: handleSyncTools }}
          />
        ) : (
          <div className="divide-y dark:divide-neutral-700">
            {server.tools.map((tool) => (
              <div
                key={tool.id}
                className="px-6 py-4 flex items-center justify-between hover:bg-neutral-50 dark:hover:bg-neutral-700"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-medium text-neutral-900 dark:text-white truncate">
                      {tool.display_name || tool.name}
                    </h3>
                    <code className="text-xs bg-neutral-100 dark:bg-neutral-700 px-1.5 py-0.5 rounded text-neutral-600 dark:text-neutral-400">
                      {tool.namespaced_name}
                    </code>
                  </div>
                  {tool.description && (
                    <p className="text-sm text-neutral-500 dark:text-neutral-400 truncate mt-1">
                      {tool.description}
                    </p>
                  )}
                  <p className="text-xs text-neutral-400 dark:text-neutral-500 mt-1">
                    Synced: {new Date(tool.synced_at).toLocaleString()}
                  </p>
                </div>

                <div className="flex items-center gap-4 ml-4">
                  {/* Input Schema Preview */}
                  {tool.input_schema && (
                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(JSON.stringify(tool.input_schema, null, 2));
                        toast.info('Schema copied', 'Input schema copied to clipboard');
                      }}
                      className="text-xs text-neutral-500 hover:text-neutral-700 dark:text-neutral-400 dark:hover:text-neutral-200"
                    >
                      Copy Schema
                    </button>
                  )}

                  {/* Enable/Disable Toggle */}
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={tool.enabled}
                      onChange={(e) => handleToggleTool(tool.id, e.target.checked)}
                      disabled={togglingTool === tool.id}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-neutral-200 dark:bg-neutral-600 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 dark:peer-focus:ring-blue-800 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-neutral-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
                    <span className="ml-2 text-sm text-neutral-600 dark:text-neutral-400">
                      {togglingTool === tool.id ? '...' : tool.enabled ? 'Enabled' : 'Disabled'}
                    </span>
                  </label>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Danger Zone */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow border border-red-200 dark:border-red-800">
        <div className="px-6 py-4">
          <h2 className="text-lg font-semibold text-red-600 dark:text-red-400">Danger Zone</h2>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            Permanently delete this external MCP server and all its synced tools.
          </p>
          <button
            onClick={handleDelete}
            className="mt-4 flex items-center gap-2 px-4 py-2 border border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20"
          >
            <Trash2 className="h-4 w-4" />
            Delete Server
          </button>
        </div>
      </div>

      {/* Edit Modal */}
      {showEditModal && (
        <ExternalMCPServerModal
          server={server}
          onClose={() => setShowEditModal(false)}
          onSubmit={handleUpdate}
        />
      )}

      {ConfirmDialog}
    </div>
  );
}
