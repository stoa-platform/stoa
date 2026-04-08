import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Puzzle,
  RefreshCw,
  ExternalLink,
  CheckCircle,
  XCircle,
  Plus,
  Server,
  AlertCircle,
  Clock,
  ArrowUpRight,
  Shield,
  Wrench,
} from 'lucide-react';
import { mcpConnectorsService } from '../../services/mcpConnectorsApi';
import { externalMcpServersService } from '../../services/externalMcpServersApi';
import { useAuth } from '../../contexts/AuthContext';
import { useEnvironment } from '../../contexts/EnvironmentContext';
import { ExternalMCPServerModal } from '../ExternalMCPServers/ExternalMCPServerModal';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import { EmptyState } from '@stoa/shared/components/EmptyState';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import { config } from '../../config';
import type {
  ConnectorTemplate,
  ExternalMCPServer,
  ExternalMCPServerCreate,
  ExternalMCPServerUpdate,
  ExternalMCPHealthStatus,
} from '../../types';

const ENABLE_MCP_CATALOG = config.features?.enableMcpCatalog ?? false;

type TabId = 'platform' | 'catalog' | 'custom';

const categoryLabels: Record<string, string> = {
  project_management: 'Project Management',
  development: 'Development',
  communication: 'Communication',
  monitoring: 'Monitoring',
  analytics: 'Analytics',
  security: 'Security',
  data: 'Data',
};

const connectorTransportLabels: Record<string, string> = {
  sse: 'SSE',
  streamable_http: 'Streamable HTTP',
  stdio: 'Stdio',
};

const serverTransportLabels: Record<string, string> = {
  sse: 'SSE',
  http: 'HTTP',
  websocket: 'WebSocket',
};

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

const ALL_CATEGORY = '__all__';

const ENVIRONMENTS = ['dev', 'staging', 'production'] as const;
type Environment = (typeof ENVIRONMENTS)[number];

const environmentLabels: Record<Environment, string> = {
  dev: 'Development',
  staging: 'Staging',
  production: 'Production',
};

const HIGH_RISK_SLUGS = new Set(['stripe', 'cloudflare']);

export function MCPServersUnified() {
  const [searchParams, setSearchParams] = useSearchParams();
  const defaultTab: TabId = 'platform';
  const activeTab = (searchParams.get('tab') as TabId) || defaultTab;
  const setActiveTab = useCallback(
    (tab: TabId) => setSearchParams({ tab }, { replace: true }),
    [setSearchParams]
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">MCP Servers</h1>
        <p className="text-neutral-500 dark:text-neutral-400 mt-1">
          Connect OAuth services or register custom MCP servers to proxy through STOA
        </p>
      </div>

      {/* Tabs */}
      <div className="border-b border-neutral-200 dark:border-neutral-700">
        <nav className="-mb-px flex gap-6" aria-label="Tabs">
          <button
            onClick={() => setActiveTab('platform')}
            className={`whitespace-nowrap pb-3 px-1 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'platform'
                ? 'border-primary-600 text-primary-600 dark:text-primary-400 dark:border-primary-400'
                : 'border-transparent text-neutral-500 hover:text-neutral-700 hover:border-neutral-300 dark:text-neutral-400 dark:hover:text-neutral-200'
            }`}
          >
            <Shield className="inline h-4 w-4 mr-1.5 -mt-0.5" />
            Platform
          </button>
          {ENABLE_MCP_CATALOG && (
            <button
              onClick={() => setActiveTab('catalog')}
              className={`whitespace-nowrap pb-3 px-1 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'catalog'
                  ? 'border-primary-600 text-primary-600 dark:text-primary-400 dark:border-primary-400'
                  : 'border-transparent text-neutral-500 hover:text-neutral-700 hover:border-neutral-300 dark:text-neutral-400 dark:hover:text-neutral-200'
              }`}
            >
              <Puzzle className="inline h-4 w-4 mr-1.5 -mt-0.5" />
              Catalog
            </button>
          )}
          <button
            onClick={() => setActiveTab('custom')}
            className={`whitespace-nowrap pb-3 px-1 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'custom'
                ? 'border-primary-600 text-primary-600 dark:text-primary-400 dark:border-primary-400'
                : 'border-transparent text-neutral-500 hover:text-neutral-700 hover:border-neutral-300 dark:text-neutral-400 dark:hover:text-neutral-200'
            }`}
          >
            <Server className="inline h-4 w-4 mr-1.5 -mt-0.5" />
            Custom Servers
          </button>
        </nav>
      </div>

      {/* Tab content */}
      {activeTab === 'platform' && <PlatformTab />}
      {activeTab === 'catalog' && ENABLE_MCP_CATALOG && <CatalogTab />}
      {activeTab === 'custom' && <CustomServersTab />}
    </div>
  );
}

