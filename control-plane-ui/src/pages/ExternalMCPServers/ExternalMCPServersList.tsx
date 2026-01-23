import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, RefreshCw, Server, CheckCircle, XCircle, AlertCircle, Clock } from 'lucide-react';
import { externalMcpServersService } from '../../services/externalMcpServersApi';
import { useAuth } from '../../contexts/AuthContext';
import { ExternalMCPServerModal } from './ExternalMCPServerModal';
import type { ExternalMCPServer, ExternalMCPServerCreate, ExternalMCPHealthStatus } from '../../types';

const healthStatusConfig: Record<ExternalMCPHealthStatus, { color: string; icon: typeof CheckCircle; label: string }> = {
  unknown: { color: 'bg-gray-100 text-gray-800', icon: Clock, label: 'Unknown' },
  healthy: { color: 'bg-green-100 text-green-800', icon: CheckCircle, label: 'Healthy' },
  degraded: { color: 'bg-yellow-100 text-yellow-800', icon: AlertCircle, label: 'Degraded' },
  unhealthy: { color: 'bg-red-100 text-red-800', icon: XCircle, label: 'Unhealthy' },
};

const transportLabels: Record<string, string> = {
  sse: 'SSE',
  http: 'HTTP',
  websocket: 'WebSocket',
};

export function ExternalMCPServersList() {
  const navigate = useNavigate();
  const { isReady } = useAuth();
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

  const handleCreate = useCallback(async (data: ExternalMCPServerCreate) => {
    try {
      await externalMcpServersService.createServer(data);
      setShowCreateModal(false);
      await loadServers();
    } catch (err: any) {
      throw new Error(err.response?.data?.detail || err.message || 'Failed to create server');
    }
  }, []);

  const handleTestConnection = useCallback(async (serverId: string) => {
    try {
      setTestingServerId(serverId);
      const result = await externalMcpServersService.testConnection(serverId);
      await loadServers(); // Refresh to get updated health status

      if (result.success) {
        alert(`Connection successful! ${result.tools_discovered !== undefined ? `Found ${result.tools_discovered} tools.` : ''} Latency: ${result.latency_ms}ms`);
      } else {
        alert(`Connection failed: ${result.error}`);
      }
    } catch (err: any) {
      alert(`Test failed: ${err.message}`);
    } finally {
      setTestingServerId(null);
    }
  }, []);

  const handleSyncTools = useCallback(async (serverId: string) => {
    try {
      setSyncingServerId(serverId);
      const result = await externalMcpServersService.syncTools(serverId);
      await loadServers(); // Refresh to get updated tool count
      alert(`Synced ${result.synced_count} tools. ${result.removed_count > 0 ? `Removed ${result.removed_count} obsolete tools.` : ''}`);
    } catch (err: any) {
      alert(`Sync failed: ${err.message}`);
    } finally {
      setSyncingServerId(null);
    }
  }, []);

  const handleDelete = useCallback(async (server: ExternalMCPServer) => {
    if (!confirm(`Are you sure you want to delete "${server.display_name}"? This will also delete all synced tools.`)) {
      return;
    }

    try {
      await externalMcpServersService.deleteServer(server.id);
      await loadServers();
    } catch (err: any) {
      alert(`Delete failed: ${err.message}`);
    }
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">External MCP Servers</h1>
          <p className="text-gray-500 mt-1">
            Register external MCP servers (Linear, GitHub, etc.) to proxy through STOA with governance
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={loadServers}
            className="flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
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
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error}
          <button onClick={() => setError(null)} className="float-right font-bold">&times;</button>
        </div>
      )}

      {/* Servers Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {servers.length === 0 ? (
          <div className="col-span-full text-center py-12 text-gray-500 bg-white rounded-lg shadow">
            <Server className="mx-auto h-12 w-12 text-gray-400" />
            <p className="mt-2">No external MCP servers registered</p>
            <p className="text-sm text-gray-400 mt-1">
              Click "Add Server" to register an external MCP server like Linear or GitHub
            </p>
          </div>
        ) : (
          servers.map((server) => {
            const healthConfig = healthStatusConfig[server.health_status];
            const HealthIcon = healthConfig.icon;

            return (
              <div
                key={server.id}
                className="bg-white rounded-lg shadow p-6 hover:shadow-md transition-shadow"
              >
                {/* Header */}
                <div className="flex justify-between items-start mb-4">
                  <div className="flex items-center gap-3">
                    {server.icon ? (
                      <img src={server.icon} alt="" className="w-10 h-10 rounded" />
                    ) : (
                      <div className="w-10 h-10 bg-gray-100 rounded flex items-center justify-center">
                        <Server className="h-5 w-5 text-gray-500" />
                      </div>
                    )}
                    <div>
                      <h3 className="text-lg font-semibold text-gray-900">{server.display_name}</h3>
                      <p className="text-sm text-gray-500 font-mono">{server.name}</p>
                    </div>
                  </div>
                  <span className={`px-2 py-1 text-xs font-medium rounded-full flex items-center gap-1 ${healthConfig.color}`}>
                    <HealthIcon className="h-3 w-3" />
                    {healthConfig.label}
                  </span>
                </div>

                {/* Info */}
                <div className="space-y-2 text-sm text-gray-600 mb-4">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Transport:</span>
                    <span className="font-mono">{transportLabels[server.transport] || server.transport}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Auth:</span>
                    <span>{server.auth_type.replace('_', ' ')}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Tools:</span>
                    <span>{server.tools_count}</span>
                  </div>
                  {server.tool_prefix && (
                    <div className="flex justify-between">
                      <span className="text-gray-500">Prefix:</span>
                      <span className="font-mono">{server.tool_prefix}__</span>
                    </div>
                  )}
                  <div className="flex justify-between items-center">
                    <span className="text-gray-500">Status:</span>
                    <span className={`px-2 py-0.5 text-xs rounded ${server.enabled ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'}`}>
                      {server.enabled ? 'Enabled' : 'Disabled'}
                    </span>
                  </div>
                </div>

                {/* Sync Error */}
                {server.sync_error && (
                  <div className="mb-4 p-2 bg-red-50 border border-red-100 rounded text-xs text-red-700 truncate" title={server.sync_error}>
                    {server.sync_error}
                  </div>
                )}

                {/* Actions */}
                <div className="flex gap-2 pt-4 border-t">
                  <button
                    onClick={() => handleTestConnection(server.id)}
                    disabled={testingServerId === server.id}
                    className="flex-1 px-3 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50"
                  >
                    {testingServerId === server.id ? 'Testing...' : 'Test'}
                  </button>
                  <button
                    onClick={() => handleSyncTools(server.id)}
                    disabled={syncingServerId === server.id}
                    className="flex-1 px-3 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50"
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
        <ExternalMCPServerModal
          onClose={() => setShowCreateModal(false)}
          onSubmit={handleCreate}
        />
      )}
    </div>
  );
}
