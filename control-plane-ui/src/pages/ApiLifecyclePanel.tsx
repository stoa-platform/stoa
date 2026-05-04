import type { ReactNode } from 'react';
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, ArrowUpRight, CheckCircle2, RefreshCw, Rocket, Send } from 'lucide-react';
import {
  apiService,
  type ApiLifecycleGatewayDeployment,
  type ApiLifecycleState,
} from '../services/api';

interface ApiLifecyclePanelProps {
  tenantId: string;
  apiId: string;
  canManage: boolean;
  canDeploy: boolean;
}

interface BackendErrorShape {
  response?: {
    data?: {
      detail?: unknown;
    };
  };
  message?: string;
}

function backendErrorMessage(error: unknown): string {
  const candidate = error as BackendErrorShape;
  const detail = candidate.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object') {
    const message = (detail as { message?: unknown }).message;
    const code = (detail as { code?: unknown }).code;
    if (typeof message === 'string' && typeof code === 'string') return `${code}: ${message}`;
    if (typeof message === 'string') return message;
    try {
      return JSON.stringify(detail);
    } catch {
      return 'Backend returned a lifecycle error';
    }
  }
  return candidate.message || 'Lifecycle action failed';
}

function statusBadgeClass(status: string): string {
  const normalized = status.toLowerCase();
  if (['ready', 'synced', 'published', 'promoted'].includes(normalized)) {
    return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300';
  }
  if (['draft', 'pending', 'promoting', 'syncing'].includes(normalized)) {
    return 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300';
  }
  if (['failed', 'error', 'drifted'].includes(normalized)) {
    return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300';
  }
  return 'bg-neutral-100 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300';
}

function formatTimestamp(value?: string | null): string | null {
  if (!value) return null;
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) return value;
  return timestamp.toLocaleString();
}

function CompactStatus({ label, value }: { label: string; value: string | boolean | null }) {
  const rendered = value == null ? 'none' : String(value);
  return (
    <div data-testid={`api-lifecycle-${label.toLowerCase().replace(/\s+/g, '-')}`}>
      <dt className="text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
        {label}
      </dt>
      <dd className="mt-1">
        <span className={`inline-flex rounded px-2 py-1 text-xs ${statusBadgeClass(rendered)}`}>
          {rendered}
        </span>
      </dd>
    </div>
  );
}

function ActionInput({
  label,
  value,
  onChange,
  placeholder,
  testId,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  testId: string;
}) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium text-neutral-700 dark:text-neutral-300">{label}</span>
      <input
        data-testid={testId}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-blue-500 focus:ring-2 focus:ring-blue-500 dark:border-neutral-700 dark:bg-neutral-900 dark:text-white"
      />
    </label>
  );
}

function ForceToggle({
  checked,
  onChange,
  testId,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  testId: string;
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-neutral-700 dark:text-neutral-300">
      <input
        data-testid={testId}
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="h-4 w-4 rounded border-neutral-300 text-blue-600 focus:ring-blue-500"
      />
      Force
    </label>
  );
}

function ActionButton({
  children,
  disabled,
  onClick,
  testId,
}: {
  children: ReactNode;
  disabled?: boolean;
  onClick: () => void;
  testId: string;
}) {
  return (
    <button
      data-testid={testId}
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="inline-flex items-center justify-center gap-2 rounded bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-neutral-300 disabled:text-neutral-600 dark:disabled:bg-neutral-700 dark:disabled:text-neutral-400"
    >
      {children}
    </button>
  );
}

