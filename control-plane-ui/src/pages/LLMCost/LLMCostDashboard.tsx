import { useState, useEffect, useCallback } from 'react';
import {
  RefreshCw,
  DollarSign,
  TrendingUp,
  AlertTriangle,
  Zap,
  Trash2,
  Server,
  Clock,
  Database,
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { apiService } from '../../services/api';
import type {
  LlmUsageResponse,
  LlmTimeseriesResponse,
  LlmProviderCostEntry,
  LlmProviderBreakdownResponse,
} from '../../services/api';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import { StatCard } from '@stoa/shared/components/StatCard';

const ACTIVE_TENANT_KEY = 'stoa-active-tenant';
const PERIODS = ['hour', 'day', 'week', 'month'] as const;
type Period = (typeof PERIODS)[number];

const PERIOD_LABELS: Record<Period, string> = {
  hour: 'Last Hour',
  day: 'Last 24h',
  week: 'Last 7 Days',
  month: 'Last 30 Days',
};

interface LlmProvider {
  id: string;
  tenant_id: string;
  provider_name: string;
  display_name: string | null;
  default_model: string | null;
  cost_per_input_token: number;
  cost_per_output_token: number;
  status: 'active' | 'inactive' | 'rate_limited';
  created_at: string;
  updated_at: string;
}

interface LlmBudget {
  id: string;
  tenant_id: string;
  monthly_limit_usd: number;
  current_spend_usd: number;
  alert_threshold_pct: number;
  usage_pct: number;
  remaining_usd: number;
  is_over_budget: boolean;
  created_at: string;
  updated_at: string;
}

export function LLMCostDashboard() {
  const { user, hasPermission } = useAuth();
  const [providers, setProviders] = useState<LlmProvider[]>([]);
  const [budget, setBudget] = useState<LlmBudget | null>(null);
  const [usage, setUsage] = useState<LlmUsageResponse | null>(null);
  const [timeseries, setTimeseries] = useState<LlmTimeseriesResponse | null>(null);
  const [providerCosts, setProviderCosts] = useState<LlmProviderCostEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [period, setPeriod] = useState<Period>('month');

  const tenantId = sessionStorage.getItem(ACTIVE_TENANT_KEY) || user?.tenant_id || '';
  const canManageProviders = hasPermission('admin:servers');

  const fetchData = useCallback(async () => {
    try {
      const [providersRes, budgetRes, usageRes, tsRes, costBreakdownRes] = await Promise.allSettled(
        [
          apiService.get<LlmProvider[]>(`/v1/tenants/${tenantId}/llm/providers`),
          apiService.get<LlmBudget>(`/v1/tenants/${tenantId}/llm/budget`),
          apiService.getLlmUsage(tenantId, period),
          apiService.getLlmTimeseries(tenantId, period),
          apiService.getLlmProviderBreakdown(tenantId, period),
        ]
      );

      if (providersRes.status === 'fulfilled') {
        setProviders(providersRes.value.data);
      }
      if (budgetRes.status === 'fulfilled') {
        setBudget(budgetRes.value.data);
      }
      if (usageRes.status === 'fulfilled') {
        setUsage(usageRes.value);
      }
      if (tsRes.status === 'fulfilled') {
        setTimeseries(tsRes.value);
      }
      if (costBreakdownRes.status === 'fulfilled') {
        setProviderCosts((costBreakdownRes.value as LlmProviderBreakdownResponse).providers || []);
      }
    } catch {
      // errors handled per-request above
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [tenantId, period]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchData();
  };

  const handleDeleteProvider = async (providerId: string) => {
    if (!confirm('Are you sure you want to delete this provider?')) return;
    try {
      await apiService.delete(`/v1/tenants/${tenantId}/llm/providers/${providerId}`);
      setProviders((prev) => prev.filter((p) => p.id !== providerId));
    } catch {
      alert('Failed to delete provider');
    }
  };

  const activeProviders = providers.filter((p) => p.status === 'active').length;
  const rateLimitedProviders = providers.filter((p) => p.status === 'rate_limited').length;

  if (loading) {
    return (
      <div className="space-y-6 p-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
          {[...Array(4)].map((_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      </div>
    );
  }

  const usagePct = budget?.usage_pct ?? 0;
  const usageColor =
    usagePct >= 90 ? 'text-red-500' : usagePct >= 70 ? 'text-yellow-500' : 'text-green-500';

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">LLM Cost Management</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Monitor LLM spend and manage provider budgets for tenant{' '}
            <span className="font-medium">{tenantId}</span>
          </p>
        </div>
        <div className="flex items-center gap-3">
          <PeriodSelector value={period} onChange={setPeriod} />
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
            data-testid="refresh-btn"
          >
            <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Prometheus-backed Usage KPI Cards */}
      {usage && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-4" data-testid="usage-cards">
          <StatCard
            label="Total Cost"
            value={`$${usage.total_cost_usd.toFixed(4)}`}
            icon={DollarSign}
            colorClass="text-emerald-500"
          />
          <StatCard
            label="Tokens Used"
            value={formatNumber(usage.input_tokens + usage.output_tokens)}
            icon={Database}
          />
          <StatCard
            label="Avg Cost / Request"
            value={`$${usage.avg_cost_per_request.toFixed(6)}`}
            icon={TrendingUp}
          />
          <StatCard
            label="Cache Savings"
            value={`$${(usage.cache_read_cost_usd + usage.cache_write_cost_usd).toFixed(4)}`}
            icon={Zap}
            colorClass="text-purple-500"
          />
        </div>
      )}

      {/* Budget Overview Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-4" data-testid="budget-cards">
        <StatCard
          label="Monthly Budget"
          value={budget ? `$${Number(budget.monthly_limit_usd).toFixed(0)}` : 'N/A'}
          icon={DollarSign}
        />
        <StatCard
          label="Current Spend"
          value={budget ? `$${Number(budget.current_spend_usd).toFixed(2)}` : '$0.00'}
          icon={TrendingUp}
          colorClass={usageColor}
        />
        <StatCard
          label="Active Providers"
          value={activeProviders}
          icon={Zap}
          colorClass="text-blue-500"
        />
        <StatCard
          label="Budget Usage"
          value={budget ? `${usagePct.toFixed(0)}%` : '0%'}
          icon={AlertTriangle}
          colorClass={usageColor}
        />
      </div>

      {/* Budget Alert */}
      {budget?.is_over_budget && (
        <div
          className="rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20"
          data-testid="over-budget-alert"
        >
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-red-500" />
            <span className="text-sm font-medium text-red-800 dark:text-red-300">
              Over Budget — Current spend exceeds the monthly limit by $
              {Math.abs(Number(budget.remaining_usd)).toFixed(2)}
            </span>
          </div>
        </div>
      )}

      {/* Budget Progress Bar */}
      {budget && (
        <div
          className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900"
          data-testid="budget-progress"
        >
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Budget Utilization
            </span>
            <span className={`text-sm font-bold ${usageColor}`}>{usagePct.toFixed(1)}%</span>
          </div>
          <div className="h-3 w-full rounded-full bg-gray-200 dark:bg-gray-700">
            <div
              className={`h-3 rounded-full transition-all ${
                usagePct >= 90 ? 'bg-red-500' : usagePct >= 70 ? 'bg-yellow-500' : 'bg-green-500'
              }`}
              style={{ width: `${Math.min(usagePct, 100)}%` }}
              data-testid="budget-bar"
            />
          </div>
          <div className="mt-1 flex justify-between text-xs text-gray-500 dark:text-gray-400">
            <span>$0</span>
            <span>Alert at {budget.alert_threshold_pct}%</span>
            <span>${Number(budget.monthly_limit_usd).toFixed(0)}</span>
          </div>
        </div>
      )}

      {/* Cost Time-Series Chart */}
      {timeseries && timeseries.points.length > 0 && (
        <CostTimeseriesChart points={timeseries.points} step={timeseries.step} />
      )}

      {/* Provider Cost Breakdown (Prometheus) */}
      {providerCosts.length > 0 && <ProviderCostBreakdown providers={providerCosts} />}

      {/* Providers Table */}
      <div className="overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between bg-gray-50 px-6 py-3 dark:bg-gray-800">
          <h2 className="text-sm font-semibold text-gray-900 dark:text-white">LLM Providers</h2>
          {rateLimitedProviders > 0 && (
            <span
              className="inline-flex items-center gap-1 rounded-full bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200"
              data-testid="rate-limited-badge"
            >
              <AlertTriangle className="h-3 w-3" />
              {rateLimitedProviders} rate limited
            </span>
          )}
        </div>
        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                Provider
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                Model
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                Input Cost
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                Output Cost
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                Status
              </th>
              {canManageProviders && (
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                  Actions
                </th>
              )}
            </tr>
          </thead>
          <tbody
            className="divide-y divide-gray-200 bg-white dark:divide-gray-700 dark:bg-gray-900"
            data-testid="providers-table-body"
          >
            {providers.length === 0 ? (
              <tr>
                <td
                  colSpan={canManageProviders ? 6 : 5}
                  className="px-6 py-8 text-center text-sm text-gray-500 dark:text-gray-400"
                >
                  No LLM providers configured for this tenant.
                </td>
              </tr>
            ) : (
              providers.map((provider) => (
                <tr key={provider.id} data-testid={`provider-row-${provider.id}`}>
                  <td className="whitespace-nowrap px-6 py-4">
                    <div className="flex items-center gap-2">
                      <Server className="h-4 w-4 text-gray-400" />
                      <div>
                        <div className="text-sm font-medium text-gray-900 dark:text-white">
                          {provider.display_name || provider.provider_name}
                        </div>
                        {provider.display_name && (
                          <div className="text-xs text-gray-500 dark:text-gray-400">
                            {provider.provider_name}
                          </div>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500 dark:text-gray-400">
                    {provider.default_model || '—'}
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500 dark:text-gray-400">
                    ${Number(provider.cost_per_input_token).toFixed(4)}/tok
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500 dark:text-gray-400">
                    ${Number(provider.cost_per_output_token).toFixed(4)}/tok
                  </td>
                  <td className="whitespace-nowrap px-6 py-4">
                    <ProviderStatusBadge status={provider.status} />
                  </td>
                  {canManageProviders && (
                    <td className="whitespace-nowrap px-6 py-4">
                      <button
                        onClick={() => handleDeleteProvider(provider.id)}
                        className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20"
                        data-testid={`delete-provider-${provider.id}`}
                      >
                        <Trash2 className="h-3 w-3" />
                        Delete
                      </button>
                    </td>
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Sub-components                                                     */
/* ------------------------------------------------------------------ */

function PeriodSelector({ value, onChange }: { value: Period; onChange: (p: Period) => void }) {
  return (
    <div
      className="inline-flex rounded-lg border border-gray-300 dark:border-gray-600"
      data-testid="period-selector"
    >
      {PERIODS.map((p) => (
        <button
          key={p}
          onClick={() => onChange(p)}
          className={`px-3 py-1.5 text-xs font-medium first:rounded-l-lg last:rounded-r-lg ${
            value === p
              ? 'bg-blue-600 text-white'
              : 'bg-white text-gray-600 hover:bg-gray-50 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700'
          }`}
          data-testid={`period-${p}`}
        >
          {PERIOD_LABELS[p]}
        </button>
      ))}
    </div>
  );
}

function CostTimeseriesChart({
  points,
  step,
}: {
  points: { timestamp: string; value: number }[];
  step: string;
}) {
  const maxValue = Math.max(...points.map((p) => p.value), 0.001);

  return (
    <div
      className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900"
      data-testid="cost-timeseries"
    >
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-white">Cost Over Time</h2>
        <span className="text-xs text-gray-500 dark:text-gray-400">
          <Clock className="mr-1 inline h-3 w-3" />
          Step: {step}
        </span>
      </div>
      <div className="flex h-40 items-end gap-px" data-testid="timeseries-bars">
        {points.map((point, i) => {
          const heightPct = (point.value / maxValue) * 100;
          return (
            <div
              key={i}
              className="group relative flex-1"
              title={`${new Date(point.timestamp).toLocaleString()}: $${point.value.toFixed(4)}`}
            >
              <div
                className="w-full rounded-t bg-blue-500 transition-all group-hover:bg-blue-400 dark:bg-blue-600"
                style={{ height: `${Math.max(heightPct, 1)}%` }}
              />
            </div>
          );
        })}
      </div>
      <div className="mt-1 flex justify-between text-xs text-gray-400 dark:text-gray-500">
        <span>{points.length > 0 ? new Date(points[0].timestamp).toLocaleDateString() : ''}</span>
        <span>
          {points.length > 0
            ? new Date(points[points.length - 1].timestamp).toLocaleDateString()
            : ''}
        </span>
      </div>
    </div>
  );
}

function ProviderCostBreakdown({ providers }: { providers: LlmProviderCostEntry[] }) {
  const totalCost = providers.reduce((sum, p) => sum + p.cost_usd, 0);

  return (
    <div
      className="overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700"
      data-testid="provider-cost-breakdown"
    >
      <div className="bg-gray-50 px-6 py-3 dark:bg-gray-800">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-white">
          Cost by Provider &amp; Model
        </h2>
      </div>
      <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
        <thead className="bg-gray-50 dark:bg-gray-800">
          <tr>
            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
              Provider
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
              Model
            </th>
            <th className="px-6 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
              Cost (USD)
            </th>
            <th className="px-6 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
              Share
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200 bg-white dark:divide-gray-700 dark:bg-gray-900">
          {providers.map((p, i) => {
            const pct = totalCost > 0 ? (p.cost_usd / totalCost) * 100 : 0;
            return (
              <tr key={i} data-testid={`cost-row-${p.provider}-${p.model}`}>
                <td className="whitespace-nowrap px-6 py-3 text-sm font-medium text-gray-900 dark:text-white">
                  {p.provider}
                </td>
                <td className="whitespace-nowrap px-6 py-3 text-sm text-gray-500 dark:text-gray-400">
                  {p.model}
                </td>
                <td className="whitespace-nowrap px-6 py-3 text-right text-sm font-medium text-gray-900 dark:text-white">
                  ${p.cost_usd.toFixed(4)}
                </td>
                <td className="whitespace-nowrap px-6 py-3 text-right text-sm text-gray-500 dark:text-gray-400">
                  {pct.toFixed(1)}%
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ProviderStatusBadge({ status }: { status: string }) {
  const config: Record<string, { color: string; label: string }> = {
    active: {
      color: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
      label: 'Active',
    },
    inactive: {
      color: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
      label: 'Inactive',
    },
    rate_limited: {
      color: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
      label: 'Rate Limited',
    },
  };
  const { color, label } = config[status] || config.active;
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${color}`}
      data-testid={`provider-status-${status}`}
    >
      {label}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* Helpers                                                            */
/* ------------------------------------------------------------------ */

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}
