/**
 * My Subscriptions Page
 *
 * Lists user's MCP Tool subscriptions with usage statistics.
 * Uses MCP Gateway endpoints (mcp.stoa.cab-i.com)
 *
 * Reference: Linear CAB-247
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  CreditCard,
  TrendingUp,
  AlertCircle,
  Loader2,
  RefreshCw,
  Wrench,
  Search,
  Filter,
  Key,
  Clock,
  CheckCircle,
  XCircle,
  Eye,
  Shield,
} from 'lucide-react';
import { useSubscriptions, useRevokeSubscription, useToggleTotpRequirement, useRotateApiKey } from '../../hooks/useSubscriptions';
import { RevealKeyModal } from '../../components/subscriptions/RevealKeyModal';
import { RotateKeyModal } from '../../components/subscriptions/RotateKeyModal';
import type { MCPSubscription } from '../../types';

type StatusFilter = 'all' | 'active' | 'expired' | 'revoked';

const statusConfig: Record<MCPSubscription['status'], {
  label: string;
  color: string;
  bgColor: string;
  icon: typeof CheckCircle;
}> = {
  active: { label: 'Active', color: 'text-green-700', bgColor: 'bg-green-100', icon: CheckCircle },
  expired: { label: 'Expired', color: 'text-amber-700', bgColor: 'bg-amber-100', icon: Clock },
  revoked: { label: 'Revoked', color: 'text-red-700', bgColor: 'bg-red-100', icon: XCircle },
};

export function MySubscriptions() {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [revealModalSubscription, setRevealModalSubscription] = useState<MCPSubscription | null>(null);
  const [rotateModalSubscription, setRotateModalSubscription] = useState<MCPSubscription | null>(null);

  const {
    data: subscriptionsData,
    isLoading,
    isError,
    error,
    refetch,
  } = useSubscriptions();

  const revokeMutation = useRevokeSubscription();
  const toggleTotpMutation = useToggleTotpRequirement();
  const rotateKeyMutation = useRotateApiKey();

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

  // Get subscriptions array from response
  const allSubscriptions = subscriptionsData?.subscriptions || [];

  // Filter subscriptions
  const filteredSubscriptions = allSubscriptions.filter((sub: MCPSubscription) => {
    // Status filter
    if (statusFilter !== 'all' && sub.status !== statusFilter) {
      return false;
    }
    // Search filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      const toolId = sub.tool_id?.toLowerCase() || '';
      return toolId.includes(query);
    }
    return true;
  });

  // Calculate stats
  const activeCount = allSubscriptions.filter((s: MCPSubscription) => s.status === 'active').length;
  const totalUsage = allSubscriptions.reduce((acc: number, s: MCPSubscription) => {
    return acc + (s.usage_count || 0);
  }, 0);
  const expiredCount = allSubscriptions.filter((s: MCPSubscription) => s.status === 'expired').length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">My Subscriptions</h1>
          <p className="text-gray-500 mt-1">
            Manage your MCP tool subscriptions and API keys
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => refetch()}
            disabled={isLoading}
            className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50"
            title="Refresh"
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
          <Link
            to="/tools"
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
          >
            <Wrench className="h-4 w-4" />
            Browse Tools
          </Link>
        </div>
      </div>

      {/* Stats Overview */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary-50 rounded-lg">
              <Key className="h-5 w-5 text-primary-600" />
            </div>
            <div>
              {isLoading ? (
                <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
              ) : (
                <>
                  <p className="text-2xl font-bold text-gray-900">{activeCount}</p>
                  <p className="text-sm text-gray-500">Active Subscriptions</p>
                </>
              )}
            </div>
          </div>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-green-50 rounded-lg">
              <TrendingUp className="h-5 w-5 text-green-600" />
            </div>
            <div>
              {isLoading ? (
                <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
              ) : (
                <>
                  <p className="text-2xl font-bold text-gray-900">{totalUsage.toLocaleString()}</p>
                  <p className="text-sm text-gray-500">Total API Calls</p>
                </>
              )}
            </div>
          </div>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-amber-50 rounded-lg">
              <AlertCircle className="h-5 w-5 text-amber-600" />
            </div>
            <div>
              {isLoading ? (
                <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
              ) : (
                <>
                  <p className="text-2xl font-bold text-gray-900">{expiredCount}</p>
                  <p className="text-sm text-gray-500">Expired</p>
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        {/* Search */}
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search by tool name..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          />
        </div>

        {/* Status Filter */}
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-gray-500" />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
            className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          >
            <option value="all">All Status</option>
            <option value="active">Active</option>
            <option value="expired">Expired</option>
            <option value="revoked">Revoked</option>
          </select>
        </div>
      </div>

      {/* Loading state */}
      {isLoading && (
        <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
          <Loader2 className="h-8 w-8 text-primary-600 animate-spin mx-auto mb-4" />
          <p className="text-gray-500">Loading subscriptions...</p>
        </div>
      )}

      {/* Error state */}
      {isError && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-6">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
            <div>
              <h3 className="font-medium text-red-800">Failed to load subscriptions</h3>
              <p className="text-sm text-red-600 mt-1">
                {(error as Error)?.message || 'An unexpected error occurred'}
              </p>
              <button
                onClick={() => refetch()}
                className="mt-3 px-4 py-2 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 text-sm font-medium transition-colors"
              >
                Try Again
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Empty state */}
      {!isLoading && !isError && filteredSubscriptions.length === 0 && (
        <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
          <div className="inline-flex p-4 bg-gray-100 rounded-full mb-4">
            <CreditCard className="h-8 w-8 text-gray-400" />
          </div>
          {allSubscriptions.length === 0 ? (
            <>
              <h2 className="text-xl font-semibold text-gray-900 mb-2">No Subscriptions Yet</h2>
              <p className="text-gray-500 max-w-md mx-auto mb-6">
                Subscribe to MCP tools to start using them with AI agents.
                Browse the tools catalog to find tools that match your needs.
              </p>
              <Link
                to="/tools"
                className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
              >
                <Wrench className="h-4 w-4" />
                Browse Tools Catalog
              </Link>
            </>
          ) : (
            <>
              <h2 className="text-xl font-semibold text-gray-900 mb-2">No Matching Subscriptions</h2>
              <p className="text-gray-500 max-w-md mx-auto mb-6">
                No subscriptions match your current filters. Try adjusting your search or filters.
              </p>
              <button
                onClick={() => {
                  setSearchQuery('');
                  setStatusFilter('all');
                }}
                className="text-primary-600 hover:text-primary-700 font-medium"
              >
                Clear Filters
              </button>
            </>
          )}
        </div>
      )}

      {/* Subscriptions Grid */}
      {!isLoading && !isError && filteredSubscriptions.length > 0 && (
        <>
          <div className="text-sm text-gray-500">
            {filteredSubscriptions.length === 1
              ? '1 subscription'
              : `${filteredSubscriptions.length} subscriptions`}
            {statusFilter !== 'all' && ` (${statusFilter})`}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredSubscriptions.map((subscription: MCPSubscription) => {
              const status = statusConfig[subscription.status];
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

                  {/* API Key prefix */}
                  {subscription.api_key_prefix && (
                    <div className="mt-2 font-mono text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded inline-block">
                      {subscription.api_key_prefix}...
                    </div>
                  )}

                  <div className="text-sm text-gray-500 space-y-1 mt-2">
                    <p>Created: {new Date(subscription.created_at).toLocaleDateString()}</p>
                    {subscription.expires_at && (
                      <p>Expires: {new Date(subscription.expires_at).toLocaleDateString()}</p>
                    )}
                    {subscription.last_used_at && (
                      <p>Last used: {new Date(subscription.last_used_at).toLocaleDateString()}</p>
                    )}
                    {subscription.usage_count !== undefined && (
                      <p>Usage: {subscription.usage_count.toLocaleString()} calls</p>
                    )}
                  </div>

                  {/* 2FA indicator */}
                  {subscription.totp_required && (
                    <div className="mt-2 flex items-center gap-1 text-xs text-primary-600">
                      <Shield className="h-3 w-3" />
                      2FA Protected
                    </div>
                  )}

                  {/* Grace period indicator (CAB-314) */}
                  {subscription.has_active_grace_period && subscription.previous_key_expires_at && (
                    <div className="mt-2 flex items-center gap-1 text-xs text-amber-600 bg-amber-50 px-2 py-1 rounded">
                      <Clock className="h-3 w-3" />
                      Grace period until {new Date(subscription.previous_key_expires_at).toLocaleString()}
                    </div>
                  )}

                  {subscription.status === 'active' && (
                    <div className="mt-4 pt-4 border-t border-gray-100 space-y-3">
                      {/* Action buttons row 1 */}
                      <div className="flex items-center justify-between">
                        {/* Reveal Key button */}
                        <button
                          onClick={() => setRevealModalSubscription(subscription)}
                          className="inline-flex items-center gap-1 text-sm text-primary-600 hover:text-primary-700 font-medium"
                        >
                          <Eye className="h-3 w-3" />
                          Reveal Key
                        </button>

                        {/* Rotate Key button (CAB-314) */}
                        <button
                          onClick={() => setRotateModalSubscription(subscription)}
                          disabled={subscription.has_active_grace_period}
                          className="inline-flex items-center gap-1 text-sm text-amber-600 hover:text-amber-700 font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                          title={subscription.has_active_grace_period ? 'Wait for grace period to end' : 'Rotate API key with grace period'}
                        >
                          <RefreshCw className="h-3 w-3" />
                          Rotate Key
                        </button>
                      </div>

                      {/* Action buttons row 2 */}
                      <div className="flex items-center justify-between">
                        {/* Toggle 2FA */}
                        <button
                          onClick={() => toggleTotpMutation.mutate({
                            id: subscription.id,
                            enabled: !subscription.totp_required
                          })}
                          disabled={toggleTotpMutation.isPending}
                          className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 font-medium disabled:opacity-50"
                          title={subscription.totp_required ? 'Disable 2FA' : 'Enable 2FA'}
                        >
                          <Shield className={`h-3 w-3 ${subscription.totp_required ? 'text-primary-600' : ''}`} />
                          {subscription.totp_required ? '2FA On' : '2FA Off'}
                        </button>

                        {/* Revoke button */}
                        <button
                          onClick={() => handleRevokeSubscription(subscription.id)}
                          disabled={revokingId === subscription.id}
                          className="text-sm text-red-600 hover:text-red-700 font-medium disabled:opacity-50"
                        >
                          {revokingId === subscription.id ? (
                            <span className="inline-flex items-center gap-1">
                              <Loader2 className="h-3 w-3 animate-spin" />
                              Revoking...
                            </span>
                          ) : (
                            'Revoke'
                          )}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
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

      {/* Rotate Key Modal (CAB-314) */}
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
    </div>
  );
}

export default MySubscriptions;
