import { useState, useEffect, useCallback, useMemo } from 'react';
import { apiService } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import { EmptyState } from '@stoa/shared/components/EmptyState';
import { TableSkeleton } from '@stoa/shared/components/Skeleton';
import { Button } from '@stoa/shared/components/Button';
import type {
  Promotion,
  PromotionStatus,
  Tenant,
  API,
  GatewayDeployment,
  GatewayInstance,
} from '../types';
import type { Schemas } from '@stoa/shared/api-types';
import { normalizeEnvironment } from '@stoa/shared/constants/environments';
import {
  ArrowRight,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  RefreshCw,
  Undo2,
  ChevronDown,
  ChevronRight,
  Plus,
  X,
  ArrowUpRight,
  AlertCircle,
} from 'lucide-react';
import { clsx } from 'clsx';

// =============================================================================
// HELPERS
// =============================================================================

function extractErrorMessage(err: unknown): string {
  if (typeof err === 'object' && err !== null && 'response' in err) {
    const resp = err as { response?: { data?: { detail?: string } } };
    if (resp.response?.data?.detail) return resp.response.data.detail;
  }
  if (err instanceof Error) return err.message;
  return 'Unknown error';
}

// =============================================================================
// STATUS CONFIG
// =============================================================================

const promotionStatusConfig: Record<
  PromotionStatus,
  { icon: typeof CheckCircle2; color: string; bg: string; label: string }
> = {
  pending: {
    icon: Clock,
    color: 'text-amber-600 dark:text-amber-400',
    bg: 'bg-amber-100 dark:bg-amber-900/30',
    label: 'Pending Approval',
  },
  promoting: {
    icon: Loader2,
    color: 'text-blue-600 dark:text-blue-400',
    bg: 'bg-blue-100 dark:bg-blue-900/30',
    label: 'Promoting',
  },
  promoted: {
    icon: CheckCircle2,
    color: 'text-green-600 dark:text-green-400',
    bg: 'bg-green-100 dark:bg-green-900/30',
    label: 'Promoted',
  },
  failed: {
    icon: XCircle,
    color: 'text-red-600 dark:text-red-400',
    bg: 'bg-red-100 dark:bg-red-900/30',
    label: 'Failed',
  },
  rolled_back: {
    icon: Undo2,
    color: 'text-orange-600 dark:text-orange-400',
    bg: 'bg-orange-100 dark:bg-orange-900/30',
    label: 'Rolled Back',
  },
};

const envColors: Record<string, string> = {
  dev: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400',
  staging: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
  production: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
};

const VALID_CHAINS: [string, string][] = [
  ['dev', 'staging'],
  ['staging', 'production'],
];

const PAGE_SIZE_MAX = 100;

function pathKey(source: string, target: string): string {
  return `${source}->${target}`;
}

function sameEnvironment(left?: string, right?: string): boolean {
  if (!left || !right) return false;
  return normalizeEnvironment(left) === normalizeEnvironment(right);
}

function gatewayFamily(gateway?: GatewayInstance | null): string {
  return String(gateway?.target_gateway_type || gateway?.gateway_type || '').toLowerCase();
}

function gatewayTopology(gateway?: GatewayInstance | null): string {
  return String(gateway?.topology || '').toLowerCase();
}

function deploymentMatchesApi(deployment: GatewayDeployment, apiId: string): boolean {
  const desired = deployment.desired_state || {};
  return [deployment.api_catalog_id, desired.api_catalog_id, desired.api_id, desired.api_name].some(
    (value) => String(value || '') === apiId
  );
}

function deploymentTenantId(deployment: GatewayDeployment): string {
  return String(deployment.desired_state?.tenant_id || '');
}

function compatibleTargetGateways(
  sourceGateway: GatewayInstance,
  gateways: GatewayInstance[],
  target: string
): GatewayInstance[] {
  const sourceFamily = gatewayFamily(sourceGateway);
  const sourceTopology = gatewayTopology(sourceGateway);
  return gateways.filter((gateway) => {
    if (gateway.id === sourceGateway.id) return false;
    if (gateway.enabled === false) return false;
    if (!sameEnvironment(gateway.environment, target)) return false;
    if (gatewayFamily(gateway) !== sourceFamily) return false;
    const targetTopology = gatewayTopology(gateway);
    return !sourceTopology || !targetTopology || targetTopology === sourceTopology;
  });
}

function deploymentIsEligibleForPath(
  deployment: GatewayDeployment,
  gateways: GatewayInstance[],
  source: string,
  target: string
): boolean {
  if (deployment.sync_status !== 'synced') return false;
  if (!sameEnvironment(deployment.gateway_environment, source)) return false;
  const sourceGateway = gateways.find((gateway) => gateway.id === deployment.gateway_instance_id);
  if (!sourceGateway) return false;
  return compatibleTargetGateways(sourceGateway, gateways, target).length > 0;
}

