/**
 * Admin Prospects Dashboard (CAB-911)
 *
 * Conversion cockpit for tracking prospects during the Feb 26 demo.
 * Shows metrics, filterable table, and detail modal with timeline.
 */
import { useState, useCallback, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import {
  useProspects,
  useProspectsMetrics,
  useProspectDetail,
  useExportProspectsCSV,
  useRefreshProspects,
} from '../hooks/useProspects';
import type {
  ProspectSummary,
  ProspectDetail,
  ProspectsMetricsResponse,
  ProspectStatus,
  ProspectsFilters,
} from '../types';
import {
  Users,
  TrendingUp,
  Clock,
  Star,
  Download,
  RefreshCw,
  X,
  ChevronLeft,
  ChevronRight,
  AlertTriangle,
  Activity,
  Eye,
  MousePointerClick,
} from 'lucide-react';

// Debounce hook
function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const handler = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(handler);
  }, [value, delay]);

  return debouncedValue;
}

const PAGE_SIZE = 25;

// Status badge colors
const statusColors: Record<ProspectStatus, { bg: string; text: string; dot: string }> = {
  converted: { bg: 'bg-green-100', text: 'text-green-800', dot: 'bg-green-500' },
  opened: { bg: 'bg-blue-100', text: 'text-blue-800', dot: 'bg-blue-500' },
  pending: { bg: 'bg-gray-100', text: 'text-gray-800', dot: 'bg-gray-400' },
  expired: { bg: 'bg-red-100', text: 'text-red-800', dot: 'bg-red-400' },
};

// NPS category colors
const npsColors = {
  promoter: 'bg-green-100 text-green-800',
  passive: 'bg-yellow-100 text-yellow-800',
  detractor: 'bg-red-100 text-red-800',
};

