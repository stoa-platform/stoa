/**
 * My Subscriptions Page
 *
 * Lists user's API subscriptions with usage statistics.
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  CreditCard,
  TrendingUp,
  AlertCircle,
  Loader2,
  RefreshCw,
  BookOpen,
  Search,
  Filter,
} from 'lucide-react';
import { useSubscriptions, useCancelSubscription } from '../../hooks/useSubscriptions';
import { SubscriptionCard } from '../../components/subscriptions/SubscriptionCard';
import type { APISubscription } from '../../types';

type StatusFilter = 'all' | 'active' | 'pending' | 'suspended' | 'cancelled';

export function MySubscriptions() {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [cancellingId, setCancellingId] = useState<string | null>(null);

  const {
    data: subscriptions,
    isLoading,
    isError,
    error,
    refetch,
  } = useSubscriptions();

  const cancelMutation = useCancelSubscription();

  const handleCancelSubscription = async (subscriptionId: string) => {
    if (confirm('Are you sure you want to cancel this subscription?')) {
      setCancellingId(subscriptionId);
      try {
        await cancelMutation.mutateAsync(subscriptionId);
      } finally {
        setCancellingId(null);
      }
    }
  };

  // Filter subscriptions
  const filteredSubscriptions = subscriptions?.items.filter((sub: APISubscription) => {
    // Status filter
    if (statusFilter !== 'all' && sub.status !== statusFilter) {
      return false;
    }
    // Search filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      const apiName = sub.api?.name?.toLowerCase() || '';
      const appName = sub.application?.name?.toLowerCase() || '';
      return apiName.includes(query) || appName.includes(query);
    }
    return true;
  }) || [];

  // Calculate stats
  const activeCount = subscriptions?.items.filter((s: APISubscription) => s.status === 'active').length || 0;
  const totalCallsToday = subscriptions?.items.reduce((acc: number, s: APISubscription) => {
    return acc + (s.usage?.callsToday || 0);
  }, 0) || 0;
  const pendingCount = subscriptions?.items.filter((s: APISubscription) => s.status === 'pending').length || 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">My Subscriptions</h1>
          <p className="text-gray-500 mt-1">
            Manage your API subscriptions and monitor usage
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
            to="/apis"
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
          >
            <BookOpen className="h-4 w-4" />
            Browse APIs
          </Link>
        </div>
      </div>

      {/* Stats Overview */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary-50 rounded-lg">
              <CreditCard className="h-5 w-5 text-primary-600" />
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
                  <p className="text-2xl font-bold text-gray-900">{totalCallsToday.toLocaleString()}</p>
                  <p className="text-sm text-gray-500">API Calls Today</p>
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
                  <p className="text-2xl font-bold text-gray-900">{pendingCount}</p>
                  <p className="text-sm text-gray-500">Pending Approval</p>
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
            placeholder="Search by API or application name..."
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
            <option value="pending">Pending</option>
            <option value="suspended">Suspended</option>
            <option value="cancelled">Cancelled</option>
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
          {subscriptions?.items.length === 0 ? (
            <>
              <h2 className="text-xl font-semibold text-gray-900 mb-2">No Subscriptions Yet</h2>
              <p className="text-gray-500 max-w-md mx-auto mb-6">
                Subscribe to APIs to start using them in your applications.
                Browse the API catalog to find APIs that match your needs.
              </p>
              <Link
                to="/apis"
                className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
              >
                <BookOpen className="h-4 w-4" />
                Browse API Catalog
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
            {filteredSubscriptions.map((subscription: APISubscription) => (
              <SubscriptionCard
                key={subscription.id}
                subscription={subscription}
                onCancel={handleCancelSubscription}
                isCancelling={cancellingId === subscription.id}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export default MySubscriptions;
