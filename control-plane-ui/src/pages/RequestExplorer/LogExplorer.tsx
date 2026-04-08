import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, ChevronRight, RefreshCw, Search, X } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { SubNav } from '../../components/SubNav';
import { observabilityTabs } from '../../components/subNavGroups';
import { apiService } from '../../services/api';

interface AdminLogEntry {
  timestamp: string;
  service: string;
  level: string;
  message: string;
  trace_id: string | null;
  tenant_id: string | null;
  request_id: string | null;
  duration_ms: number | null;
  path: string | null;
  method: string | null;
  status_code: number | null;
  consumer_id: string | null;
}

interface AdminLogQueryResponse {
  logs: AdminLogEntry[];
  total: number;
  limit: number;
  has_more: boolean;
  query_time_ms: number;
}

const SERVICE_OPTIONS = [
  { value: 'all', label: 'All Services' },
  { value: 'gateway', label: 'Gateway' },
  { value: 'api', label: 'API' },
  { value: 'auth', label: 'Auth' },
];

const LEVEL_OPTIONS = [
  { value: '', label: 'All Levels' },
  { value: 'error', label: 'Error' },
  { value: 'warning', label: 'Warning' },
  { value: 'info', label: 'Info' },
  { value: 'debug', label: 'Debug' },
];

const REFRESH_OPTIONS = [
  { value: 0, label: 'Off' },
  { value: 5, label: '5s' },
  { value: 15, label: '15s' },
  { value: 30, label: '30s' },
];

const TIME_RANGE_OPTIONS = [
  { value: '1h', label: '1h', hours: 1 },
  { value: '6h', label: '6h', hours: 6 },
  { value: '24h', label: '24h', hours: 24 },
];

const LEVEL_COLORS: Record<string, string> = {
  error: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  warning: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
  info: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  debug: 'bg-neutral-100 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-400',
};

const SERVICE_COLORS: Record<string, string> = {
  'stoa-gateway': 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
  'control-plane-api': 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  keycloak: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
};