function apiMatchesDeployment(api: API, deployment: GatewayDeployment, tenantId: string): boolean {
  const sourceTenant = deploymentTenantId(deployment);
  if (sourceTenant && sourceTenant !== tenantId) return false;
  return deploymentMatchesApi(deployment, api.id);
}

function buildEligibility(
  apisByTenant: Record<string, API[]>,
  deployments: GatewayDeployment[],
  gateways: GatewayInstance[]
): Record<string, Record<string, string[]>> {
  const result: Record<string, Record<string, Set<string>>> = {};

  for (const [tenantId, tenantApis] of Object.entries(apisByTenant)) {
    for (const [source, target] of VALID_CHAINS) {
      const key = pathKey(source, target);
      for (const api of tenantApis) {
        const eligible = deployments.some(
          (deployment) =>
            apiMatchesDeployment(api, deployment, tenantId) &&
            deploymentIsEligibleForPath(deployment, gateways, source, target)
        );
        if (!eligible) continue;
        result[tenantId] ??= {};
        result[tenantId][key] ??= new Set<string>();
        result[tenantId][key].add(api.id);
      }
    }
  }

  return Object.fromEntries(
    Object.entries(result).map(([tenantId, byPath]) => [
      tenantId,
      Object.fromEntries(Object.entries(byPath).map(([key, apiIds]) => [key, Array.from(apiIds)])),
    ])
  );
}

function eligibleApiIdsForTenant(
  eligibilityByTenant: Record<string, Record<string, string[]>>,
  tenantId: string
): Set<string> {
  return new Set(Object.values(eligibilityByTenant[tenantId] ?? {}).flat());
}

function eligibleApisForTenant(
  apisByTenant: Record<string, API[]>,
  eligibilityByTenant: Record<string, Record<string, string[]>>,
  tenantId: string
): API[] {
  const eligibleIds = eligibleApiIdsForTenant(eligibilityByTenant, tenantId);
  return (apisByTenant[tenantId] ?? []).filter((api) => eligibleIds.has(api.id));
}

async function fetchAllGatewayInstances(): Promise<GatewayInstance[]> {
  const items: GatewayInstance[] = [];
  let page = 1;
  let total = 0;
  do {
    const result = await apiService.getGatewayInstances({ page, page_size: PAGE_SIZE_MAX });
    items.push(...result.items);
    total = result.total;
    page += 1;
  } while (items.length < total);
  return items;
}

async function fetchAllSyncedSourceDeployments(): Promise<GatewayDeployment[]> {
  const deployments: GatewayDeployment[] = [];
  for (const [source] of VALID_CHAINS) {
    const sourceItems: GatewayDeployment[] = [];
    let page = 1;
    let total = 0;
    do {
      const result = await apiService.getGatewayDeployments({
        environment: source,
        sync_status: 'synced',
        page,
        page_size: PAGE_SIZE_MAX,
      });
      sourceItems.push(...result.items);
      total = result.total;
      page += 1;
    } while (sourceItems.length < total);
    deployments.push(...sourceItems);
  }
  return deployments;
}

// =============================================================================
// PROMOTION PIPELINE INDICATOR
// =============================================================================

