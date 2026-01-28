// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
import { useState, useEffect, useCallback } from 'react';
import { errorSnapshotsService } from '../services/errorSnapshotsApi';
import { useAuth } from '../contexts/AuthContext';
import type {
  MCPErrorSnapshotSummary,
  MCPErrorSnapshot,
  MCPErrorSnapshotStats,
  MCPErrorSnapshotFilters,
  MCPErrorType,
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
  DollarSign,
  Zap,
  Server,
  Wrench,
  Search,
  Copy,
  Check,
  EyeOff,
  Terminal,
} from 'lucide-react';
import { clsx } from 'clsx';

// Error type display config
const errorTypeConfig: Record<string, { label: string; color: string; bg: string }> = {
  server_timeout: { label: 'Server Timeout', color: 'text-orange-600', bg: 'bg-orange-100' },
  server_unavailable: { label: 'Server Unavailable', color: 'text-red-600', bg: 'bg-red-100' },
  server_rate_limited: { label: 'Rate Limited', color: 'text-yellow-600', bg: 'bg-yellow-100' },
  server_auth_failure: { label: 'Auth Failure', color: 'text-red-600', bg: 'bg-red-100' },
  server_internal_error: { label: 'Internal Error', color: 'text-red-600', bg: 'bg-red-100' },
  tool_not_found: { label: 'Tool Not Found', color: 'text-gray-600', bg: 'bg-gray-100' },
  tool_execution_error: { label: 'Tool Error', color: 'text-red-600', bg: 'bg-red-100' },
  tool_validation_error: { label: 'Validation Error', color: 'text-yellow-600', bg: 'bg-yellow-100' },
  tool_timeout: { label: 'Tool Timeout', color: 'text-orange-600', bg: 'bg-orange-100' },
  llm_context_exceeded: { label: 'Context Exceeded', color: 'text-purple-600', bg: 'bg-purple-100' },
  llm_content_filtered: { label: 'Content Filtered', color: 'text-purple-600', bg: 'bg-purple-100' },
  llm_quota_exceeded: { label: 'Quota Exceeded', color: 'text-purple-600', bg: 'bg-purple-100' },
  llm_rate_limited: { label: 'LLM Rate Limited', color: 'text-purple-600', bg: 'bg-purple-100' },
  policy_denied: { label: 'Policy Denied', color: 'text-red-600', bg: 'bg-red-100' },
  unknown: { label: 'Unknown', color: 'text-gray-600', bg: 'bg-gray-100' },
};

const resolutionConfig: Record<SnapshotResolutionStatus, { label: string; color: string; bg: string }> = {
  unresolved: { label: 'Unresolved', color: 'text-red-600', bg: 'bg-red-100' },
  investigating: { label: 'Investigating', color: 'text-yellow-600', bg: 'bg-yellow-100' },
  resolved: { label: 'Resolved', color: 'text-green-600', bg: 'bg-green-100' },
  ignored: { label: 'Ignored', color: 'text-gray-600', bg: 'bg-gray-100' },
};

function formatCost(cost: number): string {
  if (cost === 0) return '$0.00';
  if (cost < 0.01) return `$${cost.toFixed(4)}`;
  return `$${cost.toFixed(2)}`;
}

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
    <div className="rounded-lg bg-white p-6 shadow-sm">
      <div className="flex items-center gap-4">
        <div className={clsx('rounded-lg p-3', color)}>
          <Icon className="h-6 w-6 text-white" />
        </div>
        <div>
          <p className="text-sm font-medium text-gray-500">{title}</p>
          <p className="text-2xl font-bold text-gray-900">{value}</p>
          {subtitle && <p className="text-xs text-gray-400">{subtitle}</p>}
        </div>
      </div>
    </div>
  );
}

