/**
 * My MCP Servers Page (CAB-1319)
 *
 * Self-service management page for tenant-owned external MCP servers.
 * Allows tenant-admins to register, update, delete, test, and sync their MCP servers.
 * Devops users can view and test. Viewers can only view.
 */

import { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Search,
  Plus,
  RefreshCw,
  AlertCircle,
  Server,
  Wrench,
  Trash2,
  Zap,
  CheckCircle,
  XCircle,
  Clock,
  AlertTriangle,
  ToggleLeft,
  ToggleRight,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import {
  tenantMcpServersService,
  type TenantMCPServer,
  type TenantMCPServerDetail,
} from '../../services/tenantMcpServers';

const healthColors: Record<string, { bg: string; text: string; icon: React.ElementType }> = {
  healthy: {
    bg: 'bg-green-100 dark:bg-green-900/30',
    text: 'text-green-700 dark:text-green-400',
    icon: CheckCircle,
  },
  degraded: {
    bg: 'bg-amber-100 dark:bg-amber-900/30',
    text: 'text-amber-700 dark:text-amber-400',
    icon: AlertTriangle,
  },
  unhealthy: {
    bg: 'bg-red-100 dark:bg-red-900/30',
    text: 'text-red-700 dark:text-red-400',
    icon: XCircle,
  },
  unknown: {
    bg: 'bg-neutral-100 dark:bg-neutral-700',
    text: 'text-neutral-500 dark:text-neutral-400',
    icon: Clock,
  },
};

export function MyMCPServersPage() {
  const { user, isAuthenticated, accessToken } = useAuth();
  const [searchQuery, setSearchQuery] = useState('');
  const [servers, setServers] = useState<TenantMCPServer[]>([]);
  const [expandedServer, setExpandedServer] = useState<string | null>(null);
  const [serverDetail, setServerDetail] = useState<TenantMCPServerDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const tenantId = user?.tenant_id;

  const isWriteUser = useMemo(() => {
    const roles = user?.roles || [];
    return roles.includes('cpi-admin') || roles.includes('tenant-admin');
  }, [user?.roles]);

  const canTestConnection = useMemo(() => {
    const roles = user?.roles || [];
    return (
      roles.includes('cpi-admin') || roles.includes('tenant-admin') || roles.includes('devops')
    );
  }, [user?.roles]);

  // Load servers
  useEffect(() => {
    if (!isAuthenticated || !accessToken || !tenantId) return;

    async function loadServers() {
      setIsLoading(true);
      setError(null);
      try {
        const result = await tenantMcpServersService.list(tenantId!);
        setServers(result.servers);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load servers');
      } finally {
        setIsLoading(false);
      }
    }

    loadServers();
  }, [isAuthenticated, accessToken, tenantId, refreshKey]);

  const filteredServers = useMemo(() => {
    if (!searchQuery.trim()) return servers;
    const query = searchQuery.toLowerCase();
    return servers.filter(
      (s) =>
        s.display_name.toLowerCase().includes(query) ||
        s.name.toLowerCase().includes(query) ||
        (s.description && s.description.toLowerCase().includes(query))
    );
  }, [servers, searchQuery]);

  const handleRefresh = () => setRefreshKey((k) => k + 1);

  const handleExpandServer = useCallback(
    async (serverId: string) => {
      if (expandedServer === serverId) {
        setExpandedServer(null);
        setServerDetail(null);
        return;
      }
      if (!tenantId) return;

      setExpandedServer(serverId);
      try {
        const detail = await tenantMcpServersService.get(tenantId, serverId);
        setServerDetail(detail);
      } catch {
        setServerDetail(null);
      }
    },
    [expandedServer, tenantId]
  );

  const handleTestConnection = useCallback(
    async (serverId: string) => {
      if (!tenantId) return;
      setActionLoading(`test-${serverId}`);
      try {
        const result = await tenantMcpServersService.testConnection(tenantId, serverId);
        if (result.success) {
          handleRefresh();
        } else {
          setError(`Test connection failed: ${result.error}`);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Test connection failed');
      } finally {
        setActionLoading(null);
      }
    },
    [tenantId]
  );

  const handleSyncTools = useCallback(
    async (serverId: string) => {
      if (!tenantId) return;
      setActionLoading(`sync-${serverId}`);
      try {
        await tenantMcpServersService.syncTools(tenantId, serverId);
        handleRefresh();
        // Refresh detail if expanded
        if (expandedServer === serverId) {
          const detail = await tenantMcpServersService.get(tenantId, serverId);
          setServerDetail(detail);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Sync tools failed');
      } finally {
        setActionLoading(null);
      }
    },
    [tenantId, expandedServer]
  );

  const handleDeleteServer = useCallback(
    async (serverId: string, displayName: string) => {
      if (!tenantId) return;
      if (!window.confirm(`Delete server "${displayName}"? This cannot be undone.`)) return;

      setActionLoading(`delete-${serverId}`);
      try {
        await tenantMcpServersService.delete(tenantId, serverId);
        setServers((prev) => prev.filter((s) => s.id !== serverId));
        if (expandedServer === serverId) {
          setExpandedServer(null);
          setServerDetail(null);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Delete failed');
      } finally {
        setActionLoading(null);
      }
    },
    [tenantId, expandedServer]
  );

  const handleToggleTool = useCallback(
    async (serverId: string, toolId: string, enabled: boolean) => {
      if (!tenantId) return;
      setActionLoading(`toggle-${toolId}`);
      try {
        await tenantMcpServersService.toggleTool(tenantId, serverId, toolId, enabled);
        // Refresh detail
        if (expandedServer === serverId) {
          const detail = await tenantMcpServersService.get(tenantId, serverId);
          setServerDetail(detail);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Toggle failed');
      } finally {
        setActionLoading(null);
      }
    },
    [tenantId, expandedServer]
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">My MCP Servers</h1>
          <p className="text-neutral-500 dark:text-neutral-400 mt-1">
            Register and manage your external MCP server integrations
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleRefresh}
            disabled={isLoading}
            className="inline-flex items-center gap-2 px-4 py-2 border border-neutral-300 dark:border-neutral-600 text-neutral-700 dark:text-neutral-200 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          {isWriteUser && (
            <button
              data-testid="register-server-btn"
              className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
            >
              <Plus className="h-4 w-4" />
              Register Server
            </button>
          )}
        </div>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-neutral-400" />
        <input
          type="text"
          placeholder="Search servers..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full pl-10 pr-4 py-2 border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white placeholder-neutral-500 dark:placeholder-neutral-400 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
        />
      </div>

      {/* Error banner */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-red-500 dark:text-red-400 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
            </div>
            <button
              onClick={() => setError(null)}
              className="text-red-400 hover:text-red-600 dark:hover:text-red-300"
            >
              <XCircle className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="grid grid-cols-1 gap-4">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-5 animate-pulse"
            >
              <div className="h-5 bg-neutral-200 dark:bg-neutral-700 rounded w-1/3 mb-3" />
              <div className="h-4 bg-neutral-100 dark:bg-neutral-700 rounded w-2/3" />
            </div>
          ))}
        </div>
      )}

      {/* Server List */}
      {!isLoading && filteredServers.length > 0 && (
        <div className="space-y-3">
          {filteredServers.map((server) => {
            const health = healthColors[server.health_status] || healthColors.unknown;
            const HealthIcon = health.icon;
            const isExpanded = expandedServer === server.id;

            return (
              <div
                key={server.id}
                className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700"
              >
                {/* Server Row */}
                <div
                  className="p-5 cursor-pointer hover:bg-neutral-50 dark:hover:bg-neutral-750 transition-colors"
                  onClick={() => handleExpandServer(server.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') handleExpandServer(server.id);
                  }}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="p-2 bg-primary-50 dark:bg-primary-900/30 rounded-lg flex-shrink-0">
                        <Server className="h-5 w-5 text-primary-600 dark:text-primary-400" />
                      </div>
                      <div className="min-w-0">
                        <h3 className="font-semibold text-neutral-900 dark:text-white truncate">
                          {server.display_name}
                        </h3>
                        <p className="text-sm text-neutral-500 dark:text-neutral-400 truncate">
                          {server.base_url}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 flex-shrink-0 ml-4">
                      {/* Health Badge */}
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded ${health.bg} ${health.text}`}
                      >
                        <HealthIcon className="h-3 w-3" />
                        {server.health_status}
                      </span>
                      {/* Transport Badge */}
                      <span className="px-2 py-1 text-xs font-medium bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300 rounded uppercase">
                        {server.transport}
                      </span>
                      {/* Tools Count */}
                      <span className="inline-flex items-center gap-1 text-sm text-neutral-500 dark:text-neutral-400">
                        <Wrench className="h-4 w-4" />
                        {server.tools_count}
                      </span>
                      {/* Enabled/Disabled */}
                      {!server.enabled && (
                        <span className="px-2 py-1 text-xs font-medium bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 rounded">
                          Disabled
                        </span>
                      )}
                      {/* Expand icon */}
                      {isExpanded ? (
                        <ChevronUp className="h-5 w-5 text-neutral-400" />
                      ) : (
                        <ChevronDown className="h-5 w-5 text-neutral-400" />
                      )}
                    </div>
                  </div>
                  {server.description && (
                    <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-2 line-clamp-1 pl-12">
                      {server.description}
                    </p>
                  )}
                </div>

                {/* Expanded Detail */}
                {isExpanded && (
                  <div className="border-t border-neutral-200 dark:border-neutral-700 p-5 space-y-4">
                    {/* Actions */}
                    <div className="flex flex-wrap gap-2">
                      {canTestConnection && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleTestConnection(server.id);
                          }}
                          disabled={actionLoading === `test-${server.id}`}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm border border-neutral-300 dark:border-neutral-600 text-neutral-700 dark:text-neutral-200 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors disabled:opacity-50"
                        >
                          <Zap className="h-3.5 w-3.5" />
                          {actionLoading === `test-${server.id}` ? 'Testing...' : 'Test Connection'}
                        </button>
                      )}
                      {isWriteUser && (
                        <>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleSyncTools(server.id);
                            }}
                            disabled={actionLoading === `sync-${server.id}`}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm border border-neutral-300 dark:border-neutral-600 text-neutral-700 dark:text-neutral-200 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors disabled:opacity-50"
                          >
                            <RefreshCw
                              className={`h-3.5 w-3.5 ${actionLoading === `sync-${server.id}` ? 'animate-spin' : ''}`}
                            />
                            {actionLoading === `sync-${server.id}` ? 'Syncing...' : 'Sync Tools'}
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDeleteServer(server.id, server.display_name);
                            }}
                            disabled={actionLoading === `delete-${server.id}`}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm border border-red-300 dark:border-red-700 text-red-700 dark:text-red-400 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors disabled:opacity-50"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                            Delete
                          </button>
                        </>
                      )}
                    </div>

                    {/* Server info grid */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                      <div>
                        <span className="text-neutral-500 dark:text-neutral-400">Auth Type</span>
                        <p className="font-medium text-neutral-900 dark:text-white capitalize">
                          {server.auth_type.replace('_', ' ')}
                        </p>
                      </div>
                      <div>
                        <span className="text-neutral-500 dark:text-neutral-400">Credentials</span>
                        <p className="font-medium text-neutral-900 dark:text-white">
                          {server.has_credentials ? 'Configured' : 'None'}
                        </p>
                      </div>
                      <div>
                        <span className="text-neutral-500 dark:text-neutral-400">Last Synced</span>
                        <p className="font-medium text-neutral-900 dark:text-white">
                          {server.last_sync_at
                            ? new Date(server.last_sync_at).toLocaleDateString()
                            : 'Never'}
                        </p>
                      </div>
                      <div>
                        <span className="text-neutral-500 dark:text-neutral-400">Tool Prefix</span>
                        <p className="font-medium text-neutral-900 dark:text-white">
                          {server.tool_prefix || '(none)'}
                        </p>
                      </div>
                    </div>

                    {/* Sync error */}
                    {server.sync_error && (
                      <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-3">
                        <div className="flex items-start gap-2">
                          <AlertTriangle className="h-4 w-4 text-amber-500 mt-0.5" />
                          <p className="text-sm text-amber-700 dark:text-amber-300">
                            {server.sync_error}
                          </p>
                        </div>
                      </div>
                    )}

                    {/* Tools list */}
                    {serverDetail && serverDetail.id === server.id && (
                      <div>
                        <h4 className="text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                          Tools ({serverDetail.tools.length})
                        </h4>
                        {serverDetail.tools.length === 0 ? (
                          <p className="text-sm text-neutral-500 dark:text-neutral-400">
                            No tools discovered yet. Click &quot;Sync Tools&quot; to discover
                            available tools.
                          </p>
                        ) : (
                          <div className="space-y-2">
                            {serverDetail.tools.map((tool) => (
                              <div
                                key={tool.id}
                                className="flex items-center justify-between p-3 bg-neutral-50 dark:bg-neutral-750 rounded-lg"
                              >
                                <div className="min-w-0">
                                  <p className="text-sm font-medium text-neutral-900 dark:text-white">
                                    {tool.display_name || tool.name}
                                  </p>
                                  {tool.description && (
                                    <p className="text-xs text-neutral-500 dark:text-neutral-400 truncate">
                                      {tool.description}
                                    </p>
                                  )}
                                  <p className="text-xs text-neutral-400 dark:text-neutral-500 mt-0.5">
                                    {tool.namespaced_name}
                                  </p>
                                </div>
                                {isWriteUser && (
                                  <button
                                    onClick={() =>
                                      handleToggleTool(server.id, tool.id, !tool.enabled)
                                    }
                                    disabled={actionLoading === `toggle-${tool.id}`}
                                    className="flex-shrink-0 ml-3"
                                    title={tool.enabled ? 'Disable tool' : 'Enable tool'}
                                  >
                                    {tool.enabled ? (
                                      <ToggleRight className="h-6 w-6 text-green-600 dark:text-green-400" />
                                    ) : (
                                      <ToggleLeft className="h-6 w-6 text-neutral-400" />
                                    )}
                                  </button>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && filteredServers.length === 0 && (
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-12 text-center">
          <div className="inline-flex p-4 bg-neutral-100 dark:bg-neutral-700 rounded-full mb-4">
            <Server className="h-8 w-8 text-neutral-400 dark:text-neutral-500" />
          </div>
          <h2 className="text-xl font-semibold text-neutral-900 dark:text-white mb-2">
            {searchQuery ? 'No Servers Found' : 'No MCP Servers Registered'}
          </h2>
          <p className="text-neutral-500 dark:text-neutral-400 max-w-md mx-auto mb-6">
            {searchQuery
              ? 'No servers match your search. Try a different query.'
              : 'Register your first external MCP server to expose its tools through STOA.'}
          </p>
          {!searchQuery && isWriteUser && (
            <button
              data-testid="register-server-empty-btn"
              className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
            >
              <Plus className="h-4 w-4" />
              Register Server
            </button>
          )}
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="text-primary-600 hover:text-primary-700 font-medium"
            >
              Clear Search
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default MyMCPServersPage;
