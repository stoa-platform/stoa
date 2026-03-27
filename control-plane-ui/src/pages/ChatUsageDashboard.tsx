/**
 * ChatUsageDashboard — chat conversation metrics, token usage, model distribution (CAB-1868).
 *
 * Fetches data from 4 endpoints in parallel:
 * - /chat/usage/tenant?group_by=source  → per-app token breakdown
 * - /chat/usage/budget                  → daily budget progress
 * - /chat/usage/tenant                  → conversation metrics (count, messages, users)
 * - /chat/usage/models                  → model distribution
 */
import { useState, useEffect, useCallback } from 'react';
import { MessageSquare, RefreshCw, BarChart2, Zap, Users, Hash, Bot } from 'lucide-react';
import {
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { useAuth } from '../contexts/AuthContext';
import { apiService } from '../services/api';
import type {
  ChatUsageBySource,
  TokenBudgetStatus,
  ChatConversationMetrics,
  ChatModelDistribution,
} from '../services/api';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import { StatCard } from '@stoa/shared/components/StatCard';

const ACTIVE_TENANT_KEY = 'stoa-active-tenant';

const PERIODS = [
  { label: 'Today', days: 1 },
  { label: '7 Days', days: 7 },
  { label: '30 Days', days: 30 },
] as const;

type PeriodDays = (typeof PERIODS)[number]['days'];

const PIE_COLORS = ['#3B82F6', '#8B5CF6', '#10B981', '#F59E0B', '#EF4444', '#6366F1'];

function fmt(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function shortModel(model: string): string {
  return model.replace(/^claude-/, '').replace(/-\d{8}$/, '');
}

export function ChatUsageDashboard() {
  const { user } = useAuth();
  const tenantId = localStorage.getItem(ACTIVE_TENANT_KEY) || user?.tenant_id || '';

  const [days, setDays] = useState<PeriodDays>(7);
  const [usage, setUsage] = useState<ChatUsageBySource | null>(null);
  const [budget, setBudget] = useState<TokenBudgetStatus | null>(null);
  const [metrics, setMetrics] = useState<ChatConversationMetrics | null>(null);
  const [modelDist, setModelDist] = useState<ChatModelDistribution | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!tenantId) return;
    setError(null);
    try {
      const [usageRes, budgetRes, metricsRes, modelsRes] = await Promise.allSettled([
        apiService.getChatUsageTenant(tenantId, { days }),
        apiService.getChatBudgetStatus(tenantId),
        apiService.getChatConversationMetrics(tenantId),
        apiService.getChatModelDistribution(tenantId),
      ]);
      if (usageRes.status === 'fulfilled') setUsage(usageRes.value);
      else setError('Failed to load usage data.');
      if (budgetRes.status === 'fulfilled') setBudget(budgetRes.value);
      if (metricsRes.status === 'fulfilled') setMetrics(metricsRes.value);
      if (modelsRes.status === 'fulfilled') setModelDist(modelsRes.value);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [tenantId, days]);

  useEffect(() => {
    setLoading(true);
    fetchData();
  }, [fetchData]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchData();
  };

  if (!tenantId) {
    return (
      <div className="p-6 text-sm text-neutral-500 dark:text-neutral-400">No tenant selected.</div>
    );
  }

  const consoleTokens = usage?.sources.find((s) => s.source === 'console')?.tokens ?? 0;
  const portalTokens = usage?.sources.find((s) => s.source === 'portal')?.tokens ?? 0;
  const totalTokens = usage?.total_tokens ?? consoleTokens + portalTokens;

  const budgetPct = budget?.usage_percent ?? 0;
  const budgetColor =
    budgetPct >= 90 ? 'bg-red-500' : budgetPct >= 70 ? 'bg-yellow-500' : 'bg-blue-500';

  const sourceBarData = [
    { name: 'Console', tokens: consoleTokens },
    { name: 'Portal', tokens: portalTokens },
  ];

  const modelPieData =
    modelDist?.models.map((m) => ({
      name: shortModel(m.model),
      value: m.conversations,
    })) ?? [];

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white flex items-center gap-2">
            <BarChart2 className="h-6 w-6 text-blue-500" />
            Chat Usage
          </h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            Conversation metrics, token consumption, and model distribution for tenant{' '}
            <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300">
              {tenantId}
            </span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg border border-neutral-300 dark:border-neutral-600 overflow-hidden">
            {PERIODS.map(({ label, days: d }) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`px-3 py-1.5 text-sm font-medium transition-colors ${
                  days === d
                    ? 'bg-blue-600 text-white'
                    : 'bg-white dark:bg-neutral-800 text-neutral-600 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-700'
                }`}
                data-testid={`period-${d}`}
              >
                {label}
              </button>
            ))}
          </div>
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="inline-flex items-center gap-1.5 rounded-lg border border-neutral-300 bg-white px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-600 dark:bg-neutral-800 dark:text-neutral-300 dark:hover:bg-neutral-700"
            data-testid="refresh-btn"
          >
            <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 px-4 py-3 rounded-lg text-sm text-red-700 dark:text-red-400">
          {error}
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      ) : (
        <>
          {/* Stat cards — conversation metrics + token total */}
          <div
            className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
            data-testid="stat-cards"
          >
            <StatCard
              label="Total Tokens"
              value={fmt(totalTokens)}
              icon={Zap}
              colorClass="text-blue-500"
            />
            <StatCard
              label="Conversations"
              value={fmt(metrics?.total_conversations ?? 0)}
              icon={MessageSquare}
              colorClass="text-indigo-500"
            />
            <StatCard
              label="Messages"
              value={fmt(metrics?.total_messages ?? 0)}
              icon={Hash}
              colorClass="text-purple-500"
            />
            <StatCard
              label="Active Users"
              value={fmt(metrics?.unique_users ?? 0)}
              icon={Users}
              colorClass="text-green-500"
            />
          </div>

          {/* Charts row */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* Token usage by source — bar chart */}
            <div
              className="bg-white dark:bg-neutral-800 rounded-lg shadow p-6"
              data-testid="source-chart"
            >
              <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-4 flex items-center gap-2">
                <BarChart2 className="h-4 w-4" />
                Token Usage by App
              </h2>
              {totalTokens > 0 ? (
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={sourceBarData} barCategoryGap="30%">
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis
                      dataKey="name"
                      tick={{ fontSize: 12, fill: '#6b7280' }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      tick={{ fontSize: 12, fill: '#6b7280' }}
                      axisLine={false}
                      tickLine={false}
                      tickFormatter={(v: number) => fmt(v)}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#1f2937',
                        border: 'none',
                        borderRadius: '8px',
                        color: '#f3f4f6',
                      }}
                      formatter={(value) => [fmt(Number(value)), 'Tokens']}
                    />
                    <Bar dataKey="tokens" radius={[6, 6, 0, 0]}>
                      <Cell fill="#6366F1" />
                      <Cell fill="#8B5CF6" />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex items-center justify-center h-60 text-sm text-neutral-400">
                  No token usage data for this period.
                </div>
              )}
            </div>

            {/* Model distribution — pie chart */}
            <div
              className="bg-white dark:bg-neutral-800 rounded-lg shadow p-6"
              data-testid="model-chart"
            >
              <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-4 flex items-center gap-2">
                <Bot className="h-4 w-4" />
                Model Distribution
              </h2>
              {modelPieData.length > 0 ? (
                <ResponsiveContainer width="100%" height={240}>
                  <PieChart>
                    <Pie
                      data={modelPieData}
                      cx="50%"
                      cy="50%"
                      innerRadius={50}
                      outerRadius={90}
                      paddingAngle={2}
                      dataKey="value"
                    >
                      {modelPieData.map((_entry, i) => (
                        <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#1f2937',
                        border: 'none',
                        borderRadius: '8px',
                        color: '#f3f4f6',
                      }}
                      formatter={(value) => [
                        `${Number(value)} conversation${Number(value) !== 1 ? 's' : ''}`,
                      ]}
                    />
                    <Legend
                      verticalAlign="bottom"
                      iconType="circle"
                      iconSize={8}
                      wrapperStyle={{ fontSize: 12 }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex items-center justify-center h-60 text-sm text-neutral-400">
                  No conversations yet.
                </div>
              )}
            </div>
          </div>

          {/* Daily budget progress */}
          {budget && (
            <div
              className="bg-white dark:bg-neutral-800 rounded-lg shadow p-6"
              data-testid="budget-section"
            >
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300">
                  Daily Budget
                </h2>
                <span
                  className={`text-sm font-medium ${budgetPct >= 90 ? 'text-red-500' : budgetPct >= 70 ? 'text-yellow-500' : 'text-green-600'}`}
                >
                  {budgetPct}% used
                </span>
              </div>
              <div className="h-3 bg-neutral-100 dark:bg-neutral-700 rounded-full overflow-hidden">
                <div
                  className={`h-full ${budgetColor} rounded-full transition-all`}
                  style={{ width: `${Math.min(budgetPct, 100)}%` }}
                  data-testid="budget-bar"
                />
              </div>
              <div className="flex justify-between text-xs text-neutral-500 dark:text-neutral-400 mt-1.5">
                <span>{fmt(budget.tenant_tokens_today)} used today</span>
                <span>{fmt(budget.daily_budget)} limit</span>
              </div>
              {budget.budget_exceeded && (
                <p className="text-xs text-red-500 mt-2 font-medium">
                  Daily budget exceeded — chat requests are being throttled.
                </p>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
