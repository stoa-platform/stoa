import { useState } from 'react';
import {
  X,
  RotateCcw,
  Trash2,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Server,
  Zap,
} from 'lucide-react';
import { apiService } from '../../services/api';
import { SyncStatusBadge } from '../../components/SyncStatusBadge';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import type { GatewayDeployment } from '../../types';

interface DeploymentDetailDrawerProps {
  deployment: GatewayDeployment;
  onClose: () => void;
  onAction: () => void;
}

function formatDate(iso?: string): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString();
}

function SyncTimeline({ deployment: d }: { deployment: GatewayDeployment }) {
  const steps = [
    {
      label: 'Created',
      time: d.created_at,
      done: true,
    },
    {
      label: 'First sync attempt',
      time: d.last_sync_attempt || undefined,
      done: !!d.last_sync_attempt,
    },
    {
      label: 'Synced to gateway',
      time: d.last_sync_success || undefined,
      done: d.sync_status === 'synced',
      failed: d.sync_status === 'error' || d.sync_status === 'drifted',
    },
  ];

  return (
    <div className="space-y-3">
      {steps.map((step, i) => (
        <div key={i} className="flex items-start gap-3">
          <div className="flex flex-col items-center">
            <div
              className={`w-3 h-3 rounded-full mt-1 ${
                step.failed
                  ? 'bg-red-500'
                  : step.done
                    ? 'bg-green-500'
                    : 'bg-neutral-300 dark:bg-neutral-600'
              }`}
            />
            {i < steps.length - 1 && (
              <div className="w-0.5 h-6 bg-neutral-200 dark:bg-neutral-700" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-neutral-900 dark:text-white">{step.label}</p>
            <p className="text-xs text-neutral-500 dark:text-neutral-400">
              {formatDate(step.time)}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

function StateViewer({ title, state }: { title: string; state?: Record<string, unknown> }) {
  if (!state || Object.keys(state).length === 0) return null;

  return (
    <div>
      <h4 className="text-xs font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-2">
        {title}
      </h4>
      <div className="bg-neutral-50 dark:bg-neutral-900 rounded-lg p-3 text-xs font-mono space-y-1 overflow-x-auto">
        {Object.entries(state).map(([key, value]) => (
          <div key={key} className="flex gap-2">
            <span className="text-neutral-500 dark:text-neutral-400 shrink-0">{key}:</span>
            <span
              className={`break-all ${
                value === '' || value === null || value === undefined
                  ? 'text-red-500 dark:text-red-400 italic'
                  : 'text-neutral-900 dark:text-white'
              }`}
            >
              {value === ''
                ? '(empty)'
                : value === null || value === undefined
                  ? '(null)'
                  : String(value)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function DeploymentDetailDrawer({
  deployment: d,
  onClose,
  onAction,
}: DeploymentDetailDrawerProps) {
  const toast = useToastActions();
  const [confirm, ConfirmDialog] = useConfirm();
  const [loading, setLoading] = useState(false);
  const [testResult, setTestResult] = useState<{
    reachable: boolean;
    status_code?: number;
    latency_ms?: number;
    error?: string;
    path?: string;
  } | null>(null);
  const [testing, setTesting] = useState(false);

  const apiName = (d.desired_state?.api_name as string) || d.api_catalog_id?.slice(0, 8) || '—';
  const gatewayLabel =
    d.gateway_display_name || d.gateway_name || d.gateway_instance_id?.slice(0, 8) || '—';
  const isRetryable =
    d.sync_status === 'error' || d.sync_status === 'drifted' || d.sync_status === 'pending';

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await apiService.testDeployment(d.id);
      setTestResult(result);
    } catch {
      setTestResult({ reachable: false, error: 'Failed to run test' });
    } finally {
      setTesting(false);
    }
  };

  const handleForceSync = async () => {
    setLoading(true);
    try {
      await apiService.forceSyncDeployment(d.id);
      toast.success('Re-sync triggered');
      onAction();
    } catch {
      toast.error('Failed to trigger re-sync');
    } finally {
      setLoading(false);
    }
  };

  const handleUndeploy = async () => {
    const confirmed = await confirm({
      title: 'Undeploy API',
      message: `Remove "${apiName}" from ${gatewayLabel}? The gateway will stop proxying this API.`,
      confirmLabel: 'Undeploy',
      variant: 'danger',
    });
    if (!confirmed) return;

    setLoading(true);
    try {
      await apiService.undeployFromGateway(d.id);
      toast.success('Undeploy initiated');
      onAction();
      onClose();
    } catch {
      toast.error('Failed to undeploy');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {ConfirmDialog}
      {/* Backdrop */}
      <div className="fixed inset-0 z-40 bg-black/30" onClick={onClose} />

      {/* Drawer */}
      <div className="fixed inset-y-0 right-0 z-50 w-full max-w-lg bg-white dark:bg-neutral-800 shadow-xl overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-white dark:bg-neutral-800 border-b dark:border-neutral-700 px-6 py-4 flex items-center justify-between z-10">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold text-neutral-900 dark:text-white truncate">
              {apiName}
            </h2>
            <div className="flex items-center gap-2 mt-1">
              <Server className="h-3.5 w-3.5 text-neutral-400" />
              <span className="text-sm text-neutral-500 dark:text-neutral-400">{gatewayLabel}</span>
              {d.gateway_environment && (
                <span className="text-xs font-semibold uppercase px-2 py-0.5 rounded bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-400">
                  {d.gateway_environment}
                </span>
              )}
              {d.gateway_type && (
                <span className="text-xs text-neutral-400 dark:text-neutral-500">
                  {d.gateway_type}
                </span>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-700 hover:text-neutral-600 dark:hover:text-neutral-300"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="px-6 py-5 space-y-6">
          {/* Status card */}
          <div className="flex items-center justify-between">
            <SyncStatusBadge status={d.sync_status} className="text-sm px-3 py-1" />
            <div className="flex items-center gap-1 text-xs text-neutral-500 dark:text-neutral-400">
              <Clock className="h-3.5 w-3.5" />
              Attempt {d.sync_attempts} / 3
            </div>
          </div>

          {/* Error banner */}
          {d.sync_error && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
              <div className="flex items-start gap-2">
                <AlertTriangle className="h-4 w-4 text-red-500 mt-0.5 shrink-0" />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-red-800 dark:text-red-300">Sync Error</p>
                  <p className="text-sm text-red-700 dark:text-red-400 mt-1 break-all font-mono">
                    {d.sync_error}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Success banner */}
          {d.sync_status === 'synced' && (
            <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-green-500" />
                <p className="text-sm text-green-800 dark:text-green-300">
                  Successfully synced to gateway
                </p>
              </div>
            </div>
          )}

          {/* Connectivity Test */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-semibold text-neutral-900 dark:text-white">
                Gateway Connectivity
              </h3>
              <button
                onClick={handleTest}
                disabled={testing}
                className="flex items-center gap-1.5 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 disabled:opacity-50"
              >
                <Zap className={`h-3.5 w-3.5 ${testing ? 'animate-pulse' : ''}`} />
                {testing ? 'Testing...' : 'Test Now'}
              </button>
            </div>
            {testResult && (
              <div
                className={`rounded-lg p-3 text-sm ${
                  testResult.reachable
                    ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
                    : testResult.status_code && testResult.status_code < 500
                      ? 'bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800'
                      : 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800'
                }`}
              >
                <div className="flex items-center gap-2 mb-1">
                  {testResult.reachable ? (
                    <CheckCircle2 className="h-4 w-4 text-green-500" />
                  ) : testResult.status_code && testResult.status_code < 500 ? (
                    <AlertTriangle className="h-4 w-4 text-amber-500" />
                  ) : (
                    <AlertTriangle className="h-4 w-4 text-red-500" />
                  )}
                  <span
                    className={`font-medium ${
                      testResult.reachable
                        ? 'text-green-800 dark:text-green-300'
                        : testResult.status_code && testResult.status_code < 500
                          ? 'text-amber-800 dark:text-amber-300'
                          : 'text-red-800 dark:text-red-300'
                    }`}
                  >
                    {testResult.reachable
                      ? `Reachable — HTTP ${testResult.status_code} (${testResult.latency_ms}ms)`
                      : testResult.status_code
                        ? `Gateway responded HTTP ${testResult.status_code} — API not serving (${testResult.latency_ms}ms)`
                        : 'Unreachable'}
                  </span>
                </div>
                {testResult.path && (
                  <p className="text-xs font-mono text-neutral-500 dark:text-neutral-400">
                    GET {testResult.path}
                  </p>
                )}
                {testResult.error && (
                  <p className="text-xs font-mono text-red-600 dark:text-red-400 mt-1">
                    {testResult.error}
                  </p>
                )}
              </div>
            )}
          </div>

          {/* Timeline */}
          <div>
            <h3 className="text-sm font-semibold text-neutral-900 dark:text-white mb-3">
              Sync Timeline
            </h3>
            <SyncTimeline deployment={d} />
          </div>

          {/* Desired state */}
          <StateViewer title="Desired State" state={d.desired_state} />

          {/* Actual state */}
          {d.actual_state && Object.keys(d.actual_state).length > 0 && (
            <StateViewer title="Actual State (on gateway)" state={d.actual_state} />
          )}

          {/* Metadata */}
          <div>
            <h4 className="text-xs font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-2">
              Identifiers
            </h4>
            <dl className="text-xs space-y-1">
              <div className="flex gap-2">
                <dt className="text-neutral-500 dark:text-neutral-400 shrink-0">Deployment ID:</dt>
                <dd className="text-neutral-900 dark:text-white font-mono break-all">{d.id}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="text-neutral-500 dark:text-neutral-400 shrink-0">Catalog ID:</dt>
                <dd className="text-neutral-900 dark:text-white font-mono break-all">
                  {d.api_catalog_id}
                </dd>
              </div>
              {d.gateway_resource_id && (
                <div className="flex gap-2">
                  <dt className="text-neutral-500 dark:text-neutral-400 shrink-0">
                    Gateway Resource:
                  </dt>
                  <dd className="text-neutral-900 dark:text-white font-mono break-all">
                    {d.gateway_resource_id}
                  </dd>
                </div>
              )}
            </dl>
          </div>
        </div>

        {/* Actions */}
        <div className="sticky bottom-0 bg-white dark:bg-neutral-800 border-t dark:border-neutral-700 px-6 py-4 flex gap-3">
          {isRetryable && (
            <button
              onClick={handleForceSync}
              disabled={loading}
              className="flex-1 flex items-center justify-center gap-2 bg-blue-600 text-white px-4 py-2.5 rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50"
            >
              <RotateCcw className="h-4 w-4" />
              Force Sync
            </button>
          )}
          <button
            onClick={handleUndeploy}
            disabled={loading}
            className="flex items-center justify-center gap-2 border border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 px-4 py-2.5 rounded-lg text-sm hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50"
          >
            <Trash2 className="h-4 w-4" />
            Undeploy
          </button>
        </div>
      </div>
    </>
  );
}
