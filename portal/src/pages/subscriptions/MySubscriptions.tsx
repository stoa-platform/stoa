/**
 * My Subscriptions Page
 *
 * Lists user's MCP Tool and MCP Server subscriptions with usage statistics.
 * Uses MCP Gateway endpoints (mcp.stoa.cab-i.com)
 *
 * Reference: Linear CAB-247
 */

import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  TrendingUp,
  AlertCircle,
  RefreshCw,
  Search,
  Filter,
  Key,
  Clock,
  CheckCircle,
  XCircle,
  Eye,
  Shield,
  Download,
  Server,
  Wrench,
  ExternalLink,
} from 'lucide-react';
import { useSubscriptions, useRevokeSubscription, useRotateApiKey } from '../../hooks/useSubscriptions';
import { RevealKeyModal } from '../../components/subscriptions/RevealKeyModal';
import { RotateKeyModal } from '../../components/subscriptions/RotateKeyModal';
import { ExportConfigModal } from '../../components/subscriptions/ExportConfigModal';
import { mcpServersService } from '../../services/mcpServers';
import { useAuth } from '../../contexts/AuthContext';
import { StatCardWithIconSkeleton, ServerCardSkeletonGrid } from '../../components/skeletons';
import type { MCPSubscription, MCPServerSubscription } from '../../types';

type StatusFilter = 'all' | 'active' | 'expired' | 'revoked' | 'pending' | 'suspended';
type TabType = 'servers' | 'tools';

const statusConfig: Record<string, {
  label: string;
  color: string;
  bgColor: string;
  icon: typeof CheckCircle;
}> = {
  active: { label: 'Active', color: 'text-green-700', bgColor: 'bg-green-100', icon: CheckCircle },
  expired: { label: 'Expired', color: 'text-amber-700', bgColor: 'bg-amber-100', icon: Clock },
  revoked: { label: 'Revoked', color: 'text-red-700', bgColor: 'bg-red-100', icon: XCircle },
  pending: { label: 'Pending', color: 'text-blue-700', bgColor: 'bg-blue-100', icon: Clock },
  suspended: { label: 'Suspended', color: 'text-orange-700', bgColor: 'bg-orange-100', icon: AlertCircle },
};