// ─── Platform Tab (CAB-2003) ──────────────────────────────────────────────────

function PlatformTab() {
  const [servers, setServers] = useState<ExternalMCPServer[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const toast = useToastActions();

  const loadPlatformServers = useCallback(async () => {
    try {
      setLoading(true);
      const result = await externalMcpServersService.listServers({ page_size: 100 });
      setServers(result.servers.filter((s) => s.is_platform));
    } catch {
      /* empty — no platform servers yet is fine */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPlatformServers();
  }, [loadPlatformServers]);

  const handleSync = async (serverId: string) => {
    try {
      setSyncing(true);
      await externalMcpServersService.syncTools(serverId);
      toast.success('Tools synced successfully');
      await loadPlatformServers();
    } catch {
      toast.error('Failed to sync tools');
    } finally {
      setSyncing(false);
    }
  };

  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-4">
        <CardSkeleton />
      </div>
    );
  }

  if (servers.length === 0) {
    return (
      <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700">
        <EmptyState variant="tools" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {servers.map((server) => {
        const health = healthStatusConfig[server.health_status] ?? healthStatusConfig.unknown;
        const HealthIcon = health.icon;
        return (
          <div
            key={server.id}
            className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6"
          >
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="p-2.5 bg-blue-50 dark:bg-blue-950/30 rounded-lg">
                  <Shield className="h-6 w-6 text-blue-600" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-lg font-semibold text-neutral-900 dark:text-white">
                      {server.display_name}
                    </h3>
                    <span className="px-2 py-0.5 text-[10px] font-medium rounded-full bg-blue-100 dark:bg-blue-950/40 text-blue-700 dark:text-blue-400">
                      Platform
                    </span>
                  </div>
                  <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">
                    {server.description}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${health.color}`}
                >
                  <HealthIcon className="h-3.5 w-3.5" />
                  {health.label}
                </span>
              </div>
            </div>

            <div className="mt-4 flex items-center gap-6 text-sm text-neutral-500 dark:text-neutral-400">
              <span className="flex items-center gap-1.5">
                <Wrench className="h-4 w-4" />
                {server.tools_count} tool{server.tools_count !== 1 ? 's' : ''}
              </span>
              {server.last_sync_at && (
                <span className="flex items-center gap-1.5">
                  <Clock className="h-4 w-4" />
                  Last synced: {new Date(server.last_sync_at).toLocaleString()}
                </span>
              )}
            </div>

            <div className="mt-4 flex gap-2">
              <button
                onClick={() => handleSync(server.id)}
                disabled={syncing}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-neutral-300 dark:border-neutral-600 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${syncing ? 'animate-spin' : ''}`} />
                Sync Tools
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Catalog Tab ──────────────────────────────────────────────────────────────

function CatalogTab() {
  const { isReady } = useAuth();
  const toast = useToastActions();
  const [confirm, ConfirmDialog] = useConfirm();
  const mountedRef = useRef(true);

  const [connectors, setConnectors] = useState<ConnectorTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [categoryFilter, setCategoryFilter] = useState(ALL_CATEGORY);
  const [environmentFilter, setEnvironmentFilter] = useState<Environment | ''>('');
  const [connectingSlug, setConnectingSlug] = useState<string | null>(null);
  const [disconnectingSlug, setDisconnectingSlug] = useState<string | null>(null);
  const [promotingSlug, setPromotingSlug] = useState<string | null>(null);

  const loadConnectors = useCallback(async () => {
    try {
      setLoading(true);
      const response = await mcpConnectorsService.listConnectors(
        undefined,
        environmentFilter || undefined
      );
      if (!mountedRef.current) return;
      setConnectors(response.connectors);
      setError(null);
    } catch (err: unknown) {
      if (!mountedRef.current) return;
      const message = err instanceof Error ? err.message : 'Failed to load connectors';
      setError(message);
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [environmentFilter]);

  useEffect(() => {
    mountedRef.current = true;
    if (isReady) loadConnectors();
    return () => {
      mountedRef.current = false;
    };
  }, [isReady, loadConnectors]);

  const handleConnect = useCallback(
    async (slug: string) => {
      try {
        setConnectingSlug(slug);
        const response = await mcpConnectorsService.authorize(slug, {
          redirect_after: window.location.href,
        });
        window.location.href = response.authorize_url;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to start authorization';
        toast.error('Connection failed', message);
        setConnectingSlug(null);
      }
    },
    [toast]
  );

  const handleDisconnect = useCallback(
    async (connector: ConnectorTemplate) => {
      const confirmed = await confirm({
        title: `Disconnect ${connector.display_name}?`,
        message:
          'This will remove the connected server and its tools. You can reconnect at any time.',
        confirmLabel: 'Disconnect',
        variant: 'danger',
      });
      if (!confirmed) return;

      try {
        setDisconnectingSlug(connector.slug);
        await mcpConnectorsService.disconnect(connector.slug);
        toast.success('Disconnected', `${connector.display_name} has been disconnected`);
        await loadConnectors();
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to disconnect';
        toast.error('Disconnect failed', message);
      } finally {
        if (mountedRef.current) setDisconnectingSlug(null);
      }
    },
    [confirm, toast, loadConnectors]
  );

  const handlePromote = useCallback(
    async (connector: ConnectorTemplate, targetEnvironment: string) => {
      const isHighRisk = HIGH_RISK_SLUGS.has(connector.slug);
      const isProduction = targetEnvironment === 'production';

      if (isHighRisk && isProduction) {
        const confirmed = await confirm({
          title: `Promote ${connector.display_name} to Production?`,
          message:
            'This is a high-risk connector. Promoting to production will clone credentials and make this connector available in the production environment.',
          confirmLabel: 'Promote to Production',
          variant: 'danger',
        });
        if (!confirmed) return;
      }

      try {
        setPromotingSlug(connector.slug);
        const result = await mcpConnectorsService.promote(connector.slug, {
          target_environment: targetEnvironment,
          confirm: isHighRisk && isProduction,
        });
        toast.success(
          'Promoted',
          `${connector.display_name} promoted from ${result.source_environment} to ${result.target_environment}`
        );
        await loadConnectors();
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to promote connector';
        toast.error('Promote failed', message);
      } finally {
        if (mountedRef.current) setPromotingSlug(null);
      }
    },
    [confirm, toast, loadConnectors]
  );

  const categories = [
    ALL_CATEGORY,
    ...Array.from(new Set(connectors.map((c) => c.category))).sort(),
  ];

  const featured = connectors.filter((c) => c.is_featured);
  const filtered =
    categoryFilter === ALL_CATEGORY
      ? connectors
      : connectors.filter((c) => c.category === categoryFilter);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex justify-end">
          <div className="h-10 w-24 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Toolbar */}
      <div className="flex justify-end gap-3">
        <select
          value={environmentFilter}
          onChange={(e) => setEnvironmentFilter(e.target.value as Environment | '')}
          className="px-3 py-2 text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300"
        >
          <option value="">All environments</option>
          {ENVIRONMENTS.map((env) => (
            <option key={env} value={env}>
              {environmentLabels[env]}
            </option>
          ))}
        </select>
        <button
          onClick={loadConnectors}
          className="flex items-center gap-2 px-4 py-2 text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-800 text-neutral-700 dark:text-neutral-300"
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg">
          {error}
          <button onClick={() => setError(null)} className="float-right font-bold">
            &times;
          </button>
        </div>
      )}

      {/* Featured section */}
      {featured.length > 0 && categoryFilter === ALL_CATEGORY && (
        <div>
          <h2 className="text-lg font-semibold text-neutral-900 dark:text-white mb-3">Featured</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {featured.map((connector) => (
              <ConnectorCard
                key={connector.id}
                connector={connector}
                onConnect={handleConnect}
                onDisconnect={handleDisconnect}
                onPromote={handlePromote}
                connectingSlug={connectingSlug}
                disconnectingSlug={disconnectingSlug}
                promotingSlug={promotingSlug}
                featured
              />
            ))}
          </div>
        </div>
      )}

      {/* Category filter */}
      {categories.length > 2 && (
        <div className="flex gap-2 flex-wrap">
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setCategoryFilter(cat)}
              className={`px-3 py-1.5 text-sm rounded-full transition-colors ${
                categoryFilter === cat
                  ? 'bg-primary-600 text-white'
                  : 'bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-300 hover:bg-neutral-200 dark:hover:bg-neutral-700'
              }`}
            >
              {cat === ALL_CATEGORY ? 'All' : categoryLabels[cat] || cat}
            </button>
          ))}
        </div>
      )}

      {/* Connector grid */}
      {filtered.length === 0 ? (
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow">
          <EmptyState
            variant="default"
            title="No connectors available"
            description="No connector templates match your filter. Try selecting a different category."
          />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filtered.map((connector) => (
            <ConnectorCard
              key={connector.id}
              connector={connector}
              onConnect={handleConnect}
              onDisconnect={handleDisconnect}
              onPromote={handlePromote}
              connectingSlug={connectingSlug}
              disconnectingSlug={disconnectingSlug}
              promotingSlug={promotingSlug}
            />
          ))}
        </div>
      )}

      {ConfirmDialog}
    </div>
  );
}

