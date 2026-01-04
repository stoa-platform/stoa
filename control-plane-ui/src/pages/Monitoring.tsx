import { useState, useEffect, useCallback } from 'react';
import { apiService } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import type { TraceSummary, PipelineTrace, TraceStats, TraceStep, TraceStatus } from '../types';
import {
  Activity,
  GitCommit,
  User,
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Loader2,
  RefreshCw,
  ChevronRight,
  ChevronDown,
  GitBranch,
  Package,
  Radio,
  Zap,
  FileCode,
} from 'lucide-react';
import { clsx } from 'clsx';

// Status icon and color mapping
const statusConfig: Record<TraceStatus, { icon: typeof CheckCircle2; color: string; bg: string }> = {
  pending: { icon: Clock, color: 'text-gray-500', bg: 'bg-gray-100' },
  in_progress: { icon: Loader2, color: 'text-blue-500', bg: 'bg-blue-100' },
  success: { icon: CheckCircle2, color: 'text-green-500', bg: 'bg-green-100' },
  failed: { icon: XCircle, color: 'text-red-500', bg: 'bg-red-100' },
  skipped: { icon: AlertCircle, color: 'text-yellow-500', bg: 'bg-yellow-100' },
};

// Step name to display name mapping
const stepNames: Record<string, { label: string; icon: typeof Activity }> = {
  webhook_received: { label: 'Webhook Received', icon: Radio },
  token_verification: { label: 'Token Verification', icon: CheckCircle2 },
  event_processing: { label: 'Event Processing', icon: Zap },
  analyze_changes: { label: 'Analyze Changes', icon: FileCode },
  kafka_publish: { label: 'Kafka Publish', icon: Package },
  awx_trigger: { label: 'AWX Trigger', icon: Activity },
};