export function MySubscriptions() {
  const { isAuthenticated, accessToken } = useAuth();
  const [activeTab, setActiveTab] = useState<TabType>('servers');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [revealModalSubscription, setRevealModalSubscription] = useState<MCPSubscription | null>(null);
  const [rotateModalSubscription, setRotateModalSubscription] = useState<MCPSubscription | null>(null);
  const [exportModalSubscription, setExportModalSubscription] = useState<MCPSubscription | null>(null);

  // Server subscriptions state
  const [serverSubscriptions, setServerSubscriptions] = useState<MCPServerSubscription[]>([]);
  const [serverSubsLoading, setServerSubsLoading] = useState(false);
  const [serverSubsError, setServerSubsError] = useState<string | null>(null);

  // Tool subscriptions (legacy)
  const {
    data: subscriptionsData,
    isLoading: toolSubsLoading,
    isError: toolSubsError,
    error: toolError,
    refetch: refetchToolSubs,
  } = useSubscriptions();

  const revokeMutation = useRevokeSubscription();
  const rotateKeyMutation = useRotateApiKey();

  // Load server subscriptions
  useEffect(() => {
    if (!isAuthenticated || !accessToken) return;

    async function loadServerSubscriptions() {
      setServerSubsLoading(true);
      setServerSubsError(null);
      try {
        const subs = await mcpServersService.getMyServerSubscriptions();
        setServerSubscriptions(subs);
      } catch (err) {
        setServerSubsError(err instanceof Error ? err.message : 'Failed to load server subscriptions');
        setServerSubscriptions([]);
      } finally {
        setServerSubsLoading(false);
      }
    }

    loadServerSubscriptions();
  }, [isAuthenticated, accessToken]);

  const handleRevokeSubscription = async (subscriptionId: string) => {
    if (confirm('Are you sure you want to revoke this subscription? Your API key will be invalidated immediately.')) {
      setRevokingId(subscriptionId);
      try {
        await revokeMutation.mutateAsync(subscriptionId);
      } finally {
        setRevokingId(null);
      }
    }
  };

  const refetchAll = () => {
    refetchToolSubs();
    // Reload server subscriptions
    if (isAuthenticated && accessToken) {
      setServerSubsLoading(true);
      mcpServersService.getMyServerSubscriptions()
        .then(setServerSubscriptions)
        .catch(() => setServerSubscriptions([]))
        .finally(() => setServerSubsLoading(false));
    }
  };

  // Get tool subscriptions array
  const toolSubscriptions = subscriptionsData?.subscriptions || [];

  // Filter subscriptions based on search and status
  const filteredToolSubs = toolSubscriptions.filter((sub: MCPSubscription) => {
    if (statusFilter !== 'all' && sub.status !== statusFilter) return false;
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      return sub.tool_id?.toLowerCase().includes(query);
    }
    return true;
  });

  const filteredServerSubs = serverSubscriptions.filter((sub) => {
    if (statusFilter !== 'all' && sub.status !== statusFilter) return false;
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      return sub.server?.displayName?.toLowerCase().includes(query) ||
             sub.server_id?.toLowerCase().includes(query);
    }
    return true;
  });

  // Calculate stats
  const activeServerCount = serverSubscriptions.filter(s => s.status === 'active').length;
  const activeToolCount = toolSubscriptions.filter((s: MCPSubscription) => s.status === 'active').length;
  const totalActiveCount = activeServerCount + activeToolCount;
  const totalUsage = toolSubscriptions.reduce((acc: number, s: MCPSubscription) => acc + (s.usage_count || 0), 0);

  const isLoading = serverSubsLoading || toolSubsLoading;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">My Subscriptions</h1>
          <p className="text-gray-500 mt-1">
            Manage your MCP Server and Tool subscriptions
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={refetchAll}
            disabled={isLoading}
            className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50"
            title="Refresh"
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
          <Link
            to="/servers"
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
          >
            <Server className="h-4 w-4" />
            Browse Servers
          </Link>
        </div>
      </div>

      {/* Stats Overview */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {isLoading ? (
          <>
            <StatCardWithIconSkeleton />
            <StatCardWithIconSkeleton />
            <StatCardWithIconSkeleton />
          </>
        ) : (
          <>
            <div className="bg-white rounded-lg border border-gray-200 p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-primary-50 rounded-lg">
                  <Key className="h-5 w-5 text-primary-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-gray-900">{totalActiveCount}</p>
                  <p className="text-sm text-gray-500">Active Subscriptions</p>
                </div>
              </div>
            </div>
            <div className="bg-white rounded-lg border border-gray-200 p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-blue-50 rounded-lg">
                  <Server className="h-5 w-5 text-blue-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-gray-900">{activeServerCount}</p>
                  <p className="text-sm text-gray-500">Server Subscriptions</p>
                </div>
              </div>
            </div>
            <div className="bg-white rounded-lg border border-gray-200 p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-green-50 rounded-lg">
                  <TrendingUp className="h-5 w-5 text-green-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-gray-900">{totalUsage.toLocaleString()}</p>
                  <p className="text-sm text-gray-500">Total API Calls</p>
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-8">
          <button
            onClick={() => setActiveTab('servers')}
            className={`pb-4 px-1 border-b-2 font-medium text-sm transition-colors ${
              activeTab === 'servers'
                ? 'border-primary-500 text-primary-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            <span className="flex items-center gap-2">
              <Server className="h-4 w-4" />
              MCP Servers
              {activeServerCount > 0 && (
                <span className="px-2 py-0.5 text-xs bg-primary-100 text-primary-700 rounded-full">
                  {activeServerCount}
                </span>
              )}
            </span>
          </button>
          <button
            onClick={() => setActiveTab('tools')}
            className={`pb-4 px-1 border-b-2 font-medium text-sm transition-colors ${
              activeTab === 'tools'
                ? 'border-primary-500 text-primary-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            <span className="flex items-center gap-2">
              <Wrench className="h-4 w-4" />
              Individual Tools
              {activeToolCount > 0 && (
                <span className="px-2 py-0.5 text-xs bg-gray-100 text-gray-600 rounded-full">
                  {activeToolCount}
                </span>
              )}
            </span>
          </button>
        </nav>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            placeholder={activeTab === 'servers' ? 'Search by server name...' : 'Search by tool name...'}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-gray-500" />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
            className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          >
            <option value="all">All Status</option>
            <option value="active">Active</option>
            <option value="pending">Pending</option>
            <option value="suspended">Suspended</option>
            <option value="revoked">Revoked</option>
          </select>
        </div>
      </div>

      {/* Server Subscriptions Tab */}
      {activeTab === 'servers' && (
        <>
          {serverSubsLoading && (
            <ServerCardSkeletonGrid count={4} columns={2} />
          )}

          {serverSubsError && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-6">
              <div className="flex items-start gap-3">
                <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
                <div>
                  <h3 className="font-medium text-red-800">Failed to load server subscriptions</h3>
                  <p className="text-sm text-red-600 mt-1">{serverSubsError}</p>
                </div>
              </div>
            </div>
          )}

          {!serverSubsLoading && !serverSubsError && filteredServerSubs.length === 0 && (
            <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
              <div className="inline-flex p-4 bg-gray-100 rounded-full mb-4">
                <Server className="h-8 w-8 text-gray-400" />
              </div>
              <h2 className="text-xl font-semibold text-gray-900 mb-2">No Server Subscriptions</h2>
              <p className="text-gray-500 max-w-md mx-auto mb-6">
                Subscribe to an MCP Server to get access to all its tools with a single API key.
              </p>
              <Link
                to="/servers"
                className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
              >
                <Server className="h-4 w-4" />
                Browse MCP Servers
              </Link>
            </div>
          )}

          {!serverSubsLoading && !serverSubsError && filteredServerSubs.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {filteredServerSubs.map((sub) => {
                const status = statusConfig[sub.status] || statusConfig.pending;
                const StatusIcon = status.icon;
                const enabledTools = sub.tool_access?.filter(t => t.status === 'enabled').length || 0;
                const totalTools = sub.tool_access?.length || 0;

                return (
                  <div
                    key={sub.id}
                    className="bg-white rounded-lg border border-gray-200 p-5 hover:shadow-md transition-shadow"
                  >
                    <div className="flex items-start justify-between mb-3">
                      <div className="p-2 bg-blue-50 rounded-lg">
                        <Server className="h-5 w-5 text-blue-600" />
                      </div>
                      <span className={`inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded ${status.bgColor} ${status.color}`}>
                        <StatusIcon className="h-3 w-3" />
                        {status.label}
                      </span>
                    </div>

                    <h3 className="font-semibold text-gray-900 mb-1">
                      {sub.server?.displayName || sub.server_id}
                    </h3>
                    <p className="text-sm text-gray-500 mb-3 line-clamp-2">
                      {sub.server?.description || 'MCP Server'}
                    </p>

                    {/* Tools access summary */}
                    <div className="flex items-center gap-2 text-sm text-gray-600 mb-2">
                      <Wrench className="h-4 w-4" />
                      <span>{enabledTools} / {totalTools} tools enabled</span>
                    </div>

                    {/* API Key prefix */}
                    {sub.api_key_prefix && (
                      <div className="mt-2 font-mono text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded inline-block">
                        {sub.api_key_prefix}...
                      </div>
                    )}

                    <div className="text-sm text-gray-500 space-y-1 mt-3">
                      <p>Created: {new Date(sub.created_at).toLocaleDateString()}</p>
                      {sub.last_used_at && (
                        <p>Last used: {new Date(sub.last_used_at).toLocaleDateString()}</p>
                      )}
                    </div>

                    {sub.status === 'active' && (
                      <div className="mt-4 pt-4 border-t border-gray-100 flex items-center justify-between">
                        <Link
                          to={`/servers/${sub.server_id}`}
                          className="inline-flex items-center gap-1 text-sm text-primary-600 hover:text-primary-700 font-medium"
                        >
                          <ExternalLink className="h-3 w-3" />
                          View Details
                        </Link>
                        <button
                          className="inline-flex items-center gap-1 text-sm text-green-600 hover:text-green-700 font-medium"
                          title="Configure with Claude.ai"
                        >
                          <Download className="h-3 w-3" />
                          Get Config
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {/* Tool Subscriptions Tab */}
      {activeTab === 'tools' && (
        <>
          {toolSubsLoading && (
            <ServerCardSkeletonGrid count={6} columns={3} />
          )}

          {toolSubsError && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-6">
              <div className="flex items-start gap-3">
                <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
                <div>
                  <h3 className="font-medium text-red-800">Failed to load tool subscriptions</h3>
                  <p className="text-sm text-red-600 mt-1">
                    {(toolError as Error)?.message || 'An unexpected error occurred'}
                  </p>
                </div>
              </div>
            </div>
          )}

          {!toolSubsLoading && !toolSubsError && filteredToolSubs.length === 0 && (
            <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
              <div className="inline-flex p-4 bg-gray-100 rounded-full mb-4">
                <Wrench className="h-8 w-8 text-gray-400" />
              </div>
              <h2 className="text-xl font-semibold text-gray-900 mb-2">No Tool Subscriptions</h2>
              <p className="text-gray-500 max-w-md mx-auto mb-6">
                Individual tool subscriptions are legacy. We recommend using MCP Server subscriptions instead.
              </p>
              <Link
                to="/servers"
                className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
              >
                <Server className="h-4 w-4" />
                Browse MCP Servers
              </Link>
            </div>
          )}

          {!toolSubsLoading && !toolSubsError && filteredToolSubs.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {filteredToolSubs.map((subscription: MCPSubscription) => {
                const status = statusConfig[subscription.status] || statusConfig.active;
                const StatusIcon = status.icon;

                return (
                  <div
                    key={subscription.id}
                    className="bg-white rounded-lg border border-gray-200 p-5 hover:shadow-md transition-shadow"
                  >
                    <div className="flex items-start justify-between mb-3">
                      <div className="p-2 bg-primary-50 rounded-lg">
                        <Key className="h-5 w-5 text-primary-600" />
                      </div>
                      <span className={`inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded ${status.bgColor} ${status.color}`}>
                        <StatusIcon className="h-3 w-3" />
                        {status.label}
                      </span>
                    </div>

                    <h3 className="font-semibold text-gray-900 mb-1">
                      {subscription.tool_id}
                    </h3>

                    {subscription.api_key_prefix && (
                      <div className="mt-2 font-mono text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded inline-block">
                        {subscription.api_key_prefix}...
                      </div>
                    )}

                    <div className="text-sm text-gray-500 space-y-1 mt-2">
                      <p>Created: {new Date(subscription.created_at).toLocaleDateString()}</p>
                      {subscription.usage_count !== undefined && (
                        <p>Usage: {subscription.usage_count.toLocaleString()} calls</p>
                      )}
                    </div>

                    {subscription.totp_required && (
                      <div className="mt-2 flex items-center gap-1 text-xs text-primary-600">
                        <Shield className="h-3 w-3" />
                        2FA Protected
                      </div>
                    )}

                    {subscription.status === 'active' && (
                      <div className="mt-4 pt-4 border-t border-gray-100 flex items-center justify-between">
                        <button
                          onClick={() => setRevealModalSubscription(subscription)}
                          className="inline-flex items-center gap-1 text-sm text-primary-600 hover:text-primary-700 font-medium"
                        >
                          <Eye className="h-3 w-3" />
                          Reveal Key
                        </button>
                        <button
                          onClick={() => setExportModalSubscription(subscription)}
                          className="inline-flex items-center gap-1 text-sm text-green-600 hover:text-green-700 font-medium"
                        >
                          <Download className="h-3 w-3" />
                          Export
                        </button>
                        <button
                          onClick={() => handleRevokeSubscription(subscription.id)}
                          disabled={revokingId === subscription.id}
                          className="text-sm text-red-600 hover:text-red-700 font-medium disabled:opacity-50"
                        >
                          Revoke
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {/* Reveal Key Modal */}
      {revealModalSubscription && (
        <RevealKeyModal
          subscription={revealModalSubscription}
          isOpen={true}
          onClose={() => setRevealModalSubscription(null)}
        />
      )}

      {/* Rotate Key Modal */}
      {rotateModalSubscription && (
        <RotateKeyModal
          subscription={rotateModalSubscription}
          isOpen={true}
          onClose={() => setRotateModalSubscription(null)}
          onRotate={async (gracePeriodHours) => {
            const result = await rotateKeyMutation.mutateAsync({
              id: rotateModalSubscription.id,
              gracePeriodHours,
            });
            return result;
          }}
          isRotating={rotateKeyMutation.isPending}
        />
      )}

      {/* Export Config Modal */}
      {exportModalSubscription && (
        <ExportConfigModal
          subscription={exportModalSubscription}
          isOpen={true}
          onClose={() => setExportModalSubscription(null)}
        />
      )}
    </div>
  );
}

export default MySubscriptions;
