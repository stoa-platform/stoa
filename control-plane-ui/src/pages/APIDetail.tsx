/**
 * API Detail Page — Command center for managing a single API (CAB-1813)
 *
 * Tabs: Overview | Spec | Versions | Deployments | Promotions
 * Features: Environment pipeline, portal toggle, deploy action, RBAC
 */

import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import {
  ArrowLeft,
  Info,
  FileJson,
  GitCommit,
  Rocket,
  ArrowUpRight,
  Pencil,
  Trash2,
  ExternalLink,
  Copy,
  Check,
  AlertTriangle,
} from 'lucide-react';
import { apiService } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { useEnvironmentMode } from '../hooks/useEnvironmentMode';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import { Button } from '@stoa/shared/components/Button';
import { EnvironmentPipeline } from '../components/EnvironmentPipeline';
import type { API } from '../types';
import type { Schemas } from '@stoa/shared/api-types';
import type { ApiLifecycleState } from '../services/api/apiLifecycle';
import { ApiLifecyclePanel } from './ApiLifecyclePanel';

type TabId = 'overview' | 'spec' | 'versions' | 'deployments' | 'promotions';

const statusColors: Record<string, string> = {
  draft: 'bg-neutral-100 text-neutral-800 dark:bg-neutral-700 dark:text-neutral-300',
  published: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  deprecated: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
};

