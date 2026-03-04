import { useState, useEffect, useCallback } from 'react';
import { apiService } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import {
  Bot,
  RefreshCw,
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
  Cpu,
  Hash,
  ChevronDown,
  ChevronRight,
  GitBranch,
} from 'lucide-react';
import { clsx } from 'clsx';
import type { TraceSummary } from '../types';

// =============================================================================
// TYPES
// =============================================================================

interface AISessionStats {
  days: number;
  totals: {
    sessions: number;
    total_duration_ms: number;
    avg_duration_ms: number;
    success_count: number;
    success_rate: number;
  };
  workers: WorkerStats[];
  daily: { date: string; sessions: number }[];
}

interface WorkerStats {
  worker: string;
  sessions: number;
  total_duration_ms: number;
  avg_duration_ms: number;
  success_count: number;
  success_rate: number;
  last_activity: string | null;
}

// =============================================================================
// HELPERS
// =============================================================================

function formatDuration(ms: number | null): string {
  if (!ms) return '—';
  if (ms < 60_000) return `${Math.round(ms / 1000)}s`;
  if (ms < 3_600_000) return `${Math.round(ms / 60_000)}m`;
  const h = Math.floor(ms / 3_600_000);
  const m = Math.round((ms % 3_600_000) / 60_000);
  return `${h}h ${m}m`;
}

