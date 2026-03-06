/**
 * Internal APIs page — platform-level proxy backend management (CAB-1727).
 *
 * Read-only dashboard showing registered internal API backends with
 * status, rate limits, circuit breaker state, and health checks.
 * Visible to cpi-admin only (RBAC-gated in sidebar).
 */

import { useState, useMemo, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Search, RefreshCw, CheckCircle2, XCircle, AlertTriangle, Clock } from 'lucide-react';
import { useToastActions } from '@stoa/shared/components/Toast';
import { EmptyState } from '@stoa/shared/components/EmptyState';
import {
  proxyBackendService,
  type ProxyBackendResponse,
  type ProxyBackendHealthStatus,
} from '../../services/proxyBackendService';

const statusConfig = {
  active: {
    color: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
    label: 'Active',
  },
  disabled: {
    color: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
    label: 'Disabled',
  },
} as const;

const authTypeLabels: Record<string, string> = {
  api_key: 'API Key',
  bearer: 'Bearer',
  basic: 'Basic',
  oauth2_cc: 'OAuth2 CC',
};

const PAGE_SIZE = 20;

export function InternalApisList() {
  const toast = useToastActions();
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [page, setPage] = useState(1);
  const [healthResults, setHealthResults] = useState<Record<string, ProxyBackendHealthStatus>>({});
  const [checkingHealth, setCheckingHealth] = useState<string | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ['proxy-backends'],
    queryFn: () => proxyBackendService.list(),
  });

  const filteredBackends = useMemo(() => {
    let items = data?.items || [];
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      items = items.filter(
        (b) =>
          b.name.toLowerCase().includes(term) ||
          b.display_name?.toLowerCase().includes(term) ||
          b.base_url.toLowerCase().includes(term)
      );
    }
    if (statusFilter !== 'all') {
      items = items.filter((b) => b.status === statusFilter);
    }
    return items;
  }, [data?.items, searchTerm, statusFilter]);

  const paginatedBackends = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return filteredBackends.slice(start, start + PAGE_SIZE);
  }, [filteredBackends, page]);

  const totalPages = Math.max(1, Math.ceil(filteredBackends.length / PAGE_SIZE));

  const handleHealthCheck = useCallback(
    async (backend: ProxyBackendResponse) => {
      setCheckingHealth(backend.id);
      try {
        const result = await proxyBackendService.healthCheck(backend.id);
        setHealthResults((prev) => ({ ...prev, [backend.id]: result }));
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Health check failed';
        toast.error('Health check failed', message);
      } finally {
        setCheckingHealth(null);
      }
    },
    [toast]
  );

  const handleRefresh = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['proxy-backends'] });
    setHealthResults({});
  }, [queryClient]);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex justify-between items-center">
          <div className="h-8 w-48 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
        </div>
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow">
          <div className="p-6 space-y-4">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-12 bg-neutral-100 dark:bg-neutral-700 rounded animate-pulse"
              />
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Internal APIs</h1>
          <p className="text-neutral-500 dark:text-neutral-400 mt-1">
            Platform-level API backends proxied through the STOA Gateway
          </p>
        </div>
        <button
          onClick={handleRefresh}
          className="flex items-center gap-2 px-3 py-2 text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 dark:text-neutral-300"
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg">
          {error instanceof Error ? error.message : 'Failed to load internal APIs'}
        </div>
      )}

      {/* Summary cards */}
      {data && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <SummaryCard label="Total backends" value={data.total} />
          <SummaryCard
            label="Active"
            value={data.items.filter((b) => b.status === 'active').length}
            color="green"
          />
          <SummaryCard
            label="Rate-limited"
            value={data.items.filter((b) => b.rate_limit_rpm > 0).length}
            color="blue"
          />
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-neutral-400" />
          <input
            type="text"
            placeholder="Search backends..."
            value={searchTerm}
            onChange={(e) => {
              setSearchTerm(e.target.value);
              setPage(1);
            }}
            className="w-full pl-10 pr-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
          className="border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white"
        >
          <option value="all">All statuses</option>
          <option value="active">Active</option>
          <option value="disabled">Disabled</option>
        </select>
      </div>

      {/* Table */}
      {filteredBackends.length === 0 && !isLoading ? (
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow">
          <EmptyState
            variant="apis"
            title={
              searchTerm || statusFilter !== 'all'
                ? 'No matching backends'
                : 'No internal APIs registered'
            }
            description={
              searchTerm || statusFilter !== 'all'
                ? 'Try adjusting your filters.'
                : 'Internal API backends are configured by platform administrators.'
            }
          />
        </div>
      ) : (
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800">
                <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                  Name
                </th>
                <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                  Base URL
                </th>
                <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                  Auth
                </th>
                <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                  Rate Limit
                </th>
                <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                  Circuit Breaker
                </th>
                <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                  Status
                </th>
                <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                  Health
                </th>
              </tr>
            </thead>
            <tbody className="divide-y dark:divide-neutral-700">
              {paginatedBackends.map((backend) => {
                const status = statusConfig[backend.status];
                const health = healthResults[backend.id];
                return (
                  <tr key={backend.id} className="hover:bg-neutral-50 dark:hover:bg-neutral-750">
                    <td className="px-4 py-3">
                      <div className="font-medium text-neutral-900 dark:text-white">
                        {backend.display_name || backend.name}
                      </div>
                      <div className="text-xs text-neutral-500 dark:text-neutral-400 font-mono">
                        {backend.name}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-sm text-neutral-600 dark:text-neutral-300 font-mono truncate max-w-xs">
                      {backend.base_url}
                    </td>
                    <td className="px-4 py-3 text-sm text-neutral-600 dark:text-neutral-300">
                      {authTypeLabels[backend.auth_type] || backend.auth_type}
                    </td>
                    <td className="px-4 py-3 text-sm text-neutral-600 dark:text-neutral-300">
                      {backend.rate_limit_rpm > 0 ? (
                        <span className="inline-flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          {backend.rate_limit_rpm} rpm
                        </span>
                      ) : (
                        <span className="text-neutral-400">Unlimited</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-sm">
                      {backend.circuit_breaker_enabled ? (
                        <span className="inline-flex items-center gap-1 text-green-600 dark:text-green-400">
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          Enabled
                        </span>
                      ) : (
                        <span className="text-neutral-400">Off</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex px-2 py-0.5 text-xs font-medium rounded-full ${status.color}`}
                      >
                        {status.label}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <HealthCell
                        backendId={backend.id}
                        health={health}
                        checking={checkingHealth === backend.id}
                        onCheck={() => handleHealthCheck(backend)}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex justify-between items-center px-4 py-3 border-t dark:border-neutral-700">
              <span className="text-sm text-neutral-500 dark:text-neutral-400">
                {filteredBackends.length} results
              </span>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="px-3 py-1 text-sm border rounded disabled:opacity-50 dark:border-neutral-600 dark:text-neutral-300"
                >
                  Previous
                </button>
                <span className="px-3 py-1 text-sm text-neutral-500 dark:text-neutral-400">
                  {page} / {totalPages}
                </span>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="px-3 py-1 text-sm border rounded disabled:opacity-50 dark:border-neutral-600 dark:text-neutral-300"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SummaryCard({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color?: 'green' | 'blue';
}) {
  const colorClasses = {
    green: 'text-green-600 dark:text-green-400',
    blue: 'text-blue-600 dark:text-blue-400',
  };
  return (
    <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
      <div className="text-sm text-neutral-500 dark:text-neutral-400">{label}</div>
      <div
        className={`text-2xl font-bold mt-1 ${color ? colorClasses[color] : 'text-neutral-900 dark:text-white'}`}
      >
        {value}
      </div>
    </div>
  );
}

function HealthCell({
  backendId: _backendId,
  health,
  checking,
  onCheck,
}: {
  backendId: string;
  health?: ProxyBackendHealthStatus;
  checking: boolean;
  onCheck: () => void;
}) {
  if (checking) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-neutral-500">
        <RefreshCw className="h-3 w-3 animate-spin" />
        Checking...
      </span>
    );
  }

  if (!health) {
    return (
      <button
        onClick={onCheck}
        className="text-xs px-2 py-1 border border-neutral-300 dark:border-neutral-600 rounded hover:bg-neutral-50 dark:hover:bg-neutral-700 dark:text-neutral-300"
      >
        Check
      </button>
    );
  }

  if (health.healthy) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
        <CheckCircle2 className="h-3.5 w-3.5" />
        {health.latency_ms != null ? `${Math.round(health.latency_ms)}ms` : 'Healthy'}
      </span>
    );
  }

  return (
    <span
      className="inline-flex items-center gap-1 text-xs text-red-600 dark:text-red-400"
      title={health.error || undefined}
    >
      {health.status_code && health.status_code >= 500 ? (
        <XCircle className="h-3.5 w-3.5" />
      ) : (
        <AlertTriangle className="h-3.5 w-3.5" />
      )}
      {health.error ? health.error.slice(0, 30) : 'Unhealthy'}
    </span>
  );
}