function PromotionPipeline({ promotions }: { promotions: Promotion[] }) {
  const envs = ['dev', 'staging', 'production'] as const;

  const getEnvStatus = (env: string) => {
    const latest = promotions.find(
      (p) => p.target_environment === env && (p.status === 'promoted' || p.status === 'promoting')
    );
    if (!latest) return 'none';
    return latest.status;
  };

  return (
    <div className="flex items-center gap-2">
      {envs.map((env, i) => {
        const status = i === 0 ? 'source' : getEnvStatus(env);
        return (
          <div key={env} className="flex items-center gap-2">
            {i > 0 && (
              <ArrowRight className="h-4 w-4 text-neutral-300 dark:text-neutral-600 shrink-0" />
            )}
            <div
              className={clsx(
                'px-3 py-1.5 rounded-lg text-xs font-medium border',
                status === 'source' || status === 'promoted'
                  ? 'border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400'
                  : status === 'promoting'
                    ? 'border-blue-300 dark:border-blue-700 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400 animate-pulse'
                    : 'border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800 text-neutral-500 dark:text-neutral-400'
              )}
            >
              {env.toUpperCase()}
              {status === 'promoted' && <CheckCircle2 className="inline h-3 w-3 ml-1" />}
              {status === 'promoting' && <Loader2 className="inline h-3 w-3 ml-1 animate-spin" />}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// =============================================================================
// DIFF VIEWER
// =============================================================================

function DiffViewer({ diff }: { diff: Schemas['PromotionDiffResponse'] }) {
  return (
    <div className="space-y-4 p-4 bg-neutral-50 dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <h4 className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase mb-2">
            Source ({diff.source_environment})
          </h4>
          {diff.source_spec ? (
            <pre className="text-xs bg-white dark:bg-neutral-800 p-3 rounded border border-neutral-200 dark:border-neutral-700 overflow-auto max-h-48">
              {JSON.stringify(diff.source_spec, null, 2)}
            </pre>
          ) : (
            <p className="text-sm text-neutral-400">No deployment found</p>
          )}
        </div>
        <div>
          <h4 className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase mb-2">
            Target ({diff.target_environment})
          </h4>
          {diff.target_spec ? (
            <pre className="text-xs bg-white dark:bg-neutral-800 p-3 rounded border border-neutral-200 dark:border-neutral-700 overflow-auto max-h-48">
              {JSON.stringify(diff.target_spec, null, 2)}
            </pre>
          ) : (
            <p className="text-sm text-neutral-400">No prior deployment (first deploy to target)</p>
          )}
        </div>
      </div>
      {diff.diff_summary && Object.keys(diff.diff_summary).length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase mb-2">
            Changes
          </h4>
          <pre className="text-xs bg-white dark:bg-neutral-800 p-3 rounded border border-neutral-200 dark:border-neutral-700 overflow-auto max-h-32">
            {JSON.stringify(diff.diff_summary, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

// =============================================================================
// CREATE PROMOTION DIALOG
// =============================================================================

interface CreatePromotionDialogProps {
  tenantId: string;
  apis: API[];
  eligibleApiIdsByPath: Record<string, string[]>;
  onClose: () => void;
  onCreated: () => void;
}

function CreatePromotionDialog({
  tenantId,
  apis,
  eligibleApiIdsByPath,
  onClose,
  onCreated,
}: CreatePromotionDialogProps) {
  const [selectedApi, setSelectedApi] = useState('');
  const [source, setSource] = useState('dev');
  const [target, setTarget] = useState('staging');
  const [gateways, setGateways] = useState<GatewayInstance[]>([]);
  const [sourceDeployments, setSourceDeployments] = useState<GatewayDeployment[]>([]);
  const [selectedSourceDeploymentId, setSelectedSourceDeploymentId] = useState('');
  const [selectedTargetGatewayIds, setSelectedTargetGatewayIds] = useState<string[]>([]);
  const [message, setMessage] = useState('');
  const [loadingTargets, setLoadingTargets] = useState(true);
  const [loadingSourceDeployments, setLoadingSourceDeployments] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isValidChain = VALID_CHAINS.some(([s, t]) => s === source && t === target);
  const eligibleApisForPath = useMemo(() => {
    const eligibleIds = new Set(eligibleApiIdsByPath[pathKey(source, target)] ?? []);
    return apis.filter((api) => eligibleIds.has(api.id));
  }, [apis, eligibleApiIdsByPath, source, target]);

  useEffect(() => {
    if (selectedApi && !eligibleApisForPath.some((api) => api.id === selectedApi)) {
      setSelectedApi('');
    }
  }, [eligibleApisForPath, selectedApi]);

  useEffect(() => {
    let cancelled = false;
    async function loadGateways() {
      try {
        setLoadingTargets(true);
        const result = await apiService.getGatewayInstances({ page_size: PAGE_SIZE_MAX });
        if (!cancelled) setGateways(result.items);
      } catch (err: unknown) {
        if (!cancelled) setError(extractErrorMessage(err));
      } finally {
        if (!cancelled) setLoadingTargets(false);
      }
    }
    loadGateways();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (source === 'dev') setTarget('staging');
    else if (source === 'staging') setTarget('production');
  }, [source]);

  useEffect(() => {
    setSelectedSourceDeploymentId('');
    setSelectedTargetGatewayIds([]);
    if (!selectedApi) {
      setSourceDeployments([]);
      return;
    }

    let cancelled = false;
    async function loadSourceDeployments() {
      try {
        setLoadingSourceDeployments(true);
        const result = await apiService.getGatewayDeployments({
          environment: source,
          sync_status: 'synced',
          page_size: PAGE_SIZE_MAX,
        });
        if (!cancelled) setSourceDeployments(result.items);
      } catch (err: unknown) {
        if (!cancelled) {
          setSourceDeployments([]);
          setError(extractErrorMessage(err));
        }
      } finally {
        if (!cancelled) setLoadingSourceDeployments(false);
      }
    }

    loadSourceDeployments();
    return () => {
      cancelled = true;
    };
  }, [selectedApi, source]);

  const matchingSourceDeployments = useMemo(
    () =>
      sourceDeployments.filter(
        (deployment) =>
          deployment.sync_status === 'synced' &&
          sameEnvironment(deployment.gateway_environment, source) &&
          deploymentMatchesApi(deployment, selectedApi)
      ),
    [sourceDeployments, selectedApi, source]
  );

  const selectedSourceDeployment = useMemo(
    () =>
      matchingSourceDeployments.find((deployment) => deployment.id === selectedSourceDeploymentId),
    [matchingSourceDeployments, selectedSourceDeploymentId]
  );

  const selectedSourceGateway = useMemo(
    () => gateways.find((gateway) => gateway.id === selectedSourceDeployment?.gateway_instance_id),
    [gateways, selectedSourceDeployment]
  );

  const targetGatewayCandidates = useMemo(() => {
    if (!selectedSourceGateway) return [];
    return compatibleTargetGateways(selectedSourceGateway, gateways, target);
  }, [gateways, selectedSourceGateway, target]);

  useEffect(() => {
    setSelectedTargetGatewayIds((current) =>
      current.filter((id) => targetGatewayCandidates.some((gateway) => gateway.id === id))
    );
  }, [targetGatewayCandidates]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (
      !selectedApi ||
      !selectedSourceDeploymentId ||
      selectedTargetGatewayIds.length === 0 ||
      !message.trim()
    ) {
      return;
    }
    try {
      setSubmitting(true);
      setError(null);
      await apiService.createPromotion(tenantId, selectedApi, {
        source_deployment_id: selectedSourceDeploymentId,
        target_gateway_ids: selectedTargetGatewayIds,
        source_environment: source,
        target_environment: target,
        message: message.trim(),
      });
      onCreated();
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : typeof err === 'object' && err !== null && 'response' in err
            ? ((err as { response?: { data?: { detail?: string } } }).response?.data?.detail ??
              'Failed to create promotion')
            : 'Failed to create promotion';
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-xl w-full max-w-2xl mx-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between border-b border-neutral-200 dark:border-neutral-700 px-6 py-4">
          <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">
            Create Promotion
          </h2>
          <button
            onClick={onClose}
            className="text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          {error && (
            <div className="flex items-start gap-2 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg text-sm">
              <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* API selector */}
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              API
            </label>
            <select
              value={selectedApi}
              onChange={(e) => setSelectedApi(e.target.value)}
              className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white text-sm"
              disabled={!isValidChain || eligibleApisForPath.length === 0}
              required
              data-testid="promotion-api-select"
            >
              <option value="">
                {eligibleApisForPath.length === 0
                  ? 'No eligible APIs for this path'
                  : 'Select an eligible API...'}
              </option>
              {eligibleApisForPath.map((api) => (
                <option key={api.id} value={api.id}>
                  {api.display_name} ({api.name})
                </option>
              ))}
            </select>
          </div>

          {/* Environment chain */}
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Promotion Path
            </label>
            <div className="flex items-center gap-3">
              <select
                value={source}
                onChange={(e) => setSource(e.target.value)}
                className="flex-1 px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white text-sm"
              >
                <option value="dev">Dev</option>
                <option value="staging">Staging</option>
              </select>
              <ArrowRight className="h-5 w-5 text-neutral-400 shrink-0" />
              <select
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                className="flex-1 px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white text-sm"
              >
                <option value="staging">Staging</option>
                <option value="production">Production</option>
              </select>
            </div>
            {!isValidChain && (
              <p className="text-xs text-red-500 mt-1">
                Invalid chain. Only dev &rarr; staging and staging &rarr; production are allowed.
              </p>
            )}
          </div>

          {/* Source deployment */}
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Source Deployment
            </label>
            <select
              value={selectedSourceDeploymentId}
              onChange={(e) => {
                setSelectedSourceDeploymentId(e.target.value);
                setSelectedTargetGatewayIds([]);
              }}
              className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white text-sm"
              disabled={!selectedApi || loadingSourceDeployments}
              required
              data-testid="source-deployment-select"
            >
              <option value="">
                {loadingSourceDeployments
                  ? 'Loading synced deployments...'
                  : 'Select a synced source deployment...'}
              </option>
              {matchingSourceDeployments.map((deployment) => (
                <option key={deployment.id} value={deployment.id}>
                  {deployment.gateway_display_name ||
                    deployment.gateway_name ||
                    deployment.gateway_instance_id}{' '}
                  · {deployment.gateway_type || 'gateway'} · {deployment.id.slice(0, 8)}
                </option>
              ))}
            </select>
            {selectedApi && !loadingSourceDeployments && matchingSourceDeployments.length === 0 && (
              <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
                No synced {source} gateway deployment exists for this API.
              </p>
            )}
          </div>

          {/* Target gateways */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
                Target Gateways
              </label>
              {selectedSourceGateway && (
                <span className="text-xs text-neutral-500 dark:text-neutral-400">
                  {gatewayFamily(selectedSourceGateway)}
                  {gatewayTopology(selectedSourceGateway)
                    ? ` · ${gatewayTopology(selectedSourceGateway)}`
                    : ''}
                </span>
              )}
            </div>
            <div
              className="border border-neutral-200 dark:border-neutral-700 rounded-lg divide-y divide-neutral-200 dark:divide-neutral-700 overflow-hidden"
              data-testid="target-gateway-list"
            >
              {loadingTargets ? (
                <div className="px-3 py-3 text-sm text-neutral-500 dark:text-neutral-400">
                  Loading gateways...
                </div>
              ) : !selectedSourceDeploymentId ? (
                <div className="px-3 py-3 text-sm text-neutral-500 dark:text-neutral-400">
                  Select a source deployment first.
                </div>
              ) : targetGatewayCandidates.length === 0 ? (
                <div className="px-3 py-3 text-sm text-amber-600 dark:text-amber-400">
                  No compatible {target} gateway found for the selected source gateway.
                </div>
              ) : (
                targetGatewayCandidates.map((gateway) => (
                  <label
                    key={gateway.id}
                    className="flex items-center gap-3 px-3 py-2 text-sm hover:bg-neutral-50 dark:hover:bg-neutral-700"
                  >
                    <input
                      type="checkbox"
                      checked={selectedTargetGatewayIds.includes(gateway.id)}
                      onChange={(e) => {
                        setSelectedTargetGatewayIds((current) =>
                          e.target.checked
                            ? [...current, gateway.id]
                            : current.filter((id) => id !== gateway.id)
                        );
                      }}
                      className="h-4 w-4 rounded border-neutral-300 text-blue-600 focus:ring-blue-500"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block font-medium text-neutral-900 dark:text-white truncate">
                        {gateway.display_name || gateway.name}
                      </span>
                      <span className="block text-xs text-neutral-500 dark:text-neutral-400 truncate">
                        {gateway.name} · {gateway.environment}
                      </span>
                    </span>
                  </label>
                ))
              )}
            </div>
          </div>

          {/* Message */}
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Message <span className="text-red-500">*</span>
            </label>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Why are you promoting this API? (audit trail)"
              rows={3}
              maxLength={1000}
              className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white text-sm resize-none"
              required
            />
            <p className="text-xs text-neutral-400 mt-1">{message.length}/1000</p>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-2 border-t border-neutral-200 dark:border-neutral-700">
            <Button variant="secondary" onClick={onClose} type="button">
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={
                submitting ||
                !selectedApi ||
                !selectedSourceDeploymentId ||
                selectedTargetGatewayIds.length === 0 ||
                !message.trim() ||
                !isValidChain
              }
            >
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Creating...
                </>
              ) : (
                <>
                  <ArrowUpRight className="h-4 w-4" />
                  Create Promotion
                </>
              )}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// =============================================================================
// PROMOTION ROW
// =============================================================================

interface PromotionRowProps {
  promotion: Promotion;
  tenantId: string;
  canPromote: boolean;
  currentUser: string;
  onRefresh: () => void;
}

function PromotionRow({
  promotion,
  tenantId,
  canPromote,
  currentUser,
  onRefresh,
}: PromotionRowProps) {
  const [expanded, setExpanded] = useState(false);
  const [diff, setDiff] = useState<Schemas['PromotionDiffResponse'] | null>(null);
  const [loadingDiff, setLoadingDiff] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const toast = useToastActions();
  const [confirm, confirmDialog] = useConfirm();

  const status = promotionStatusConfig[promotion.status];
  const StatusIcon = status.icon;
  const isProductionTarget = promotion.target_environment === 'production';
  const isSelfRequest = promotion.requested_by === currentUser;
  const canApprove =
    canPromote && promotion.status === 'pending' && !(isSelfRequest && isProductionTarget);
  const isSelfApproval =
    canPromote && promotion.status === 'pending' && isSelfRequest && isProductionTarget;
  const canComplete = canPromote && promotion.status === 'promoting';
  const canRollback = canPromote && promotion.status === 'promoted';

  const handleExpand = async () => {
    if (!expanded && !diff) {
      setLoadingDiff(true);
      try {
        const result = await apiService.getPromotionDiff(tenantId, promotion.id);
        setDiff(result);
      } catch {
        // Diff may not be available for all promotions
      } finally {
        setLoadingDiff(false);
      }
    }
    setExpanded(!expanded);
  };

  const handleApprove = async () => {
    const ok = await confirm({
      title: 'Approve Promotion',
      message: `Approve promotion of API from ${promotion.source_environment} to ${promotion.target_environment}? This will trigger the deployment pipeline.`,
      confirmLabel: 'Approve',
      variant: 'default',
    });
    if (!ok) return;
    try {
      setActionLoading(true);
      await apiService.approvePromotion(tenantId, promotion.id);
      toast.success('Promotion approved', 'Deployment pipeline triggered');
      onRefresh();
    } catch (err: unknown) {
      toast.error('Approval failed', extractErrorMessage(err));
    } finally {
      setActionLoading(false);
    }
  };

  const handleComplete = async () => {
    const ok = await confirm({
      title: 'Verify Promotion Completion',
      message: `Complete this promotion only if all linked gateway deployments are synced for ${promotion.source_environment} → ${promotion.target_environment}.`,
      confirmLabel: 'Verify Complete',
      variant: 'default',
    });
    if (!ok) return;
    try {
      setActionLoading(true);
      await apiService.completePromotion(tenantId, promotion.id);
      toast.success('Promotion completed', 'All linked deployments are synced');
      onRefresh();
    } catch (err: unknown) {
      toast.error('Complete failed', extractErrorMessage(err));
    } finally {
      setActionLoading(false);
    }
  };

  const handleRollback = async () => {
    const ok = await confirm({
      title: 'Rollback Promotion',
      message: `Rollback this promotion? This will create a reverse promotion from ${promotion.target_environment} to ${promotion.source_environment}.`,
      confirmLabel: 'Rollback',
      variant: 'danger',
    });
    if (!ok) return;
    try {
      setActionLoading(true);
      await apiService.rollbackPromotion(tenantId, promotion.id, {
        message: `Rollback of promotion ${promotion.id.slice(0, 8)}`,
      });
      toast.success('Rollback created', 'Reverse promotion created');
      onRefresh();
    } catch (err: unknown) {
      toast.error('Rollback failed', extractErrorMessage(err));
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div>
      <div
        className={clsx(
          'grid grid-cols-[2fr_1.5fr_1fr_1.5fr_1fr_1fr] gap-2 px-6 py-4 items-center cursor-pointer transition-colors',
          expanded
            ? 'bg-blue-50 dark:bg-blue-900/10'
            : 'hover:bg-neutral-50 dark:hover:bg-neutral-700'
        )}
        onClick={handleExpand}
      >
        {/* API + Message */}
        <div className="flex items-center gap-2 min-w-0">
          <button className="text-neutral-400 dark:text-neutral-500 shrink-0">
            {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </button>
          <div className="min-w-0">
            <div className="text-sm font-medium text-neutral-900 dark:text-white truncate">
              {promotion.api_id.slice(0, 8)}...
            </div>
            <div className="text-xs text-neutral-500 dark:text-neutral-400 truncate">
              {promotion.message}
            </div>
          </div>
        </div>

        {/* Environment chain */}
        <div className="flex items-center gap-1.5">
          <span
            className={clsx(
              'px-2 py-0.5 text-xs font-medium rounded',
              envColors[promotion.source_environment] || 'bg-neutral-100 text-neutral-700'
            )}
          >
            {promotion.source_environment.toUpperCase()}
          </span>
          <ArrowRight className="h-3.5 w-3.5 text-neutral-400" />
          <span
            className={clsx(
              'px-2 py-0.5 text-xs font-medium rounded',
              envColors[promotion.target_environment] || 'bg-neutral-100 text-neutral-700'
            )}
          >
            {promotion.target_environment.toUpperCase()}
          </span>
          {promotion.target_gateway_ids?.length ? (
            <span className="text-xs text-neutral-500 dark:text-neutral-400">
              {promotion.target_gateway_ids.length} gw
            </span>
          ) : null}
        </div>

        {/* Status */}
        <div>
          <span
            className={clsx(
              'inline-flex items-center gap-1.5 px-2 py-1 rounded text-xs font-medium',
              status.bg,
              status.color
            )}
          >
            <StatusIcon
              className={clsx('h-3.5 w-3.5', promotion.status === 'promoting' && 'animate-spin')}
            />
            {status.label}
          </span>
        </div>

        {/* Requested by + date */}
        <div>
          <div className="text-sm text-neutral-900 dark:text-white">{promotion.requested_by}</div>
          <div className="text-xs text-neutral-500 dark:text-neutral-400">
            {new Date(promotion.created_at).toLocaleString()}
          </div>
        </div>

        {/* Approved by */}
        <div className="text-sm text-neutral-500 dark:text-neutral-400">
          {promotion.approved_by || '—'}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
          {canApprove && (
            <button
              onClick={handleApprove}
              disabled={actionLoading}
              className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-green-600 text-white hover:bg-green-700 disabled:opacity-50"
            >
              <CheckCircle2 className="h-3.5 w-3.5" />
              Approve
            </button>
          )}
          {isSelfApproval && (
            <span
              className="text-xs text-amber-600 dark:text-amber-400"
              title="4-eyes principle: you cannot approve your own promotion"
            >
              Self-approve blocked
            </span>
          )}
          {canComplete && (
            <button
              onClick={handleComplete}
              disabled={actionLoading}
              className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
            >
              <CheckCircle2 className="h-3.5 w-3.5" />
              Verify Complete
            </button>
          )}
          {canRollback && (
            <button
              onClick={handleRollback}
              disabled={actionLoading}
              className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-orange-600 text-white hover:bg-orange-700 disabled:opacity-50"
            >
              <Undo2 className="h-3.5 w-3.5" />
              Rollback
            </button>
          )}
        </div>
      </div>

      {/* Expanded: Diff viewer */}
      {expanded && (
        <div className="px-6 pb-4 bg-blue-50/50 dark:bg-blue-900/5 border-t border-neutral-100 dark:border-neutral-700">
          <div className="pt-4">
            {loadingDiff ? (
              <div className="flex items-center gap-2 text-sm text-neutral-500">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading diff...
              </div>
            ) : diff ? (
              <DiffViewer diff={diff} />
            ) : (
              <p className="text-sm text-neutral-500 dark:text-neutral-400">
                No diff available for this promotion.
              </p>
            )}
          </div>
        </div>
      )}

      {confirmDialog}
    </div>
  );
}

// =============================================================================
// MAIN PROMOTIONS PAGE
// =============================================================================

export function Promotions() {
  const { isReady, hasPermission, user } = useAuth();
  const toast = useToastActions();

  const [promotions, setPromotions] = useState<Promotion[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [apisByTenant, setApisByTenant] = useState<Record<string, API[]>>({});
  const [eligibilityByTenant, setEligibilityByTenant] = useState<
    Record<string, Record<string, string[]>>
  >({});
  const [selectedTenant, setSelectedTenant] = useState('');
  const [selectedApi, setSelectedApi] = useState('');
  const [selectedStatus, setSelectedStatus] = useState('');
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [eligibilityLoading, setEligibilityLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateDialog, setShowCreateDialog] = useState(false);

  const canPromote = hasPermission('apis:deploy');
  const pageSize = 20;
  const eligibleTenants = useMemo(
    () =>
      tenants.filter((tenant) => eligibleApiIdsForTenant(eligibilityByTenant, tenant.id).size > 0),
    [tenants, eligibilityByTenant]
  );
  const apis = useMemo(
    () => eligibleApisForTenant(apisByTenant, eligibilityByTenant, selectedTenant),
    [apisByTenant, eligibilityByTenant, selectedTenant]
  );
  const selectedTenantEligibility = eligibilityByTenant[selectedTenant] ?? {};

  const loadPromotions = useCallback(async () => {
    if (!selectedTenant) return;
    try {
      setLoading(true);
      const result = await apiService.listPromotions(selectedTenant, {
        api_id: selectedApi || undefined,
        status: selectedStatus || undefined,
        page,
        page_size: pageSize,
      });
      setPromotions(result.items);
      setTotalCount(result.total);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load promotions');
      setPromotions([]);
      setTotalCount(0);
    } finally {
      setLoading(false);
    }
  }, [selectedTenant, selectedApi, selectedStatus, page]);

  const loadPromotionEligibility = useCallback(async () => {
    try {
      setLoading(true);
      setEligibilityLoading(true);
      const tenantData = await apiService.getTenants();
      const apiEntries = await Promise.all(
        tenantData.map(async (tenant) => [tenant.id, await apiService.getApis(tenant.id)] as const)
      );
      const nextApisByTenant = Object.fromEntries(apiEntries);
      const [gatewayData, deploymentData] = await Promise.all([
        fetchAllGatewayInstances(),
        fetchAllSyncedSourceDeployments(),
      ]);
      const nextEligibilityByTenant = buildEligibility(
        nextApisByTenant,
        deploymentData,
        gatewayData
      );
      const firstEligibleTenant = tenantData.find(
        (tenant) => eligibleApiIdsForTenant(nextEligibilityByTenant, tenant.id).size > 0
      );

      setTenants(tenantData);
      setApisByTenant(nextApisByTenant);
      setEligibilityByTenant(nextEligibilityByTenant);
      setSelectedTenant((current) =>
        current && eligibleApiIdsForTenant(nextEligibilityByTenant, current).size > 0
          ? current
          : (firstEligibleTenant?.id ?? '')
      );
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load promotion eligibility');
      setTenants([]);
      setApisByTenant({});
      setEligibilityByTenant({});
      setSelectedTenant('');
      setPromotions([]);
      setTotalCount(0);
    } finally {
      setEligibilityLoading(false);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isReady) loadPromotionEligibility();
  }, [isReady, loadPromotionEligibility]);

  useEffect(() => {
    setPage(1);
  }, [selectedTenant]);

  useEffect(() => {
    if (selectedApi && !apis.some((api) => api.id === selectedApi)) {
      setSelectedApi('');
    }
  }, [apis, selectedApi]);

  useEffect(() => {
    if (selectedTenant) loadPromotions();
  }, [loadPromotions, selectedTenant]);

  const handleCreated = () => {
    setShowCreateDialog(false);
    toast.success('Promotion created', 'Promotion request submitted for approval');
    loadPromotions();
  };

  const handleRefresh = async () => {
    await loadPromotionEligibility();
    if (selectedTenant) await loadPromotions();
  };

  const totalPages = Math.ceil(totalCount / pageSize);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Promotions</h1>
          <p className="text-neutral-500 dark:text-neutral-400 mt-1">
            Promote APIs across environments — dev &rarr; staging &rarr; production
          </p>
        </div>
        {canPromote && (
          <Button
            onClick={() => setShowCreateDialog(true)}
            disabled={!selectedTenant || eligibilityLoading || apis.length === 0}
          >
            <Plus className="h-4 w-4" />
            New Promotion
          </Button>
        )}
      </div>

      {/* Pipeline Indicator */}
      {promotions.length > 0 && (
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-sm border border-neutral-100 dark:border-neutral-700 p-4">
          <h3 className="text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-3">
            Promotion Pipeline
          </h3>
          <PromotionPipeline promotions={promotions} />
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-4">
        <select
          value={selectedTenant}
          onChange={(e) => setSelectedTenant(e.target.value)}
          className="px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white text-sm"
          data-testid="promotion-tenant-filter"
        >
          <option value="">Select tenant...</option>
          {eligibleTenants.map((t) => (
            <option key={t.id} value={t.id}>
              {t.display_name}
            </option>
          ))}
        </select>
        <select
          value={selectedApi}
          onChange={(e) => {
            setSelectedApi(e.target.value);
            setPage(1);
          }}
          className="px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white text-sm"
          disabled={!selectedTenant || apis.length === 0}
          data-testid="promotion-api-filter"
        >
          <option value="">All APIs</option>
          {apis.map((api) => (
            <option key={api.id} value={api.id}>
              {api.display_name}
            </option>
          ))}
        </select>
        <select
          value={selectedStatus}
          onChange={(e) => {
            setSelectedStatus(e.target.value);
            setPage(1);
          }}
          className="px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white text-sm"
        >
          <option value="">All Statuses</option>
          <option value="pending">Pending</option>
          <option value="promoting">Promoting</option>
          <option value="promoted">Promoted</option>
          <option value="failed">Failed</option>
          <option value="rolled_back">Rolled Back</option>
        </select>
        <button
          onClick={handleRefresh}
          className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 text-sm"
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg">
          {error}
          <button onClick={() => setError(null)} className="float-right font-bold">
            &times;
          </button>
        </div>
      )}

      {/* Promotions List */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-sm border border-neutral-100 dark:border-neutral-700 overflow-hidden">
        {loading ? (
          <TableSkeleton rows={5} columns={6} />
        ) : !selectedTenant ? (
          <EmptyState
            variant="deployments"
            description="No APIs are eligible for promotion right now."
          />
        ) : promotions.length === 0 ? (
          <EmptyState
            variant="deployments"
            description="No promotions yet. Create one to promote an API across environments."
          />
        ) : (
          <div className="divide-y divide-neutral-200 dark:divide-neutral-700">
            {/* Table header */}
            <div className="grid grid-cols-[2fr_1.5fr_1fr_1.5fr_1fr_1fr] gap-2 px-6 py-3 bg-neutral-50 dark:bg-neutral-700 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
              <span>API / Message</span>
              <span>Path</span>
              <span>Status</span>
              <span>Requested By</span>
              <span>Approved By</span>
              <span>Actions</span>
            </div>
            {promotions.map((promotion) => (
              <PromotionRow
                key={promotion.id}
                promotion={promotion}
                tenantId={selectedTenant}
                canPromote={canPromote}
                currentUser={user?.username || ''}
                onRefresh={loadPromotions}
              />
            ))}
          </div>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-neutral-500 dark:text-neutral-400">
            Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, totalCount)} of{' '}
            {totalCount}
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-3 py-1.5 text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg disabled:opacity-50 hover:bg-neutral-50 dark:hover:bg-neutral-700"
            >
              Previous
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="px-3 py-1.5 text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg disabled:opacity-50 hover:bg-neutral-50 dark:hover:bg-neutral-700"
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Create Promotion Dialog */}
      {showCreateDialog && selectedTenant && (
        <CreatePromotionDialog
          tenantId={selectedTenant}
          apis={apis}
          eligibleApiIdsByPath={selectedTenantEligibility}
          onClose={() => setShowCreateDialog(false)}
          onCreated={handleCreated}
        />
      )}
    </div>
  );
}
