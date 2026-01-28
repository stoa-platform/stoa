// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
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
  Code,
} from 'lucide-react';
import { externalMcpServersService } from '../../services/externalMcpServersApi';
import { useAuth } from '../../contexts/AuthContext';
import { ExternalMCPServerModal } from './ExternalMCPServerModal';
import type {
  ExternalMCPServerDetail as ServerDetail,
  ExternalMCPServerUpdate,
  ExternalMCPHealthStatus,
} from '../../types';

const healthStatusConfig: Record<ExternalMCPHealthStatus, { color: string; bgColor: string; icon: typeof CheckCircle; label: string }> = {
  unknown: { color: 'text-gray-600', bgColor: 'bg-gray-100', icon: Clock, label: 'Unknown' },
  healthy: { color: 'text-green-600', bgColor: 'bg-green-100', icon: CheckCircle, label: 'Healthy' },
  degraded: { color: 'text-yellow-600', bgColor: 'bg-yellow-100', icon: AlertCircle, label: 'Degraded' },
  unhealthy: { color: 'text-red-600', bgColor: 'bg-red-100', icon: XCircle, label: 'Unhealthy' },
};

export function ExternalMCPServerDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { isReady } = useAuth();

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

  const handleUpdate = useCallback(async (data: ExternalMCPServerUpdate) => {
    if (!id) return;

    try {
      await externalMcpServersService.updateServer(id, data);
      setShowEditModal(false);
      await loadServer();
    } catch (err: any) {
      throw new Error(err.response?.data?.detail || err.message || 'Failed to update server');
    }
  }, [id]);

  const handleTestConnection = useCallback(async () => {
    if (!id) return;

    try {
      setTesting(true);
      const result = await externalMcpServersService.testConnection(id);
      await loadServer();

      if (result.success) {
        alert(`Connection successful! ${result.tools_discovered !== undefined ? `Found ${result.tools_discovered} tools.` : ''} Latency: ${result.latency_ms}ms`);
      } else {
        alert(`Connection failed: ${result.error}`);
      }
    } catch (err: any) {
      alert(`Test failed: ${err.message}`);
    } finally {
      setTesting(false);
    }
  }, [id]);

  const handleSyncTools = useCallback(async () => {
    if (!id) return;

    try {
      setSyncing(true);
      const result = await externalMcpServersService.syncTools(id);
      await loadServer();
      alert(`Synced ${result.synced_count} tools. ${result.removed_count > 0 ? `Removed ${result.removed_count} obsolete tools.` : ''}`);
    } catch (err: any) {
      alert(`Sync failed: ${err.message}`);
    } finally {
      setSyncing(false);
    }
  }, [id]);

  const handleToggleTool = useCallback(async (toolId: string, enabled: boolean) => {
    if (!id) return;

    try {
      setTogglingTool(toolId);
      await externalMcpServersService.updateTool(id, toolId, { enabled });
      await loadServer();
    } catch (err: any) {
      alert(`Failed to update tool: ${err.message}`);
    } finally {
      setTogglingTool(null);
    }
  }, [id]);

  const handleDelete = useCallback(async () => {
    if (!id || !server) return;

    if (!confirm(`Are you sure you want to delete "${server.display_name}"? This will also delete all synced tools and cannot be undone.`)) {
      return;
    }

    try {
      await externalMcpServersService.deleteServer(id);
      navigate('/external-mcp-servers');
    } catch (err: any) {
      alert(`Delete failed: ${err.message}`);
    }
  }, [id, server, navigate]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (error || !server) {
    return (
      <div className="space-y-4">
        <button
          onClick={() => navigate('/external-mcp-servers')}
          className="flex items-center gap-2 text-gray-600 hover:text-gray-900"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Servers
        </button>
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
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
            className="flex items-center gap-2 text-gray-600 hover:text-gray-900"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div className="flex items-center gap-3">
            {server.icon ? (
              <img src={server.icon} alt="" className="w-12 h-12 rounded-lg" />
            ) : (
              <div className="w-12 h-12 bg-gray-100 rounded-lg flex items-center justify-center">
                <Server className="h-6 w-6 text-gray-500" />
              </div>
            )}
            <div>
              <h1 className="text-2xl font-bold text-gray-900">{server.display_name}</h1>
              <p className="text-sm text-gray-500 font-mono">{server.name}</p>
            </div>
          </div>
        </div>

        <div className="flex gap-3">
          <button
            onClick={handleTestConnection}
            disabled={testing}
            className="flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
          >
            <Play className="h-4 w-4" />
            {testing ? 'Testing...' : 'Test Connection'}
          </button>
          <button
            onClick={handleSyncTools}
            disabled={syncing}
            className="flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
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
      <div className="bg-white rounded-lg shadow p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {/* Health Status */}
          <div>
            <label className="block text-sm font-medium text-gray-500 mb-1">Health Status</label>
            <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full ${healthConfig.bgColor}`}>
              <HealthIcon className={`h-4 w-4 ${healthConfig.color}`} />
              <span className={`text-sm font-medium ${healthConfig.color}`}>{healthConfig.label}</span>
            </div>
            {server.last_health_check && (
              <p className="text-xs text-gray-500 mt-1">
                Last checked: {new Date(server.last_health_check).toLocaleString()}
              </p>
            )}
          </div>

          {/* Base URL */}
          <div>
            <label className="block text-sm font-medium text-gray-500 mb-1">Base URL</label>
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
            <label className="block text-sm font-medium text-gray-500 mb-1">Transport / Auth</label>
            <p className="text-sm text-gray-900">
              {server.transport.toUpperCase()} / {server.auth_type.replace('_', ' ')}
            </p>
          </div>

          {/* Status */}
          <div>
            <label className="block text-sm font-medium text-gray-500 mb-1">Status</label>
            <span className={`inline-flex px-2 py-1 text-xs rounded-full ${server.enabled ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'}`}>
              {server.enabled ? 'Enabled' : 'Disabled'}
            </span>
          </div>
        </div>

        {/* Description */}
        {server.description && (
          <div className="mt-6 pt-6 border-t">
            <label className="block text-sm font-medium text-gray-500 mb-1">Description</label>
            <p className="text-sm text-gray-700">{server.description}</p>
          </div>
        )}

        {/* Sync Error */}
        {server.sync_error && (
          <div className="mt-6 p-4 bg-red-50 border border-red-100 rounded-lg">
            <h4 className="text-sm font-medium text-red-800 mb-1">Sync Error</h4>
            <p className="text-sm text-red-700">{server.sync_error}</p>
          </div>
        )}

        {/* Metadata */}
        <div className="mt-6 pt-6 border-t grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <span className="text-gray-500">Tool Prefix:</span>{' '}
            <code className="bg-gray-100 px-1 rounded">{server.tool_prefix || server.name}__</code>
          </div>
          <div>
            <span className="text-gray-500">Tools Count:</span> {server.tools.length}
          </div>
          <div>
            <span className="text-gray-500">Last Synced:</span>{' '}
            {server.last_sync_at ? new Date(server.last_sync_at).toLocaleString() : 'Never'}
          </div>
          <div>
            <span className="text-gray-500">Created:</span>{' '}
            {new Date(server.created_at).toLocaleString()}
          </div>
        </div>
      </div>

      {/* Tools List */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b flex justify-between items-center">
          <h2 className="text-lg font-semibold text-gray-900">
            Tools ({server.tools.length})
          </h2>
          <p className="text-sm text-gray-500">
            Enable/disable tools to control which are exposed via STOA
          </p>
        </div>

        {server.tools.length === 0 ? (
          <div className="p-12 text-center text-gray-500">
            <Code className="h-12 w-12 mx-auto text-gray-400" />
            <p className="mt-2">No tools synced yet</p>
            <p className="text-sm text-gray-400">Click "Sync Tools" to discover available tools</p>
          </div>
        ) : (
          <div className="divide-y">
            {server.tools.map((tool) => (
              <div key={tool.id} className="px-6 py-4 flex items-center justify-between hover:bg-gray-50">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-medium text-gray-900 truncate">
                      {tool.display_name || tool.name}
                    </h3>
                    <code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded text-gray-600">
                      {tool.namespaced_name}
                    </code>
                  </div>
                  {tool.description && (
                    <p className="text-sm text-gray-500 truncate mt-1">{tool.description}</p>
                  )}
                  <p className="text-xs text-gray-400 mt-1">
                    Synced: {new Date(tool.synced_at).toLocaleString()}
                  </p>
                </div>

                <div className="flex items-center gap-4 ml-4">
                  {/* Input Schema Preview */}
                  {tool.input_schema && (
                    <button
                      onClick={() => alert(JSON.stringify(tool.input_schema, null, 2))}
                      className="text-xs text-gray-500 hover:text-gray-700"
                    >
                      View Schema
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
                    <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
                    <span className="ml-2 text-sm text-gray-600">
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
      <div className="bg-white rounded-lg shadow border border-red-200">
        <div className="px-6 py-4">
          <h2 className="text-lg font-semibold text-red-600">Danger Zone</h2>
          <p className="text-sm text-gray-500 mt-1">
            Permanently delete this external MCP server and all its synced tools.
          </p>
          <button
            onClick={handleDelete}
            className="mt-4 flex items-center gap-2 px-4 py-2 border border-red-300 text-red-600 rounded-lg hover:bg-red-50"
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
    </div>
  );
}
