import { useState, useEffect, useCallback, useMemo } from 'react';
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
  DollarSign,
  Zap,
  Download,
  TrendingUp,
  TrendingDown,
  Minus,
} from 'lucide-react';
import { clsx } from 'clsx';
import type { TraceSummary } from '../types';
import { SparklineChart } from '../components/charts/SparklineChart';

// =============================================================================
// TYPES
// =============================================================================

interface ModelStats {
  model: string;
  sessions: number;
  cost_usd: number;
  tokens: number;
}

interface AISessionStats {
  days: number;
  totals: {
    sessions: number;
    total_duration_ms: number;
    avg_duration_ms: number;
    success_count: number;
    success_rate: number;
    total_cost_usd: number;
    total_tokens: number;
    avg_cost_per_session: number;
    cost_delta_usd: number;
    cost_delta_pct: number;
    tokens_delta: number;
    prev_cost_usd: number;
  };
  by_model: ModelStats[];
  workers: WorkerStats[];
  daily: { date: string; sessions: number; cost_usd: number; tokens: number }[];
}

interface WorkerStats {
  worker: string;
  sessions: number;
  total_duration_ms: number;
  avg_duration_ms: number;
  success_count: number;
  success_rate: number;
  last_activity: string | null;
  total_cost_usd: number;
  total_tokens: number;
  avg_cost_usd: number;
  primary_model: string | null;
}

// =============================================================================
// HELPERS
// =============================================================================

function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—';
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

function formatCost(usd: number | null | undefined): string {
  if (usd === null || usd === undefined || usd === 0) return '$0';
  if (usd < 0.01) return '<$0.01';
  return `$${usd.toFixed(2)}`;
}

