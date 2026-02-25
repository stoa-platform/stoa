import { useState, useEffect, useCallback, Fragment } from 'react';
import {
  RefreshCw,
  ClipboardList,
  Download,
  Search,
  Filter,
  Shield,
  AlertTriangle,
  User,
  Settings,
  Key,
  Globe,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { apiService } from '../services/api';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import { StatCard } from '@stoa/shared/components/StatCard';
import { EmptyState } from '@stoa/shared/components/EmptyState';

const AUTO_REFRESH_INTERVAL = 30_000;
const ACTIVE_TENANT_KEY = 'stoa-active-tenant';
const PAGE_SIZE = 20;

type AuditAction =
  | 'create'
  | 'update'
  | 'delete'
  | 'deploy'
  | 'login'
  | 'logout'
  | 'access_denied'
  | 'config_change'
  | string;
type AuditStatus = 'success' | 'failure' | 'warning' | string;

interface AuditEntry {
  id: string;
  timestamp: string;
  actor: string;
  actor_type: 'user' | 'system' | 'service';
  action: AuditAction;
  resource_type: string;
  resource_id: string;
  resource_name: string;
  status: AuditStatus;
  details: string;
  ip_address?: string;
  tenant_id: string;
}

interface AuditFilters {
  action?: string;
  status?: string;
  date_from?: string;
  date_to?: string;
  search?: string;
}

const ACTION_ICONS: Record<string, typeof User> = {
  create: Settings,
  update: Settings,
  delete: AlertTriangle,
  deploy: Globe,
  login: Key,
  logout: Key,
  access_denied: Shield,
  config_change: Settings,
};

const STATUS_STYLES: Record<string, { bg: string; text: string }> = {
  success: {
    bg: 'bg-green-100 dark:bg-green-900/30',
    text: 'text-green-700 dark:text-green-400',
  },
  failure: {
    bg: 'bg-red-100 dark:bg-red-900/30',
    text: 'text-red-700 dark:text-red-400',
  },
  warning: {
    bg: 'bg-yellow-100 dark:bg-yellow-900/30',
    text: 'text-yellow-700 dark:text-yellow-400',
  },
};

function formatTimestamp(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleString('fr-FR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export function AuditLog() {
  const { user, isReady } = useAuth();
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<AuditFilters>({});
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [exporting, setExporting] = useState(false);

  const tenantId = localStorage.getItem(ACTIVE_TENANT_KEY) || user?.tenant_id || 'default';

  const loadData = useCallback(async () => {
    try {
      const params: Record<string, any> = {
        page,
        page_size: PAGE_SIZE,
      };
      if (filters.action) params.action = filters.action;
      if (filters.status) params.status = filters.status;
      if (filters.date_from) params.date_from = filters.date_from;
      if (filters.date_to) params.date_to = filters.date_to;
      if (filters.search) params.search = filters.search;

      const { data } = await apiService.get<{
        entries: AuditEntry[];
        total: number;
        page: number;
        page_size: number;
        has_more: boolean;
      }>(`/v1/audit/${tenantId}`, { params });

      setEntries(data.entries || []);
      setTotal(data.total || 0);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load audit log');
      setEntries([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [tenantId, page, filters]);

  useEffect(() => {
    if (isReady) loadData();
  }, [isReady, loadData]);

  useEffect(() => {
    if (!isReady) return;
    const interval = setInterval(loadData, AUTO_REFRESH_INTERVAL);
    return () => clearInterval(interval);
  }, [isReady, loadData]);

  const handleExport = async (format: 'csv' | 'json') => {
    setExporting(true);
    try {
      const { data } = await apiService.get<string>(`/v1/audit/${tenantId}/export/${format}`, {
        params: {
          ...(filters.action && { action: filters.action }),
          ...(filters.status && { status: filters.status }),
          ...(filters.date_from && { date_from: filters.date_from }),
          ...(filters.date_to && { date_to: filters.date_to }),
        },
      });
      const blob = new Blob([typeof data === 'string' ? data : JSON.stringify(data, null, 2)], {
        type: format === 'csv' ? 'text/csv' : 'application/json',
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit-log-${tenantId}-${new Date().toISOString().slice(0, 10)}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError(`Failed to export as ${format.toUpperCase()}`);
    } finally {
      setExporting(false);
    }
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  const successCount = entries.filter((e) => e.status === 'success').length;
  const failureCount = entries.filter((e) => e.status === 'failure').length;
  const uniqueActors = new Set(entries.map((e) => e.actor)).size;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Audit Log</h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            Track platform actions, configuration changes, and access events for{' '}
            <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300">
              {tenantId}
            </span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <button
              onClick={() => handleExport('csv')}
              disabled={exporting}
              className="flex items-center gap-2 border border-neutral-300 dark:border-neutral-600 text-neutral-700 dark:text-neutral-300 px-3 py-2 rounded-lg text-sm hover:bg-neutral-50 dark:hover:bg-neutral-700 disabled:opacity-50"
            >
              <Download className="h-4 w-4" />
              Export
            </button>
          </div>
          <button
            onClick={loadData}
            className="flex items-center gap-2 border border-neutral-300 dark:border-neutral-600 text-neutral-700 dark:text-neutral-300 px-3 py-2 rounded-lg text-sm hover:bg-neutral-50 dark:hover:bg-neutral-700"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg flex items-center justify-between">
          <span className="text-sm">{error}</span>
          <button
            onClick={() => setError(null)}
            className="text-red-500 hover:text-red-700 dark:hover:text-red-300"
          >
            &times;
          </button>
        </div>
      )}

      {loading && entries.length === 0 ? (
        <div className="space-y-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <CardSkeleton key={i} className="h-24" />
            ))}
          </div>
          <CardSkeleton className="h-96" />
        </div>
      ) : (
        <>
          {/* KPI Row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard
              label="Total Events"
              value={total.toLocaleString()}
              icon={ClipboardList}
              colorClass="text-blue-600"
              subtitle="All audit entries"
            />
            <StatCard
              label="Successful"
              value={successCount}
              icon={Settings}
              colorClass="text-green-600"
              subtitle="On this page"
            />
            <StatCard
              label="Failed"
              value={failureCount}
              icon={AlertTriangle}
              colorClass={failureCount > 0 ? 'text-red-600' : 'text-green-600'}
              subtitle="On this page"
            />
            <StatCard
              label="Unique Actors"
              value={uniqueActors}
              icon={User}
              colorClass="text-blue-600"
              subtitle="On this page"
            />
          </div>

          {/* Filter Bar */}
          <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
            <div className="flex items-center gap-3">
              {/* Search */}
              <div className="flex-1 relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-neutral-400" />
                <input
                  type="text"
                  placeholder="Search by actor, resource, or details..."
                  value={filters.search || ''}
                  onChange={(e) => {
                    setFilters((f) => ({ ...f, search: e.target.value || undefined }));
                    setPage(1);
                  }}
                  className="w-full pl-10 pr-4 py-2 text-sm border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>

              {/* Toggle filters */}
              <button
                onClick={() => setShowFilters(!showFilters)}
                className={`flex items-center gap-2 px-3 py-2 text-sm border rounded-lg ${
                  showFilters
                    ? 'border-blue-500 text-blue-600 bg-blue-50 dark:bg-blue-900/20'
                    : 'border-neutral-300 dark:border-neutral-600 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-700'
                }`}
              >
                <Filter className="h-4 w-4" />
                Filters
              </button>
            </div>

            {/* Expanded filters */}
            {showFilters && (
              <div className="flex items-center gap-3 mt-3 pt-3 border-t border-neutral-100 dark:border-neutral-700">
                <select
                  value={filters.action || ''}
                  onChange={(e) => {
                    setFilters((f) => ({ ...f, action: e.target.value || undefined }));
                    setPage(1);
                  }}
                  className="text-sm border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300 rounded-lg px-3 py-2"
                >
                  <option value="">All Actions</option>
                  <option value="create">Create</option>
                  <option value="update">Update</option>
                  <option value="delete">Delete</option>
                  <option value="deploy">Deploy</option>
                  <option value="login">Login</option>
                  <option value="access_denied">Access Denied</option>
                </select>
                <select
                  value={filters.status || ''}
                  onChange={(e) => {
                    setFilters((f) => ({ ...f, status: e.target.value || undefined }));
                    setPage(1);
                  }}
                  className="text-sm border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300 rounded-lg px-3 py-2"
                >
                  <option value="">All Statuses</option>
                  <option value="success">Success</option>
                  <option value="failure">Failure</option>
                  <option value="warning">Warning</option>
                </select>
                <input
                  type="date"
                  value={filters.date_from || ''}
                  onChange={(e) => {
                    setFilters((f) => ({ ...f, date_from: e.target.value || undefined }));
                    setPage(1);
                  }}
                  className="text-sm border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300 rounded-lg px-3 py-2"
                />
                <span className="text-xs text-neutral-400">to</span>
                <input
                  type="date"
                  value={filters.date_to || ''}
                  onChange={(e) => {
                    setFilters((f) => ({ ...f, date_to: e.target.value || undefined }));
                    setPage(1);
                  }}
                  className="text-sm border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300 rounded-lg px-3 py-2"
                />
                <button
                  onClick={() => {
                    setFilters({});
                    setPage(1);
                  }}
                  className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                >
                  Clear
                </button>
              </div>
            )}
          </div>

          {/* Audit Log Table */}
          <div className="bg-white dark:bg-neutral-800 rounded-lg shadow overflow-hidden">
            {entries.length > 0 ? (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase border-b border-neutral-100 dark:border-neutral-700">
                        <th className="px-4 py-3 w-8" />
                        <th className="px-4 py-3">Timestamp</th>
                        <th className="px-4 py-3">Actor</th>
                        <th className="px-4 py-3">Action</th>
                        <th className="px-4 py-3">Resource</th>
                        <th className="px-4 py-3 text-center">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-neutral-50 dark:divide-neutral-700">
                      {entries.map((entry) => {
                        const ActionIcon = ACTION_ICONS[entry.action] || Settings;
                        const statusStyle = STATUS_STYLES[entry.status] || STATUS_STYLES.success;
                        const isExpanded = expandedId === entry.id;

                        return (
                          <Fragment key={entry.id}>
                            <tr
                              className="hover:bg-neutral-50 dark:hover:bg-neutral-750 cursor-pointer"
                              onClick={() => setExpandedId(isExpanded ? null : entry.id)}
                            >
                              <td className="px-4 py-3">
                                {isExpanded ? (
                                  <ChevronDown className="h-4 w-4 text-neutral-400" />
                                ) : (
                                  <ChevronRight className="h-4 w-4 text-neutral-400" />
                                )}
                              </td>
                              <td className="px-4 py-3 text-xs text-neutral-600 dark:text-neutral-400 whitespace-nowrap">
                                {formatTimestamp(entry.timestamp)}
                              </td>
                              <td className="px-4 py-3">
                                <div className="flex items-center gap-2">
                                  <User className="h-3.5 w-3.5 text-neutral-400" />
                                  <span className="text-neutral-900 dark:text-white">
                                    {entry.actor}
                                  </span>
                                </div>
                              </td>
                              <td className="px-4 py-3">
                                <div className="flex items-center gap-2">
                                  <ActionIcon className="h-3.5 w-3.5 text-neutral-400" />
                                  <span className="text-neutral-700 dark:text-neutral-300 capitalize">
                                    {entry.action.replace(/_/g, ' ')}
                                  </span>
                                </div>
                              </td>
                              <td className="px-4 py-3">
                                <span className="font-mono text-xs text-neutral-700 dark:text-neutral-300">
                                  {entry.resource_type}/{entry.resource_name || entry.resource_id}
                                </span>
                              </td>
                              <td className="px-4 py-3 text-center">
                                <span
                                  className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${statusStyle.bg} ${statusStyle.text}`}
                                >
                                  {entry.status}
                                </span>
                              </td>
                            </tr>
                            {isExpanded && (
                              <tr>
                                <td
                                  colSpan={6}
                                  className="px-8 py-4 bg-neutral-50 dark:bg-neutral-850 border-b border-neutral-100 dark:border-neutral-700"
                                >
                                  <div className="grid grid-cols-2 gap-4 text-sm">
                                    <div>
                                      <span className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                                        Details
                                      </span>
                                      <p className="mt-1 text-neutral-700 dark:text-neutral-300">
                                        {entry.details || 'No additional details'}
                                      </p>
                                    </div>
                                    <div className="space-y-2">
                                      <div>
                                        <span className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                                          Resource ID
                                        </span>
                                        <p className="mt-1 font-mono text-xs text-neutral-700 dark:text-neutral-300">
                                          {entry.resource_id}
                                        </p>
                                      </div>
                                      {entry.ip_address && (
                                        <div>
                                          <span className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                                            IP Address
                                          </span>
                                          <p className="mt-1 font-mono text-xs text-neutral-700 dark:text-neutral-300">
                                            {entry.ip_address}
                                          </p>
                                        </div>
                                      )}
                                      <div>
                                        <span className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                                          Actor Type
                                        </span>
                                        <p className="mt-1 text-neutral-700 dark:text-neutral-300 capitalize">
                                          {entry.actor_type}
                                        </p>
                                      </div>
                                    </div>
                                  </div>
                                </td>
                              </tr>
                            )}
                          </Fragment>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                {/* Pagination */}
                {totalPages > 1 && (
                  <div className="flex items-center justify-between px-4 py-3 border-t border-neutral-100 dark:border-neutral-700">
                    <span className="text-xs text-neutral-500 dark:text-neutral-400">
                      Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} of{' '}
                      {total}
                    </span>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setPage((p) => Math.max(1, p - 1))}
                        disabled={page === 1}
                        className="px-3 py-1 text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg disabled:opacity-50 hover:bg-neutral-50 dark:hover:bg-neutral-700 text-neutral-700 dark:text-neutral-300"
                      >
                        Previous
                      </button>
                      <span className="text-sm text-neutral-700 dark:text-neutral-300">
                        {page} / {totalPages}
                      </span>
                      <button
                        onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                        disabled={page === totalPages}
                        className="px-3 py-1 text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg disabled:opacity-50 hover:bg-neutral-50 dark:hover:bg-neutral-700 text-neutral-700 dark:text-neutral-300"
                      >
                        Next
                      </button>
                    </div>
                  </div>
                )}
              </>
            ) : (
              <EmptyState
                title="No audit entries"
                description={
                  Object.keys(filters).length > 0
                    ? 'No entries match the current filters. Try adjusting your search criteria.'
                    : 'Audit events will appear here once platform actions are performed.'
                }
                illustration={<ClipboardList className="h-12 w-12" />}
              />
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default AuditLog;