function timeAgo(iso: string | null): string {
  if (!iso) return 'Never';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

// =============================================================================
// STAT CARD
// =============================================================================

function StatCard({
  label,
  value,
  icon: Icon,
  accent,
}: {
  label: string;
  value: string | number;
  icon: typeof Bot;
  accent?: string;
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
      <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
        <Icon className="h-4 w-4" />
        {label}
      </div>
      <div
        className={clsx('mt-1 text-2xl font-semibold', accent || 'text-gray-900 dark:text-white')}
      >
        {value}
      </div>
    </div>
  );
}

// =============================================================================
// WORKER CARD
// =============================================================================

function isRecentlyActive(iso: string | null): boolean {
  if (!iso) return false;
  return Date.now() - new Date(iso).getTime() < 3_600_000;
}

function WorkerCard({ worker }: { worker: WorkerStats }) {
  const [isActive] = useState(() => isRecentlyActive(worker.last_activity));

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Cpu className="h-4 w-4 text-purple-500" />
          <span className="font-medium text-gray-900 dark:text-white">{worker.worker}</span>
        </div>
        <span
          className={clsx(
            'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium',
            isActive
              ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
              : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
          )}
        >
          <span
            className={clsx('h-1.5 w-1.5 rounded-full', isActive ? 'bg-green-500' : 'bg-gray-400')}
          />
          {isActive ? 'Active' : 'Idle'}
        </span>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
        <div>
          <span className="text-gray-500 dark:text-gray-400">Sessions</span>
          <p className="font-medium text-gray-900 dark:text-white">{worker.sessions}</p>
        </div>
        <div>
          <span className="text-gray-500 dark:text-gray-400">Success</span>
          <p className="font-medium text-gray-900 dark:text-white">{worker.success_rate}%</p>
        </div>
        <div>
          <span className="text-gray-500 dark:text-gray-400">Avg Duration</span>
          <p className="font-medium text-gray-900 dark:text-white">
            {formatDuration(worker.avg_duration_ms)}
          </p>
        </div>
        <div>
          <span className="text-gray-500 dark:text-gray-400">Last Active</span>
          <p className="font-medium text-gray-900 dark:text-white">
            {timeAgo(worker.last_activity)}
          </p>
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// SESSION ROW
// =============================================================================

function SessionRow({ trace }: { trace: TraceSummary }) {
  const [expanded, setExpanded] = useState(false);
  const isSuccess = trace.status === 'success';

  return (
    <>
      <tr
        className="cursor-pointer border-b border-gray-100 hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800/50"
        onClick={() => setExpanded(!expanded)}
      >
        <td className="px-4 py-3">
          <button className="text-gray-400">
            {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </button>
        </td>
        <td className="px-4 py-3">
          {isSuccess ? (
            <CheckCircle2 className="h-4 w-4 text-green-500" />
          ) : (
            <XCircle className="h-4 w-4 text-red-500" />
          )}
        </td>
        <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">
          {trace.api_name || '—'}
        </td>
        <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">{trace.trigger_type}</td>
        <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
          {formatDuration(trace.total_duration_ms ?? null)}
        </td>
        <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">{trace.tenant_id}</td>
      </tr>
      {expanded && (
        <tr className="border-b border-gray-100 dark:border-gray-700">
          <td colSpan={6} className="bg-gray-50 px-8 py-3 dark:bg-gray-800/30">
            <div className="flex items-center gap-4 text-sm text-gray-600 dark:text-gray-300">
              <span className="flex items-center gap-1">
                <Hash className="h-3.5 w-3.5" /> {trace.id.slice(0, 8)}
              </span>
              {trace.trigger_type && (
                <span className="flex items-center gap-1">
                  <GitBranch className="h-3.5 w-3.5" /> {trace.trigger_type}
                </span>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// =============================================================================
// MAIN DASHBOARD
// =============================================================================

export function HegemonDashboard() {
  const { hasPermission } = useAuth();
  const [stats, setStats] = useState<AISessionStats | null>(null);
  const [sessions, setSessions] = useState<TraceSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(7);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [statsData, tracesData] = await Promise.all([
        apiService.getAiSessionStats(days),
        apiService.getTraces(50, 'hegemon'),
      ]);
      setStats(statsData);
      setSessions(tracesData.traces);
    } catch (err) {
      console.error('Failed to fetch hegemon data:', err);
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (!hasPermission('tenants:read')) {
    return (
      <div className="flex h-64 items-center justify-center text-gray-500">
        You do not have permission to view this page.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Bot className="h-6 w-6 text-purple-500" />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">AI Factory</h1>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white"
          >
            <option value={1}>Today</option>
            <option value={7}>7 days</option>
            <option value={30}>30 days</option>
          </select>
          <button
            onClick={fetchData}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-md bg-purple-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            Refresh
          </button>
        </div>
      </div>

      {loading && !stats ? (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-purple-500" />
        </div>
      ) : stats ? (
        <>
          {/* Summary Cards */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label="Total Sessions" value={stats.totals.sessions} icon={Hash} />
            <StatCard
              label="Success Rate"
              value={`${stats.totals.success_rate}%`}
              icon={CheckCircle2}
              accent={stats.totals.success_rate >= 80 ? 'text-green-600' : 'text-amber-600'}
            />
            <StatCard
              label="Avg Duration"
              value={formatDuration(stats.totals.avg_duration_ms)}
              icon={Clock}
            />
            <StatCard label="Workers" value={stats.workers.length} icon={Cpu} />
          </div>

          {/* Worker Cards */}
          {stats.workers.length > 0 && (
            <div>
              <h2 className="mb-3 text-lg font-semibold text-gray-900 dark:text-white">Workers</h2>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {stats.workers.map((w) => (
                  <WorkerCard key={w.worker} worker={w} />
                ))}
              </div>
            </div>
          )}

          {/* Session List */}
          <div>
            <h2 className="mb-3 text-lg font-semibold text-gray-900 dark:text-white">
              Recent Sessions
            </h2>
            {sessions.length === 0 ? (
              <div className="rounded-lg border border-gray-200 bg-white p-8 text-center text-gray-500 dark:border-gray-700 dark:bg-gray-800">
                No AI sessions recorded yet.
              </div>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800">
                    <tr>
                      <th className="w-10 px-4 py-3" />
                      <th className="w-10 px-4 py-3">Status</th>
                      <th className="px-4 py-3">Ticket</th>
                      <th className="px-4 py-3">Source</th>
                      <th className="px-4 py-3">Duration</th>
                      <th className="px-4 py-3">Tenant</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white dark:bg-gray-900">
                    {sessions.map((s) => (
                      <SessionRow key={s.id} trace={s} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      ) : (
        <div className="text-center text-gray-500">Failed to load data.</div>
      )}
    </div>
  );
}