export function APIDetail() {
  const { tenantId, apiId } = useParams<{ tenantId: string; apiId: string }>();
  const navigate = useNavigate();
  const { hasPermission } = useAuth();
  const { canEdit, canDelete, canDeploy } = useEnvironmentMode();
  const toast = useToastActions();
  const [confirm, ConfirmDialog] = useConfirm();
  const [activeTab, setActiveTab] = useState<TabId>('overview');

  const canManage = hasPermission('apis:update') && canEdit;
  const canRemove = hasPermission('apis:delete') && canDelete;

  // Fetch API details
  const {
    data: api,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['api', tenantId, apiId],
    queryFn: () => apiService.getApi(tenantId!, apiId!),
    enabled: !!tenantId && !!apiId,
  });

  const { data: lifecycle, isLoading: lifecycleLoading } = useQuery({
    queryKey: ['api-lifecycle', tenantId, apiId],
    queryFn: () => apiService.getApiLifecycleState(tenantId!, apiId!),
    enabled: !!tenantId && !!apiId,
  });

  // Fetch version history (lazy — only when tab is active)
  const { data: versions = [], isLoading: versionsLoading } = useQuery({
    queryKey: ['api-versions', tenantId, apiId],
    queryFn: () => apiService.getApiVersions(tenantId!, apiId!),
    enabled: !!tenantId && !!apiId && activeTab === 'versions',
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: () => apiService.deleteApi(tenantId!, apiId!),
    onSuccess: () => {
      toast.success('API deleted');
      navigate('/apis');
    },
    onError: () => toast.error('Failed to delete API'),
  });

  const handleDelete = async () => {
    const confirmed = await confirm({
      title: 'Delete API',
      message: `Are you sure you want to delete "${api?.display_name}"? This action cannot be undone.`,
      confirmLabel: 'Delete',
      variant: 'danger',
    });
    if (confirmed) deleteMutation.mutate();
  };

  const tabs: { id: TabId; label: string; icon: React.ReactNode }[] = [
    { id: 'overview', label: 'Overview', icon: <Info className="h-4 w-4" /> },
    { id: 'spec', label: 'Spec', icon: <FileJson className="h-4 w-4" /> },
    { id: 'versions', label: 'Versions', icon: <GitCommit className="h-4 w-4" /> },
    { id: 'deployments', label: 'Deployments', icon: <Rocket className="h-4 w-4" /> },
    { id: 'promotions', label: 'Promotions', icon: <ArrowUpRight className="h-4 w-4" /> },
  ];

  // --- Loading state ---
  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-2">
          <div className="h-4 w-4 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
          <div className="h-4 w-24 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
        </div>
        <CardSkeleton className="h-32" />
        <CardSkeleton className="h-64" />
      </div>
    );
  }

  // --- Error state ---
  if (error || !api) {
    return (
      <div className="space-y-6">
        <button
          onClick={() => navigate('/apis')}
          className="flex items-center gap-2 text-sm text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-white"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to APIs
        </button>
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6 text-center">
          <p className="text-red-800 dark:text-red-400">
            {error instanceof Error ? error.message : 'API not found'}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {ConfirmDialog}

      {/* Back button */}
      <button
        onClick={() => navigate('/apis')}
        className="flex items-center gap-2 text-sm text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-white transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to APIs
      </button>

      {/* Header */}
      <div className="bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg p-6">
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">
                {api.display_name}
              </h1>
              <span className="text-sm text-neutral-500 dark:text-neutral-400">v{api.version}</span>
              <span
                className={`px-2 py-0.5 rounded-full text-xs font-medium ${statusColors[api.status] || statusColors.draft}`}
              >
                {api.status}
              </span>
            </div>
            {api.description && (
              <p className="text-neutral-600 dark:text-neutral-400 text-sm max-w-2xl">
                {api.description}
              </p>
            )}
            <div className="flex items-center gap-2 text-xs text-neutral-500 dark:text-neutral-400">
              <ExternalLink className="h-3 w-3" />
              <span className="font-mono">{api.backend_url}</span>
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2 flex-shrink-0">
            {canManage && (
              <Button variant="ghost" size="sm" onClick={() => navigate(`/apis?edit=${api.id}`)}>
                <Pencil className="h-4 w-4" />
              </Button>
            )}
            {canRemove && (
              <Button variant="ghost" size="sm" onClick={handleDelete}>
                <Trash2 className="h-4 w-4 text-red-500" />
              </Button>
            )}
          </div>
        </div>

        {/* Environment Pipeline */}
        <div className="mt-4 pt-4 border-t border-neutral-100 dark:border-neutral-800">
          <EnvironmentPipeline
            deployed_dev={isEnvironmentSynced(lifecycle, 'dev') ?? api.deployed_dev}
            deployed_staging={isEnvironmentSynced(lifecycle, 'staging') ?? api.deployed_staging}
          />
        </div>
      </div>

      <ApiLifecyclePanel
        tenantId={tenantId!}
        apiId={apiId!}
        canManage={canManage}
        canDeploy={canDeploy}
      />

      {/* Tabs */}
      <div className="border-b border-neutral-200 dark:border-neutral-700">
        <nav className="-mb-px flex gap-6" aria-label="API detail tabs">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`whitespace-nowrap pb-3 px-1 text-sm font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
                activeTab === tab.id
                  ? 'border-primary-600 text-primary-600 dark:text-primary-400 dark:border-primary-400'
                  : 'border-transparent text-neutral-500 hover:text-neutral-700 hover:border-neutral-300 dark:text-neutral-400 dark:hover:text-neutral-200'
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab Content */}
      <div className="bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg p-6">
        {activeTab === 'overview' && <OverviewTab api={api} />}
        {activeTab === 'spec' && <SpecTab api={api} />}
        {activeTab === 'versions' && <VersionsTab versions={versions} loading={versionsLoading} />}
        {activeTab === 'deployments' && (
          <DeploymentsTab lifecycle={lifecycle} loading={lifecycleLoading} />
        )}
        {activeTab === 'promotions' && (
          <PromotionsTab lifecycle={lifecycle} loading={lifecycleLoading} />
        )}
      </div>
    </div>
  );
}

function isEnvironmentSynced(
  lifecycle: ApiLifecycleState | undefined,
  environment: string
): boolean | null {
  if (!lifecycle) return null;
  const deployments = lifecycle.deployments.filter(
    (deployment) => deployment.environment === environment
  );
  if (deployments.length === 0) return null;
  return deployments.some((deployment) => deployment.sync_status === 'synced');
}

// --- Tab Components ---

function OverviewTab({ api }: { api: API }) {
  const fields = [
    { label: 'Name', value: api.name },
    { label: 'Display Name', value: api.display_name },
    { label: 'Version', value: api.version },
    { label: 'Status', value: api.status },
    { label: 'Backend URL', value: api.backend_url, mono: true },
    { label: 'Audience', value: api.audience || 'public' },
    {
      label: 'Portal',
      value: api.portal_promoted ? 'Published' : 'Private',
    },
    { label: 'Tags', value: api.tags?.join(', ') || 'None' },
    { label: 'Catalog Release', value: api.catalog_release_tag || 'Unversioned', mono: true },
    {
      label: 'Catalog PR',
      value:
        api.catalog_pr_number && api.catalog_pr_url
          ? `#${api.catalog_pr_number} ${api.catalog_pr_url}`
          : 'None',
      mono: Boolean(api.catalog_pr_url),
    },
    { label: 'Merge Commit', value: api.catalog_merge_commit_sha || 'None', mono: true },
  ];

  return (
    <dl className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {fields.map((f) => (
        <div key={f.label}>
          <dt className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
            {f.label}
          </dt>
          <dd
            className={`mt-1 text-sm text-neutral-900 dark:text-white ${f.mono ? 'font-mono' : ''}`}
          >
            {f.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function SpecTab({ api }: { api: API }) {
  const [copied, setCopied] = useState(false);
  const { data, isLoading, error } = useQuery({
    queryKey: ['api-openapi', api.tenant_id, api.name],
    queryFn: () => apiService.getApiOpenApiSpec(api.tenant_id, api.name),
    staleTime: 5 * 60 * 1000,
  });

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="h-16 bg-neutral-100 dark:bg-neutral-800 rounded animate-pulse" />
        <div className="h-80 bg-neutral-100 dark:bg-neutral-800 rounded animate-pulse" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="py-12 text-center text-neutral-500 dark:text-neutral-400">
        <AlertTriangle className="h-12 w-12 mx-auto mb-4 text-red-400" />
        <p className="text-sm">OpenAPI specification is unavailable.</p>
        <p className="text-xs mt-1 font-mono">
          tenants/{api.tenant_id}/apis/{api.name}/openapi.yaml
        </p>
      </div>
    );
  }

  const sourceLabel =
    data.source === 'git' && data.is_authoritative
      ? 'Git authoritative'
      : data.source === 'git'
        ? 'Git source'
        : data.source === 'db_cache'
          ? 'DB cache'
          : 'Generated fallback';
  const sourceClass =
    data.source === 'git' && data.is_authoritative
      ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
      : data.source === 'git'
        ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400'
        : data.source === 'db_cache'
          ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400'
          : 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400';
  const prettySpec = JSON.stringify(data.spec, null, 2);

  const copySpec = async () => {
    await navigator.clipboard.writeText(prettySpec);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="space-y-2 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${sourceClass}`}>
              {sourceLabel}
            </span>
            {data.is_authoritative && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-50 text-green-700 ring-1 ring-green-200 dark:bg-green-900/20 dark:text-green-300 dark:ring-green-800">
                <Check className="h-3 w-3" />
                Authoritative
              </span>
            )}
            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-neutral-100 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300">
              {data.format}
            </span>
          </div>
          <div className="text-xs text-neutral-500 dark:text-neutral-400 space-y-1">
            <p className="font-mono break-all">{data.git_path}</p>
            {data.git_commit_sha && <p className="font-mono break-all">{data.git_commit_sha}</p>}
          </div>
        </div>
        <Button variant="ghost" size="sm" onClick={copySpec}>
          {copied ? <Check className="h-4 w-4 mr-1" /> : <Copy className="h-4 w-4 mr-1" />}
          {copied ? 'Copied' : 'Copy'}
        </Button>
      </div>

      {!data.is_authoritative && (
        <div className="flex items-start gap-2 rounded-lg border border-yellow-200 bg-yellow-50 px-3 py-2 text-sm text-yellow-800 dark:border-yellow-900/60 dark:bg-yellow-900/20 dark:text-yellow-300">
          <AlertTriangle className="h-4 w-4 mt-0.5 flex-shrink-0" />
          <span>
            This view is not backed by the canonical Git OpenAPI file. The Git source must be
            restored for runtime reconciliation.
          </span>
        </div>
      )}

      <pre className="max-h-[560px] overflow-auto rounded-lg border border-neutral-200 bg-neutral-950 p-4 text-xs leading-5 text-neutral-100 dark:border-neutral-700">
        {prettySpec}
      </pre>
    </div>
  );
}

function VersionsTab({
  versions,
  loading,
}: {
  versions: Schemas['APIVersionEntry'][];
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-16 bg-neutral-100 dark:bg-neutral-800 rounded animate-pulse" />
        ))}
      </div>
    );
  }

  if (versions.length === 0) {
    return (
      <div className="text-center py-12 text-neutral-500 dark:text-neutral-400">
        <GitCommit className="h-12 w-12 mx-auto mb-4 text-neutral-300 dark:text-neutral-600" />
        <p className="text-sm">No version history available.</p>
        <p className="text-xs mt-1">Requires Git provider integration to be configured.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {versions.map((v, i) => (
        <div
          key={v.sha}
          className="flex items-start gap-3 p-3 rounded-lg border border-neutral-100 dark:border-neutral-800 hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition-colors"
        >
          {/* Timeline dot */}
          <div className="flex flex-col items-center mt-1">
            <div
              className={`h-3 w-3 rounded-full ${
                i === 0 ? 'bg-green-500 dark:bg-green-400' : 'bg-neutral-300 dark:bg-neutral-600'
              }`}
            />
            {i < versions.length - 1 && (
              <div className="w-px h-full bg-neutral-200 dark:bg-neutral-700 mt-1" />
            )}
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <p className="text-sm text-neutral-900 dark:text-white font-medium truncate">
              {v.message.split('\n')[0]}
            </p>
            <div className="flex items-center gap-3 mt-1 text-xs text-neutral-500 dark:text-neutral-400">
              <span>{v.author}</span>
              <span className="font-mono">{v.sha.slice(0, 8)}</span>
              <span>{new Date(v.date).toLocaleDateString()}</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function DeploymentsTab({
  lifecycle,
  loading,
}: {
  lifecycle: ApiLifecycleState | undefined;
  loading: boolean;
}) {
  if (loading) {
    return <CardSkeleton className="h-32" />;
  }

  const deployments = lifecycle?.deployments || [];

  const syncStatusBadge: Record<string, string> = {
    pending: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
    syncing: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
    synced: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
    drifted: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
    error: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
    deleting: 'bg-neutral-100 text-neutral-800 dark:bg-neutral-700 dark:text-neutral-300',
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          {deployments.length} lifecycle gateway deployment{deployments.length !== 1 ? 's' : ''}
        </p>
      </div>

      {deployments.length === 0 ? (
        <div className="text-center py-12 text-neutral-500 dark:text-neutral-400">
          <Rocket className="h-12 w-12 mx-auto mb-4 text-neutral-300 dark:text-neutral-600" />
          <p className="text-sm">No gateway deployments yet for this API.</p>
          <p className="text-xs mt-1">Use the lifecycle panel to request a deployment.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {deployments.map((d) => (
            <div
              key={d.id}
              className="p-3 rounded-lg border border-neutral-100 dark:border-neutral-800"
            >
              <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-neutral-900 dark:text-white">
                      {d.environment} / {d.gateway_name || d.gateway_instance_id.slice(0, 8)}
                    </span>
                    <span
                      className={`text-xs px-2 py-0.5 rounded ${syncStatusBadge[d.sync_status] || ''}`}
                    >
                      {d.sync_status}
                    </span>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-neutral-500 dark:text-neutral-400">
                    <span>gateway {d.gateway_instance_id}</span>
                    <span>
                      generation {d.synced_generation}/{d.desired_generation}
                    </span>
                    {d.gateway_resource_id && <span>resource {d.gateway_resource_id}</span>}
                  </div>
                </div>
                <span className="text-xs text-neutral-400 dark:text-neutral-500">
                  {d.last_sync_success
                    ? new Date(d.last_sync_success).toLocaleString()
                    : d.last_sync_attempt
                      ? new Date(d.last_sync_attempt).toLocaleString()
                      : '—'}
                </span>
              </div>
              {(d.sync_error || d.policy_sync_error) && (
                <div className="mt-3 space-y-2">
                  {d.sync_error && (
                    <p className="rounded border border-red-200 bg-red-50 p-2 text-xs text-red-800 dark:border-red-900/60 dark:bg-red-900/20 dark:text-red-200">
                      {d.sync_error}
                    </p>
                  )}
                  {d.policy_sync_error && (
                    <p className="rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800 dark:border-amber-900/60 dark:bg-amber-900/20 dark:text-amber-200">
                      {d.policy_sync_error}
                    </p>
                  )}
                </div>
              )}
              {d.sync_steps?.some((step) => step.status.toLowerCase() === 'failed') && (
                <div className="mt-3 space-y-1 text-xs">
                  <p className="font-medium text-neutral-700 dark:text-neutral-300">
                    Failed sync steps
                  </p>
                  {d.sync_steps
                    .filter((step) => step.status.toLowerCase() === 'failed')
                    .map((step) => (
                      <p
                        key={`${d.id}:${step.name}`}
                        className="rounded bg-neutral-50 p-2 font-mono text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300"
                      >
                        {step.name}: {step.detail || step.status}
                      </p>
                    ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <p className="text-xs text-neutral-500 dark:text-neutral-400">
        Runtime writes for lifecycle APIs are controlled by the lifecycle panel.
      </p>
    </div>
  );
}

function PromotionsTab({
  lifecycle,
  loading,
}: {
  lifecycle: ApiLifecycleState | undefined;
  loading: boolean;
}) {
  if (loading) {
    return <CardSkeleton className="h-32" />;
  }

  const promotions = lifecycle?.promotions || [];

  if (promotions.length === 0) {
    return (
      <div className="text-center py-12 text-neutral-500 dark:text-neutral-400">
        <ArrowUpRight className="h-12 w-12 mx-auto mb-4 text-neutral-300 dark:text-neutral-600" />
        <p className="text-sm">No promotions yet for this API.</p>
        <p className="text-xs mt-1">
          Use the lifecycle panel to promote this API between environments.
        </p>
      </div>
    );
  }

  const statusBadge: Record<string, string> = {
    pending: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
    promoting: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
    promoted: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
    failed: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
    rolled_back: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  };

  return (
    <div className="space-y-2">
      {promotions.map((p) => (
        <div
          key={p.id}
          className="p-3 rounded-lg border border-neutral-100 dark:border-neutral-800"
        >
          <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
            <div className="min-w-0">
              <div className="flex items-center gap-3">
                <span className="text-xs font-mono text-neutral-600 dark:text-neutral-400">
                  {p.source_environment} → {p.target_environment}
                </span>
                <span className={`text-xs px-2 py-0.5 rounded ${statusBadge[p.status] || ''}`}>
                  {p.status}
                </span>
              </div>
              <p className="mt-1 text-sm text-neutral-700 dark:text-neutral-300">{p.message}</p>
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-neutral-500 dark:text-neutral-400">
                {p.source_deployment_id && <span>source {p.source_deployment_id}</span>}
                {p.target_deployment_id && <span>target {p.target_deployment_id}</span>}
                {p.target_gateway_ids && p.target_gateway_ids.length > 0 && (
                  <span>target gateways {p.target_gateway_ids.join(', ')}</span>
                )}
              </div>
            </div>
            <div className="text-xs text-neutral-400 dark:text-neutral-500">
              {p.requested_by && <span>{p.requested_by}</span>}
              {p.completed_at && (
                <span> · completed {new Date(p.completed_at).toLocaleString()}</span>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