// Format seconds to human readable
function formatDuration(seconds: number | undefined | null): string {
  if (seconds === undefined || seconds === null) return '—';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${Math.round(seconds / 3600)}h`;
}

// Format date to locale string
function formatDate(date: string | undefined | null): string {
  if (!date) return '—';
  return new Date(date).toLocaleDateString('fr-FR', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function AdminProspects() {
  const { hasRole } = useAuth();

  // State
  const [filters, setFilters] = useState<ProspectsFilters>({});
  const [page, setPage] = useState(1);
  const [selectedProspectId, setSelectedProspectId] = useState<string | null>(null);
  const [companySearch, setCompanySearch] = useState('');

  const debouncedCompany = useDebounce(companySearch, 300);

  // Queries
  const {
    data: prospectsData,
    isLoading: prospectsLoading,
    error: prospectsError,
  } = useProspects(
    { ...filters, company: debouncedCompany || undefined, page, limit: PAGE_SIZE },
    { enabled: hasRole('cpi-admin') }
  );

  const { data: metrics, isLoading: metricsLoading } = useProspectsMetrics(
    { date_from: filters.date_from, date_to: filters.date_to },
    { enabled: hasRole('cpi-admin') }
  );

  const { data: selectedProspect, isLoading: detailLoading } = useProspectDetail(
    selectedProspectId,
    { enabled: !!selectedProspectId }
  );

  const exportMutation = useExportProspectsCSV();
  const { refresh } = useRefreshProspects();

  // Reset page when filters change
  useEffect(() => {
    setPage(1);
  }, [filters, debouncedCompany]);

  // Handlers
  const handleStatusFilter = useCallback((status: ProspectStatus | '') => {
    setFilters((prev) => ({ ...prev, status: status || undefined }));
  }, []);

  const handleExport = useCallback(() => {
    exportMutation.mutate({ ...filters, company: debouncedCompany || undefined });
  }, [exportMutation, filters, debouncedCompany]);

  // RBAC check
  if (!hasRole('cpi-admin')) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <AlertTriangle className="h-12 w-12 text-red-500 mx-auto mb-4" />
          <h1 className="text-xl font-semibold text-gray-900 mb-2">Access Denied</h1>
          <p className="text-gray-600">Platform admin role required to view this page.</p>
        </div>
      </div>
    );
  }

  const totalPages = prospectsData
    ? Math.ceil(prospectsData.meta.total / PAGE_SIZE)
    : 0;

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Prospects Dashboard</h1>
            <p className="text-gray-500 mt-1">Conversion tracking for demo prospects</p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => refresh()}
              className="flex items-center gap-2 px-3 py-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
            >
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
            <button
              onClick={handleExport}
              disabled={exportMutation.isPending}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              <Download className="h-4 w-4" />
              {exportMutation.isPending ? 'Exporting...' : 'Export CSV'}
            </button>
          </div>
        </div>

        {/* Metrics Header */}
        <MetricsHeader metrics={metrics} isLoading={metricsLoading} />

        {/* Filters */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex-1 min-w-[200px]">
              <input
                type="text"
                placeholder="Search by company..."
                value={companySearch}
                onChange={(e) => setCompanySearch(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>
            <select
              value={filters.status || ''}
              onChange={(e) => handleStatusFilter(e.target.value as ProspectStatus | '')}
              className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="">All Statuses</option>
              <option value="pending">Pending</option>
              <option value="opened">Opened</option>
              <option value="converted">Converted</option>
              <option value="expired">Expired</option>
            </select>
            <span className="text-sm text-gray-500">
              {prospectsData?.meta.total ?? 0} prospects
            </span>
          </div>
        </div>

        {/* Table */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
          {prospectsLoading ? (
            <div className="p-8 text-center">
              <RefreshCw className="h-8 w-8 animate-spin text-blue-600 mx-auto" />
              <p className="mt-2 text-gray-500">Loading prospects...</p>
            </div>
          ) : prospectsError ? (
            <div className="p-8 text-center">
              <AlertTriangle className="h-8 w-8 text-red-500 mx-auto" />
              <p className="mt-2 text-red-600">Failed to load prospects</p>
            </div>
          ) : !prospectsData?.data.length ? (
            <div className="p-8 text-center">
              <Users className="h-8 w-8 text-gray-400 mx-auto" />
              <p className="mt-2 text-gray-500">No prospects found</p>
            </div>
          ) : (
            <>
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Company / Email
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Time to Tool
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      NPS
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Events
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Last Activity
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {prospectsData.data.map((prospect) => (
                    <ProspectRow
                      key={prospect.id}
                      prospect={prospect}
                      onClick={() => setSelectedProspectId(prospect.id)}
                    />
                  ))}
                </tbody>
              </table>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="bg-gray-50 px-6 py-3 flex items-center justify-between border-t">
                  <span className="text-sm text-gray-500">
                    Page {page} of {totalPages}
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      disabled={page === 1}
                      className="p-2 rounded-lg hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <ChevronLeft className="h-5 w-5" />
                    </button>
                    <button
                      onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                      disabled={page === totalPages}
                      className="p-2 rounded-lg hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <ChevronRight className="h-5 w-5" />
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Detail Modal */}
        {selectedProspectId && (
          <ProspectDetailModal
            prospect={selectedProspect}
            isLoading={detailLoading}
            onClose={() => setSelectedProspectId(null)}
          />
        )}
      </div>
    </div>
  );
}

// =============================================================================
// Sub-components
// =============================================================================

function MetricsHeader({
  metrics,
  isLoading,
}: {
  metrics: ProspectsMetricsResponse | undefined;
  isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-20 mb-2" />
            <div className="h-8 bg-gray-200 rounded w-16" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      <MetricCard
        title="Invites"
        value={metrics?.total_invited ?? 0}
        subtitle={`${metrics?.total_active ?? 0} active`}
        icon={Users}
        color="bg-blue-500"
      />
      <MetricCard
        title="Active"
        value={metrics?.total_active ?? 0}
        subtitle={`${metrics?.by_status?.converted ?? 0} converted`}
        icon={TrendingUp}
        color="bg-green-500"
      />
      <MetricCard
        title="Avg Time to Tool"
        value={formatDuration(metrics?.avg_time_to_tool)}
        subtitle="from first visit"
        icon={Clock}
        color="bg-purple-500"
      />
      <MetricCard
        title="NPS Score"
        value={metrics?.avg_nps?.toFixed(1) ?? '—'}
        subtitle={`${metrics?.nps?.promoters ?? 0} promoters`}
        icon={Star}
        color="bg-amber-500"
      />
    </div>
  );
}

function MetricCard({
  title,
  value,
  subtitle,
  icon: Icon,
  color,
}: {
  title: string;
  value: string | number;
  subtitle: string;
  icon: typeof Users;
  color: string;
}) {
  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <div className="flex items-center gap-4">
        <div className={`rounded-lg p-3 ${color}`}>
          <Icon className="h-6 w-6 text-white" />
        </div>
        <div>
          <p className="text-sm font-medium text-gray-500">{title}</p>
          <p className="text-2xl font-bold text-gray-900">{value}</p>
          <p className="text-xs text-gray-400">{subtitle}</p>
        </div>
      </div>
    </div>
  );
}

function ProspectRow({
  prospect,
  onClick,
}: {
  prospect: ProspectSummary;
  onClick: () => void;
}) {
  const statusStyle = statusColors[prospect.status];

  return (
    <tr
      onClick={onClick}
      className="hover:bg-gray-50 cursor-pointer transition-colors"
    >
      <td className="px-6 py-4">
        <div className="font-medium text-gray-900">{prospect.company}</div>
        <div className="text-sm text-gray-500">{prospect.email}</div>
      </td>
      <td className="px-6 py-4">
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${statusStyle.bg} ${statusStyle.text}`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${statusStyle.dot}`} />
          {prospect.status}
        </span>
      </td>
      <td className="px-6 py-4 text-sm text-gray-900">
        {formatDuration(prospect.time_to_first_tool_seconds)}
      </td>
      <td className="px-6 py-4">
        {prospect.nps_score ? (
          <span
            className={`px-2 py-1 rounded-full text-xs font-medium ${npsColors[prospect.nps_category!]}`}
          >
            {prospect.nps_score}/10
          </span>
        ) : (
          <span className="text-gray-400">—</span>
        )}
      </td>
      <td className="px-6 py-4 text-sm text-gray-900">{prospect.total_events}</td>
      <td className="px-6 py-4 text-sm text-gray-500">
        {formatDate(prospect.last_activity_at)}
      </td>
    </tr>
  );
}

function ProspectDetailModal({
  prospect,
  isLoading,
  onClose,
}: {
  prospect: ProspectDetail | undefined;
  isLoading: boolean;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <div>
            {isLoading ? (
              <div className="h-6 bg-gray-200 rounded w-40 animate-pulse" />
            ) : prospect ? (
              <>
                <h2 className="text-lg font-semibold text-gray-900">
                  {prospect.company}
                </h2>
                <p className="text-sm text-gray-500">{prospect.email}</p>
              </>
            ) : null}
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <X className="h-5 w-5 text-gray-500" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {isLoading ? (
            <div className="animate-pulse space-y-4">
              <div className="h-4 bg-gray-200 rounded w-3/4" />
              <div className="h-4 bg-gray-200 rounded w-1/2" />
              <div className="h-32 bg-gray-200 rounded" />
            </div>
          ) : prospect ? (
            <>
              {/* Info Grid */}
              <div className="grid grid-cols-2 gap-4">
                <InfoItem label="Status" value={prospect.status} />
                <InfoItem label="Source" value={prospect.source || '—'} />
                <InfoItem label="Invited" value={formatDate(prospect.created_at)} />
                <InfoItem label="First Visit" value={formatDate(prospect.opened_at)} />
                <InfoItem
                  label="Time to Tool"
                  value={formatDuration(prospect.metrics.time_to_first_tool_seconds)}
                />
                <InfoItem
                  label="NPS"
                  value={prospect.nps_score ? `${prospect.nps_score}/10` : '—'}
                />
              </div>

              {/* NPS Feedback */}
              {prospect.nps_comment && (
                <div className="bg-blue-50 rounded-lg p-4">
                  <p className="text-sm font-medium text-blue-800 mb-1">Feedback</p>
                  <p className="text-blue-700">&ldquo;{prospect.nps_comment}&rdquo;</p>
                </div>
              )}

              {/* Metrics */}
              <div className="grid grid-cols-3 gap-4">
                <StatBox
                  icon={MousePointerClick}
                  label="Tools Called"
                  value={prospect.metrics.tools_called_count}
                />
                <StatBox
                  icon={Eye}
                  label="Pages Viewed"
                  value={prospect.metrics.pages_viewed_count}
                />
                <StatBox
                  icon={AlertTriangle}
                  label="Errors"
                  value={prospect.metrics.errors_count}
                  highlight={prospect.metrics.errors_count > 0}
                />
              </div>

              {/* Timeline */}
              <div>
                <h3 className="text-sm font-medium text-gray-900 mb-3">
                  Timeline ({prospect.timeline.length} events)
                </h3>
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {prospect.timeline.map((event) => (
                    <TimelineEvent key={event.id} event={event} />
                  ))}
                </div>
              </div>

              {/* Errors */}
              {prospect.errors.length > 0 && (
                <div>
                  <h3 className="text-sm font-medium text-red-700 mb-3">
                    Errors ({prospect.errors.length})
                  </h3>
                  <div className="space-y-2">
                    {prospect.errors.map((event) => (
                      <div
                        key={event.id}
                        className="bg-red-50 rounded-lg p-3 text-sm text-red-700"
                      >
                        <span className="text-xs text-red-500">
                          {formatDate(event.timestamp)}
                        </span>
                        <span className="mx-2">—</span>
                        {(event.metadata as { error?: string }).error || 'Unknown error'}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <p className="text-gray-500">Prospect not found</p>
          )}
        </div>
      </div>
    </div>
  );
}

function InfoItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-gray-500">{label}</p>
      <p className="text-sm font-medium text-gray-900 capitalize">{value}</p>
    </div>
  );
}

function StatBox({
  icon: Icon,
  label,
  value,
  highlight,
}: {
  icon: typeof Activity;
  label: string;
  value: number;
  highlight?: boolean;
}) {
  return (
    <div
      className={`rounded-lg p-3 text-center ${
        highlight ? 'bg-red-50' : 'bg-gray-50'
      }`}
    >
      <Icon
        className={`h-5 w-5 mx-auto ${highlight ? 'text-red-500' : 'text-gray-400'}`}
      />
      <p className="text-lg font-semibold text-gray-900 mt-1">{value}</p>
      <p className="text-xs text-gray-500">{label}</p>
    </div>
  );
}

function TimelineEvent({
  event,
}: {
  event: ProspectDetail['timeline'][0];
}) {
  const eventIcons: Record<string, typeof Activity> = {
    invite_opened: Eye,
    tool_called: MousePointerClick,
    page_viewed: Eye,
    error_encountered: AlertTriangle,
  };

  const Icon = eventIcons[event.event_type] || Activity;

  return (
    <div className="flex items-start gap-3 text-sm">
      <span className="text-xs text-gray-400 w-20 flex-shrink-0">
        {new Date(event.timestamp).toLocaleTimeString('fr-FR', {
          hour: '2-digit',
          minute: '2-digit',
        })}
      </span>
      <Icon className="h-4 w-4 text-gray-400 mt-0.5 flex-shrink-0" />
      <div className="flex-1">
        <span className="font-medium text-gray-700">{event.event_type}</span>
        {event.is_first_tool_call && (
          <span className="ml-2 text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded">
            First!
          </span>
        )}
        {(event.metadata as { tool?: string; page?: string }).tool && (
          <span className="ml-2 text-gray-500">
            {(event.metadata as { tool: string }).tool}
          </span>
        )}
        {(event.metadata as { page?: string }).page && (
          <span className="ml-2 text-gray-500">
            {(event.metadata as { page: string }).page}
          </span>
        )}
      </div>
    </div>
  );
}