function formatTokens(n: number | null | undefined): string {
  if (n === null || n === undefined || n === 0) return '0';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}k`;
  return String(n);
}

function shortModel(model: string | null | undefined): string {
  if (!model) return '—';
  if (model.includes('opus')) return 'Opus';
  if (model.includes('sonnet')) return 'Sonnet';
  if (model.includes('haiku')) return 'Haiku';
  return model;
}

// =============================================================================
// STAT CARD
// =============================================================================

function StatCard({
  label,
  value,
  icon: Icon,
  accent,
  trend,
}: {
  label: string;
  value: string | number;
  icon: typeof Bot;
  accent?: string;
  trend?: { delta: number; label: string };
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
      {trend && (
        <div
          className={clsx(
            'mt-1 flex items-center gap-1 text-xs',
            trend.delta > 0 ? 'text-red-500' : trend.delta < 0 ? 'text-green-500' : 'text-gray-400'
          )}
        >
          {trend.delta > 0 ? (
            <TrendingUp className="h-3 w-3" />
          ) : trend.delta < 0 ? (
            <TrendingDown className="h-3 w-3" />
          ) : (
            <Minus className="h-3 w-3" />
          )}
          {trend.delta > 0 ? '+' : ''}
          {trend.label}
        </div>
      )}
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
      <div className="mt-3 grid grid-cols-3 gap-2 text-sm">
        <div>
          <span className="text-gray-500 dark:text-gray-400">Sessions</span>
          <p className="font-medium text-gray-900 dark:text-white">{worker.sessions}</p>
        </div>
        <div>
          <span className="text-gray-500 dark:text-gray-400">Success</span>
          <p className="font-medium text-gray-900 dark:text-white">{worker.success_rate}%</p>
        </div>
        <div>
          <span className="text-gray-500 dark:text-gray-400">Cost</span>
          <p className="font-medium text-gray-900 dark:text-white">
            {formatCost(worker.total_cost_usd)}
          </p>
        </div>
        <div>
          <span className="text-gray-500 dark:text-gray-400">Avg Duration</span>
          <p className="font-medium text-gray-900 dark:text-white">
            {formatDuration(worker.avg_duration_ms)}
          </p>
        </div>
        <div>
          <span className="text-gray-500 dark:text-gray-400">Model</span>
          <p className="font-medium text-gray-900 dark:text-white">
            {shortModel(worker.primary_model)}
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
        <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
          {trace.trigger_source || trace.trigger_type}
        </td>
        <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
          {formatDuration(trace.total_duration_ms ?? null)}
        </td>
        <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">{trace.tenant_id}</td>
      </tr>
      {expanded && (
        <tr className="border-b border-gray-100 dark:border-gray-700">
          <td colSpan={6} className="bg-gray-50 px-8 py-4 dark:bg-gray-800/30">
            <div className="space-y-2 text-sm text-gray-600 dark:text-gray-300">
              <div className="flex flex-wrap items-center gap-4">
                <span className="flex items-center gap-1">
                  <Hash className="h-3.5 w-3.5" /> {trace.id.slice(0, 8)}
                </span>
                {trace.trigger_source && (
                  <span className="flex items-center gap-1">
                    <Cpu className="h-3.5 w-3.5" /> {trace.trigger_source}
                  </span>
                )}
                {trace.git_author && (
                  <span className="flex items-center gap-1">
                    <GitBranch className="h-3.5 w-3.5" /> {trace.git_author}
                  </span>
                )}
                {trace.git_commit_sha && (
                  <span className="font-mono text-xs">{trace.git_commit_sha}</span>
                )}
              </div>
              {(trace.steps_count > 0 || trace.steps_completed > 0) && (
                <div className="flex items-center gap-3 text-xs">
                  <span>
                    Steps: {trace.steps_completed}/{trace.steps_count} completed
                  </span>
                  {trace.steps_failed > 0 && (
                    <span className="text-red-500">{trace.steps_failed} failed</span>
                  )}
                </div>
              )}
              {(trace.cost_usd != null || trace.model) && (
                <div className="flex items-center gap-3 text-xs">
                  {trace.cost_usd != null && (
                    <span className="flex items-center gap-1">
                      <DollarSign className="h-3 w-3" /> {formatCost(trace.cost_usd)}
                    </span>
                  )}
                  {trace.total_tokens != null && (
                    <span className="flex items-center gap-1">
                      <Zap className="h-3 w-3" /> {formatTokens(trace.total_tokens)} tokens
                    </span>
                  )}
                  {trace.model && (
                    <span className="rounded bg-gray-200 px-1.5 py-0.5 text-xs dark:bg-gray-700">
                      {shortModel(trace.model)}
                    </span>
                  )}
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// =============================================================================
// MODEL BREAKDOWN (CAB-1692)
// =============================================================================

const MODEL_COLORS: Record<string, string> = {
  opus: '#8b5cf6',
  sonnet: '#3b82f6',
  haiku: '#10b981',
  unknown: '#6b7280',
};

function getModelColor(model: string): string {
  for (const [key, color] of Object.entries(MODEL_COLORS)) {
    if (model.toLowerCase().includes(key)) return color;
  }
  return MODEL_COLORS.unknown;
}

function ModelBreakdown({ models }: { models: ModelStats[] }) {
  const totalCost = models.reduce((sum, m) => sum + m.cost_usd, 0);

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Cost by Model</h2>
      {/* Bar */}
      <div className="mt-3 flex h-4 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-700">
        {models.map((m) => {
          const pct = totalCost > 0 ? (m.cost_usd / totalCost) * 100 : 0;
          return (
            <div
              key={m.model}
              className="h-full transition-all"
              style={{ width: `${pct}%`, backgroundColor: getModelColor(m.model) }}
              title={`${shortModel(m.model)}: ${formatCost(m.cost_usd)} (${pct.toFixed(0)}%)`}
            />
          );
        })}
      </div>
      {/* Legend */}
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {models.map((m) => (
          <div key={m.model} className="flex items-center gap-2 text-sm">
            <span
              className="h-3 w-3 rounded-full"
              style={{ backgroundColor: getModelColor(m.model) }}
            />
            <div>
              <span className="font-medium text-gray-900 dark:text-white">
                {shortModel(m.model)}
              </span>
              <span className="ml-1 text-gray-500 dark:text-gray-400">
                {formatCost(m.cost_usd)} / {formatTokens(m.tokens)}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// =============================================================================
// DAILY COST CHART
// =============================================================================

function DailyCostChart({
  daily,
}: {
  daily: { date: string; sessions: number; cost_usd: number; tokens: number }[];
}) {
  const sparklineData = useMemo(
    () =>
      daily.map((d) => ({
        timestamp: new Date(d.date).getTime() / 1000,
        value: d.cost_usd,
      })),
    [daily]
  );

  const totalCost = daily.reduce((sum, d) => sum + d.cost_usd, 0);

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Daily Cost</h2>
        <span className="text-sm text-gray-500 dark:text-gray-400">
          {formatCost(totalCost)} total
        </span>
      </div>
      <div className="mt-3 flex items-end gap-4">
        <SparklineChart data={sparklineData} color="#10b981" height={64} width={600} />
        <div className="flex flex-col gap-1 text-xs text-gray-500 dark:text-gray-400">
          <span>{daily[0]?.date}</span>
          <span>{daily[daily.length - 1]?.date}</span>
        </div>
      </div>
    </div>
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
            onClick={async () => {
              try {
                const blob = await apiService.exportAiSessionsCsv(days);
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `hegemon-sessions-${days}d.csv`;
                a.click();
                URL.revokeObjectURL(url);
              } catch (err) {
                console.error('CSV export failed:', err);
              }
            }}
            className="inline-flex items-center gap-2 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
          >
            <Download className="h-4 w-4" />
            CSV
          </button>
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
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
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
            <StatCard
              label="Total Cost"
              value={formatCost(stats.totals.total_cost_usd)}
              icon={DollarSign}
              accent="text-emerald-600"
              trend={
                stats.totals.prev_cost_usd > 0
                  ? {
                      delta: stats.totals.cost_delta_usd,
                      label: `${stats.totals.cost_delta_pct > 0 ? '+' : ''}${stats.totals.cost_delta_pct}% vs prev`,
                    }
                  : undefined
              }
            />
            <StatCard
              label="Total Tokens"
              value={formatTokens(stats.totals.total_tokens)}
              icon={Zap}
            />
            <StatCard label="Workers" value={stats.workers.length} icon={Cpu} />
          </div>

          {/* Daily Cost Chart + Model Breakdown */}
          {stats.daily.length > 1 && <DailyCostChart daily={stats.daily} />}
          {stats.by_model && stats.by_model.length > 0 && (
            <ModelBreakdown models={stats.by_model} />
          )}

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
                      <th className="px-4 py-3">Worker</th>
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
