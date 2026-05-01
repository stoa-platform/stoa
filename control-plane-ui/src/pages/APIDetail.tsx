/**
 * API Detail Page — Command center for managing a single API (CAB-1813)
 *
 * Tabs: Overview | Spec | Versions | Deployments | Promotions
 * Features: Environment pipeline, portal toggle, deploy action, RBAC
 */

import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  Info,
  FileJson,
  GitCommit,
  Rocket,
  ArrowUpRight,
  Globe,
  GlobeLock,
  Pencil,
  Trash2,
  ExternalLink,
} from 'lucide-react';
import { apiService } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { useEnvironmentMode } from '../hooks/useEnvironmentMode';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import { Button } from '@stoa/shared/components/Button';
import { EnvironmentPipeline } from '../components/EnvironmentPipeline';
import type { API, GatewayDeployment } from '../types';
import type { Schemas } from '@stoa/shared/api-types';
import { DeployAPIDialog } from './GatewayDeployments/DeployAPIDialog';

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
  const queryClient = useQueryClient();
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

  // Fetch version history (lazy — only when tab is active)
  const { data: versions = [], isLoading: versionsLoading } = useQuery({
    queryKey: ['api-versions', tenantId, apiId],
    queryFn: () => apiService.getApiVersions(tenantId!, apiId!),
    enabled: !!tenantId && !!apiId && activeTab === 'versions',
  });

  // Portal toggle mutation
  const portalToggle = useMutation({
    mutationFn: async (promoted: boolean) => {
      if (!api) return;
      const currentTags = api.tags || [];
      const newTags = promoted
        ? [...currentTags.filter((t) => t !== 'portal:published'), 'portal:published']
        : currentTags.filter((t) => t !== 'portal:published');
      await apiService.updateApi(tenantId!, apiId!, { tags: newTags });
      // Trigger catalog sync so the Portal DB picks up the change
      await apiService.triggerCatalogSync(tenantId!).catch(() => {
        /* sync is best-effort — tag update already succeeded */
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api', tenantId, apiId] });
      toast.success(api?.portal_promoted ? 'Removed from portal' : 'Published to portal');
    },
    onError: () => toast.error('Failed to update portal status'),
  });

  // Deploy mutation
  const deployMutation = useMutation({
    mutationFn: async (environment: 'dev' | 'staging') => {
      await apiService.createDeployment(tenantId!, {
        api_id: apiId!,
        api_name: api?.name || apiId!,
        environment,
        version: api?.version || '1.0.0',
      });
      // Sync catalog so deployment flags are reflected in Portal
      await apiService.triggerCatalogSync(tenantId!).catch(() => {});
    },
    onSuccess: (_data, environment) => {
      queryClient.invalidateQueries({ queryKey: ['api', tenantId, apiId] });
      toast.success(`Deployment to ${environment} initiated`);
    },
    onError: () => toast.error('Deployment failed'),
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

  const handleDeploy = async (env: 'dev' | 'staging') => {
    const confirmed = await confirm({
      title: `Deploy to ${env.toUpperCase()}`,
      message: `Deploy "${api?.display_name}" v${api?.version} to ${env}?`,
      confirmLabel: 'Deploy',
    });
    if (confirmed) deployMutation.mutate(env);
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
            {/* Portal toggle */}
            {canManage && (
              <Button
                variant={api.portal_promoted ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => portalToggle.mutate(!api.portal_promoted)}
                disabled={portalToggle.isPending}
              >
                {api.portal_promoted ? (
                  <>
                    <Globe className="h-4 w-4 mr-1" />
                    Portal: Published
                  </>
                ) : (
                  <>
                    <GlobeLock className="h-4 w-4 mr-1" />
                    Portal: Private
                  </>
                )}
              </Button>
            )}

            {/* Deploy buttons */}
            {canDeploy && (
              <>
                {!api.deployed_dev && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDeploy('dev')}
                    disabled={deployMutation.isPending}
                  >
                    Deploy DEV
                  </Button>
                )}
                {api.deployed_dev && !api.deployed_staging && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDeploy('staging')}
                    disabled={deployMutation.isPending}
                  >
                    Deploy STG
                  </Button>
                )}
              </>
            )}

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
            deployed_dev={api.deployed_dev}
            deployed_staging={api.deployed_staging}
          />
        </div>
      </div>

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
        {activeTab === 'deployments' && <DeploymentsTab api={api} tenantId={tenantId!} />}
        {activeTab === 'promotions' && <PromotionsTab api={api} tenantId={tenantId!} />}
      </div>
    </div>
  );
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
  // The OpenAPI spec is not directly in the API response — it's stored in the Git repository.
  // For now show a placeholder directing users to the spec file.
  return (
    <div className="text-center py-12 text-neutral-500 dark:text-neutral-400">
      <FileJson className="h-12 w-12 mx-auto mb-4 text-neutral-300 dark:text-neutral-600" />
      <p className="text-sm">OpenAPI specification is stored in the GitOps repository.</p>
      <p className="text-xs mt-1 font-mono">
        tenants/{api.tenant_id}/apis/{api.name}/openapi.yaml
      </p>
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

function DeploymentsTab({ api, tenantId }: { api: API; tenantId: string }) {
  const toast = useToastActions();
  const queryClient = useQueryClient();
  const [showDeployDialog, setShowDeployDialog] = useState(false);

  // Query gateway deployments for this specific API
  const { data, isLoading } = useQuery({
    queryKey: ['gateway-deployments', api.id],
    queryFn: () => apiService.getGatewayDeployments({ page_size: 100 }),
    enabled: !!api.id,
  });

  const forceSyncMutation = useMutation({
    mutationFn: (deploymentId: string) => apiService.forceSyncDeployment(deploymentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['gateway-deployments', api.id] });
      toast.success('Re-sync triggered');
    },
    onError: () => toast.error('Failed to trigger re-sync'),
  });

  if (isLoading) {
    return <CardSkeleton className="h-32" />;
  }

  // Filter deployments to this API by matching api_catalog_id
  const deployments = (data?.items || []).filter(
    (d: GatewayDeployment) => d.api_catalog_id === api.id
  );

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
      {/* Header with deploy button */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          {deployments.length} gateway deployment{deployments.length !== 1 ? 's' : ''}
        </p>
        <button
          onClick={() => setShowDeployDialog(true)}
          className="bg-blue-600 text-white px-3 py-1.5 rounded-lg text-sm hover:bg-blue-700"
        >
          + Deploy
        </button>
      </div>

      {deployments.length === 0 ? (
        <div className="text-center py-12 text-neutral-500 dark:text-neutral-400">
          <Rocket className="h-12 w-12 mx-auto mb-4 text-neutral-300 dark:text-neutral-600" />
          <p className="text-sm">No gateway deployments yet for this API.</p>
          <p className="text-xs mt-1">Click + Deploy to deploy to gateways.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {deployments.map((d) => (
            <div
              key={d.id}
              className="flex items-center justify-between p-3 rounded-lg border border-neutral-100 dark:border-neutral-800"
            >
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium text-neutral-900 dark:text-white">
                  {d.gateway_name || d.gateway_instance_id?.slice(0, 8)}
                </span>
                <span className="text-xs font-semibold uppercase px-2 py-0.5 rounded bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400">
                  {d.gateway_environment || '—'}
                </span>
                <span
                  className={`text-xs px-2 py-0.5 rounded ${syncStatusBadge[d.sync_status] || ''}`}
                >
                  {d.sync_status}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {d.sync_status === 'drifted' && (
                  <button
                    onClick={() => forceSyncMutation.mutate(d.id)}
                    disabled={forceSyncMutation.isPending}
                    className="text-xs text-orange-600 dark:text-orange-400 hover:underline"
                  >
                    Re-deploy
                  </button>
                )}
                {d.sync_status === 'error' && (
                  <button
                    onClick={() => forceSyncMutation.mutate(d.id)}
                    disabled={forceSyncMutation.isPending}
                    className="text-xs text-red-600 dark:text-red-400 hover:underline"
                  >
                    Retry
                  </button>
                )}
                <span className="text-xs text-neutral-400 dark:text-neutral-500">
                  {d.last_sync_success
                    ? new Date(d.last_sync_success).toLocaleString()
                    : d.created_at
                      ? new Date(d.created_at).toLocaleString()
                      : '—'}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {showDeployDialog && (
        <DeployAPIDialog
          onClose={() => setShowDeployDialog(false)}
          onDeployed={() => {
            setShowDeployDialog(false);
            queryClient.invalidateQueries({ queryKey: ['gateway-deployments', api.id] });
            toast.success('Deployment initiated');
          }}
          preselectedApiKey={`${tenantId}:${api.name || api.id}`}
        />
      )}
    </div>
  );
}

function PromotionsTab({ api, tenantId }: { api: API; tenantId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['promotions', tenantId],
    queryFn: () => apiService.listPromotions(tenantId, { page: 1, page_size: 20 }),
    enabled: !!tenantId,
  });

  if (isLoading) {
    return <CardSkeleton className="h-32" />;
  }

  const promotions = (data?.items || []).filter(
    (p: { api_id?: string }) => p.api_id === api.id || p.api_id === api.name
  );

  if (promotions.length === 0) {
    return (
      <div className="text-center py-12 text-neutral-500 dark:text-neutral-400">
        <ArrowUpRight className="h-12 w-12 mx-auto mb-4 text-neutral-300 dark:text-neutral-600" />
        <p className="text-sm">No promotions yet for this API.</p>
        <p className="text-xs mt-1">
          Use the Promotions page to promote this API between environments.
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
      {promotions.map(
        (p: {
          id: string;
          source_environment: string;
          target_environment: string;
          status: string;
          created_at: string;
          requested_by?: string;
        }) => (
          <div
            key={p.id}
            className="flex items-center justify-between p-3 rounded-lg border border-neutral-100 dark:border-neutral-800"
          >
            <div className="flex items-center gap-3">
              <span className="text-xs font-mono text-neutral-600 dark:text-neutral-400">
                {p.source_environment} → {p.target_environment}
              </span>
              <span className={`text-xs px-2 py-0.5 rounded ${statusBadge[p.status] || ''}`}>
                {p.status}
              </span>
            </div>
            <div className="flex items-center gap-3 text-xs text-neutral-400 dark:text-neutral-500">
              {p.requested_by && <span>{p.requested_by}</span>}
              <span>{new Date(p.created_at).toLocaleString()}</span>
            </div>
          </div>
        )
      )}
    </div>
  );
}
