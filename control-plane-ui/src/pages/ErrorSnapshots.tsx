import { useState, useEffect, useCallback } from 'react';
import { errorSnapshotsService } from '../services/errorSnapshotsApi';
import { useAuth } from '../contexts/AuthContext';
import type {
  ErrorSnapshotSummary,
  ErrorSnapshotDetail,
  ErrorSnapshotStats,
  ErrorSnapshotFilters,
  SnapshotTrigger,
  SnapshotResolutionStatus,
  SnapshotFiltersResponse,
} from '../types';
import {
  AlertTriangle,
  CheckCircle2,
  AlertCircle,
  Loader2,
  RefreshCw,
  ChevronRight,
  ChevronDown,
  Clock,
  Server,
  Search,
  Copy,
  Check,
  EyeOff,
  Terminal,
} from 'lucide-react';
import { clsx } from 'clsx';

// Trigger type display config
const triggerConfig: Record<string, { label: string; color: string; bg: string }> = {
  '4xx': {
    label: '4xx Client Error',
    color: 'text-yellow-600',
    bg: 'bg-yellow-100 dark:bg-yellow-900/30',
  },
  '5xx': {
    label: '5xx Server Error',
    color: 'text-red-600',
    bg: 'bg-red-100 dark:bg-red-900/30',
  },
  timeout: {
    label: 'Timeout',
    color: 'text-orange-600',
    bg: 'bg-orange-100 dark:bg-orange-900/30',
  },
  manual: {
    label: 'Manual',
    color: 'text-neutral-600 dark:text-neutral-400',
    bg: 'bg-neutral-100 dark:bg-neutral-700',
  },
};

const resolutionConfig: Record<
  SnapshotResolutionStatus,
  { label: string; color: string; bg: string }
> = {
  unresolved: {
    label: 'Unresolved',
    color: 'text-red-600',
    bg: 'bg-red-100 dark:bg-red-900/30',
  },
  investigating: {
    label: 'Investigating',
    color: 'text-yellow-600',
    bg: 'bg-yellow-100 dark:bg-yellow-900/30',
  },
  resolved: {
    label: 'Resolved',
    color: 'text-green-600',
    bg: 'bg-green-100 dark:bg-green-900/30',
  },
  ignored: {
    label: 'Ignored',
    color: 'text-neutral-600 dark:text-neutral-400',
    bg: 'bg-neutral-100 dark:bg-neutral-700',
  },
};

