/**
 * UsagePage - CAB-280
 * Dashboard Usage Consumer pour DevOps/CPI
 *
 * Page principale /usage dans le Portal STOA
 */

import { useState, useEffect } from 'react';
import { Activity, CheckCircle, Clock, AlertTriangle, RefreshCw } from 'lucide-react';
import { StatCard, CallsTable, UsageChart, TopTools, SubscriptionsList } from '../../components/usage';
import { usageService, formatLatency } from '../../services/usage';
import type { UsageSummary, UsageCallsResponse, ActiveSubscription } from '../../types';

type Period = 'today' | 'week' | 'month';

export function UsagePage() {
  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [callsResponse, setCallsResponse] = useState<UsageCallsResponse | null>(null);
  const [subscriptions, setSubscriptions] = useState<ActiveSubscription[]>([]);

  const [summaryLoading, setSummaryLoading] = useState(true);
  const [callsLoading, setCallsLoading] = useState(true);
  const [subsLoading, setSubsLoading] = useState(true);

  const [selectedPeriod, setSelectedPeriod] = useState<Period>('today');
  const [error, setError] = useState<string | null>(null);

  // Fetch data
  const fetchData = async () => {
    setError(null);

    // Fetch summary
    setSummaryLoading(true);
    try {
      const summaryData = await usageService.getSummary();
      setSummary(summaryData);
    } catch (err) {
      console.error('Failed to fetch usage summary:', err);
      setError('Failed to load usage data');
    } finally {
      setSummaryLoading(false);
    }

    // Fetch calls
    setCallsLoading(true);
    try {
      const callsData = await usageService.getCalls({ limit: 20 });
      setCallsResponse(callsData);
    } catch (err) {
      console.error('Failed to fetch calls:', err);
    } finally {
      setCallsLoading(false);
    }

    // Fetch subscriptions
    setSubsLoading(true);
    try {
      const subsData = await usageService.getActiveSubscriptions();
      setSubscriptions(subsData);
    } catch (err) {
      console.error('Failed to fetch subscriptions:', err);
    } finally {
      setSubsLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

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
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              Usage Dashboard
            </h1>
            <p className="text-gray-500 mt-1">
              Monitor your MCP tool consumption and performance
            </p>
          </div>

          <button
            onClick={fetchData}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
        </div>

        {/* Error banner */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-red-500" />
            <span className="text-red-700">{error}</span>
          </div>
        )}

        {/* Stats Cards Row */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <StatCard
            title="Total Calls"
            value={periodStats?.total_calls.toLocaleString() ?? '—'}
            subtitle={selectedPeriod === 'today' ? 'Today' : selectedPeriod === 'week' ? 'This week' : 'This month'}
            icon={<Activity className="w-5 h-5" />}
            color="cyan"
            isLoading={summaryLoading}
          />

          <StatCard
            title="Success Rate"
            value={periodStats ? `${periodStats.success_rate.toFixed(1)}%` : '—'}
            subtitle="Successful calls"
            icon={<CheckCircle className="w-5 h-5" />}
            color={periodStats && periodStats.success_rate >= 95 ? 'emerald' : 'amber'}
            trend={periodStats ? { value: 2.3, isPositive: true } : undefined}
            isLoading={summaryLoading}
          />

          <StatCard
            title="Avg Latency"
            value={periodStats ? formatLatency(periodStats.avg_latency_ms) : '—'}
            subtitle="Response time"
            icon={<Clock className="w-5 h-5" />}
            color={periodStats && periodStats.avg_latency_ms <= 200 ? 'emerald' : 'amber'}
            isLoading={summaryLoading}
          />

          <StatCard
            title="Errors"
            value={periodStats?.error_count.toString() ?? '—'}
            subtitle="Failed calls"
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
            <UsageChart
              data={summary?.daily_calls ?? []}
              isLoading={summaryLoading}
            />

            {/* Calls Table */}
            <CallsTable
              calls={callsResponse?.calls ?? []}
              isLoading={callsLoading}
            />
          </div>

          {/* Right Column - Top Tools & Subscriptions */}
          <div className="space-y-6">
            {/* Top Tools */}
            <TopTools
              tools={summary?.top_tools ?? []}
              isLoading={summaryLoading}
            />

            {/* Active Subscriptions */}
            <SubscriptionsList
              subscriptions={subscriptions}
              isLoading={subsLoading}
            />
          </div>
        </div>

        {/* Period Selector */}
        <div className="mt-8 flex items-center justify-center gap-2">
          <span className="text-sm text-gray-500">View period:</span>
          {(['today', 'week', 'month'] as const).map((period) => (
            <button
              key={period}
              onClick={() => setSelectedPeriod(period)}
              className={`
                px-4 py-2 rounded-lg text-sm font-medium transition-colors
                ${selectedPeriod === period
                  ? 'bg-primary-100 text-primary-700 border border-primary-200'
                  : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
                }
              `}
            >
              {period === 'today' ? 'Today' : period === 'week' ? 'This Week' : 'This Month'}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

export default UsagePage;
