import { useState, useEffect, useCallback } from 'react';
import { apiService } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { config } from '../config';
import type { Deployment, Tenant, API, TraceSummary, PipelineTrace, TraceStats, TraceStep, TraceStatus } from '../types';
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
  { id: 'pipelines', name: 'Pipeline Traces', icon: Activity, description: 'GitLab → Kafka → AWX traces' },
  { id: 'history', name: 'Deployment History', icon: Rocket, description: 'API deployment records' },
  { id: 'config', name: 'GitLab Config', icon: Settings, description: 'GitOps configuration' },
];

// =============================================================================
// PIPELINE TRACES TAB (ex-Monitoring)
// =============================================================================

const statusConfig: Record<TraceStatus, { icon: typeof CheckCircle2; color: string; bg: string }> = {
  pending: { icon: Clock, color: 'text-gray-500', bg: 'bg-gray-100' },
  in_progress: { icon: Loader2, color: 'text-blue-500', bg: 'bg-blue-100' },
  success: { icon: CheckCircle2, color: 'text-green-500', bg: 'bg-green-100' },
  failed: { icon: XCircle, color: 'text-red-500', bg: 'bg-red-100' },
  skipped: { icon: AlertCircle, color: 'text-yellow-500', bg: 'bg-yellow-100' },
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
  return date.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function StatsCard({ title, value, subtitle, icon: Icon, color }: {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: typeof Activity;
  color: string;
}) {
  return (
    <div className="rounded-lg bg-white p-6 shadow-sm border border-gray-100">
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
              <div className="absolute left-4 top-8 h-full w-0.5 bg-gray-200" />
            )}
            <div className={clsx('flex items-start gap-3 rounded-lg p-3', cfg.bg)}>
              <div className={clsx('rounded-full p-1', cfg.bg)}>
                <StepIcon className={clsx('h-5 w-5', cfg.color, step.status === 'in_progress' && 'animate-spin')} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <StepTypeIcon className="h-4 w-4 text-gray-400" />
                  <span className="font-medium text-gray-900">{stepInfo.label}</span>
                  {step.duration_ms && (
                    <span className="text-xs text-gray-500">({formatDuration(step.duration_ms)})</span>
                  )}
                </div>
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
                {step.error && (
                  <div className="mt-2 text-xs text-red-600 bg-red-50 rounded p-2">
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

function TraceRow({ trace, isExpanded, onToggle }: {
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
      apiService.getTrace(trace.id)
        .then(setDetails)
        .finally(() => setLoading(false));
    }
  }, [isExpanded, trace.id, details]);

  return (
    <div className="border-b border-gray-100 last:border-0">
      <div
        className="flex items-center gap-4 p-4 hover:bg-gray-50 cursor-pointer"
        onClick={onToggle}
      >
        <button className="text-gray-400">
          {isExpanded ? <ChevronDown className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
        </button>
        <div className={clsx('rounded-full p-1.5', cfg.bg)}>
          <StatusIcon className={clsx('h-4 w-4', cfg.color, trace.status === 'in_progress' && 'animate-spin')} />
        </div>
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
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <User className="h-4 w-4" />
          <span>{trace.git_author || 'unknown'}</span>
        </div>
        {trace.git_commit_sha && (
          <div className="flex items-center gap-1 text-sm text-gray-400 font-mono">
            <GitCommit className="h-4 w-4" />
            <span>{trace.git_commit_sha}</span>
          </div>
        )}
        <div className="flex items-center gap-1 text-sm text-gray-500 w-20 justify-end">
          <Clock className="h-4 w-4" />
          <span>{formatDuration(trace.total_duration_ms)}</span>
        </div>
        <div className="flex items-center gap-1 text-sm w-16">
          <span className="text-green-600">{trace.steps_completed}</span>
          <span className="text-gray-400">/</span>
          <span className="text-gray-600">{trace.steps_count}</span>
          {trace.steps_failed > 0 && (
            <span className="text-red-500 ml-1">({trace.steps_failed})</span>
          )}
        </div>
        <div className="text-sm text-gray-400 w-24 text-right">
          {formatTime(trace.created_at)}
        </div>
      </div>

      {isExpanded && (
        <div className="bg-gray-50 p-4 border-t border-gray-100">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
            </div>
          ) : details ? (
            <div className="grid grid-cols-2 gap-6">
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
                {details.error_summary && (
                  <div className="bg-red-50 rounded-lg p-4">
                    <h5 className="font-medium text-red-800 mb-2">Error</h5>
                    <p className="text-sm text-red-600">{details.error_summary}</p>
                  </div>
                )}
              </div>
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
        <p className="text-gray-500">End-to-end tracing of GitLab → Kafka → AWX pipeline</p>
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

      {stats && (
        <div className="grid grid-cols-4 gap-4">
          <StatsCard title="Total Pipelines" value={stats.total} icon={Activity} color="bg-blue-500" />
          <StatsCard
            title="Success Rate"
            value={`${stats.success_rate}%`}
            subtitle={`${stats.by_status?.success || 0} successful`}
            icon={CheckCircle2}
            color="bg-green-500"
          />
          <StatsCard title="Failed" value={stats.by_status?.failed || 0} icon={XCircle} color="bg-red-500" />
          <StatsCard title="Avg Duration" value={formatDuration(stats.avg_duration_ms)} icon={Clock} color="bg-purple-500" />
        </div>
      )}

      <div className="rounded-lg bg-white shadow-sm border border-gray-100">
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

// =============================================================================
// DEPLOYMENT HISTORY TAB (ex-Deployments)
// =============================================================================

function DeploymentHistoryTab() {
  const { isReady } = useAuth();
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [apis, setApis] = useState<API[]>([]);
  const [selectedTenant, setSelectedTenant] = useState<string>('');
  const [selectedApi, setSelectedApi] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isReady) loadTenants();
  }, [isReady]);

  useEffect(() => {
    if (selectedTenant) {
      loadApis(selectedTenant);
      loadDeployments(selectedTenant);
    }
  }, [selectedTenant]);

  useEffect(() => {
    if (selectedTenant) {
      loadDeployments(selectedTenant, selectedApi || undefined);
    }
  }, [selectedApi]);

  async function loadTenants() {
    try {
      const data = await apiService.getTenants();
      setTenants(data);
      if (data.length > 0) setSelectedTenant(data[0].id);
      setLoading(false);
    } catch (err: any) {
      setError(err.message || 'Failed to load tenants');
      setLoading(false);
    }
  }

  async function loadApis(tenantId: string) {
    try {
      const data = await apiService.getApis(tenantId);
      setApis(data);
    } catch (err: any) {
      console.error('Failed to load APIs:', err);
    }
  }

  async function loadDeployments(tenantId: string, apiId?: string) {
    try {
      setLoading(true);
      const data = await apiService.getDeployments(tenantId, apiId);
      setDeployments(data);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to load deployments');
      setDeployments([]);
    } finally {
      setLoading(false);
    }
  }

  async function handleRollback(deploymentId: string) {
    if (!confirm('Are you sure you want to rollback this deployment?')) return;
    try {
      await apiService.rollbackDeployment(selectedTenant, deploymentId);
      loadDeployments(selectedTenant, selectedApi || undefined);
    } catch (err: any) {
      setError(err.message || 'Failed to rollback deployment');
    }
  }

  const statusColors: Record<string, string> = {
    pending: 'bg-yellow-100 text-yellow-800',
    in_progress: 'bg-blue-100 text-blue-800',
    success: 'bg-green-100 text-green-800',
    failed: 'bg-red-100 text-red-800',
    rolled_back: 'bg-gray-100 text-gray-800',
  };

  if (loading && tenants.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Filters */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-100 p-4">
        <div className="flex flex-wrap gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Tenant</label>
            <select
              value={selectedTenant}
              onChange={(e) => {
                setSelectedTenant(e.target.value);
                setSelectedApi('');
              }}
              className="w-48 border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              {tenants.map((tenant) => (
                <option key={tenant.id} value={tenant.id}>
                  {tenant.display_name || tenant.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">API (optional)</label>
            <select
              value={selectedApi}
              onChange={(e) => setSelectedApi(e.target.value)}
              className="w-48 border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="">All APIs</option>
              {apis.map((api) => (
                <option key={api.id} value={api.id}>
                  {api.display_name || api.name}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error}
          <button onClick={() => setError(null)} className="float-right font-bold">&times;</button>
        </div>
      )}

      {/* Deployments List */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-100 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-32">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
          </div>
        ) : deployments.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <Rocket className="mx-auto h-12 w-12 text-gray-400" />
            <p className="mt-2">No deployments found</p>
            <p className="text-sm text-gray-400">Deploy an API to see it here</p>
          </div>
        ) : (
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">API</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Environment</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Version</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Started</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Deployed By</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {deployments.map((deployment) => (
                <tr key={deployment.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium text-gray-900">{deployment.api_name}</div>
                    <div className="text-xs text-gray-500 font-mono">{deployment.api_id}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`px-2 py-1 text-xs font-medium rounded ${
                      deployment.environment === 'dev' ? 'bg-green-100 text-green-700' : 'bg-blue-100 text-blue-700'
                    }`}>
                      {deployment.environment.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    v{deployment.version}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-full ${statusColors[deployment.status]}`}>
                      {deployment.status.replace('_', ' ')}
                    </span>
                    {deployment.error_message && (
                      <p className="text-xs text-red-600 mt-1 max-w-xs truncate" title={deployment.error_message}>
                        {deployment.error_message}
                      </p>
                    )}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {new Date(deployment.started_at).toLocaleString()}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {deployment.deployed_by}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    <div className="flex gap-2">
                      {deployment.awx_job_id && (
                        <a
                          href={config.services.awx.getJobUrl(deployment.awx_job_id)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:text-blue-800"
                        >
                          View Job
                        </a>
                      )}
                      {deployment.status === 'success' && (
                        <button
                          onClick={() => handleRollback(deployment.id)}
                          className="text-orange-600 hover:text-orange-800"
                        >
                          Rollback
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
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
      <div className="bg-white rounded-lg shadow-sm border border-gray-100 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">GitOps Integration</h3>
        <p className="text-gray-600 mb-4">
          API definitions are managed through Git. When you commit changes to the repository,
          webhooks automatically trigger the deployment pipeline.
        </p>
        <div className="bg-gray-50 rounded-lg p-4 font-mono text-sm">
          <div className="text-gray-500 mb-2"># Pipeline flow</div>
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
      <div className="bg-white rounded-lg shadow-sm border border-gray-100 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Repository Structure</h3>
        <div className="bg-gray-50 rounded-lg p-4 font-mono text-sm">
          <pre className="text-gray-700">{`stoa-api-definitions/
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
      <div className="bg-white rounded-lg shadow-sm border border-gray-100 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">External Resources</h3>
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
      <div className="bg-white rounded-lg shadow-sm border border-gray-100 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Webhook Configuration</h3>
        <div className="space-y-3">
          <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
            <div>
              <p className="font-medium text-gray-900">GitLab Webhook</p>
              <p className="text-sm text-gray-500">Receives push and merge request events</p>
            </div>
            <span className="flex items-center gap-2 px-3 py-1 bg-green-100 text-green-800 rounded-full text-sm">
              <CheckCircle2 className="h-4 w-4" />
              Active
            </span>
          </div>
          <div className="text-sm text-gray-500">
            <p><strong>Endpoint:</strong> <code className="bg-gray-100 px-2 py-0.5 rounded">{config.api.baseUrl}/webhooks/gitlab</code></p>
            <p className="mt-1"><strong>Supported Events:</strong> Push Hook, Merge Request Hook, Tag Push Hook</p>
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
        <h1 className="text-2xl font-bold text-gray-900">Deployments</h1>
        <p className="text-gray-500 mt-1">GitOps pipeline monitoring and deployment history</p>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-8">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={clsx(
                'flex items-center gap-2 py-4 px-1 border-b-2 font-medium text-sm transition-colors',
                activeTab === tab.id
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
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
