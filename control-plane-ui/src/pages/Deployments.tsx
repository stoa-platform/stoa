import { useState, useEffect, useCallback } from 'react';
import { apiService } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { config } from '../config';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import { EmptyState } from '@stoa/shared/components/EmptyState';
import { TableSkeleton } from '@stoa/shared/components/Skeleton';
import { DeployLogViewer } from '../components/DeployLogViewer';
import { DeployProgress } from '../components/DeployProgress';
import { useDeployEvents } from '../hooks/useDeployEvents';
import type {
  Deployment,
  DeploymentStatus,
  Tenant,
  API,
  TraceSummary,
  PipelineTrace,
  TraceStats,
  TraceStep,
  TraceStatus,
} from '../types';
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
  Rocket,
  ExternalLink,
  Settings,
  ScrollText,
} from 'lucide-react';
import { clsx } from 'clsx';

// =============================================================================
// TAB COMPONENTS
// =============================================================================

type TabId = 'pipelines' | 'history' | 'config';

interface Tab {
  id: TabId;
  name: string;
  icon: typeof Activity;
  description: string;
}

const tabs: Tab[] = [
  {
    id: 'pipelines',
    name: 'Pipeline Traces',
    icon: Activity,
    description: 'GitLab → Kafka → AWX traces',
  },
  {
    id: 'history',
    name: 'Deployment History',
    icon: Rocket,
    description: 'API deployment records',
  },
  { id: 'config', name: 'GitLab Config', icon: Settings, description: 'GitOps configuration' },
];

// =============================================================================
// PIPELINE TRACES TAB (ex-Monitoring)
// =============================================================================

const statusConfig: Record<TraceStatus, { icon: typeof CheckCircle2; color: string; bg: string }> =
  {
    pending: { icon: Clock, color: 'text-gray-500', bg: 'bg-gray-100 dark:bg-gray-800' },
    in_progress: { icon: Loader2, color: 'text-blue-500', bg: 'bg-blue-100 dark:bg-blue-900/30' },
    success: {
      icon: CheckCircle2,
      color: 'text-green-500',
      bg: 'bg-green-100 dark:bg-green-900/30',
    },
    failed: { icon: XCircle, color: 'text-red-500', bg: 'bg-red-100 dark:bg-red-900/30' },
    skipped: {
      icon: AlertCircle,
      color: 'text-yellow-500',
      bg: 'bg-yellow-100 dark:bg-yellow-900/30',
    },
  };

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
  return date.toLocaleTimeString('fr-FR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

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
  icon: typeof Activity;
  color: string;
}) {
  return (
    <div className="rounded-lg bg-white dark:bg-neutral-800 p-6 shadow-sm border border-gray-100 dark:border-neutral-700">
      <div className="flex items-center gap-4">
        <div className={clsx('rounded-lg p-3', color)}>
          <Icon className="h-6 w-6 text-white" />
        </div>
        <div>
          <p className="text-sm font-medium text-gray-500 dark:text-neutral-400">{title}</p>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">{value}</p>
          {subtitle && <p className="text-xs text-gray-400 dark:text-neutral-500">{subtitle}</p>}
        </div>
      </div>
    </div>
  );
}