export function ApiLifecyclePanel({
  tenantId,
  apiId,
  canManage,
  canDeploy,
}: ApiLifecyclePanelProps) {
  const queryClient = useQueryClient();
  const [deployEnvironment, setDeployEnvironment] = useState('dev');
  const [deployGatewayId, setDeployGatewayId] = useState('');
  const [deployForce, setDeployForce] = useState(false);
  const [publishEnvironment, setPublishEnvironment] = useState('dev');
  const [publishGatewayId, setPublishGatewayId] = useState('');
  const [publishForce, setPublishForce] = useState(false);
  const [sourceEnvironment, setSourceEnvironment] = useState('dev');
  const [targetEnvironment, setTargetEnvironment] = useState('staging');
  const [sourceGatewayId, setSourceGatewayId] = useState('');
  const [targetGatewayId, setTargetGatewayId] = useState('');
  const [promotionForce, setPromotionForce] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const lifecycleQuery = useQuery({
    queryKey: ['api-lifecycle', tenantId, apiId],
    queryFn: () => apiService.getApiLifecycleState(tenantId, apiId),
    enabled: Boolean(tenantId && apiId),
    retry: false,
  });

  const refreshLifecycle = async () => {
    await lifecycleQuery.refetch();
    await queryClient.invalidateQueries({ queryKey: ['api', tenantId, apiId] });
  };

  const handleMutationError = (error: unknown) => {
    setActionMessage(null);
    setActionError(backendErrorMessage(error));
  };

  const validateMutation = useMutation({
    mutationFn: () => apiService.validateLifecycleDraft(tenantId, apiId),
    onSuccess: async (response) => {
      setActionError(null);
      setActionMessage(`Validation ${response.validation.code}: ${response.validation.message}`);
      await refreshLifecycle();
    },
    onError: handleMutationError,
  });

  const deployMutation = useMutation({
    mutationFn: () =>
      apiService.deployLifecycleApi(tenantId, apiId, {
        environment: deployEnvironment,
        gateway_instance_id: deployGatewayId.trim() || null,
        force: deployForce,
      }),
    onSuccess: async (response) => {
      setActionError(null);
      setActionMessage(`Deployment ${response.action}: ${response.deployment_status}`);
      await refreshLifecycle();
    },
    onError: handleMutationError,
  });

  const publishMutation = useMutation({
    mutationFn: () =>
      apiService.publishLifecycleApi(tenantId, apiId, {
        environment: publishEnvironment,
        gateway_instance_id: publishGatewayId.trim() || null,
        force: publishForce,
      }),
    onSuccess: async (response) => {
      setActionError(null);
      setActionMessage(`Portal publication ${response.result}: ${response.publication_status}`);
      await refreshLifecycle();
    },
    onError: handleMutationError,
  });

  const promoteMutation = useMutation({
    mutationFn: () =>
      apiService.promoteLifecycleApi(tenantId, apiId, {
        source_environment: sourceEnvironment,
        target_environment: targetEnvironment,
        source_gateway_instance_id: sourceGatewayId.trim() || null,
        target_gateway_instance_id: targetGatewayId.trim() || null,
        force: promotionForce,
      }),
    onSuccess: async (response) => {
      setActionError(null);
      setActionMessage(`Promotion ${response.result}: ${response.promotion_status}`);
      await refreshLifecycle();
    },
    onError: handleMutationError,
  });

  const lifecycle = lifecycleQuery.data;
  const isReady = lifecycle?.catalog_status === 'ready';
  const canValidateCatalog =
    canManage && (lifecycle?.catalog_status === 'draft' || lifecycle?.catalog_status === 'ready');
  const actionsDisabled = !lifecycle || lifecycleQuery.isLoading;

  return (
    <section
      data-testid="api-lifecycle-panel"
      className="space-y-5 rounded-lg border border-neutral-200 bg-white p-5 dark:border-neutral-700 dark:bg-neutral-900"
    >
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">API lifecycle</h2>
          <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
            Canonical draft, validation, runtime deployment, portal publication, and promotion.
          </p>
        </div>
        <button
          data-testid="api-lifecycle-refresh"
          type="button"
          onClick={() => void refreshLifecycle()}
          disabled={lifecycleQuery.isFetching}
          className="inline-flex items-center gap-2 rounded border border-neutral-300 px-3 py-2 text-sm text-neutral-700 hover:bg-neutral-50 disabled:opacity-60 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
        >
          <RefreshCw className={`h-4 w-4 ${lifecycleQuery.isFetching ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {lifecycleQuery.isError && (
        <div
          data-testid="api-lifecycle-unavailable"
          className="flex items-start gap-2 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-900/20 dark:text-amber-200"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
          <span>{backendErrorMessage(lifecycleQuery.error)}</span>
        </div>
      )}

      {lifecycle && <LifecycleSummary lifecycle={lifecycle} />}

      {actionError && (
        <div
          data-testid="api-lifecycle-action-error"
          className="flex items-start gap-2 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-900/20 dark:text-red-200"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
          <span>{actionError}</span>
        </div>
      )}

      {actionMessage && (
        <div
          data-testid="api-lifecycle-action-message"
          className="flex items-start gap-2 rounded border border-green-200 bg-green-50 p-3 text-sm text-green-700 dark:border-green-900/60 dark:bg-green-900/20 dark:text-green-200"
        >
          <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0" />
          <span>{actionMessage}</span>
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-4">
        <div className="space-y-3 rounded border border-neutral-200 p-4 dark:border-neutral-700">
          <h3 className="text-sm font-semibold text-neutral-900 dark:text-white">Validate</h3>
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            Validates the stored OpenAPI/Swagger contract and sets catalog readiness.
          </p>
          <ActionButton
            testId="api-lifecycle-validate"
            disabled={actionsDisabled || !canValidateCatalog || validateMutation.isPending}
            onClick={() => validateMutation.mutate()}
          >
            <CheckCircle2 className="h-4 w-4" />
            {lifecycle?.catalog_status === 'ready' ? 'Revalidate' : 'Validate draft'}
          </ActionButton>
        </div>

        <div className="space-y-3 rounded border border-neutral-200 p-4 dark:border-neutral-700">
          <h3 className="text-sm font-semibold text-neutral-900 dark:text-white">Deploy</h3>
          <ActionInput
            testId="api-lifecycle-deploy-environment"
            label="Environment"
            value={deployEnvironment}
            onChange={setDeployEnvironment}
          />
          <ActionInput
            testId="api-lifecycle-deploy-gateway"
            label="Gateway instance ID"
            value={deployGatewayId}
            onChange={setDeployGatewayId}
            placeholder="optional"
          />
          <ForceToggle
            testId="api-lifecycle-deploy-force"
            checked={deployForce}
            onChange={setDeployForce}
          />
          <ActionButton
            testId="api-lifecycle-deploy"
            disabled={actionsDisabled || !canDeploy || !isReady || deployMutation.isPending}
            onClick={() => deployMutation.mutate()}
          >
            <Rocket className="h-4 w-4" />
            Deploy
          </ActionButton>
        </div>

        <div className="space-y-3 rounded border border-neutral-200 p-4 dark:border-neutral-700">
          <h3 className="text-sm font-semibold text-neutral-900 dark:text-white">Publish</h3>
          <ActionInput
            testId="api-lifecycle-publish-environment"
            label="Environment"
            value={publishEnvironment}
            onChange={setPublishEnvironment}
          />
          <ActionInput
            testId="api-lifecycle-publish-gateway"
            label="Gateway instance ID"
            value={publishGatewayId}
            onChange={setPublishGatewayId}
            placeholder="optional"
          />
          <ForceToggle
            testId="api-lifecycle-publish-force"
            checked={publishForce}
            onChange={setPublishForce}
          />
          <ActionButton
            testId="api-lifecycle-publish"
            disabled={actionsDisabled || !canManage || !isReady || publishMutation.isPending}
            onClick={() => publishMutation.mutate()}
          >
            <Send className="h-4 w-4" />
            Publish
          </ActionButton>
        </div>

        <div className="space-y-3 rounded border border-neutral-200 p-4 dark:border-neutral-700">
          <h3 className="text-sm font-semibold text-neutral-900 dark:text-white">Promote</h3>
          <div className="grid grid-cols-2 gap-2">
            <ActionInput
              testId="api-lifecycle-promote-source-env"
              label="Source"
              value={sourceEnvironment}
              onChange={setSourceEnvironment}
            />
            <ActionInput
              testId="api-lifecycle-promote-target-env"
              label="Target"
              value={targetEnvironment}
              onChange={setTargetEnvironment}
            />
          </div>
          <ActionInput
            testId="api-lifecycle-promote-source-gateway"
            label="Source gateway ID"
            value={sourceGatewayId}
            onChange={setSourceGatewayId}
            placeholder="optional"
          />
          <ActionInput
            testId="api-lifecycle-promote-target-gateway"
            label="Target gateway ID"
            value={targetGatewayId}
            onChange={setTargetGatewayId}
            placeholder="optional"
          />
          <ForceToggle
            testId="api-lifecycle-promote-force"
            checked={promotionForce}
            onChange={setPromotionForce}
          />
          <ActionButton
            testId="api-lifecycle-promote"
            disabled={actionsDisabled || !canDeploy || !isReady || promoteMutation.isPending}
            onClick={() => promoteMutation.mutate()}
          >
            <ArrowUpRight className="h-4 w-4" />
            Promote
          </ActionButton>
        </div>
      </div>
    </section>
  );
}

function LifecycleSummary({ lifecycle }: { lifecycle: ApiLifecycleState }) {
  return (
    <div className="space-y-4">
      <dl className="grid grid-cols-2 gap-4 md:grid-cols-5">
        <CompactStatus label="Catalog status" value={lifecycle.catalog_status} />
        <CompactStatus label="Lifecycle phase" value={lifecycle.lifecycle_phase} />
        <CompactStatus label="Portal" value={lifecycle.portal.status} />
        <CompactStatus label="Spec source" value={lifecycle.spec.source} />
        <CompactStatus label="Spec present" value={lifecycle.spec.has_openapi_spec} />
      </dl>

      {lifecycle.last_error && (
        <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-900/20 dark:text-red-200">
          {lifecycle.last_error}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <DeploymentSummary deployments={lifecycle.deployments} />
        <SummaryList
          title="Portal publications"
          empty="Not published"
          items={lifecycle.portal.publications.map((publication) => ({
            id: `${publication.environment}:${publication.gateway_instance_id}`,
            title: `${publication.environment} / ${publication.publication_status}`,
            status: publication.result,
            detail: publication.deployment_id,
          }))}
        />
        <SummaryList
          title="Promotions"
          empty="No promotion"
          items={lifecycle.promotions.map((promotion) => ({
            id: promotion.id,
            title: `${promotion.source_environment} to ${promotion.target_environment}`,
            status: promotion.status,
            detail: promotion.message,
          }))}
        />
      </div>
    </div>
  );
}

function DeploymentSummary({ deployments }: { deployments: ApiLifecycleGatewayDeployment[] }) {
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-neutral-900 dark:text-white">Deployments</h3>
      {deployments.length === 0 ? (
        <p className="rounded border border-dashed border-neutral-300 p-3 text-sm text-neutral-500 dark:border-neutral-700 dark:text-neutral-400">
          No gateway deployment
        </p>
      ) : (
        <div className="space-y-2">
          {deployments.map((deployment) => {
            const failedSteps = (deployment.sync_steps || []).filter(
              (step) => step.status.toLowerCase() === 'failed'
            );
            const lastAttempt = formatTimestamp(deployment.last_sync_attempt);
            const lastSuccess = formatTimestamp(deployment.last_sync_success);

            return (
              <div
                data-testid="api-lifecycle-deployments-item"
                key={deployment.id}
                className="rounded border border-neutral-200 p-3 dark:border-neutral-700"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="min-w-0 text-sm font-medium text-neutral-900 dark:text-white">
                    {deployment.environment} / {deployment.gateway_name}
                  </span>
                  <span
                    className={`shrink-0 rounded px-2 py-1 text-xs ${statusBadgeClass(
                      deployment.sync_status
                    )}`}
                  >
                    {deployment.sync_status}
                  </span>
                </div>

                <dl className="mt-2 grid gap-2 text-xs text-neutral-500 dark:text-neutral-400">
                  <div>
                    <dt className="font-medium text-neutral-700 dark:text-neutral-300">
                      Gateway instance
                    </dt>
                    <dd className="break-all font-mono">{deployment.gateway_instance_id}</dd>
                  </div>
                  <div>
                    <dt className="font-medium text-neutral-700 dark:text-neutral-300">
                      Generation
                    </dt>
                    <dd>
                      synced {deployment.synced_generation} / desired{' '}
                      {deployment.desired_generation}
                    </dd>
                  </div>
                  {(lastAttempt || lastSuccess) && (
                    <div>
                      <dt className="font-medium text-neutral-700 dark:text-neutral-300">
                        Sync timestamps
                      </dt>
                      <dd>
                        {lastAttempt ? `last attempt: ${lastAttempt}` : null}
                        {lastAttempt && lastSuccess ? ' · ' : null}
                        {lastSuccess ? `last success: ${lastSuccess}` : null}
                      </dd>
                    </div>
                  )}
                  {deployment.public_url && (
                    <div>
                      <dt className="font-medium text-neutral-700 dark:text-neutral-300">
                        Public URL
                      </dt>
                      <dd className="break-all font-mono">{deployment.public_url}</dd>
                    </div>
                  )}
                </dl>

                {deployment.sync_error && (
                  <div
                    data-testid="api-lifecycle-deployment-error"
                    className="mt-3 rounded border border-red-200 bg-red-50 p-3 text-xs text-red-800 dark:border-red-900/60 dark:bg-red-900/20 dark:text-red-200"
                  >
                    <div className="mb-1 font-semibold">Gateway deployment error</div>
                    <p className="whitespace-pre-wrap break-words font-mono">
                      {deployment.sync_error}
                    </p>
                  </div>
                )}

                {deployment.policy_sync_error && (
                  <div
                    data-testid="api-lifecycle-deployment-policy-error"
                    className="mt-3 rounded border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800 dark:border-amber-900/60 dark:bg-amber-900/20 dark:text-amber-200"
                  >
                    <div className="mb-1 font-semibold">
                      Policy sync {deployment.policy_sync_status || 'error'}
                    </div>
                    <p className="whitespace-pre-wrap break-words font-mono">
                      {deployment.policy_sync_error}
                    </p>
                  </div>
                )}

                {failedSteps.length > 0 && (
                  <div className="mt-3 space-y-2" data-testid="api-lifecycle-deployment-steps">
                    <div className="text-xs font-semibold text-neutral-700 dark:text-neutral-300">
                      Failed sync steps
                    </div>
                    {failedSteps.map((step) => (
                      <div
                        data-testid="api-lifecycle-deployment-step"
                        key={`${deployment.id}:${step.name}`}
                        className="rounded bg-neutral-50 p-2 text-xs dark:bg-neutral-800"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-medium text-neutral-900 dark:text-white">
                            {step.name}
                          </span>
                          <span className={`rounded px-2 py-0.5 ${statusBadgeClass(step.status)}`}>
                            {step.status}
                          </span>
                        </div>
                        {step.detail && (
                          <p className="mt-1 whitespace-pre-wrap break-words font-mono text-neutral-600 dark:text-neutral-300">
                            {step.detail}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function SummaryList({
  title,
  empty,
  items,
}: {
  title: string;
  empty: string;
  items: { id: string; title: string; status: string; detail?: string | null }[];
}) {
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-neutral-900 dark:text-white">{title}</h3>
      {items.length === 0 ? (
        <p className="rounded border border-dashed border-neutral-300 p-3 text-sm text-neutral-500 dark:border-neutral-700 dark:text-neutral-400">
          {empty}
        </p>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <div
              data-testid={`api-lifecycle-${title.toLowerCase().replace(/\s+/g, '-')}-item`}
              key={item.id}
              className="rounded border border-neutral-200 p-3 dark:border-neutral-700"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium text-neutral-900 dark:text-white">
                  {item.title}
                </span>
                <span className={`rounded px-2 py-1 text-xs ${statusBadgeClass(item.status)}`}>
                  {item.status}
                </span>
              </div>
              {item.detail && (
                <p className="mt-1 truncate font-mono text-xs text-neutral-500 dark:text-neutral-400">
                  {item.detail}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