// ─── Custom Servers Tab ───────────────────────────────────────────────────────

function CustomServersTab() {
  const navigate = useNavigate();
  const { isReady } = useAuth();
  const { activeEnvironment } = useEnvironment();
  const toast = useToastActions();
  const [confirm, ConfirmDialog] = useConfirm();
  const [servers, setServers] = useState<ExternalMCPServer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [testingServerId, setTestingServerId] = useState<string | null>(null);
  const [syncingServerId, setSyncingServerId] = useState<string | null>(null);
  const mountedRef = useRef(true);

  const loadServers = useCallback(async () => {
    try {
      setLoading(true);
      const response = await externalMcpServersService.listServers({
        environment: activeEnvironment,
      });
      if (!mountedRef.current) return;
      setServers(response.servers);
      setError(null);
    } catch (err: unknown) {
      if (!mountedRef.current) return;
      const message = err instanceof Error ? err.message : 'Failed to load servers';
      setError(message);
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [activeEnvironment]);

  useEffect(() => {
    mountedRef.current = true;
    if (isReady) loadServers();
    return () => {
      mountedRef.current = false;
    };
  }, [isReady, loadServers]);

  const handleCreate = useCallback(
    async (data: ExternalMCPServerCreate | ExternalMCPServerUpdate) => {
      try {
        const createData = {
          ...(data as ExternalMCPServerCreate),
          environment: activeEnvironment,
        };
        await externalMcpServersService.createServer(createData);
        setShowCreateModal(false);
        await loadServers();
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to create server';
        throw new Error(message);
      }
    },
    [activeEnvironment, loadServers]
  );

  const handleTestConnection = useCallback(
    async (serverId: string) => {
      try {
        setTestingServerId(serverId);
        const result = await externalMcpServersService.testConnection(serverId);
        await loadServers();

        if (result.success) {
          toast.success(
            'Connection successful',
            `${result.tools_discovered !== undefined ? `Found ${result.tools_discovered} tools. ` : ''}Latency: ${result.latency_ms}ms`
          );
        } else {
          toast.error('Connection failed', result.error);
        }
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Test failed';
        toast.error('Test failed', message);
      } finally {
        setTestingServerId(null);
      }
    },
    [toast, loadServers]
  );

  const handleSyncTools = useCallback(
    async (serverId: string) => {
      try {
        setSyncingServerId(serverId);
        const result = await externalMcpServersService.syncTools(serverId);
        await loadServers();
        toast.success(
          'Tools synchronized',
          `Synced ${result.synced_count} tools${result.removed_count > 0 ? `. Removed ${result.removed_count} obsolete.` : ''}`
        );
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Sync failed';
        toast.error('Sync failed', message);
      } finally {
        setSyncingServerId(null);
      }
    },
    [toast, loadServers]
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
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Delete failed';
        toast.error('Delete failed', message);
      }
    },
    [toast, confirm, loadServers]
  );

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex justify-end gap-3">
          <div className="h-10 w-24 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
          <div className="h-10 w-28 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
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
      {/* Toolbar */}
      <div className="flex justify-end gap-3">
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

      {/* Error */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg">
          {error}
          <button onClick={() => setError(null)} className="float-right font-bold">
            &times;
          </button>
        </div>
      )}

      {/* Server grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {servers.length === 0 ? (
          <div className="col-span-full bg-white dark:bg-neutral-800 rounded-lg shadow">
            <EmptyState
              variant="servers"
              title="No custom MCP servers registered"
              description="Register external MCP servers like Linear or GitHub to proxy through STOA with governance."
              action={{ label: 'Add Server', onClick: () => setShowCreateModal(true) }}
            />
          </div>
        ) : (
          servers.map((server) => (
            <ServerCard
              key={server.id}
              server={server}
              onTest={handleTestConnection}
              onSync={handleSyncTools}
              onDelete={handleDelete}
              onView={(id) => navigate(`/external-mcp-servers/${id}`)}
              testingServerId={testingServerId}
              syncingServerId={syncingServerId}
            />
          ))
        )}
      </div>

      {showCreateModal && (
        <ExternalMCPServerModal onClose={() => setShowCreateModal(false)} onSubmit={handleCreate} />
      )}

      {ConfirmDialog}
    </div>
  );
}

// ─── ConnectorCard ────────────────────────────────────────────────────────────

interface ConnectorCardProps {
  connector: ConnectorTemplate;
  onConnect: (slug: string) => void;
  onDisconnect: (connector: ConnectorTemplate) => void;
  onPromote: (connector: ConnectorTemplate, targetEnvironment: string) => void;
  connectingSlug: string | null;
  disconnectingSlug: string | null;
  promotingSlug: string | null;
  featured?: boolean;
}

function ConnectorCard({
  connector,
  onConnect,
  onDisconnect,
  onPromote,
  connectingSlug,
  disconnectingSlug,
  promotingSlug,
  featured,
}: ConnectorCardProps) {
  const isConnecting = connectingSlug === connector.slug;
  const isDisconnecting = disconnectingSlug === connector.slug;
  const isPromoting = promotingSlug === connector.slug;

  const nextEnvironment = connector.connected_environment
    ? connector.connected_environment === 'dev'
      ? 'staging'
      : connector.connected_environment === 'staging'
        ? 'production'
        : null
    : null;

  return (
    <div
      className={`bg-white dark:bg-neutral-800 rounded-lg shadow p-6 hover:shadow-md transition-shadow ${
        featured ? 'ring-2 ring-primary-200 dark:ring-primary-800' : ''
      }`}
    >
      <div className="flex items-start gap-3 mb-4">
        {connector.icon_url ? (
          <img src={connector.icon_url} alt="" className="w-10 h-10 rounded flex-shrink-0" />
        ) : (
          <div className="w-10 h-10 bg-neutral-100 dark:bg-neutral-700 rounded flex items-center justify-center flex-shrink-0">
            <Puzzle className="h-5 w-5 text-neutral-500 dark:text-neutral-400" />
          </div>
        )}
        <div className="flex-1 min-w-0">
          <h3 className="text-lg font-semibold text-neutral-900 dark:text-white truncate">
            {connector.display_name}
          </h3>
          {connector.description && (
            <p className="text-sm text-neutral-500 dark:text-neutral-400 line-clamp-2 mt-0.5">
              {connector.description}
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-2 mb-4">
        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300">
          {categoryLabels[connector.category] || connector.category}
        </span>
        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">
          {connectorTransportLabels[connector.transport] || connector.transport}
        </span>
        {connector.is_connected && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-300">
            <CheckCircle className="h-3 w-3" />
            Connected
          </span>
        )}
        {connector.connected_environment && (
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
              connector.connected_environment === 'production'
                ? 'bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300'
                : connector.connected_environment === 'staging'
                  ? 'bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300'
                  : 'bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300'
            }`}
          >
            {environmentLabels[connector.connected_environment as Environment] ||
              connector.connected_environment}
          </span>
        )}
      </div>

      <div className="flex gap-2 pt-4 border-t dark:border-neutral-700">
        {connector.is_connected ? (
          <>
            <button
              onClick={() => onDisconnect(connector)}
              disabled={isDisconnecting}
              className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-sm border border-red-200 dark:border-red-800 text-red-600 dark:text-red-400 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50"
            >
              <XCircle className="h-4 w-4" />
              {isDisconnecting ? 'Disconnecting...' : 'Disconnect'}
            </button>
            {nextEnvironment && (
              <button
                onClick={() => onPromote(connector, nextEnvironment)}
                disabled={isPromoting}
                className="flex items-center justify-center gap-1.5 px-3 py-2 text-sm border border-primary-300 dark:border-primary-700 text-primary-600 dark:text-primary-400 rounded-lg hover:bg-primary-50 dark:hover:bg-primary-900/20 disabled:opacity-50"
                title={`Promote to ${environmentLabels[nextEnvironment as Environment]}`}
              >
                <ArrowUpRight className="h-4 w-4" />
                {isPromoting ? '...' : environmentLabels[nextEnvironment as Environment]}
              </button>
            )}
            {connector.documentation_url && (
              <a
                href={connector.documentation_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-center px-3 py-2 text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 text-neutral-700 dark:text-neutral-300"
              >
                <ExternalLink className="h-4 w-4" />
              </a>
            )}
          </>
        ) : (
          <>
            <button
              onClick={() => onConnect(connector.slug)}
              disabled={isConnecting}
              className="flex-1 px-3 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
            >
              {isConnecting ? 'Connecting...' : 'Connect'}
            </button>
            {connector.documentation_url && (
              <a
                href={connector.documentation_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-center px-3 py-2 text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 text-neutral-700 dark:text-neutral-300"
              >
                <ExternalLink className="h-4 w-4" />
              </a>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ─── ServerCard ───────────────────────────────────────────────────────────────

interface ServerCardProps {
  server: ExternalMCPServer;
  onTest: (id: string) => void;
  onSync: (id: string) => void;
  onDelete: (server: ExternalMCPServer) => void;
  onView: (id: string) => void;
  testingServerId: string | null;
  syncingServerId: string | null;
}

function ServerCard({
  server,
  onTest,
  onSync,
  onDelete,
  onView,
  testingServerId,
  syncingServerId,
}: ServerCardProps) {
  const healthConfig = healthStatusConfig[server.health_status];
  const HealthIcon = healthConfig.icon;

  return (
    <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-6 hover:shadow-md transition-shadow">
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

      <div className="space-y-2 text-sm text-neutral-600 dark:text-neutral-300 mb-4">
        <div className="flex justify-between">
          <span className="text-neutral-500 dark:text-neutral-400">Transport:</span>
          <span className="font-mono">
            {serverTransportLabels[server.transport] || server.transport}
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
        {server.environment && (
          <div className="flex justify-between">
            <span className="text-neutral-500 dark:text-neutral-400">Environment:</span>
            <span className="capitalize">{server.environment}</span>
          </div>
        )}
        {server.gateway_instance_id && (
          <div className="flex justify-between">
            <span className="text-neutral-500 dark:text-neutral-400">Gateway:</span>
            <span className="font-mono text-xs">{server.gateway_instance_id}</span>
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

      {server.sync_error && (
        <div
          className="mb-4 p-2 bg-red-50 dark:bg-red-900/20 border border-red-100 dark:border-red-800 rounded text-xs text-red-700 dark:text-red-400 truncate"
          title={server.sync_error}
        >
          {server.sync_error}
        </div>
      )}

      <div className="flex gap-2 pt-4 border-t dark:border-neutral-700">
        <button
          onClick={() => onTest(server.id)}
          disabled={testingServerId === server.id}
          className="flex-1 px-3 py-2 text-sm border border-neutral-300 dark:border-neutral-600 rounded hover:bg-neutral-50 dark:hover:bg-neutral-700 dark:text-neutral-300 disabled:opacity-50"
        >
          {testingServerId === server.id ? 'Testing...' : 'Test'}
        </button>
        <button
          onClick={() => onSync(server.id)}
          disabled={syncingServerId === server.id}
          className="flex-1 px-3 py-2 text-sm border border-neutral-300 dark:border-neutral-600 rounded hover:bg-neutral-50 dark:hover:bg-neutral-700 dark:text-neutral-300 disabled:opacity-50"
        >
          {syncingServerId === server.id ? 'Syncing...' : 'Sync'}
        </button>
        <button
          onClick={() => onView(server.id)}
          className="flex-1 px-3 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          View
        </button>
      </div>

      <button
        onClick={() => onDelete(server)}
        className="mt-2 w-full px-3 py-1.5 text-xs text-red-600 hover:bg-red-50 rounded opacity-0 hover:opacity-100 transition-opacity"
      >
        Delete Server
      </button>
    </div>
  );
}