function formatDateTime(isoString?: string): string {
  if (!isoString) return '-';
  const date = new Date(isoString);
  return date.toLocaleString('fr-FR', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

// Stats Card Component
function StatsCard({
  title,
  value,
  subtitle,
  icon: Icon,
  color,
}: {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: typeof AlertTriangle;
  color: string;
}) {
  return (
    <div className="rounded-lg bg-white dark:bg-neutral-800 p-6 shadow-sm">
      <div className="flex items-center gap-4">
        <div className={clsx('rounded-lg p-3', color)}>
          <Icon className="h-6 w-6 text-white" />
        </div>
        <div>
          <p className="text-sm font-medium text-neutral-500 dark:text-neutral-400">{title}</p>
          <p className="text-2xl font-bold text-neutral-900 dark:text-white">{value}</p>
          {subtitle && <p className="text-xs text-neutral-400 dark:text-neutral-500">{subtitle}</p>}
        </div>
      </div>
    </div>
  );
}

// Resolution Status Badge
function ResolutionBadge({
  status,
  onClick,
}: {
  status: SnapshotResolutionStatus;
  onClick?: (e: React.MouseEvent) => void;
}) {
  const cfg = resolutionConfig[status];
  return (
    <button
      onClick={onClick}
      className={clsx(
        'px-2 py-1 rounded-full text-xs font-medium transition-colors',
        cfg.bg,
        cfg.color,
        onClick && 'hover:opacity-80 cursor-pointer'
      )}
    >
      {cfg.label}
    </button>
  );
}

// Replay Command Component
function ReplayCommand({ snapshotId }: { snapshotId: string }) {
  const [command, setCommand] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [visible, setVisible] = useState(false);

  const generateCommand = async () => {
    if (command) {
      setVisible(!visible);
      return;
    }
    setLoading(true);
    try {
      const result = await errorSnapshotsService.generateReplay(snapshotId);
      setCommand(result.curl_command);
      setWarning(result.warning || null);
      setVisible(true);
    } catch (error) {
      console.error('Failed to generate replay command:', error);
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = async () => {
    if (command) {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="mt-4">
      <button
        onClick={generateCommand}
        disabled={loading}
        className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-800"
      >
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : visible ? (
          <EyeOff className="h-4 w-4" />
        ) : (
          <Terminal className="h-4 w-4" />
        )}
        {visible ? 'Hide' : 'Generate'} cURL Command
      </button>

      {visible && command && (
        <div className="mt-2 bg-neutral-900 rounded-lg p-4 relative">
          {warning && (
            <div className="mb-2 text-xs text-yellow-400 flex items-center gap-1">
              <AlertCircle className="h-3 w-3" />
              {warning}
            </div>
          )}
          <button
            onClick={copyToClipboard}
            className="absolute top-2 right-2 text-neutral-400 hover:text-white"
          >
            {copied ? <Check className="h-4 w-4 text-green-400" /> : <Copy className="h-4 w-4" />}
          </button>
          <pre className="text-xs text-green-400 overflow-x-auto whitespace-pre-wrap">
            {command}
          </pre>
        </div>
      )}
    </div>
  );
}

// Snapshot Row Component
function SnapshotRow({
  snapshot,
  isExpanded,
  onToggle,
  onResolutionChange,
}: {
  snapshot: ErrorSnapshotSummary;
  isExpanded: boolean;
  onToggle: () => void;
  onResolutionChange: (status: SnapshotResolutionStatus) => void;
}) {
  const [details, setDetails] = useState<ErrorSnapshotDetail | null>(null);
  const [loading, setLoading] = useState(false);

  const tConfig = triggerConfig[snapshot.trigger] || triggerConfig.manual;

  useEffect(() => {
    if (isExpanded && !details) {
      setLoading(true);
      errorSnapshotsService
        .getSnapshot(snapshot.id)
        .then(setDetails)
        .finally(() => setLoading(false));
    }
  }, [isExpanded, snapshot.id, details]);

  return (
    <div className="border-b border-neutral-100 dark:border-neutral-700 last:border-0">
      {/* Summary row */}
      <div
        className="flex items-center gap-4 p-4 hover:bg-neutral-50 dark:hover:bg-neutral-700 cursor-pointer"
        onClick={onToggle}
      >
        {/* Expand icon */}
        <button className="text-neutral-400">
          {isExpanded ? <ChevronDown className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
        </button>

        {/* Trigger badge */}
        <span
          className={clsx(
            'px-2 py-1 rounded-full text-xs font-medium whitespace-nowrap',
            tConfig.bg,
            tConfig.color
          )}
        >
          {tConfig.label}
        </span>

        {/* HTTP Status */}
        <span
          className={clsx(
            'px-2 py-0.5 rounded text-xs font-mono',
            snapshot.status >= 500
              ? 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400'
              : 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400'
          )}
        >
          {snapshot.status}
        </span>

        {/* Method + Path */}
        <div className="flex-1 min-w-0">
          <p className="text-sm text-neutral-900 dark:text-white truncate">
            <span className="font-mono font-medium">{snapshot.method}</span>{' '}
            <span className="text-neutral-600 dark:text-neutral-400">{snapshot.path}</span>
          </p>
          <div className="flex items-center gap-2 mt-1 text-xs text-neutral-500 dark:text-neutral-400">
            <span className="flex items-center gap-1">
              <Server className="h-3 w-3" />
              {snapshot.source}
            </span>
            <span className="flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {formatDuration(snapshot.duration_ms)}
            </span>
          </div>
        </div>

        {/* Resolution status */}
        <ResolutionBadge
          status={snapshot.resolution_status}
          onClick={(e) => {
            e?.stopPropagation?.();
          }}
        />

        {/* Timestamp */}
        <span className="text-xs text-neutral-400 dark:text-neutral-500 w-24 text-right">
          {formatDateTime(snapshot.timestamp)}
        </span>
      </div>

      {/* Expanded details */}
      {isExpanded && (
        <div className="bg-neutral-50 dark:bg-neutral-900 p-4 border-t border-neutral-100 dark:border-neutral-700">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
            </div>
          ) : details ? (
            <div className="space-y-4">
              {/* Resolution actions */}
              <div className="flex items-center gap-2 pb-4 border-b border-neutral-200 dark:border-neutral-700">
                <span className="text-sm text-neutral-600 dark:text-neutral-400">Set status:</span>
                {(
                  [
                    'unresolved',
                    'investigating',
                    'resolved',
                    'ignored',
                  ] as SnapshotResolutionStatus[]
                ).map((s) => (
                  <button
                    key={s}
                    onClick={() => onResolutionChange(s)}
                    className={clsx(
                      'px-3 py-1 rounded-full text-xs font-medium transition-colors',
                      details.resolution_status === s
                        ? `${resolutionConfig[s].bg} ${resolutionConfig[s].color}`
                        : 'bg-neutral-100 text-neutral-600 hover:bg-neutral-200 dark:bg-neutral-700 dark:text-neutral-400 dark:hover:bg-neutral-600'
                    )}
                  >
                    {resolutionConfig[s].label}
                  </button>
                ))}
              </div>

              <div className="grid grid-cols-3 gap-6">
                {/* Left: Request Info */}
                <div className="space-y-4">
                  <h4 className="font-medium text-neutral-900 dark:text-white">Request</h4>
                  <div className="bg-white dark:bg-neutral-800 rounded-lg p-4 space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-neutral-500 dark:text-neutral-400">Method:</span>
                      <span className="font-mono">{details.request.method}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-neutral-500 dark:text-neutral-400">Path:</span>
                      <span
                        className="font-mono text-xs truncate max-w-48"
                        title={details.request.path}
                      >
                        {details.request.path}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-neutral-500 dark:text-neutral-400">Status:</span>
                      <span className="font-mono">{details.response.status}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-neutral-500 dark:text-neutral-400">Duration:</span>
                      <span className="font-mono">
                        {formatDuration(details.response.duration_ms)}
                      </span>
                    </div>
                    {details.trace_id && (
                      <div className="flex justify-between">
                        <span className="text-neutral-500 dark:text-neutral-400">Trace ID:</span>
                        <span className="font-mono text-xs">{details.trace_id}</span>
                      </div>
                    )}
                    {details.request.client_ip && (
                      <div className="flex justify-between">
                        <span className="text-neutral-500 dark:text-neutral-400">Client IP:</span>
                        <span className="font-mono text-xs">{details.request.client_ip}</span>
                      </div>
                    )}
                  </div>

                  {/* Response body preview */}
                  {details.response.body != null && (
                    <div className="bg-red-50 dark:bg-red-900/20 rounded-lg p-4">
                      <h5 className="font-medium text-red-800 dark:text-red-400 mb-2">
                        Response Body
                      </h5>
                      <div className="text-xs font-mono bg-white/50 dark:bg-neutral-900 rounded p-2 max-h-32 overflow-auto text-red-600 dark:text-red-400">
                        <pre>
                          {typeof details.response.body === 'string'
                            ? details.response.body
                            : JSON.stringify(details.response.body, null, 2)}
                        </pre>
                      </div>
                    </div>
                  )}
                </div>

                {/* Middle: Routing & Backend */}
                <div className="space-y-4">
                  <h4 className="font-medium text-neutral-900 dark:text-white">Routing</h4>
                  <div className="bg-white dark:bg-neutral-800 rounded-lg p-4 space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-neutral-500 dark:text-neutral-400">Source:</span>
                      <span>{details.source}</span>
                    </div>
                    {details.routing.api_name && (
                      <div className="flex justify-between">
                        <span className="text-neutral-500 dark:text-neutral-400">API:</span>
                        <span>
                          {details.routing.api_name}
                          {details.routing.api_version && ` v${details.routing.api_version}`}
                        </span>
                      </div>
                    )}
                    {details.routing.backend_url && (
                      <div className="flex justify-between">
                        <span className="text-neutral-500 dark:text-neutral-400">Backend:</span>
                        <span
                          className="text-xs truncate max-w-40"
                          title={details.routing.backend_url}
                        >
                          {details.routing.backend_url}
                        </span>
                      </div>
                    )}
                  </div>

                  {/* Backend state */}
                  {details.backend_state.health !== 'unknown' && (
                    <div className="bg-white dark:bg-neutral-800 rounded-lg p-4 space-y-2 text-sm">
                      <h5 className="font-medium text-neutral-700 dark:text-neutral-300">
                        Backend Health
                      </h5>
                      <div className="flex justify-between">
                        <span className="text-neutral-500 dark:text-neutral-400">Health:</span>
                        <span
                          className={clsx(
                            'font-medium',
                            details.backend_state.health === 'healthy'
                              ? 'text-green-600'
                              : details.backend_state.health === 'degraded'
                                ? 'text-yellow-600'
                                : 'text-red-600'
                          )}
                        >
                          {details.backend_state.health}
                        </span>
                      </div>
                      {details.backend_state.error_rate_1m != null && (
                        <div className="flex justify-between">
                          <span className="text-neutral-500 dark:text-neutral-400">
                            Error Rate:
                          </span>
                          <span>{(details.backend_state.error_rate_1m * 100).toFixed(1)}%</span>
                        </div>
                      )}
                      {details.backend_state.p99_latency_ms != null && (
                        <div className="flex justify-between">
                          <span className="text-neutral-500 dark:text-neutral-400">
                            P99 Latency:
                          </span>
                          <span>{formatDuration(details.backend_state.p99_latency_ms)}</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Right: Environment */}
                <div className="space-y-4">
                  <h4 className="font-medium text-neutral-900 dark:text-white">Environment</h4>
                  <div className="bg-white dark:bg-neutral-800 rounded-lg p-4 space-y-2 text-sm">
                    {details.environment.pod && (
                      <div className="flex justify-between">
                        <span className="text-neutral-500 dark:text-neutral-400">Pod:</span>
                        <span className="text-xs font-mono truncate max-w-40">
                          {details.environment.pod}
                        </span>
                      </div>
                    )}
                    {details.environment.node && (
                      <div className="flex justify-between">
                        <span className="text-neutral-500 dark:text-neutral-400">Node:</span>
                        <span className="text-xs">{details.environment.node}</span>
                      </div>
                    )}
                    {details.environment.namespace && (
                      <div className="flex justify-between">
                        <span className="text-neutral-500 dark:text-neutral-400">Namespace:</span>
                        <span>{details.environment.namespace}</span>
                      </div>
                    )}
                    <div className="flex justify-between">
                      <span className="text-neutral-500 dark:text-neutral-400">Trigger:</span>
                      <span>{details.trigger}</span>
                    </div>
                  </div>

                  {/* Masked fields warning */}
                  {details.masked_fields.length > 0 && (
                    <div className="bg-yellow-50 dark:bg-yellow-900/20 rounded-lg p-3 text-xs text-yellow-700 dark:text-yellow-400">
                      <p className="font-medium">PII Masked:</p>
                      <p className="mt-1">{details.masked_fields.join(', ')}</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Replay command */}
              <ReplayCommand snapshotId={snapshot.id} />
            </div>
          ) : (
            <p className="text-center text-neutral-500 dark:text-neutral-400 py-4">
              Failed to load details
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// Main Error Snapshots Page
export function ErrorSnapshots() {
  const { isReady } = useAuth();
  const [snapshots, setSnapshots] = useState<ErrorSnapshotSummary[]>([]);
  const [stats, setStats] = useState<ErrorSnapshotStats | null>(null);
  const [filters, setFilters] = useState<ErrorSnapshotFilters>({});
  const [availableFilters, setAvailableFilters] = useState<SnapshotFiltersResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');

  const pageSize = 20;

  const loadData = useCallback(async () => {
    try {
      const activeFilters: ErrorSnapshotFilters = {
        ...filters,
        path_contains: searchQuery || undefined,
      };

      const [snapshotsData, statsData, filtersData] = await Promise.all([
        errorSnapshotsService.getSnapshots(activeFilters, page, pageSize),
        errorSnapshotsService.getStats(),
        availableFilters ? Promise.resolve(availableFilters) : errorSnapshotsService.getFilters(),
      ]);
      setSnapshots(snapshotsData.items);
      setTotal(snapshotsData.total);
      setStats(statsData);
      if (!availableFilters) {
        setAvailableFilters(filtersData);
      }
    } catch (error) {
      console.error('Failed to load error snapshots:', error);
    } finally {
      setLoading(false);
    }
  }, [filters, page, searchQuery, availableFilters]);

  useEffect(() => {
    if (!isReady) return;

    loadData();

    if (autoRefresh) {
      const interval = setInterval(loadData, 10000);
      return () => clearInterval(interval);
    }
  }, [loadData, autoRefresh, isReady]);

  const handleResolutionChange = async (snapshotId: string, status: SnapshotResolutionStatus) => {
    try {
      await errorSnapshotsService.updateResolution(snapshotId, status);
      loadData();
    } catch (error) {
      console.error('Failed to update resolution:', error);
    }
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    loadData();
  };

  const hasNext = page * pageSize < total;

  if (loading && snapshots.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Error Snapshots</h1>
          <p className="text-neutral-500 dark:text-neutral-400">
            Time-travel debugging for gateway errors
          </p>
        </div>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-neutral-600 dark:text-neutral-400">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="rounded border-neutral-300"
            />
            Auto-refresh (10s)
          </label>
          <button
            onClick={loadData}
            className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-4 gap-4">
          <StatsCard
            title="Total Errors"
            value={stats.total}
            subtitle={`${stats.resolution_stats.unresolved} unresolved`}
            icon={AlertTriangle}
            color="bg-red-500"
          />
          <StatsCard
            title="5xx Errors"
            value={stats.by_trigger['5xx'] || 0}
            subtitle="Server errors"
            icon={AlertCircle}
            color="bg-orange-500"
          />
          <StatsCard
            title="Timeouts"
            value={stats.by_trigger['timeout'] || 0}
            subtitle="Request timeouts"
            icon={Clock}
            color="bg-purple-500"
          />
          <StatsCard
            title="Resolved"
            value={`${Math.round((stats.resolution_stats.resolved / Math.max(stats.total, 1)) * 100)}%`}
            subtitle={`${stats.resolution_stats.resolved} of ${stats.total}`}
            icon={CheckCircle2}
            color="bg-blue-500"
          />
        </div>
      )}

      {/* Filters */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
        <div className="flex flex-wrap gap-4">
          {/* Search */}
          <form onSubmit={handleSearch} className="relative flex-1 min-w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-neutral-400" />
            <input
              type="text"
              placeholder="Search by path..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </form>

          {/* Trigger filter */}
          <select
            value={filters.trigger || ''}
            onChange={(e) =>
              setFilters((f) => ({
                ...f,
                trigger: (e.target.value as SnapshotTrigger) || undefined,
              }))
            }
            className="border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white"
          >
            <option value="">All Triggers</option>
            {availableFilters?.triggers.map((t) => (
              <option key={t} value={t}>
                {triggerConfig[t]?.label || t}
              </option>
            ))}
          </select>

          {/* Source filter */}
          <select
            value={filters.source || ''}
            onChange={(e) =>
              setFilters((f) => ({
                ...f,
                source: e.target.value || undefined,
              }))
            }
            className="border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white"
          >
            <option value="">All Gateways</option>
            {availableFilters?.sources.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>

          {/* Resolution status filter */}
          <select
            value={filters.resolution_status || ''}
            onChange={(e) =>
              setFilters((f) => ({
                ...f,
                resolution_status: (e.target.value as SnapshotResolutionStatus) || undefined,
              }))
            }
            className="border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white"
          >
            <option value="">All Statuses</option>
            {availableFilters?.resolution_statuses.map((s) => (
              <option key={s} value={s}>
                {resolutionConfig[s as SnapshotResolutionStatus]?.label || s}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Snapshots Table */}
      <div className="rounded-lg bg-white dark:bg-neutral-800 shadow-sm">
        <div className="border-b border-neutral-100 dark:border-neutral-700 px-4 py-3 flex justify-between items-center">
          <h2 className="font-medium text-neutral-900 dark:text-white">
            Error Snapshots ({total})
          </h2>
          <div className="text-sm text-neutral-500 dark:text-neutral-400">
            Page {page} of {Math.max(1, Math.ceil(total / pageSize))}
          </div>
        </div>

        {snapshots.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-neutral-500 dark:text-neutral-400">
            <AlertTriangle className="h-12 w-12 mb-4 text-neutral-300 dark:text-neutral-600" />
            <p>No error snapshots found</p>
            <p className="text-sm">Errors will appear here when they occur</p>
          </div>
        ) : (
          <div>
            {snapshots.map((snapshot) => (
              <SnapshotRow
                key={snapshot.id}
                snapshot={snapshot}
                isExpanded={expandedId === snapshot.id}
                onToggle={() => setExpandedId(expandedId === snapshot.id ? null : snapshot.id)}
                onResolutionChange={(s) => handleResolutionChange(snapshot.id, s)}
              />
            ))}
          </div>
        )}

        {/* Pagination */}
        {total > pageSize && (
          <div className="flex justify-between items-center px-4 py-3 border-t border-neutral-100 dark:border-neutral-700">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-4 py-2 text-sm text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-white disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Previous
            </button>
            <span className="text-sm text-neutral-500 dark:text-neutral-400">
              Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, total)} of {total}
            </span>
            <button
              onClick={() => setPage((p) => p + 1)}
              disabled={!hasNext}
              className="px-4 py-2 text-sm text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-white disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Next
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default ErrorSnapshots;
