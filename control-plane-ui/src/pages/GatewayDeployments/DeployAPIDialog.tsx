import { useState, useEffect } from 'react';
import { X, AlertCircle, CheckCircle2 } from 'lucide-react';
import { apiService } from '../../services/api';
import type { API, GatewayDeployment } from '../../types';

interface GatewayOption {
  id: string;
  name: string;
  display_name: string;
  gateway_type: string;
  environment: string;
}

interface DeployableEnv {
  environment: string;
  deployable: boolean;
  promotion_status: string;
}

interface ExistingDeployment {
  gateway_instance_id: string;
  sync_status: string;
}

interface Tenant {
  id: string;
  name: string;
}

interface DeployAPIDialogProps {
  onClose: () => void;
  onDeployed: () => void;
  /** Pre-select an API (from API Detail page). Format: "tenantId:apiName" */
  preselectedApiKey?: string;
}

export function DeployAPIDialog({ onClose, onDeployed, preselectedApiKey }: DeployAPIDialogProps) {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [selectedTenant, setSelectedTenant] = useState('');
  const [apis, setApis] = useState<API[]>([]);
  const [gateways, setGateways] = useState<GatewayOption[]>([]);
  const [selectedApi, setSelectedApi] = useState('');
  const [selectedEnv, setSelectedEnv] = useState('');
  const [selectedGateways, setSelectedGateways] = useState<string[]>([]);
  const [deployableEnvs, setDeployableEnvs] = useState<DeployableEnv[]>([]);
  const [existingDeployments, setExistingDeployments] = useState<ExistingDeployment[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingApis, setLoadingApis] = useState(false);
  const [loadingEnvs, setLoadingEnvs] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load tenants and gateways on mount
  useEffect(() => {
    async function loadData() {
      try {
        const [tenantList, gwResult] = await Promise.all([
          apiService.getTenants(),
          apiService.getGatewayInstances({ page_size: 100 }),
        ]);
        setTenants(tenantList);
        setGateways(gwResult.items);

        // Auto-select first tenant (or preselected)
        if (preselectedApiKey) {
          const [tenantId] = preselectedApiKey.split(':');
          setSelectedTenant(tenantId);
        } else if (tenantList.length > 0) {
          setSelectedTenant(tenantList[0].id);
        }
      } catch {
        setError('Failed to load data');
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [preselectedApiKey]);

  // Load APIs when tenant changes (from Git, same as /apis page)
  useEffect(() => {
    if (!selectedTenant) {
      setApis([]);
      setSelectedApi('');
      return;
    }

    setLoadingApis(true);
    apiService
      .getApis(selectedTenant)
      .then((result) => {
        setApis(result);
        // Auto-select preselected API
        if (preselectedApiKey) {
          const [, apiName] = preselectedApiKey.split(':');
          const found = result.find((a) => a.name === apiName || a.id === apiName);
          if (found) setSelectedApi(found.name);
        }
      })
      .catch(() => setApis([]))
      .finally(() => setLoadingApis(false));
  }, [selectedTenant, preselectedApiKey]);

  // Load deployable environments when API is selected
  useEffect(() => {
    if (!selectedApi || !selectedTenant) {
      setDeployableEnvs([]);
      setSelectedEnv('');
      return;
    }

    setLoadingEnvs(true);
    // Use the deploy endpoint which will ensure-sync the API to catalog
    apiService
      .getDeployableEnvironments(selectedTenant, selectedApi)
      .then((result) => {
        setDeployableEnvs(result.environments);
        const firstDeployable = result.environments.find((e) => e.deployable);
        if (firstDeployable) setSelectedEnv(firstDeployable.environment);
      })
      .catch(() => {
        // If API not in catalog yet, dev is always deployable
        setDeployableEnvs([
          { environment: 'dev', deployable: true, promotion_status: 'not_required' },
          { environment: 'staging', deployable: false, promotion_status: 'not_promoted' },
          { environment: 'production', deployable: false, promotion_status: 'not_promoted' },
        ]);
        setSelectedEnv('dev');
      })
      .finally(() => setLoadingEnvs(false));
  }, [selectedApi, selectedTenant]);

  // Load existing deployments when env changes
  useEffect(() => {
    if (!selectedEnv) {
      setExistingDeployments([]);
      return;
    }
    apiService
      .getGatewayDeployments({ environment: selectedEnv, page_size: 100 })
      .then((result) => {
        setExistingDeployments(
          result.items
            .filter((d: GatewayDeployment) => {
              const apiName = d.desired_state?.api_name as string;
              const apiId = d.desired_state?.api_id as string;
              return apiName === selectedApi || apiId === selectedApi;
            })
            .map((d: GatewayDeployment) => ({
              gateway_instance_id: d.gateway_instance_id,
              sync_status: d.sync_status,
            }))
        );
      })
      .catch(() => setExistingDeployments([]));
  }, [selectedEnv, selectedApi]);

  // Filter gateways by selected environment
  const filteredGateways = gateways.filter((gw) => selectedEnv && gw.environment === selectedEnv);

  const isAlreadyDeployed = (gwId: string) =>
    existingDeployments.some((d) => d.gateway_instance_id === gwId && d.sync_status === 'synced');

  const toggleGateway = (id: string) => {
    setSelectedGateways((prev) =>
      prev.includes(id) ? prev.filter((g) => g !== id) : [...prev, id]
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedApi || !selectedEnv || !selectedTenant || selectedGateways.length === 0) return;

    setSubmitting(true);
    setError(null);

    try {
      await apiService.deployApiToEnv(selectedTenant, selectedApi, {
        environment: selectedEnv,
        gateway_ids: selectedGateways,
      });
      onDeployed();
    } catch {
      setError('Failed to deploy API');
    } finally {
      setSubmitting(false);
    }
  };

  const envLabels: Record<string, string> = {
    dev: 'Development',
    staging: 'Staging',
    production: 'Production',
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-xl w-full max-w-2xl mx-4">
        {/* Header */}
        <div className="flex items-center justify-between border-b dark:border-neutral-700 px-6 py-4">
          <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">
            Deploy API to Gateways
          </h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-700 hover:text-neutral-600 dark:hover:text-neutral-300"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          {error && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg text-sm flex items-center gap-2">
              <AlertCircle className="h-4 w-4 flex-shrink-0" />
              {error}
            </div>
          )}

          {loading ? (
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <div className="h-4 w-32 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
                <div className="h-10 w-full bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
              </div>
              <div className="space-y-2">
                <div className="h-4 w-28 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
                <div className="h-32 w-full bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
              </div>
            </div>
          ) : (
            <>
              {/* Tenant Selection */}
              {tenants.length > 1 && (
                <div>
                  <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                    Tenant
                  </label>
                  <select
                    value={selectedTenant}
                    onChange={(e) => {
                      setSelectedTenant(e.target.value);
                      setSelectedApi('');
                      setSelectedEnv('');
                      setSelectedGateways([]);
                    }}
                    required
                    disabled={!!preselectedApiKey}
                    className="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:opacity-60"
                  >
                    <option value="">Select a tenant...</option>
                    {tenants.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name || t.id}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {/* API Selection (from Git, same source as /apis page) */}
              <div>
                <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                  API
                </label>
                {loadingApis ? (
                  <div className="h-10 w-full bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
                ) : apis.length === 0 && selectedTenant ? (
                  <p className="text-sm text-neutral-500 dark:text-neutral-400">
                    No APIs found for this tenant.
                  </p>
                ) : (
                  <select
                    value={selectedApi}
                    onChange={(e) => {
                      setSelectedApi(e.target.value);
                      setSelectedEnv('');
                      setSelectedGateways([]);
                    }}
                    required
                    disabled={!!preselectedApiKey || !selectedTenant}
                    className="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:opacity-60"
                  >
                    <option value="">Select an API...</option>
                    {apis.map((api) => (
                      <option key={api.name} value={api.name}>
                        {api.display_name || api.name} v{api.version}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              {/* Environment Selection */}
              {selectedApi && (
                <div>
                  <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                    Environment
                  </label>
                  {loadingEnvs ? (
                    <div className="h-10 w-full bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
                  ) : (
                    <select
                      value={selectedEnv}
                      onChange={(e) => {
                        setSelectedEnv(e.target.value);
                        setSelectedGateways([]);
                      }}
                      required
                      className="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    >
                      <option value="">Select environment...</option>
                      {deployableEnvs.map((env) => (
                        <option
                          key={env.environment}
                          value={env.environment}
                          disabled={!env.deployable}
                        >
                          {envLabels[env.environment] || env.environment}
                          {!env.deployable ? ' (not promoted)' : ''}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              )}

              {/* Gateway Multi-Select */}
              {selectedEnv && (
                <div>
                  <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                    Target Gateways ({envLabels[selectedEnv] || selectedEnv})
                  </label>
                  {filteredGateways.length === 0 ? (
                    <p className="text-sm text-neutral-500 dark:text-neutral-400">
                      No gateways registered in {envLabels[selectedEnv] || selectedEnv}.
                    </p>
                  ) : (
                    <div className="space-y-2 max-h-48 overflow-y-auto border border-neutral-200 dark:border-neutral-600 rounded-lg p-3">
                      {filteredGateways.map((gw) => {
                        const deployed = isAlreadyDeployed(gw.id);
                        return (
                          <label
                            key={gw.id}
                            className={`flex items-center gap-3 p-2 rounded-lg cursor-pointer ${
                              deployed
                                ? 'opacity-60 bg-green-50 dark:bg-green-900/10'
                                : 'hover:bg-neutral-50 dark:hover:bg-neutral-700'
                            }`}
                          >
                            <input
                              type="checkbox"
                              checked={deployed || selectedGateways.includes(gw.id)}
                              onChange={() => !deployed && toggleGateway(gw.id)}
                              disabled={deployed}
                              className="h-4 w-4 rounded border-neutral-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50"
                            />
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium text-neutral-900 dark:text-white">
                                {gw.display_name}
                              </p>
                              <p className="text-xs text-neutral-500 dark:text-neutral-400">
                                {gw.gateway_type}
                              </p>
                            </div>
                            {deployed && (
                              <span className="flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
                                <CheckCircle2 className="h-3.5 w-3.5" />
                                Synced
                              </span>
                            )}
                          </label>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-2 border-t dark:border-neutral-700">
            <button
              type="button"
              onClick={onClose}
              className="border border-neutral-300 dark:border-neutral-600 text-neutral-700 dark:text-neutral-300 px-4 py-2 rounded-lg text-sm hover:bg-neutral-50 dark:hover:bg-neutral-700"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || !selectedApi || !selectedEnv || selectedGateways.length === 0}
              className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50"
            >
              {submitting
                ? 'Deploying...'
                : `Deploy to ${selectedGateways.length} gateway${selectedGateways.length !== 1 ? 's' : ''}`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