function formatDuration(ms?: number): string {
  if (!ms) return '-';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatTime(isoString?: string): string {
  if (!isoString) return '-';
  const date = new Date(isoString);
  return date.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}


// Stats Card Component
function StatsCard({ title, value, subtitle, icon: Icon, color }: {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: typeof Activity;
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

// Step Timeline Component
function StepTimeline({ steps }: { steps: TraceStep[] }) {
  return (
    <div className="space-y-3">
      {steps.map((step, index) => {
        const config = statusConfig[step.status];
        const StepIcon = config.icon;
        const stepInfo = stepNames[step.name] || { label: step.name, icon: Activity };
        const StepTypeIcon = stepInfo.icon;

        return (
          <div key={index} className="relative">
            {/* Connector line */}
            {index < steps.length - 1 && (
              <div className="absolute left-4 top-8 h-full w-0.5 bg-gray-200" />
            )}

            <div className={clsx('flex items-start gap-3 rounded-lg p-3', config.bg)}>
              {/* Status icon */}
              <div className={clsx('rounded-full p-1', config.bg)}>
                <StepIcon className={clsx('h-5 w-5', config.color, step.status === 'in_progress' && 'animate-spin')} />
              </div>

              {/* Step info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <StepTypeIcon className="h-4 w-4 text-gray-400" />
                  <span className="font-medium text-gray-900">{stepInfo.label}</span>
                  {step.duration_ms && (
                    <span className="text-xs text-gray-500">({formatDuration(step.duration_ms)})</span>
                  )}
                </div>

                {/* Details */}
                {step.details && (
                  <div className="mt-2 text-xs text-gray-600 font-mono bg-white/50 rounded p-2">
                    {Object.entries(step.details).map(([key, value]) => (
                      <div key={key} className="flex gap-2">
                        <span className="text-gray-400">{key}:</span>
                        <span className="truncate">
                          {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Error */}
                {step.error && (
                  <div className="mt-2 text-xs text-red-600 bg-red-50 rounded p-2">
                    {step.error}
                  </div>
                )}
              </div>

              {/* Timing */}
              {step.started_at && (
                <div className="text-xs text-gray-400 text-right">
                  {formatTime(step.started_at)}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// Trace Row Component
function TraceRow({ trace, isExpanded, onToggle }: {
  trace: TraceSummary;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const [details, setDetails] = useState<PipelineTrace | null>(null);
  const [loading, setLoading] = useState(false);

  const config = statusConfig[trace.status];
  const StatusIcon = config.icon;

  useEffect(() => {
    if (isExpanded && !details) {
      setLoading(true);
      apiService.getTrace(trace.id)
        .then(setDetails)
        .finally(() => setLoading(false));
    }
  }, [isExpanded, trace.id, details]);

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

        {/* Status */}
        <div className={clsx('rounded-full p-1.5', config.bg)}>
          <StatusIcon className={clsx('h-4 w-4', config.color, trace.status === 'in_progress' && 'animate-spin')} />
        </div>

        {/* Trigger info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <GitBranch className="h-4 w-4 text-gray-400" />
            <span className="font-medium text-gray-900">{trace.trigger_type}</span>
            {trace.api_name && (
              <>
                <span className="text-gray-400">→</span>
                <span className="text-blue-600">{trace.api_name}</span>
              </>
            )}
          </div>
          {trace.git_commit_message && (
            <p className="text-sm text-gray-500 truncate mt-1">{trace.git_commit_message}</p>
          )}
        </div>

        {/* Author */}
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <User className="h-4 w-4" />
          <span>{trace.git_author || 'unknown'}</span>
        </div>

        {/* Commit */}
        {trace.git_commit_sha && (
          <div className="flex items-center gap-1 text-sm text-gray-400 font-mono">
            <GitCommit className="h-4 w-4" />
            <span>{trace.git_commit_sha}</span>
          </div>
        )}

        {/* Duration */}
        <div className="flex items-center gap-1 text-sm text-gray-500 w-20 justify-end">
          <Clock className="h-4 w-4" />
          <span>{formatDuration(trace.total_duration_ms)}</span>
        </div>

        {/* Steps progress */}
        <div className="flex items-center gap-1 text-sm w-16">
          <span className="text-green-600">{trace.steps_completed}</span>
          <span className="text-gray-400">/</span>
          <span className="text-gray-600">{trace.steps_count}</span>
          {trace.steps_failed > 0 && (
            <span className="text-red-500 ml-1">({trace.steps_failed})</span>
          )}
        </div>

        {/* Time */}
        <div className="text-sm text-gray-400 w-24 text-right">
          {formatTime(trace.created_at)}
        </div>
      </div>

      {/* Expanded details */}
      {isExpanded && (
        <div className="bg-gray-50 p-4 border-t border-gray-100">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
            </div>
          ) : details ? (
            <div className="grid grid-cols-2 gap-6">
              {/* Left: Git Info */}
              <div className="space-y-4">
                <h4 className="font-medium text-gray-900">Git Information</h4>
                <div className="bg-white rounded-lg p-4 space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Project:</span>
                    <span className="font-mono">{details.git_project || '-'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Branch:</span>
                    <span className="font-mono">{details.git_branch || '-'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Author:</span>
                    <span>{details.git_author} {details.git_author_email && `<${details.git_author_email}>`}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Commit:</span>
                    <span className="font-mono">{details.git_commit_sha || '-'}</span>
                  </div>
                  {details.git_files_changed && details.git_files_changed.length > 0 && (
                    <div>
                      <span className="text-gray-500">Files changed:</span>
                      <ul className="mt-1 text-xs font-mono text-gray-600 max-h-32 overflow-auto">
                        {details.git_files_changed.map((file, i) => (
                          <li key={i} className="truncate">{file}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>

                {/* Error summary */}
                {details.error_summary && (
                  <div className="bg-red-50 rounded-lg p-4">
                    <h5 className="font-medium text-red-800 mb-2">Error</h5>
                    <p className="text-sm text-red-600">{details.error_summary}</p>
                  </div>
                )}
              </div>

              {/* Right: Pipeline Steps */}
              <div className="space-y-4">
                <h4 className="font-medium text-gray-900">Pipeline Steps</h4>
                <StepTimeline steps={details.steps} />
              </div>
            </div>
          ) : (
            <p className="text-center text-gray-500 py-4">Failed to load details</p>
          )}
        </div>
      )}
    </div>
  );
}

// Main Monitoring Page
export function Monitoring() {
  const { isReady } = useAuth();
  const [traces, setTraces] = useState<TraceSummary[]>([]);
  const [stats, setStats] = useState<TraceStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const loadData = useCallback(async () => {
    try {
      const [tracesData, statsData] = await Promise.all([
        apiService.getTraces(50),
        apiService.getTraceStats(),
      ]);
      setTraces(tracesData.traces);
      setStats(statsData);
    } catch (error) {
      console.error('Failed to load monitoring data:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isReady) return;

    loadData();

    if (autoRefresh) {
      const interval = setInterval(loadData, 5000);
      return () => clearInterval(interval);
    }
  }, [loadData, autoRefresh, isReady]);

  if (loading) {
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
          <h1 className="text-2xl font-bold text-gray-900">Pipeline Monitoring</h1>
          <p className="text-gray-500">End-to-end tracing of GitLab → Kafka → AWX pipeline</p>
        </div>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-gray-600">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="rounded border-gray-300"
            />
            Auto-refresh (5s)
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
            title="Total Pipelines"
            value={stats.total}
            icon={Activity}
            color="bg-blue-500"
          />
          <StatsCard
            title="Success Rate"
            value={`${stats.success_rate}%`}
            subtitle={`${stats.by_status?.success || 0} successful`}
            icon={CheckCircle2}
            color="bg-green-500"
          />
          <StatsCard
            title="Failed"
            value={stats.by_status?.failed || 0}
            icon={XCircle}
            color="bg-red-500"
          />
          <StatsCard
            title="Avg Duration"
            value={formatDuration(stats.avg_duration_ms)}
            icon={Clock}
            color="bg-purple-500"
          />
        </div>
      )}

      {/* Traces Table */}
      <div className="rounded-lg bg-white shadow-sm">
        <div className="border-b border-gray-100 px-4 py-3">
          <h2 className="font-medium text-gray-900">Recent Pipeline Executions</h2>
        </div>

        {traces.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-500">
            <Activity className="h-12 w-12 mb-4 text-gray-300" />
            <p>No pipeline traces yet</p>
            <p className="text-sm">Push to GitLab to trigger a pipeline</p>
          </div>
        ) : (
          <div>
            {traces.map((trace) => (
              <TraceRow
                key={trace.id}
                trace={trace}
                isExpanded={expandedId === trace.id}
                onToggle={() => setExpandedId(expandedId === trace.id ? null : trace.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default Monitoring;