function StepTimeline({ steps }: { steps: TraceStep[] }) {
  return (
    <div className="space-y-3">
      {steps.map((step, index) => {
        const cfg = statusConfig[step.status];
        const StepIcon = cfg.icon;
        const stepInfo = stepNames[step.name] || { label: step.name, icon: Activity };
        const StepTypeIcon = stepInfo.icon;

        return (
          <div key={index} className="relative">
            {index < steps.length - 1 && (
              <div className="absolute left-4 top-8 h-full w-0.5 bg-gray-200 dark:bg-neutral-600" />
            )}
            <div className={clsx('flex items-start gap-3 rounded-lg p-3', cfg.bg)}>
              <div className={clsx('rounded-full p-1', cfg.bg)}>
                <StepIcon
                  className={clsx(
                    'h-5 w-5',
                    cfg.color,
                    step.status === 'in_progress' && 'animate-spin'
                  )}
                />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <StepTypeIcon className="h-4 w-4 text-gray-400 dark:text-neutral-500" />
                  <span className="font-medium text-gray-900 dark:text-white">
                    {stepInfo.label}
                  </span>
                  {step.duration_ms && (
                    <span className="text-xs text-gray-500">
                      ({formatDuration(step.duration_ms)})
                    </span>
                  )}
                </div>
                {step.details && (
                  <div className="mt-2 text-xs text-gray-600 dark:text-neutral-300 font-mono bg-white/50 dark:bg-neutral-800/50 rounded p-2">
                    {Object.entries(step.details).map(([key, value]) => (
                      <div key={key} className="flex gap-2">
                        <span className="text-gray-400 dark:text-neutral-500">{key}:</span>
                        <span className="truncate">
                          {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {step.error && (
                  <div className="mt-2 text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 rounded p-2">
                    {step.error}
                  </div>
                )}
              </div>
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

function TraceRow({
  trace,
  isExpanded,
  onToggle,
}: {
  trace: TraceSummary;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const [details, setDetails] = useState<PipelineTrace | null>(null);
  const [loading, setLoading] = useState(false);
  const cfg = statusConfig[trace.status];
  const StatusIcon = cfg.icon;

  useEffect(() => {
    if (isExpanded && !details) {
      setLoading(true);
      apiService
        .getTrace(trace.id)
        .then(setDetails)
        .finally(() => setLoading(false));
    }
  }, [isExpanded, trace.id, details]);

  return (
    <div className="border-b border-gray-100 dark:border-neutral-700 last:border-0">
      <div
        className="flex items-center gap-4 p-4 hover:bg-gray-50 dark:hover:bg-neutral-700 cursor-pointer"
        onClick={onToggle}
      >
        <button className="text-gray-400 dark:text-neutral-500">
          {isExpanded ? <ChevronDown className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
        </button>
        <div className={clsx('rounded-full p-1.5', cfg.bg)}>
          <StatusIcon
            className={clsx('h-4 w-4', cfg.color, trace.status === 'in_progress' && 'animate-spin')}
          />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <GitBranch className="h-4 w-4 text-gray-400 dark:text-neutral-500" />
            <span className="font-medium text-gray-900 dark:text-white">{trace.trigger_type}</span>
            {trace.api_name && (
              <>
                <span className="text-gray-400 dark:text-neutral-500">→</span>
                <span className="text-blue-600">{trace.api_name}</span>
              </>
            )}
          </div>
          {trace.git_commit_message && (
            <p className="text-sm text-gray-500 dark:text-neutral-400 truncate mt-1">
              {trace.git_commit_message}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-neutral-400">
          <User className="h-4 w-4" />
          <span>{trace.git_author || 'unknown'}</span>
        </div>
        {trace.git_commit_sha && (
          <div className="flex items-center gap-1 text-sm text-gray-400 dark:text-neutral-500 font-mono">
            <GitCommit className="h-4 w-4" />
            <span>{trace.git_commit_sha}</span>
          </div>
        )}
        <div className="flex items-center gap-1 text-sm text-gray-500 dark:text-neutral-400 w-20 justify-end">
          <Clock className="h-4 w-4" />
          <span>{formatDuration(trace.total_duration_ms)}</span>
        </div>
        <div className="flex items-center gap-1 text-sm w-16">
          <span className="text-green-600">{trace.steps_completed}</span>
          <span className="text-gray-400 dark:text-neutral-500">/</span>
          <span className="text-gray-600 dark:text-neutral-300">{trace.steps_count}</span>
          {trace.steps_failed > 0 && (
            <span className="text-red-500 ml-1">({trace.steps_failed})</span>
          )}
        </div>
        <div className="text-sm text-gray-400 dark:text-neutral-500 w-24 text-right">
          {formatTime(trace.created_at)}
        </div>
      </div>

      {isExpanded && (
        <div className="bg-gray-50 dark:bg-neutral-800 p-4 border-t border-gray-100 dark:border-neutral-700">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
            </div>
          ) : details ? (
            <div className="grid grid-cols-2 gap-6">
              <div className="space-y-4">
                <h4 className="font-medium text-gray-900 dark:text-white">Git Information</h4>
                <div className="bg-white dark:bg-neutral-700 rounded-lg p-4 space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-500 dark:text-neutral-400">Project:</span>
                    <span className="font-mono dark:text-neutral-200">
                      {details.git_project || '-'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500 dark:text-neutral-400">Branch:</span>
                    <span className="font-mono dark:text-neutral-200">
                      {details.git_branch || '-'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500 dark:text-neutral-400">Author:</span>
                    <span>
                      {details.git_author}{' '}
                      {details.git_author_email && `<${details.git_author_email}>`}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500 dark:text-neutral-400">Commit:</span>
                    <span className="font-mono dark:text-neutral-200">
                      {details.git_commit_sha || '-'}
                    </span>
                  </div>
                  {details.git_files_changed && details.git_files_changed.length > 0 && (
                    <div>
                      <span className="text-gray-500 dark:text-neutral-400">Files changed:</span>
                      <ul className="mt-1 text-xs font-mono text-gray-600 dark:text-neutral-300 max-h-32 overflow-auto">
                        {details.git_files_changed.map((file, i) => (
                          <li key={i} className="truncate">
                            {file}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
                {details.error_summary && (
                  <div className="bg-red-50 dark:bg-red-900/20 rounded-lg p-4">
                    <h5 className="font-medium text-red-800 dark:text-red-400 mb-2">Error</h5>
                    <p className="text-sm text-red-600 dark:text-red-300">
                      {details.error_summary}
                    </p>
                  </div>
                )}
              </div>
              <div className="space-y-4">
                <h4 className="font-medium text-gray-900 dark:text-white">Pipeline Steps</h4>
                <StepTimeline steps={details.steps} />
              </div>
            </div>
          ) : (
            <p className="text-center text-gray-500 dark:text-neutral-400 py-4">
              Failed to load details
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function PipelineTracesTab() {
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
      <div className="flex items-center justify-between">
        <p className="text-gray-500 dark:text-neutral-400">
          End-to-end tracing of GitLab → Kafka → AWX pipeline
        </p>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-neutral-400">
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

      <div className="rounded-lg bg-white dark:bg-neutral-800 shadow-sm border border-gray-100 dark:border-neutral-700">
        <div className="border-b border-gray-100 dark:border-neutral-700 px-4 py-3">
          <h2 className="font-medium text-gray-900 dark:text-white">Recent Pipeline Executions</h2>
        </div>
        {traces.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-500 dark:text-neutral-400">
            <Activity className="h-12 w-12 mb-4 text-gray-300 dark:text-neutral-600" />
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

// =============================================================================
// DEPLOYMENT HISTORY TAB (ex-Deployments)
// =============================================================================

function DeploymentHistoryTab() {
  const { isReady, hasPermission } = useAuth();
  const toast = useToastActions();
  const [confirm, ConfirmDialog] = useConfirm();
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [apis, setApis] = useState<API[]>([]);
  const [selectedTenant, setSelectedTenant] = useState<string>('');
  const [selectedApi, setSelectedApi] = useState<string>('');
  const [selectedEnv, setSelectedEnv] = useState<string>('');
  const [selectedStatus, setSelectedStatus] = useState<string>('');
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const canDeploy = hasPermission('apis:deploy');
  const pageSize = 20;

  // SSE: real-time deploy events replace polling
  const handleStatusChange = useCallback((deploymentId: string, newStatus: DeploymentStatus) => {
    setDeployments((prev) =>
      prev.map((d) => (d.id === deploymentId ? { ...d, status: newStatus } : d))
    );
  }, []);

  const { deployStates, loadHistoricalLogs } = useDeployEvents({
    tenantId: selectedTenant,
    enabled: !!selectedTenant,
    onStatusChange: handleStatusChange,
  });

  const loadDeploymentsRef = useCallback(async () => {
    if (!selectedTenant) return;
    try {
      setLoading(true);
      const result = await apiService.listDeployments(selectedTenant, {
        api_id: selectedApi || undefined,
        environment: selectedEnv || undefined,
        status: selectedStatus || undefined,
        page,
        page_size: pageSize,
      });
      setDeployments(result.items);
      setTotalCount(result.total);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load deployments');
      setDeployments([]);
      setTotalCount(0);
    } finally {
      setLoading(false);
    }
  }, [selectedTenant, selectedApi, selectedEnv, selectedStatus, page]);

  useEffect(() => {
    if (isReady) loadTenants();
  }, [isReady]);

  useEffect(() => {
    if (selectedTenant) {
      loadApis(selectedTenant);
      setPage(1);
    }
  }, [selectedTenant]);

  useEffect(() => {
    if (selectedTenant) {
      loadDeploymentsRef();
    }
  }, [loadDeploymentsRef]);

  async function loadTenants() {
    try {
      const data = await apiService.getTenants();
      setTenants(data);
      if (data.length > 0) setSelectedTenant(data[0].id);
      setLoading(false);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load tenants');
      setLoading(false);
    }
  }

  async function loadApis(tenantId: string) {
    try {
      const data = await apiService.getApis(tenantId);
      setApis(data);
    } catch (err: unknown) {
      console.error('Failed to load APIs:', err);
    }
  }

  const handleExpand = useCallback(
    (deploymentId: string) => {
      if (expandedId === deploymentId) {
        setExpandedId(null);
        return;
      }
      setExpandedId(deploymentId);
      // Load historical logs for completed deployments
      const deployment = deployments.find((d) => d.id === deploymentId);
      if (deployment && deployment.status !== 'in_progress' && deployment.status !== 'pending') {
        loadHistoricalLogs(deploymentId).catch(console.error);
      }
    },
    [expandedId, deployments, loadHistoricalLogs]
  );

  const handleRollback = useCallback(
    async (deploymentId: string, apiName: string, apiId: string) => {
      // Load previous successful versions for version selector
      let versions: Deployment[] = [];
      try {
        const result = await apiService.listDeployments(selectedTenant, {
          api_id: apiId,
          status: 'success',
          page: 1,
          page_size: 10,
        });
        versions = result.items.filter((d) => d.id !== deploymentId);
        // versions available for future version-selector UI
      } catch {
        // Fallback: rollback without version selection
      }

      const targetLabel =
        versions.length > 0
          ? `Select a version to rollback "${apiName}" to, or confirm to use the previous version.`
          : `Are you sure you want to rollback the deployment for "${apiName}"? This will restore the previous version.`;

      const confirmed = await confirm({
        title: 'Rollback Deployment',
        message: targetLabel,
        confirmLabel: 'Rollback',
        variant: 'warning',
      });
      if (!confirmed) return;

      try {
        await apiService.rollbackDeployment(selectedTenant, deploymentId);
        toast.success(`Deployment for ${apiName} rolled back successfully`);
        loadDeploymentsRef();
      } catch (err: unknown) {
        toast.error(err instanceof Error ? err.message : 'Failed to rollback deployment');
      }
    },
    [selectedTenant, confirm, toast, loadDeploymentsRef]
  );

  const deployStatusColors: Record<string, string> = {
    pending: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
    in_progress: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
    success: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
    failed: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
    rolled_back: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
  };

  const envColors: Record<string, string> = {
    dev: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
    staging: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
    production: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  };

  const totalPages = Math.ceil(totalCount / pageSize);

  if (loading && tenants.length === 0) {
    return (
      <div className="space-y-6">
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-sm border border-gray-100 dark:border-neutral-700 p-4">
          <div className="h-10 w-48 bg-gray-200 dark:bg-neutral-700 rounded animate-pulse" />
        </div>
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-sm border border-gray-100 dark:border-neutral-700 overflow-hidden">
          <TableSkeleton rows={5} columns={7} />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Filters */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-sm border border-gray-100 dark:border-neutral-700 p-4">
        <div className="flex flex-wrap gap-4 items-end">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1">
              Tenant
            </label>
            <select
              value={selectedTenant}
              onChange={(e) => {
                setSelectedTenant(e.target.value);
                setSelectedApi('');
                setPage(1);
              }}
              className="w-48 border border-gray-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              {tenants.map((tenant) => (
                <option key={tenant.id} value={tenant.id}>
                  {tenant.display_name || tenant.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1">
              API
            </label>
            <select
              value={selectedApi}
              onChange={(e) => {
                setSelectedApi(e.target.value);
                setPage(1);
              }}
              className="w-48 border border-gray-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="">All APIs</option>
              {apis.map((api) => (
                <option key={api.id} value={api.id}>
                  {api.display_name || api.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1">
              Environment
            </label>
            <select
              value={selectedEnv}
              onChange={(e) => {
                setSelectedEnv(e.target.value);
                setPage(1);
              }}
              className="w-40 border border-gray-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="">All</option>
              <option value="dev">Dev</option>
              <option value="staging">Staging</option>
              <option value="production">Production</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1">
              Status
            </label>
            <select
              value={selectedStatus}
              onChange={(e) => {
                setSelectedStatus(e.target.value);
                setPage(1);
              }}
              className="w-40 border border-gray-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="">All</option>
              <option value="pending">Pending</option>
              <option value="in_progress">In Progress</option>
              <option value="success">Success</option>
              <option value="failed">Failed</option>
              <option value="rolled_back">Rolled Back</option>
            </select>
          </div>
          <button
            onClick={loadDeploymentsRef}
            className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 text-sm"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg">
          {error}
          <button onClick={() => setError(null)} className="float-right font-bold">
            &times;
          </button>
        </div>
      )}

      {/* Deployments List */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-sm border border-gray-100 dark:border-neutral-700 overflow-hidden">
        {loading ? (
          <TableSkeleton rows={5} columns={7} />
        ) : deployments.length === 0 ? (
          <EmptyState variant="deployments" description="Deploy an API to see it here." />
        ) : (
          <div className="divide-y divide-gray-200 dark:divide-neutral-700">
            {/* Table header */}
            <div className="grid grid-cols-[2fr_1fr_1fr_1fr_1.5fr_1fr_1fr] gap-2 px-6 py-3 bg-gray-50 dark:bg-neutral-700 text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase tracking-wider">
              <span>API</span>
              <span>Environment</span>
              <span>Version</span>
              <span>Status</span>
              <span>Created</span>
              <span>Deployed By</span>
              <span>Actions</span>
            </div>
            {deployments.map((deployment) => {
              const isExpanded = expandedId === deployment.id;
              const deployState = deployStates[deployment.id];
              const liveStatus = deployState?.status || deployment.status;

              return (
                <div key={deployment.id}>
                  <div
                    className={clsx(
                      'grid grid-cols-[2fr_1fr_1fr_1fr_1.5fr_1fr_1fr] gap-2 px-6 py-4 items-center cursor-pointer transition-colors',
                      isExpanded
                        ? 'bg-blue-50 dark:bg-blue-900/10'
                        : 'hover:bg-gray-50 dark:hover:bg-neutral-700'
                    )}
                    onClick={() => handleExpand(deployment.id)}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <button className="text-gray-400 dark:text-neutral-500 shrink-0">
                        {isExpanded ? (
                          <ChevronDown className="h-4 w-4" />
                        ) : (
                          <ChevronRight className="h-4 w-4" />
                        )}
                      </button>
                      <div className="min-w-0">
                        <div className="text-sm font-medium text-gray-900 dark:text-white truncate">
                          {deployment.api_name}
                        </div>
                        {deployment.commit_sha && (
                          <div className="text-xs text-gray-400 dark:text-neutral-500 font-mono">
                            {deployment.commit_sha.slice(0, 7)}
                          </div>
                        )}
                        {deployment.error_message && (
                          <div className="text-xs text-red-500 dark:text-red-400 truncate">
                            {deployment.error_message}
                          </div>
                        )}
                      </div>
                    </div>
                    <div>
                      <span
                        className={`px-2 py-1 text-xs font-medium rounded ${envColors[deployment.environment] || 'bg-gray-100 text-gray-700'}`}
                      >
                        {deployment.environment.toUpperCase()}
                      </span>
                    </div>
                    <div className="text-sm text-gray-500 dark:text-neutral-400">
                      v{deployment.version}
                      {deployment.rollback_of && (
                        <div className="text-xs text-orange-500 dark:text-orange-400">
                          rollback &rarr; v{deployment.rollback_version}
                        </div>
                      )}
                    </div>
                    <div>
                      <span
                        className={clsx(
                          'inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-full',
                          deployStatusColors[liveStatus] || ''
                        )}
                      >
                        {liveStatus === 'in_progress' && (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        )}
                        {liveStatus.replace('_', ' ')}
                      </span>
                    </div>
                    <div className="text-sm text-gray-500 dark:text-neutral-400">
                      {new Date(deployment.created_at).toLocaleString()}
                    </div>
                    <div className="text-sm text-gray-500 dark:text-neutral-400 truncate">
                      {deployment.deployed_by}
                    </div>
                    <div className="text-sm" onClick={(e) => e.stopPropagation()}>
                      {canDeploy && deployment.status === 'success' && (
                        <button
                          onClick={() =>
                            handleRollback(deployment.id, deployment.api_name, deployment.api_id)
                          }
                          className="text-orange-600 hover:text-orange-800 dark:text-orange-400 dark:hover:text-orange-300"
                        >
                          Rollback
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Expanded detail: live logs + progress */}
                  {isExpanded && (
                    <div className="bg-gray-50 dark:bg-neutral-800/50 border-t border-gray-100 dark:border-neutral-700 px-6 py-4 space-y-4">
                      {/* Progress indicator for active deployments */}
                      {(liveStatus === 'in_progress' || deployState) && (
                        <div className="flex items-center gap-4">
                          <span className="text-sm font-medium text-gray-700 dark:text-neutral-300">
                            Progress
                          </span>
                          <DeployProgress
                            currentStep={deployState?.currentStep || null}
                            status={deployState?.status || deployment.status}
                          />
                        </div>
                      )}

                      {/* Deploy info summary */}
                      <div className="grid grid-cols-3 gap-4 text-sm">
                        {deployment.rollback_of && (
                          <div>
                            <span className="text-gray-500 dark:text-neutral-400">
                              Rollback of:
                            </span>{' '}
                            <span className="text-orange-600 dark:text-orange-400">
                              v{deployment.rollback_version}
                            </span>
                          </div>
                        )}
                        {deployment.spec_hash && (
                          <div>
                            <span className="text-gray-500 dark:text-neutral-400">Spec hash:</span>{' '}
                            <span className="font-mono text-gray-700 dark:text-neutral-300">
                              {deployment.spec_hash.slice(0, 12)}
                            </span>
                          </div>
                        )}
                        {deployment.error_message && (
                          <div className="col-span-3 bg-red-50 dark:bg-red-900/20 rounded-lg p-3 text-red-700 dark:text-red-400">
                            {deployment.error_message}
                          </div>
                        )}
                      </div>

                      {/* Live log viewer */}
                      <div>
                        <div className="flex items-center gap-2 mb-2">
                          <ScrollText className="h-4 w-4 text-gray-500 dark:text-neutral-400" />
                          <span className="text-sm font-medium text-gray-700 dark:text-neutral-300">
                            Deploy Logs
                          </span>
                          {liveStatus === 'in_progress' && (
                            <span className="flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400">
                              <span className="relative flex h-2 w-2">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
                                <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500" />
                              </span>
                              Live
                            </span>
                          )}
                        </div>
                        <DeployLogViewer logs={deployState?.logs || []} />
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-gray-500 dark:text-neutral-400">
            Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, totalCount)} of{' '}
            {totalCount}
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-3 py-1.5 text-sm border border-gray-300 dark:border-neutral-600 rounded-lg disabled:opacity-50 hover:bg-gray-50 dark:hover:bg-neutral-700 dark:text-white"
            >
              Previous
            </button>
            <span className="px-3 py-1.5 text-sm text-gray-700 dark:text-neutral-300">
              {page} / {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="px-3 py-1.5 text-sm border border-gray-300 dark:border-neutral-600 rounded-lg disabled:opacity-50 hover:bg-gray-50 dark:hover:bg-neutral-700 dark:text-white"
            >
              Next
            </button>
          </div>
        </div>
      )}

      {ConfirmDialog}
    </div>
  );
}

// =============================================================================
// GITLAB CONFIG TAB (ex-Git page)
// =============================================================================

function GitLabConfigTab() {
  return (
    <div className="space-y-6">
      {/* GitOps Overview */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-sm border border-gray-100 dark:border-neutral-700 p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          GitOps Integration
        </h3>
        <p className="text-gray-600 dark:text-neutral-400 mb-4">
          API definitions are managed through Git. When you commit changes to the repository,
          webhooks automatically trigger the deployment pipeline.
        </p>
        <div className="bg-gray-50 dark:bg-neutral-900 rounded-lg p-4 font-mono text-sm">
          <div className="text-gray-500 dark:text-neutral-400 mb-2"># Pipeline flow</div>
          <div className="text-blue-600">GitLab Push</div>
          <div className="text-gray-400 ml-4">↓ webhook</div>
          <div className="text-green-600 ml-4">Control-Plane-API</div>
          <div className="text-gray-400 ml-8">↓ publish event</div>
          <div className="text-purple-600 ml-8">Kafka (deploy-requests)</div>
          <div className="text-gray-400 ml-12">↓ consume</div>
          <div className="text-orange-600 ml-12">AWX Job Template</div>
          <div className="text-gray-400 ml-16">↓ deploy</div>
          <div className="text-green-600 ml-16">webMethods Gateway</div>
        </div>
      </div>

      {/* Repository Structure */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-sm border border-gray-100 dark:border-neutral-700 p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Repository Structure
        </h3>
        <div className="bg-gray-50 dark:bg-neutral-900 rounded-lg p-4 font-mono text-sm">
          <pre className="text-gray-700 dark:text-neutral-300">{`stoa-api-definitions/
├── tenants/
│   ├── tenant-acme/
│   │   ├── apis/
│   │   │   ├── customer-api/
│   │   │   │   ├── openapi.yaml
│   │   │   │   └── config.yaml
│   │   │   └── order-api/
│   │   │       └── openapi.yaml
│   │   └── mcp-servers/
│   │       └── acme-tools/
│   │           └── config.yaml
│   └── tenant-globex/
│       └── apis/
│           └── inventory-api/
│               └── openapi.yaml
└── platform/
    └── mcp-servers/
        └── shared-tools/
            └── config.yaml`}</pre>
        </div>
      </div>

      {/* External Links */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-sm border border-gray-100 dark:border-neutral-700 p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          External Resources
        </h3>
        <div className="flex flex-wrap gap-4">
          <a
            href={config.services.gitlab.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 transition-colors"
          >
            <GitBranch className="h-5 w-5" />
            GitLab Repository
            <ExternalLink className="h-4 w-4" />
          </a>
          <a
            href={config.services.awx.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
          >
            <Activity className="h-5 w-5" />
            AWX Dashboard
            <ExternalLink className="h-4 w-4" />
          </a>
        </div>
      </div>

      {/* Webhook Status */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-sm border border-gray-100 dark:border-neutral-700 p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Webhook Configuration
        </h3>
        <div className="space-y-3">
          <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-neutral-900 rounded-lg">
            <div>
              <p className="font-medium text-gray-900 dark:text-white">GitLab Webhook</p>
              <p className="text-sm text-gray-500 dark:text-neutral-400">
                Receives push and merge request events
              </p>
            </div>
            <span className="flex items-center gap-2 px-3 py-1 bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400 rounded-full text-sm">
              <CheckCircle2 className="h-4 w-4" />
              Active
            </span>
          </div>
          <div className="text-sm text-gray-500 dark:text-neutral-400">
            <p>
              <strong>Endpoint:</strong>{' '}
              <code className="bg-gray-100 dark:bg-neutral-700 px-2 py-0.5 rounded">
                {config.api.baseUrl}/webhooks/gitlab
              </code>
            </p>
            <p className="mt-1">
              <strong>Supported Events:</strong> Push Hook, Merge Request Hook, Tag Push Hook
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// MAIN DEPLOYMENTS PAGE
// =============================================================================

export function Deployments() {
  const [activeTab, setActiveTab] = useState<TabId>('pipelines');

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Deployments</h1>
        <p className="text-gray-500 dark:text-neutral-400 mt-1">
          GitOps pipeline monitoring and deployment history
        </p>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-neutral-700">
        <nav className="flex gap-8">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={clsx(
                'flex items-center gap-2 py-4 px-1 border-b-2 font-medium text-sm transition-colors',
                activeTab === tab.id
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 dark:text-neutral-400 hover:text-gray-700 dark:hover:text-neutral-300 hover:border-gray-300 dark:hover:border-neutral-500'
              )}
            >
              <tab.icon className="h-5 w-5" />
              {tab.name}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab Content */}
      <div>
        {activeTab === 'pipelines' && <PipelineTracesTab />}
        {activeTab === 'history' && <DeploymentHistoryTab />}
        {activeTab === 'config' && <GitLabConfigTab />}
      </div>
    </div>
  );
}

export default Deployments;
