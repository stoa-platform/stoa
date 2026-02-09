/**
 * Consumers Page
 *
 * Lists external API consumers with stats, search, and creation modal (CAB-1121).
 */

import { useState, useMemo } from 'react';
import {
  Plus,
  Users,
  Loader2,
  AlertCircle,
  RefreshCw,
  Search,
  CheckCircle,
  PauseCircle,
  ShieldOff,
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { useConsumers, useCreateConsumer } from '../../hooks/useConsumers';
import { ConsumerCard } from '../../components/consumers/ConsumerCard';
import { CreateConsumerModal } from '../../components/consumers/CreateConsumerModal';
import type { Consumer, ConsumerCreateRequest } from '../../types';

export function ConsumersPage() {
  const { user } = useAuth();
  const tenantId = user?.tenant_id || '';

  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');

  const {
    data: consumersData,
    isLoading,
    isError,
    error,
    refetch,
  } = useConsumers(tenantId || undefined);
  const createMutation = useCreateConsumer(tenantId);

  const consumers = useMemo(() => consumersData?.items || [], [consumersData?.items]);

  // Filter consumers by search and status
  const filteredConsumers = useMemo(() => {
    return consumers.filter((c: Consumer) => {
      const matchesSearch =
        !searchQuery ||
        c.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        c.external_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
        c.email.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesStatus = statusFilter === 'all' || c.status === statusFilter;
      return matchesSearch && matchesStatus;
    });
  }, [consumers, searchQuery, statusFilter]);

  // Stats
  const stats = useMemo(() => {
    const total = consumers.length;
    const active = consumers.filter((c: Consumer) => c.status === 'active').length;
    const suspended = consumers.filter((c: Consumer) => c.status === 'suspended').length;
    const blocked = consumers.filter((c: Consumer) => c.status === 'blocked').length;
    return { total, active, suspended, blocked };
  }, [consumers]);

  const handleCreateConsumer = async (data: ConsumerCreateRequest) => {
    setCreateError(null);
    try {
      await createMutation.mutateAsync(data);
      setIsCreateModalOpen(false);
    } catch (err) {
      setCreateError((err as Error)?.message || 'Failed to create consumer');
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Consumers</h1>
          <p className="text-gray-500 dark:text-neutral-400 mt-1">
            Manage your external API consumers
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => refetch()}
            disabled={isLoading}
            className="p-2 text-gray-500 hover:text-gray-700 dark:hover:text-neutral-200 hover:bg-gray-100 dark:hover:bg-neutral-700 rounded-lg transition-colors disabled:opacity-50"
            title="Refresh"
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={() => setIsCreateModalOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
          >
            <Plus className="h-4 w-4" />
            Register Consumer
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      {!isLoading && !isError && consumers.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 p-4">
            <div className="flex items-center gap-2 mb-1">
              <Users className="h-4 w-4 text-gray-400" />
              <span className="text-sm text-gray-500 dark:text-neutral-400">Total</span>
            </div>
            <p className="text-2xl font-bold text-gray-900 dark:text-white">{stats.total}</p>
          </div>
          <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 p-4">
            <div className="flex items-center gap-2 mb-1">
              <CheckCircle className="h-4 w-4 text-green-500" />
              <span className="text-sm text-gray-500 dark:text-neutral-400">Active</span>
            </div>
            <p className="text-2xl font-bold text-green-600 dark:text-green-400">{stats.active}</p>
          </div>
          <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 p-4">
            <div className="flex items-center gap-2 mb-1">
              <PauseCircle className="h-4 w-4 text-amber-500" />
              <span className="text-sm text-gray-500 dark:text-neutral-400">Suspended</span>
            </div>
            <p className="text-2xl font-bold text-amber-600 dark:text-amber-400">
              {stats.suspended}
            </p>
          </div>
          <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 p-4">
            <div className="flex items-center gap-2 mb-1">
              <ShieldOff className="h-4 w-4 text-red-500" />
              <span className="text-sm text-gray-500 dark:text-neutral-400">Blocked</span>
            </div>
            <p className="text-2xl font-bold text-red-600 dark:text-red-400">{stats.blocked}</p>
          </div>
        </div>
      )}

      {/* Search & Filters */}
      {!isLoading && !isError && consumers.length > 0 && (
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by name, ID, or email..."
              className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            />
          </div>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-4 py-2 border border-gray-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          >
            <option value="all">All statuses</option>
            <option value="active">Active</option>
            <option value="suspended">Suspended</option>
            <option value="blocked">Blocked</option>
          </select>
        </div>
      )}

      {/* Loading state */}
      {isLoading && (
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 p-12 text-center">
          <Loader2 className="h-8 w-8 text-primary-600 animate-spin mx-auto mb-4" />
          <p className="text-gray-500 dark:text-neutral-400">Loading consumers...</p>
        </div>
      )}

      {/* Error state */}
      {isError && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
            <div>
              <h3 className="font-medium text-red-800 dark:text-red-300">
                Failed to load consumers
              </h3>
              <p className="text-sm text-red-600 dark:text-red-400 mt-1">
                {(error as Error)?.message || 'An unexpected error occurred'}
              </p>
              <button
                onClick={() => refetch()}
                className="mt-3 px-4 py-2 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded-lg hover:bg-red-200 dark:hover:bg-red-900/50 text-sm font-medium transition-colors"
              >
                Try Again
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Empty state */}
      {!isLoading && !isError && consumers.length === 0 && (
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 p-12 text-center">
          <div className="inline-flex p-4 bg-gray-100 dark:bg-neutral-700 rounded-full mb-4">
            <Users className="h-8 w-8 text-gray-400 dark:text-neutral-500" />
          </div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
            No Consumers Yet
          </h2>
          <p className="text-gray-500 dark:text-neutral-400 max-w-md mx-auto mb-6">
            Register your first API consumer to start managing external access to your APIs. Each
            consumer gets their own OAuth credentials.
          </p>
          <button
            onClick={() => setIsCreateModalOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
          >
            <Plus className="h-4 w-4" />
            Register Your First Consumer
          </button>
        </div>
      )}

      {/* Filtered empty state */}
      {!isLoading && !isError && consumers.length > 0 && filteredConsumers.length === 0 && (
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 p-8 text-center">
          <Search className="h-8 w-8 text-gray-300 dark:text-neutral-600 mx-auto mb-3" />
          <p className="text-gray-500 dark:text-neutral-400">
            No consumers match your search criteria
          </p>
        </div>
      )}

      {/* Consumers grid */}
      {!isLoading && !isError && filteredConsumers.length > 0 && (
        <>
          <div className="text-sm text-gray-500 dark:text-neutral-400">
            {filteredConsumers.length === 1
              ? '1 consumer'
              : `${filteredConsumers.length} consumers`}
            {filteredConsumers.length !== consumers.length &&
              ` (filtered from ${consumers.length})`}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredConsumers.map((consumer: Consumer) => (
              <ConsumerCard key={consumer.id} consumer={consumer} />
            ))}
          </div>
        </>
      )}

      {/* Create Modal */}
      <CreateConsumerModal
        isOpen={isCreateModalOpen}
        onClose={() => {
          setIsCreateModalOpen(false);
          setCreateError(null);
        }}
        onSubmit={handleCreateConsumer}
        isLoading={createMutation.isPending}
        error={createError}
      />
    </div>
  );
}

export default ConsumersPage;
