/**
 * My Subscriptions Page
 *
 * Lists user's MCP Tool and MCP Server subscriptions with usage statistics.
 * Uses MCP Gateway endpoints (mcp.gostoa.dev)
 *
 * Reference: Linear CAB-247
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
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
  Shield,
  Download,
  Server,
  Wrench,
  ExternalLink,
  CreditCard,
} from 'lucide-react';
import { ConfirmDialog } from '@stoa/shared/components/ConfirmDialog';
import { useToastActions } from '@stoa/shared/components/Toast';
import { Button } from '@stoa/shared/components/Button';
import { useSubscriptions, useRevokeSubscription } from '../../hooks/useSubscriptions';
import { ExportConfigModal } from '../../components/subscriptions/ExportConfigModal';
import { mcpServersService } from '../../services/mcpServers';
import { apiSubscriptionsService } from '../../services/apiSubscriptions';
import type { APISubscriptionResponse } from '../../services/apiSubscriptions';
import { useAuth } from '../../contexts/AuthContext';
import { StatCardWithIconSkeleton, ServerCardSkeletonGrid } from '../../components/skeletons';
import type { MCPSubscription } from '../../types';

type StatusFilter = 'all' | 'active' | 'expired' | 'revoked' | 'pending' | 'suspended';
type TabType = 'servers' | 'tools' | 'apis';

const statusConfig: Record<
  string,
  {
    label: string;
    color: string;
    bgColor: string;
    icon: typeof CheckCircle;
  }
> = {
  active: {
    label: 'Active',
    color: 'text-green-700 dark:text-green-400',
    bgColor: 'bg-green-100 dark:bg-green-900/30',
    icon: CheckCircle,
  },
  expired: {
    label: 'Expired',
    color: 'text-amber-700 dark:text-amber-400',
    bgColor: 'bg-amber-100 dark:bg-amber-900/30',
    icon: Clock,
  },
  revoked: {
    label: 'Revoked',
    color: 'text-red-700 dark:text-red-400',
    bgColor: 'bg-red-100 dark:bg-red-900/30',
    icon: XCircle,
  },
  pending: {
    label: 'Pending',
    color: 'text-blue-700 dark:text-blue-400',
    bgColor: 'bg-blue-100 dark:bg-blue-900/30',
    icon: Clock,
  },
  suspended: {
    label: 'Suspended',
    color: 'text-orange-700 dark:text-orange-400',
    bgColor: 'bg-orange-100 dark:bg-orange-900/30',
    icon: AlertCircle,
  },
};

type ModalState = {
  type: 'export';
  subscription: MCPSubscription;
} | null;

type RevokeState = {
  confirmId: string | null;
  revokingId: string | null;
};

export function MySubscriptions() {
  const { isAuthenticated, accessToken } = useAuth();
  const toast = useToastActions();
  const queryClient = useQueryClient();

  // 5 useState total (was 11)
  const [activeTab, setActiveTab] = useState<TabType>('servers');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [activeModal, setActiveModal] = useState<ModalState>(null);
  const [revokeState, setRevokeState] = useState<RevokeState>({
    confirmId: null,
    revokingId: null,
  });

  const isReady = isAuthenticated && !!accessToken;

  // Server subscriptions via React Query (replaces 3 useState + 1 useEffect)
  const {
    data: serverSubscriptions = [],
    isLoading: serverSubsLoading,
    error: serverSubsErrorObj,
  } = useQuery({
    queryKey: ['server-subscriptions'],
    queryFn: () => mcpServersService.getMyServerSubscriptions(),
    enabled: isReady,
  });

  const serverSubsError = serverSubsErrorObj
    ? serverSubsErrorObj instanceof Error
      ? serverSubsErrorObj.message
      : 'Failed to load server subscriptions'
    : null;

  // Tool subscriptions (legacy) — already React Query
  const {
    data: subscriptionsData,
    isLoading: toolSubsLoading,
    isError: toolSubsError,
    error: toolError,
  } = useSubscriptions();

  // API subscriptions (classic — approved/rejected by tenant admin in Console)
  const { data: apiSubsData, isLoading: apiSubsLoading } = useQuery({
    queryKey: ['api-subscriptions'],
    queryFn: () => apiSubscriptionsService.listMySubscriptions(),
    enabled: isReady,
  });

  const apiSubscriptions: APISubscriptionResponse[] = apiSubsData?.items || [];

  const filteredApiSubs = apiSubscriptions.filter((sub) => {
    if (statusFilter !== 'all' && sub.status !== statusFilter) return false;
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      return (
        sub.application_name?.toLowerCase().includes(query) ||
        sub.api_name?.toLowerCase().includes(query)
      );
    }
    return true;
  });

  const revokeMutation = useRevokeSubscription();

  const handleRevokeSubscription = (subscriptionId: string) => {
    setRevokeState((prev) => ({ ...prev, confirmId: subscriptionId }));
  };

  const confirmRevoke = async () => {
    if (!revokeState.confirmId) return;
    setRevokeState((prev) => ({ ...prev, revokingId: prev.confirmId }));
    try {
      await revokeMutation.mutateAsync(revokeState.confirmId);
      toast.success('Subscription revoked', 'Your subscription has been deactivated.');
    } catch (err) {
      toast.error(
        'Failed to revoke subscription',
        err instanceof Error ? err.message : 'An error occurred'
      );
    } finally {
      setRevokeState({ confirmId: null, revokingId: null });
    }
  };

  const refetchAll = () => {
    queryClient.invalidateQueries({ queryKey: ['server-subscriptions'] });
    queryClient.invalidateQueries({ queryKey: ['subscriptions'] });
    queryClient.invalidateQueries({ queryKey: ['api-subscriptions'] });
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
      return (
        sub.server?.displayName?.toLowerCase().includes(query) ||
        sub.server_id?.toLowerCase().includes(query)
      );
    }
    return true;
  });

  // Calculate stats
  const activeServerCount = serverSubscriptions.filter((s) => s.status === 'active').length;
  const activeToolCount = toolSubscriptions.filter(
    (s: MCPSubscription) => s.status === 'active'
  ).length;
  const totalActiveCount = activeServerCount + activeToolCount;
  const totalUsage = toolSubscriptions.reduce(
    (acc: number, s: MCPSubscription) => acc + (s.usage_count || 0),
    0
  );

  const activeApiCount = apiSubscriptions.filter((s) => s.status === 'active').length;
  const pendingApiCount = apiSubscriptions.filter((s) => s.status === 'pending').length;

  const isLoading = serverSubsLoading || toolSubsLoading || apiSubsLoading;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">My Subscriptions</h1>
          <p className="text-neutral-500 dark:text-neutral-400 mt-1">
            Manage your MCP Server and Tool subscriptions
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={refetchAll}
            disabled={isLoading}
            title="Refresh"
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          </Button>
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
            <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-primary-50 dark:bg-primary-900/30 rounded-lg">
                  <Key className="h-5 w-5 text-primary-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-neutral-900 dark:text-white">
                    {totalActiveCount}
                  </p>
                  <p className="text-sm text-neutral-500 dark:text-neutral-400">
                    Active Subscriptions
                  </p>
                </div>
              </div>
            </div>
            <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                  <Server className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-neutral-900 dark:text-white">
                    {activeServerCount}
                  </p>
                  <p className="text-sm text-neutral-500 dark:text-neutral-400">
                    Server Subscriptions
                  </p>
                </div>
              </div>
            </div>
            <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-green-50 dark:bg-green-900/20 rounded-lg">
                  <TrendingUp className="h-5 w-5 text-green-600 dark:text-green-400" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-neutral-900 dark:text-white">
                    {totalUsage.toLocaleString()}
                  </p>
                  <p className="text-sm text-neutral-500 dark:text-neutral-400">Total API Calls</p>
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Tabs */}
      <div className="border-b border-neutral-200 dark:border-neutral-700">
        <nav className="flex gap-8">
          <button
            onClick={() => setActiveTab('servers')}
            className={`pb-4 px-1 border-b-2 font-medium text-sm transition-colors ${
              activeTab === 'servers'
                ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                : 'border-transparent text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200'
            }`}
          >
            <span className="flex items-center gap-2">
              <Server className="h-4 w-4" />
              MCP Servers
              {activeServerCount > 0 && (
                <span className="px-2 py-0.5 text-xs bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-400 rounded-full">
                  {activeServerCount}
                </span>
              )}
            </span>
          </button>
          <button
            onClick={() => setActiveTab('tools')}
            className={`pb-4 px-1 border-b-2 font-medium text-sm transition-colors ${
              activeTab === 'tools'
                ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                : 'border-transparent text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200'
            }`}
          >
            <span className="flex items-center gap-2">
              <Wrench className="h-4 w-4" />
              Individual Tools
              {activeToolCount > 0 && (
                <span className="px-2 py-0.5 text-xs bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-400 rounded-full">
                  {activeToolCount}
                </span>
              )}
            </span>
          </button>
          <button
            onClick={() => setActiveTab('apis')}
            className={`pb-4 px-1 border-b-2 font-medium text-sm transition-colors ${
              activeTab === 'apis'
                ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                : 'border-transparent text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200'
            }`}
          >
            <span className="flex items-center gap-2">
              <CreditCard className="h-4 w-4" />
              API Subscriptions
              {(activeApiCount > 0 || pendingApiCount > 0) && (
                <span className="px-2 py-0.5 text-xs bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-400 rounded-full">
                  {pendingApiCount > 0 ? `${pendingApiCount} pending` : activeApiCount}
                </span>
              )}
            </span>
          </button>
        </nav>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-neutral-400 dark:text-neutral-500" />
          <input
            type="text"
            placeholder={
              activeTab === 'servers' ? 'Search by server name...' : 'Search by tool name...'
            }
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 dark:bg-neutral-800 dark:text-white"
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-neutral-500 dark:text-neutral-400" />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
            className="px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 dark:bg-neutral-800 dark:text-white"
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
          {serverSubsLoading && <ServerCardSkeletonGrid count={4} columns={2} />}

          {serverSubsError && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6">
              <div className="flex items-start gap-3">
                <AlertCircle className="h-5 w-5 text-red-500 dark:text-red-400 mt-0.5" />
                <div>
                  <h3 className="font-medium text-red-800 dark:text-red-300">
                    Failed to load server subscriptions
                  </h3>
                  <p className="text-sm text-red-600 dark:text-red-400 mt-1">{serverSubsError}</p>
                </div>
              </div>
            </div>
          )}

          {!serverSubsLoading && !serverSubsError && filteredServerSubs.length === 0 && (
            <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-12 text-center">
              <div className="inline-flex p-4 bg-neutral-100 dark:bg-neutral-700 rounded-full mb-4">
                <Server className="h-8 w-8 text-neutral-400 dark:text-neutral-500" />
              </div>
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-white mb-2">
                No Server Subscriptions
              </h2>
              <p className="text-neutral-500 dark:text-neutral-400 max-w-md mx-auto mb-6">
                Subscribe to an MCP Server to get access to all its tools with your OAuth2
                credentials.
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
                const enabledTools =
                  sub.tool_access?.filter((t) => t.status === 'enabled').length || 0;
                const totalTools = sub.tool_access?.length || 0;

                return (
                  <div
                    key={sub.id}
                    className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-5 hover:shadow-md transition-shadow"
                  >
                    <div className="flex items-start justify-between mb-3">
                      <div className="p-2 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                        <Server className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                      </div>
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded ${status.bgColor} ${status.color}`}
                      >
                        <StatusIcon className="h-3 w-3" />
                        {status.label}
                      </span>
                    </div>

                    <h3 className="font-semibold text-neutral-900 dark:text-white mb-1">
                      {sub.server?.displayName || sub.server_id}
                    </h3>
                    <p className="text-sm text-neutral-500 dark:text-neutral-400 mb-3 line-clamp-2">
                      {sub.server?.description || 'MCP Server'}
                    </p>

                    {/* Tools access summary */}
                    <div className="flex items-center gap-2 text-sm text-neutral-600 dark:text-neutral-400 mb-2">
                      <Wrench className="h-4 w-4" />
                      <span>
                        {enabledTools} / {totalTools} tools enabled
                      </span>
                    </div>

                    <div className="text-sm text-neutral-500 dark:text-neutral-400 space-y-1 mt-3">
                      <p>Created: {new Date(sub.created_at).toLocaleDateString()}</p>
                      {sub.last_used_at && (
                        <p>Last used: {new Date(sub.last_used_at).toLocaleDateString()}</p>
                      )}
                    </div>

                    {sub.status === 'active' && (
                      <div className="mt-4 pt-4 border-t border-neutral-100 dark:border-neutral-700 flex items-center justify-between">
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
          {toolSubsLoading && <ServerCardSkeletonGrid count={6} columns={3} />}

          {toolSubsError && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6">
              <div className="flex items-start gap-3">
                <AlertCircle className="h-5 w-5 text-red-500 dark:text-red-400 mt-0.5" />
                <div>
                  <h3 className="font-medium text-red-800 dark:text-red-300">
                    Failed to load tool subscriptions
                  </h3>
                  <p className="text-sm text-red-600 dark:text-red-400 mt-1">
                    {(toolError as Error)?.message || 'An unexpected error occurred'}
                  </p>
                </div>
              </div>
            </div>
          )}

          {!toolSubsLoading && !toolSubsError && filteredToolSubs.length === 0 && (
            <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-12 text-center">
              <div className="inline-flex p-4 bg-neutral-100 dark:bg-neutral-700 rounded-full mb-4">
                <Wrench className="h-8 w-8 text-neutral-400 dark:text-neutral-500" />
              </div>
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-white mb-2">
                No Tool Subscriptions
              </h2>
              <p className="text-neutral-500 dark:text-neutral-400 max-w-md mx-auto mb-6">
                Individual tool subscriptions are legacy. We recommend using MCP Server
                subscriptions instead.
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
                    className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-5 hover:shadow-md transition-shadow"
                  >
                    <div className="flex items-start justify-between mb-3">
                      <div className="p-2 bg-primary-50 dark:bg-primary-900/30 rounded-lg">
                        <Key className="h-5 w-5 text-primary-600" />
                      </div>
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded ${status.bgColor} ${status.color}`}
                      >
                        <StatusIcon className="h-3 w-3" />
                        {status.label}
                      </span>
                    </div>

                    <h3 className="font-semibold text-neutral-900 dark:text-white mb-1">
                      {subscription.tool_id}
                    </h3>

                    <div className="text-sm text-neutral-500 dark:text-neutral-400 space-y-1 mt-2">
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
                      <div className="mt-4 pt-4 border-t border-neutral-100 dark:border-neutral-700 flex items-center justify-between">
                        <button
                          onClick={() => setActiveModal({ type: 'export', subscription })}
                          className="inline-flex items-center gap-1 text-sm text-green-600 hover:text-green-700 font-medium"
                        >
                          <Download className="h-3 w-3" />
                          Export
                        </button>
                        <button
                          onClick={() => handleRevokeSubscription(subscription.id)}
                          disabled={revokeState.revokingId === subscription.id}
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

      {/* API Subscriptions Tab */}
      {activeTab === 'apis' && (
        <>
          {apiSubsLoading ? (
            <ServerCardSkeletonGrid count={3} />
          ) : filteredApiSubs.length === 0 ? (
            <div className="text-center py-12">
              <CreditCard className="h-12 w-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-neutral-900 dark:text-white mb-1">
                No API subscriptions
              </h3>
              <p className="text-neutral-500 dark:text-neutral-400">
                Subscribe to APIs from the{' '}
                <Link to="/discover" className="text-primary-600 hover:underline">
                  API Catalog
                </Link>
              </p>
            </div>
          ) : (
            <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 overflow-hidden">
              <table className="min-w-full divide-y divide-neutral-200 dark:divide-neutral-700">
                <thead className="bg-neutral-50 dark:bg-neutral-900/50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 uppercase">
                      Application
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 uppercase">
                      API
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 uppercase">
                      Plan
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 uppercase">
                      Status
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 uppercase">
                      Created
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-200 dark:divide-neutral-700">
                  {filteredApiSubs.map((sub) => {
                    const cfg = statusConfig[sub.status] || statusConfig.active;
                    return (
                      <tr key={sub.id} className="hover:bg-neutral-50 dark:hover:bg-neutral-700/50">
                        <td className="px-4 py-3 text-sm font-medium text-neutral-900 dark:text-white">
                          {sub.application_name}
                        </td>
                        <td className="px-4 py-3 text-sm text-neutral-600 dark:text-neutral-300">
                          {sub.api_name}
                          <span className="text-xs text-neutral-400 ml-1">v{sub.api_version}</span>
                        </td>
                        <td className="px-4 py-3 text-sm text-neutral-500">
                          {sub.plan_name || '—'}
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${cfg.color} ${cfg.bgColor}`}
                          >
                            <cfg.icon className="h-3 w-3" />
                            {cfg.label}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-sm text-neutral-500">
                          {new Date(sub.created_at).toLocaleDateString()}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* Export Config Modal */}
      {activeModal?.type === 'export' && (
        <ExportConfigModal
          subscription={activeModal.subscription}
          isOpen={true}
          onClose={() => setActiveModal(null)}
        />
      )}

      {/* Revoke Confirmation Dialog */}
      <ConfirmDialog
        open={!!revokeState.confirmId}
        title="Revoke Subscription"
        message="Are you sure you want to revoke this subscription? Access will be deactivated immediately."
        confirmLabel="Revoke"
        variant="danger"
        onConfirm={confirmRevoke}
        onCancel={() => setRevokeState({ confirmId: null, revokingId: null })}
        loading={revokeState.revokingId === revokeState.confirmId}
      />
    </div>
  );
}

export default MySubscriptions;
