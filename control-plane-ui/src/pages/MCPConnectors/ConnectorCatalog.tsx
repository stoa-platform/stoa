import { useState, useEffect, useCallback, useRef } from 'react';
import { Puzzle, RefreshCw, ExternalLink, CheckCircle, XCircle } from 'lucide-react';
import { mcpConnectorsService } from '../../services/mcpConnectorsApi';
import { useAuth } from '../../contexts/AuthContext';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import { EmptyState } from '@stoa/shared/components/EmptyState';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import type { ConnectorTemplate } from '../../types';

const categoryLabels: Record<string, string> = {
  project_management: 'Project Management',
  development: 'Development',
  communication: 'Communication',
  monitoring: 'Monitoring',
  analytics: 'Analytics',
  security: 'Security',
  data: 'Data',
};

const transportLabels: Record<string, string> = {
  sse: 'SSE',
  streamable_http: 'Streamable HTTP',
  stdio: 'Stdio',
};

const ALL_CATEGORY = '__all__';

export function ConnectorCatalog() {
  const { isReady } = useAuth();
  const toast = useToastActions();
  const [confirm, ConfirmDialog] = useConfirm();
  const mountedRef = useRef(true);

  const [connectors, setConnectors] = useState<ConnectorTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [categoryFilter, setCategoryFilter] = useState(ALL_CATEGORY);
  const [connectingSlug, setConnectingSlug] = useState<string | null>(null);
  const [disconnectingSlug, setDisconnectingSlug] = useState<string | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    if (isReady) {
      loadConnectors();
    }
    return () => {
      mountedRef.current = false;
    };
  }, [isReady]);

  async function loadConnectors() {
    try {
      setLoading(true);
      const response = await mcpConnectorsService.listConnectors();
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
  }

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
    [confirm, toast]
  );

  // Derive categories from data
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
        <div className="flex justify-between items-center">
          <div className="h-8 w-64 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
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
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">MCP Connectors</h1>
          <p className="text-neutral-500 dark:text-neutral-400 mt-1">
            Connect third-party services to STOA with one click via OAuth
          </p>
        </div>
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
                connectingSlug={connectingSlug}
                disconnectingSlug={disconnectingSlug}
                featured
              />
            ))}
          </div>
        </div>
      )}

      {/* Category filter tabs */}
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
              connectingSlug={connectingSlug}
              disconnectingSlug={disconnectingSlug}
            />
          ))}
        </div>
      )}

      {ConfirmDialog}
    </div>
  );
}

interface ConnectorCardProps {
  connector: ConnectorTemplate;
  onConnect: (slug: string) => void;
  onDisconnect: (connector: ConnectorTemplate) => void;
  connectingSlug: string | null;
  disconnectingSlug: string | null;
  featured?: boolean;
}

function ConnectorCard({
  connector,
  onConnect,
  onDisconnect,
  connectingSlug,
  disconnectingSlug,
  featured,
}: ConnectorCardProps) {
  const isConnecting = connectingSlug === connector.slug;
  const isDisconnecting = disconnectingSlug === connector.slug;

  return (
    <div
      className={`bg-white dark:bg-neutral-800 rounded-lg shadow p-6 hover:shadow-md transition-shadow ${
        featured ? 'ring-2 ring-primary-200 dark:ring-primary-800' : ''
      }`}
    >
      {/* Header */}
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

      {/* Badges */}
      <div className="flex flex-wrap gap-2 mb-4">
        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300">
          {categoryLabels[connector.category] || connector.category}
        </span>
        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">
          {transportLabels[connector.transport] || connector.transport}
        </span>
        {connector.is_connected && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-300">
            <CheckCircle className="h-3 w-3" />
            Connected
          </span>
        )}
      </div>

      {/* Actions */}
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