// Cost Badge Component
function CostBadge({ cost }: { cost: number }) {
  let colorClass = 'bg-green-100 text-green-800';
  if (cost >= 0.1) {
    colorClass = 'bg-red-100 text-red-800';
  } else if (cost >= 0.01) {
    colorClass = 'bg-yellow-100 text-yellow-800';
  }

  return (
    <span className={clsx('px-2 py-1 rounded-full text-xs font-medium', colorClass)}>
      {formatCost(cost)}
    </span>
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
  const config = resolutionConfig[status];
  return (
    <button
      onClick={onClick}
      className={clsx(
        'px-2 py-1 rounded-full text-xs font-medium transition-colors',
        config.bg,
        config.color,
        onClick && 'hover:opacity-80 cursor-pointer'
      )}
    >
      {config.label}
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
        <div className="mt-2 bg-gray-900 rounded-lg p-4 relative">
          {warning && (
            <div className="mb-2 text-xs text-yellow-400 flex items-center gap-1">
              <AlertCircle className="h-3 w-3" />
              {warning}
            </div>
          )}
          <button
            onClick={copyToClipboard}
            className="absolute top-2 right-2 text-gray-400 hover:text-white"
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
  snapshot: MCPErrorSnapshotSummary;
  isExpanded: boolean;
  onToggle: () => void;
  onResolutionChange: (status: SnapshotResolutionStatus) => void;
}) {
  const [details, setDetails] = useState<MCPErrorSnapshot | null>(null);
  const [loading, setLoading] = useState(false);

  const errorConfig = errorTypeConfig[snapshot.error_type] || errorTypeConfig.unknown;

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
    <div className="border-b border-gray-100 last:border-0">
      {/* Summary row */}
      <div
        className="flex items-center gap-4 p-4 hover:bg-gray-50 cursor-pointer"
        onClick={onToggle}
      >
        {/* Expand icon */}
        <button className="text-gray-400">
          {isExpanded ? <ChevronDown className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
        </button>

        {/* Error type badge */}
        <span className={clsx('px-2 py-1 rounded-full text-xs font-medium', errorConfig.bg, errorConfig.color)}>
          {errorConfig.label}
        </span>

        {/* HTTP Status */}
        <span
          className={clsx(
            'px-2 py-0.5 rounded text-xs font-mono',
            snapshot.response_status >= 500 ? 'bg-red-100 text-red-800' : 'bg-yellow-100 text-yellow-800'
          )}
        >
          {snapshot.response_status}
        </span>

        {/* Error message */}
        <div className="flex-1 min-w-0">
          <p className="text-sm text-gray-900 truncate">{snapshot.error_message}</p>
          <div className="flex items-center gap-2 mt-1 text-xs text-gray-500">
            {snapshot.mcp_server_name && (
              <span className="flex items-center gap-1">
                <Server className="h-3 w-3" />
                {snapshot.mcp_server_name}
              </span>
            )}
            {snapshot.tool_name && (
              <span className="flex items-center gap-1">
                <Wrench className="h-3 w-3" />
                {snapshot.tool_name}
              </span>
            )}
          </div>
        </div>

        {/* Cost */}
        <CostBadge cost={snapshot.total_cost_usd} />

        {/* Tokens wasted */}
        {snapshot.tokens_wasted > 0 && (
          <span className="flex items-center gap-1 text-xs text-gray-500">
            <Zap className="h-3 w-3" />
            {snapshot.tokens_wasted.toLocaleString()}
          </span>
        )}

        {/* Resolution status */}
        <ResolutionBadge
          status={snapshot.resolution_status}
          onClick={(e) => {
            e?.stopPropagation?.();
          }}
        />

        {/* Timestamp */}
        <span className="text-xs text-gray-400 w-24 text-right">{formatDateTime(snapshot.timestamp)}</span>
      </div>

      {/* Expanded details */}
      {isExpanded && (
        <div className="bg-gray-50 p-4 border-t border-gray-100">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
            </div>
          ) : details ? (
            <div className="space-y-4">
              {/* Resolution actions */}
              <div className="flex items-center gap-2 pb-4 border-b border-gray-200">
                <span className="text-sm text-gray-600">Set status:</span>
                {(['unresolved', 'investigating', 'resolved', 'ignored'] as SnapshotResolutionStatus[]).map(
                  (status) => (
                    <button
                      key={status}
                      onClick={() => onResolutionChange(status)}
                      className={clsx(
                        'px-3 py-1 rounded-full text-xs font-medium transition-colors',
                        details.resolution_status === status
                          ? `${resolutionConfig[status].bg} ${resolutionConfig[status].color}`
                          : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                      )}
                    >
                      {resolutionConfig[status].label}
                    </button>
                  )
                )}
              </div>

              <div className="grid grid-cols-3 gap-6">
                {/* Left: Request Info */}
                <div className="space-y-4">
                  <h4 className="font-medium text-gray-900">Request</h4>
                  <div className="bg-white rounded-lg p-4 space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-500">Method:</span>
                      <span className="font-mono">{details.request_method || '-'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">Path:</span>
                      <span className="font-mono text-xs truncate max-w-48" title={details.request_path}>
                        {details.request_path || '-'}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">Status:</span>
                      <span className="font-mono">{details.response_status}</span>
                    </div>
                    {details.trace_id && (
                      <div className="flex justify-between">
                        <span className="text-gray-500">Trace ID:</span>
                        <span className="font-mono text-xs">{details.trace_id}</span>
                      </div>
                    )}
                  </div>

                  {/* Error details */}
                  <div className="bg-red-50 rounded-lg p-4">
                    <h5 className="font-medium text-red-800 mb-2">Error</h5>
                    <p className="text-sm text-red-600">{details.error_message}</p>
                    {details.error_code && (
                      <p className="text-xs text-red-500 mt-1 font-mono">{details.error_code}</p>
                    )}
                  </div>
                </div>

                {/* Middle: Tool/Server Context */}
                <div className="space-y-4">
                  <h4 className="font-medium text-gray-900">MCP Context</h4>
                  <div className="bg-white rounded-lg p-4 space-y-2 text-sm">
                    {details.mcp_server_name && (
                      <div className="flex justify-between">
                        <span className="text-gray-500">Server:</span>
                        <span>{details.mcp_server_name}</span>
                      </div>
                    )}
                    {details.tool_name && (
                      <div className="flex justify-between">
                        <span className="text-gray-500">Tool:</span>
                        <span>{details.tool_name}</span>
                      </div>
                    )}
                    <div className="flex justify-between">
                      <span className="text-gray-500">Retries:</span>
                      <span>
                        {details.retry_attempts}/{details.retry_max_attempts}
                      </span>
                    </div>
                  </div>

                  {/* Tool invocation details */}
                  {details.snapshot?.tool_invocation && (
                    <div className="bg-white rounded-lg p-4">
                      <h5 className="font-medium text-gray-700 mb-2 text-sm">Tool Invocation</h5>
                      <div className="text-xs font-mono bg-gray-50 rounded p-2 max-h-32 overflow-auto">
                        <pre>{JSON.stringify(details.snapshot.tool_invocation.input_params, null, 2)}</pre>
                      </div>
                      {details.snapshot.tool_invocation.duration_ms && (
                        <p className="text-xs text-gray-500 mt-2">
                          Duration: {details.snapshot.tool_invocation.duration_ms}ms
                        </p>
                      )}
                    </div>
                  )}
                </div>

                {/* Right: LLM/Cost Context */}
                <div className="space-y-4">
                  <h4 className="font-medium text-gray-900">Cost & Tokens</h4>
                  <div className="bg-white rounded-lg p-4 space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-500">Total Cost:</span>
                      <CostBadge cost={details.total_cost_usd} />
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">Tokens Wasted:</span>
                      <span className="text-red-600">{details.tokens_wasted.toLocaleString()}</span>
                    </div>
                    {details.llm_provider && (
                      <div className="flex justify-between">
                        <span className="text-gray-500">LLM Provider:</span>
                        <span>{details.llm_provider}</span>
                      </div>
                    )}
                    {details.llm_model && (
                      <div className="flex justify-between">
                        <span className="text-gray-500">Model:</span>
                        <span className="text-xs">{details.llm_model}</span>
                      </div>
                    )}
                    {details.llm_tokens_input !== undefined && (
                      <div className="flex justify-between">
                        <span className="text-gray-500">Input Tokens:</span>
                        <span>{details.llm_tokens_input?.toLocaleString()}</span>
                      </div>
                    )}
                    {details.llm_tokens_output !== undefined && (
                      <div className="flex justify-between">
                        <span className="text-gray-500">Output Tokens:</span>
                        <span>{details.llm_tokens_output?.toLocaleString()}</span>
                      </div>
                    )}
                  </div>

                  {/* Masked fields warning */}
                  {details.snapshot?.masked_fields && details.snapshot.masked_fields.length > 0 && (
                    <div className="bg-yellow-50 rounded-lg p-3 text-xs text-yellow-700">
                      <p className="font-medium">PII Masked:</p>
                      <p className="mt-1">{details.snapshot.masked_fields.join(', ')}</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Replay command */}
              <ReplayCommand snapshotId={snapshot.id} />
            </div>
          ) : (
            <p className="text-center text-gray-500 py-4">Failed to load details</p>
          )}
        </div>
      )}
    </div>
  );
}

// Main Error Snapshots Page
export function ErrorSnapshots() {
  const { isReady } = useAuth();
  const [snapshots, setSnapshots] = useState<MCPErrorSnapshotSummary[]>([]);
  const [stats, setStats] = useState<MCPErrorSnapshotStats | null>(null);
  const [filters, setFilters] = useState<MCPErrorSnapshotFilters>({});
  const [availableFilters, setAvailableFilters] = useState<SnapshotFiltersResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [hasNext, setHasNext] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  const pageSize = 20;

  const loadData = useCallback(async () => {
    try {
      const [snapshotsData, statsData, filtersData] = await Promise.all([
        errorSnapshotsService.getSnapshots({ ...filters, search: searchQuery || undefined }, page, pageSize),
        errorSnapshotsService.getStats(),
        availableFilters ? Promise.resolve(availableFilters) : errorSnapshotsService.getFilters(),
      ]);
      setSnapshots(snapshotsData.snapshots);
      setTotal(snapshotsData.total);
      setHasNext(snapshotsData.has_next);
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
      // Refresh data
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
          <h1 className="text-2xl font-bold text-gray-900">MCP Error Snapshots</h1>
          <p className="text-gray-500">Time-travel debugging for MCP Gateway errors</p>
        </div>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-gray-600">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="rounded border-gray-300"
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
            title="Total Cost"
            value={formatCost(stats.total_cost_usd)}
            subtitle={`Avg: ${formatCost(stats.avg_cost_usd)}`}
            icon={DollarSign}
            color="bg-green-500"
          />
          <StatsCard
            title="Tokens Wasted"
            value={stats.total_tokens_wasted.toLocaleString()}
            icon={Zap}
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
      <div className="bg-white rounded-lg shadow p-4">
        <div className="flex flex-wrap gap-4">
          {/* Search */}
          <form onSubmit={handleSearch} className="relative flex-1 min-w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search errors..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </form>

          {/* Error type filter */}
          <select
            value={filters.error_types?.[0] || ''}
            onChange={(e) =>
              setFilters((f) => ({
                ...f,
                error_types: e.target.value ? [e.target.value as MCPErrorType] : undefined,
              }))
            }
            className="border border-gray-300 rounded-lg px-3 py-2"
          >
            <option value="">All Error Types</option>
            {availableFilters?.error_types.map((type) => (
              <option key={type} value={type}>
                {errorTypeConfig[type]?.label || type}
              </option>
            ))}
          </select>

          {/* Server filter */}
          <select
            value={filters.server_names?.[0] || ''}
            onChange={(e) =>
              setFilters((f) => ({
                ...f,
                server_names: e.target.value ? [e.target.value] : undefined,
              }))
            }
            className="border border-gray-300 rounded-lg px-3 py-2"
          >
            <option value="">All Servers</option>
            {availableFilters?.servers.map((server) => (
              <option key={server} value={server}>
                {server}
              </option>
            ))}
          </select>

          {/* Resolution status filter */}
          <select
            value={filters.resolution_status?.[0] || ''}
            onChange={(e) =>
              setFilters((f) => ({
                ...f,
                resolution_status: e.target.value ? [e.target.value as SnapshotResolutionStatus] : undefined,
              }))
            }
            className="border border-gray-300 rounded-lg px-3 py-2"
          >
            <option value="">All Statuses</option>
            {availableFilters?.resolution_statuses.map((status) => (
              <option key={status} value={status}>
                {resolutionConfig[status as SnapshotResolutionStatus]?.label || status}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Snapshots Table */}
      <div className="rounded-lg bg-white shadow-sm">
        <div className="border-b border-gray-100 px-4 py-3 flex justify-between items-center">
          <h2 className="font-medium text-gray-900">Error Snapshots ({total})</h2>
          {/* Pagination info */}
          <div className="text-sm text-gray-500">
            Page {page} of {Math.ceil(total / pageSize)}
          </div>
        </div>

        {snapshots.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-500">
            <AlertTriangle className="h-12 w-12 mb-4 text-gray-300" />
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
                onResolutionChange={(status) => handleResolutionChange(snapshot.id, status)}
              />
            ))}
          </div>
        )}

        {/* Pagination */}
        {total > pageSize && (
          <div className="flex justify-between items-center px-4 py-3 border-t border-gray-100">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Previous
            </button>
            <span className="text-sm text-gray-500">
              Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, total)} of {total}
            </span>
            <button
              onClick={() => setPage((p) => p + 1)}
              disabled={!hasNext}
              className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 disabled:opacity-50 disabled:cursor-not-allowed"
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