export function LogExplorer() {
  const navigate = useNavigate();
  const { hasRole } = useAuth();

  const [logs, setLogs] = useState<AdminLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [queryTimeMs, setQueryTimeMs] = useState<number>(0);

  // Filters
  const [service, setService] = useState('all');
  const [level, setLevel] = useState('');
  const [search, setSearch] = useState('');
  const [timeRange, setTimeRange] = useState('1h');
  const [refreshInterval, setRefreshInterval] = useState(0);

  // Detail panel
  const [selectedLog, setSelectedLog] = useState<AdminLogEntry | null>(null);

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchLogs = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const hours = TIME_RANGE_OPTIONS.find((o) => o.value === timeRange)?.hours ?? 1;
      const end = new Date();
      const start = new Date(end.getTime() - hours * 60 * 60 * 1000);

      const params: Record<string, string> = {
        service,
        start_time: start.toISOString(),
        end_time: end.toISOString(),
        limit: '50',
      };
      if (level) params.level = level;
      if (search) params.search = search;

      const { data } = await apiService.get<AdminLogQueryResponse>('/v1/admin/logs', { params });

      setLogs(data.logs);
      setQueryTimeMs(data.query_time_ms);
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 503) {
        setError('Loki unavailable');
      } else if (status === 403) {
        setError('Insufficient permissions');
      } else {
        setError('Failed to fetch logs');
      }
      setLogs([]);
    } finally {
      setLoading(false);
    }
  }, [service, level, search, timeRange]);

  // Initial fetch + refetch on filter change
  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  // Auto-refresh timer
  useEffect(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (refreshInterval > 0) {
      timerRef.current = setInterval(fetchLogs, refreshInterval * 1000);
    }
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [refreshInterval, fetchLogs]);

  const canAccess = hasRole('cpi-admin') || hasRole('tenant-admin');
  if (!canAccess) {
    return (
      <div className="flex items-center justify-center h-64 text-neutral-500">
        You do not have permission to view logs.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Gateway Logs</h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            Structured gateway, API, and auth logs from Loki
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            aria-label="Auto-refresh"
            value={refreshInterval}
            onChange={(e) => setRefreshInterval(Number(e.target.value))}
            className="border border-neutral-300 dark:border-neutral-600 rounded-lg px-2 py-2 text-sm bg-white dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300"
          >
            {REFRESH_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <button
            onClick={fetchLogs}
            disabled={loading}
            className="flex items-center gap-2 border border-neutral-300 dark:border-neutral-600 text-neutral-700 dark:text-neutral-300 px-3 py-2 rounded-lg text-sm hover:bg-neutral-50 dark:hover:bg-neutral-700 disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      <SubNav tabs={observabilityTabs} />

      {/* Filter Bar */}
      <div className="flex items-center gap-3 flex-wrap">
        <select
          aria-label="Service"
          value={service}
          onChange={(e) => setService(e.target.value)}
          className="border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300"
        >
          {SERVICE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>

        <select
          aria-label="Level"
          value={level}
          onChange={(e) => setLevel(e.target.value)}
          className="border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300"
        >
          {LEVEL_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>

        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-neutral-400" />
          <input
            type="text"
            placeholder="Search logs..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg text-sm bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white placeholder:text-neutral-400"
          />
        </div>

        <div className="flex items-center gap-1 bg-neutral-100 dark:bg-neutral-800 rounded-lg p-0.5">
          {TIME_RANGE_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setTimeRange(opt.value)}
              className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
                timeRange === opt.value
                  ? 'bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white shadow-sm'
                  : 'text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Error / Unavailable Banner */}
      {error && (
        <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 px-4 py-3 rounded-lg flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-yellow-600" />
          <span className="text-sm text-yellow-700 dark:text-yellow-400">{error}</span>
        </div>
      )}

      {/* Log Table + Detail Panel */}
      <div className="flex gap-4">
        {/* Table */}
        <div className="flex-1 bg-white dark:bg-neutral-800 rounded-lg shadow overflow-hidden">
          {logs.length === 0 && !loading && !error ? (
            <div className="flex flex-col items-center justify-center py-16">
              <Search className="h-8 w-8 text-neutral-300 dark:text-neutral-600 mb-2" />
              <p className="text-sm text-neutral-500 dark:text-neutral-400">No logs found</p>
              <p className="text-xs text-neutral-400 mt-1">
                Try adjusting your filters or time range
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase border-b border-neutral-100 dark:border-neutral-700">
                    <th className="px-4 py-3">Timestamp</th>
                    <th className="px-4 py-3">Service</th>
                    <th className="px-4 py-3">Level</th>
                    <th className="px-4 py-3">Message</th>
                    <th className="px-4 py-3 text-right">Duration</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-50 dark:divide-neutral-700">
                  {logs.map((log, i) => (
                    <tr
                      key={`${log.request_id || i}-${log.timestamp}`}
                      onClick={() => setSelectedLog(log)}
                      className={`cursor-pointer hover:bg-neutral-50 dark:hover:bg-neutral-750 ${
                        selectedLog?.request_id === log.request_id
                          ? 'bg-blue-50 dark:bg-blue-900/10'
                          : ''
                      }`}
                    >
                      <td className="px-4 py-2.5 text-xs text-neutral-500 dark:text-neutral-400 whitespace-nowrap">
                        {new Date(log.timestamp).toLocaleTimeString('fr-FR', {
                          hour: '2-digit',
                          minute: '2-digit',
                          second: '2-digit',
                        })}
                      </td>
                      <td className="px-4 py-2.5">
                        <span
                          className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
                            SERVICE_COLORS[log.service] ||
                            'bg-neutral-100 text-neutral-700 dark:bg-neutral-700 dark:text-neutral-300'
                          }`}
                        >
                          {log.service}
                        </span>
                      </td>
                      <td className="px-4 py-2.5">
                        <span
                          className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
                            LEVEL_COLORS[log.level] || 'bg-neutral-100 text-neutral-600'
                          }`}
                        >
                          {log.level}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-neutral-900 dark:text-white max-w-md truncate">
                        {log.message}
                      </td>
                      <td className="px-4 py-2.5 text-right text-neutral-500 dark:text-neutral-400 whitespace-nowrap">
                        {log.duration_ms != null ? `${log.duration_ms}ms` : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {/* Footer */}
          {logs.length > 0 && (
            <div className="px-4 py-2 border-t border-neutral-100 dark:border-neutral-700 text-xs text-neutral-400">
              {logs.length} entries &middot; {queryTimeMs.toFixed(0)}ms
            </div>
          )}
        </div>

        {/* Detail Panel */}
        {selectedLog && (
          <div className="w-96 bg-white dark:bg-neutral-800 rounded-lg shadow p-4 space-y-3 self-start sticky top-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-neutral-900 dark:text-white">
                Log Details
              </h3>
              <button
                onClick={() => setSelectedLog(null)}
                className="text-neutral-400 hover:text-neutral-600"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-2 text-sm">
              <DetailRow label="Timestamp" value={selectedLog.timestamp} />
              <DetailRow label="Service" value={selectedLog.service} />
              <DetailRow label="Level" value={selectedLog.level} />
              <DetailRow label="Message" value={selectedLog.message} />
              <DetailRow label="Path" value={selectedLog.path} />
              <DetailRow label="Method" value={selectedLog.method} />
              <DetailRow label="Status Code" value={selectedLog.status_code?.toString()} />
              <DetailRow
                label="Duration"
                value={selectedLog.duration_ms != null ? `${selectedLog.duration_ms}ms` : null}
              />
              <DetailRow label="Request ID" value={selectedLog.request_id} />
              <DetailRow label="Consumer ID" value={selectedLog.consumer_id} />
              <DetailRow label="Tenant ID" value={selectedLog.tenant_id} />

              {/* Trace ID with navigation link */}
              {selectedLog.trace_id && selectedLog.trace_id !== '-' ? (
                <div className="flex items-center justify-between py-1">
                  <span className="text-neutral-500 dark:text-neutral-400">Trace ID</span>
                  <button
                    onClick={() => navigate(`/call-flow/trace/${selectedLog.trace_id}`)}
                    className="text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1 text-xs font-mono"
                  >
                    {selectedLog.trace_id}
                    <ChevronRight className="h-3 w-3" />
                  </button>
                </div>
              ) : (
                <DetailRow label="Trace ID" value={selectedLog.trace_id} />
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null;
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-neutral-500 dark:text-neutral-400">{label}</span>
      <span className="text-neutral-900 dark:text-white font-mono text-xs max-w-[200px] truncate">
        {value}
      </span>
    </div>
  );
}

export default LogExplorer;
