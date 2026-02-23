/**
 * UsagePage - CAB-280
 * Dashboard Usage Consumer pour DevOps/CPI
 *
 * Page principale /usage dans le Portal STOA
 */

import { useState, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Activity, CheckCircle, Clock, AlertTriangle, RefreshCw } from 'lucide-react';
import {
  StatCard,
  CallsTable,
  UsageChart,
  TopTools,
  SubscriptionsList,
} from '../../components/usage';
import { usageService, formatLatency } from '../../services/usage';
import { useAuth } from '../../contexts/AuthContext';
import { config } from '../../config';
import { loadNamespace } from '../../i18n';

type Period = 'today' | 'week' | 'month';

export function UsagePage() {
  const { isAuthenticated, isLoading: authLoading, accessToken } = useAuth();
  const queryClient = useQueryClient();
  const { t, i18n: i18nInstance } = useTranslation('usage');
  const i18nEnabled = config.features.enableI18n;

  useEffect(() => {
    if (i18nEnabled) {
      const lng = i18nInstance.language;
      loadNamespace(lng, 'usage');
      if (lng !== 'en') loadNamespace('en', 'usage');
    }
  }, [i18nEnabled, i18nInstance.language]);

  const [selectedPeriod, setSelectedPeriod] = useState<Period>('today');

  const isReady = isAuthenticated && !authLoading && !!accessToken;

  // 3 parallel queries — no waterfall
  const {
    data: summary = null,
    isLoading: summaryLoading,
    error: summaryError,
  } = useQuery({
    queryKey: ['usage', 'summary'],
    queryFn: () => usageService.getSummary(),
    enabled: isReady,
    staleTime: 30_000,
  });

  const { data: callsResponse = null, isLoading: callsLoading } = useQuery({
    queryKey: ['usage', 'calls'],
    queryFn: () => usageService.getCalls({ limit: 20 }),
    enabled: isReady,
    staleTime: 30_000,
  });

  const { data: subscriptions = [], isLoading: subsLoading } = useQuery({
    queryKey: ['usage', 'subscriptions'],
    queryFn: () => usageService.getActiveSubscriptions(),
    enabled: isReady,
    staleTime: 30_000,
  });

  const error = summaryError ? summaryError.message || 'Failed to load usage data' : null;

  const refetchAll = () => {
    queryClient.invalidateQueries({ queryKey: ['usage'] });
  };

  // Get stats for selected period
  const getPeriodStats = () => {
    if (!summary) return null;
    switch (selectedPeriod) {
      case 'today':
        return summary.today;
      case 'week':
        return summary.this_week;
      case 'month':
        return summary.this_month;
    }
  };

  const periodStats = getPeriodStats();

  return (
    <div className="min-h-screen bg-neutral-50 dark:bg-neutral-900">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">
              {i18nEnabled ? t('title') : 'Usage Dashboard'}
            </h1>
            <p className="text-neutral-500 dark:text-neutral-400 mt-1">
              {i18nEnabled ? t('subtitle') : 'Monitor your MCP tool consumption and performance'}
            </p>
          </div>

          <button
            onClick={refetchAll}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-neutral-700 dark:text-neutral-200 bg-white dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            {i18nEnabled ? t('refresh') : 'Refresh'}
          </button>
        </div>

        {/* Error banner */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-red-500 dark:text-red-400" />
            <span className="text-red-700 dark:text-red-300">{error}</span>
          </div>
        )}

        {/* Stats Cards Row */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <StatCard
            title={i18nEnabled ? t('totalCalls') : 'Total Calls'}
            value={periodStats?.total_calls.toLocaleString() ?? '—'}
            subtitle={
              selectedPeriod === 'today'
                ? i18nEnabled
                  ? t('today')
                  : 'Today'
                : selectedPeriod === 'week'
                  ? i18nEnabled
                    ? t('thisWeek')
                    : 'This week'
                  : i18nEnabled
                    ? t('thisMonth')
                    : 'This month'
            }
            icon={<Activity className="w-5 h-5" />}
            color="cyan"
            isLoading={summaryLoading}
          />

          <StatCard
            title={i18nEnabled ? t('successRate') : 'Success Rate'}
            value={periodStats ? `${periodStats.success_rate.toFixed(1)}%` : '—'}
            subtitle={i18nEnabled ? t('successfulCalls') : 'Successful calls'}
            icon={<CheckCircle className="w-5 h-5" />}
            color={periodStats && periodStats.success_rate >= 95 ? 'emerald' : 'amber'}
            trend={periodStats ? { value: 2.3, isPositive: true } : undefined}
            isLoading={summaryLoading}
          />

          <StatCard
            title={i18nEnabled ? t('avgLatency') : 'Avg Latency'}
            value={periodStats ? formatLatency(periodStats.avg_latency_ms) : '—'}
            subtitle={i18nEnabled ? t('responseTime') : 'Response time'}
            icon={<Clock className="w-5 h-5" />}
            color={periodStats && periodStats.avg_latency_ms <= 200 ? 'emerald' : 'amber'}
            isLoading={summaryLoading}
          />

          <StatCard
            title={i18nEnabled ? t('errors') : 'Errors'}
            value={periodStats?.error_count.toString() ?? '—'}
            subtitle={i18nEnabled ? t('failedCalls') : 'Failed calls'}
            icon={<AlertTriangle className="w-5 h-5" />}
            color={periodStats && periodStats.error_count > 10 ? 'red' : 'emerald'}
            isLoading={summaryLoading}
          />
        </div>

        {/* Main Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Column - Chart & Calls Table */}
          <div className="lg:col-span-2 space-y-6">
            {/* Usage Chart */}
            <UsageChart data={summary?.daily_calls ?? []} isLoading={summaryLoading} />

            {/* Calls Table */}
            <CallsTable calls={callsResponse?.calls ?? []} isLoading={callsLoading} />
          </div>

          {/* Right Column - Top Tools & Subscriptions */}
          <div className="space-y-6">
            {/* Top Tools */}
            <TopTools tools={summary?.top_tools ?? []} isLoading={summaryLoading} />

            {/* Active Subscriptions */}
            <SubscriptionsList subscriptions={subscriptions} isLoading={subsLoading} />
          </div>
        </div>

        {/* Period Selector */}
        <div className="mt-8 flex items-center justify-center gap-2">
          <span className="text-sm text-neutral-500 dark:text-neutral-400">
            {i18nEnabled ? t('viewPeriod') : 'View period:'}
          </span>
          {(['today', 'week', 'month'] as const).map((period) => (
            <button
              key={period}
              onClick={() => setSelectedPeriod(period)}
              className={`
                px-4 py-2 rounded-lg text-sm font-medium transition-colors
                ${
                  selectedPeriod === period
                    ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 border border-primary-200 dark:border-primary-700'
                    : 'text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-700'
                }
              `}
            >
              {period === 'today'
                ? i18nEnabled
                  ? t('today')
                  : 'Today'
                : period === 'week'
                  ? i18nEnabled
                    ? t('thisWeek')
                    : 'This Week'
                  : i18nEnabled
                    ? t('thisMonth')
                    : 'This Month'}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

export default UsagePage;
