import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Search, Users } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { apiService } from '../services/api';
import { useToastActions } from '@stoa/shared/components/Toast';
import type { API, Tenant } from '../types';

const AUDIENCE_OPTIONS = ['public', 'internal', 'partner'] as const;
type Audience = (typeof AUDIENCE_OPTIONS)[number];

const audienceBadgeClasses: Record<Audience, string> = {
  public: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  internal: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  partner: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400',
};

export function AudienceGovernance() {
  const { user, hasPermission } = useAuth();
  const toast = useToastActions();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [tenantFilter, setTenantFilter] = useState('');
  const [editingApi, setEditingApi] = useState<string | null>(null);

  const canEdit = hasPermission('apis:update');
  const isCpiAdmin = user?.roles.includes('cpi-admin');

  const { data: tenants } = useQuery({
    queryKey: ['tenants'],
    queryFn: () => apiService.getTenants(),
    enabled: isCpiAdmin,
  });

  const activeTenantId = isCpiAdmin ? tenantFilter : user?.tenant_id;

  const { data: apis, isLoading } = useQuery({
    queryKey: ['apis', activeTenantId],
    queryFn: () => apiService.getApis(activeTenantId!),
    enabled: !!activeTenantId,
  });

  const mutation = useMutation({
    mutationFn: ({
      tenantId,
      apiId,
      audience,
    }: {
      tenantId: string;
      apiId: string;
      audience: string;
    }) => apiService.updateApiAudience(tenantId, apiId, audience),
    onSuccess: (_data, variables) => {
      toast.success(`Audience updated to "${variables.audience}"`);
      queryClient.invalidateQueries({ queryKey: ['apis', variables.tenantId] });
      setEditingApi(null);
    },
    onError: () => {
      toast.error('Failed to update audience');
    },
  });

  const handleAudienceChange = useCallback(
    (tenantId: string, apiId: string, audience: string) => {
      mutation.mutate({ tenantId, apiId, audience });
    },
    [mutation]
  );

  const filteredApis = (apis ?? []).filter(
    (api) =>
      !search ||
      api.name.toLowerCase().includes(search.toLowerCase()) ||
      api.display_name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">
            Audience Governance
          </h1>
          <p className="text-neutral-500 dark:text-neutral-400 mt-1">
            Manage API audience visibility levels
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-4">
        {isCpiAdmin && tenants && (
          <select
            value={tenantFilter}
            onChange={(e) => setTenantFilter(e.target.value)}
            className="rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 px-3 py-2 text-sm text-neutral-900 dark:text-white"
          >
            <option value="">Select tenant...</option>
            {tenants.map((t: Tenant) => (
              <option key={t.id} value={t.name}>
                {t.display_name}
              </option>
            ))}
          </select>
        )}
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400" />
          <input
            type="text"
            placeholder="Search APIs..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 text-sm text-neutral-900 dark:text-white placeholder-neutral-400"
          />
        </div>
      </div>

      {/* No tenant selected */}
      {!activeTenantId && (
        <div className="text-center py-12 text-neutral-500 dark:text-neutral-400">
          <Users className="w-12 h-12 mx-auto mb-4 opacity-50" />
          <p>Select a tenant to view API audience settings.</p>
        </div>
      )}

      {/* Loading */}
      {isLoading && activeTenantId && (
        <div className="text-center py-12 text-neutral-500 dark:text-neutral-400">
          Loading APIs...
        </div>
      )}

      {/* API Table */}
      {activeTenantId && !isLoading && (
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none overflow-hidden">
          <table className="min-w-full divide-y divide-neutral-200 dark:divide-neutral-700">
            <thead className="bg-neutral-50 dark:bg-neutral-900/50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                  API
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                  Version
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                  Audience
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-200 dark:divide-neutral-700">
              {filteredApis.length === 0 ? (
                <tr>
                  <td
                    colSpan={4}
                    className="px-6 py-8 text-center text-neutral-500 dark:text-neutral-400"
                  >
                    No APIs found.
                  </td>
                </tr>
              ) : (
                filteredApis.map((api: API) => (
                  <tr key={api.id} className="hover:bg-neutral-50 dark:hover:bg-neutral-700/30">
                    <td className="px-6 py-4">
                      <div className="text-sm font-medium text-neutral-900 dark:text-white">
                        {api.display_name}
                      </div>
                      <div className="text-xs text-neutral-500 dark:text-neutral-400">
                        {api.name}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-sm text-neutral-500 dark:text-neutral-400">
                      {api.version}
                    </td>
                    <td className="px-6 py-4">
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-neutral-100 text-neutral-800 dark:bg-neutral-700 dark:text-neutral-300">
                        {api.status}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      {canEdit && editingApi === api.id ? (
                        <select
                          defaultValue={api.audience ?? 'public'}
                          onChange={(e) =>
                            handleAudienceChange(api.tenant_id, api.name, e.target.value)
                          }
                          onBlur={() => setEditingApi(null)}
                          autoFocus
                          className="rounded border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 px-2 py-1 text-xs text-neutral-900 dark:text-white"
                        >
                          {AUDIENCE_OPTIONS.map((opt) => (
                            <option key={opt} value={opt}>
                              {opt}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <button
                          onClick={() => canEdit && setEditingApi(api.id)}
                          disabled={!canEdit}
                          className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                            audienceBadgeClasses[(api.audience as Audience) ?? 'public']
                          } ${canEdit ? 'cursor-pointer hover:ring-2 hover:ring-offset-1 hover:ring-blue-400' : 'cursor-default'}`}
                        >
                          {api.audience ?? 'public'}
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
