import { useState, useEffect, useCallback } from 'react';
import {
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Zap,
  DollarSign,
  CheckCircle,
  BarChart2,
  Clock,
  ExternalLink,
  Cpu,
  Activity,
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';

const AUTO_REFRESH_INTERVAL = 30_000; // 30 seconds

// Types for tenant usage metrics
interface TenantUsageMetrics {
  totalCalls: number;
  callsTrend: number; // percentage change vs last period
  tokensConsumed: number;
  tokensTrend: number;
  slaCompliance: number;
  estimatedCost: number;
  costTrend: number;
  avgLatency: number;
  errorRate: number;
}

interface ToolUsage {
  name: string;
  displayName: string;
  calls: number;
  percentage: number;
  avgLatency: number;
}

interface DailyUsage {
  date: string;
  calls: number;
  tokens: number;
}

function formatNumber(num: number): string {
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(1)}M`;
  if (num >= 1_000) return `${(num / 1_000).toFixed(1)}K`;
  return num.toString();
}

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('fr-FR', {
    style: 'currency',
    currency: 'EUR',
  }).format(amount);
}

function MetricCard({
  label,
  value,
  unit,
  trend,
  trendLabel,
  icon: Icon,
  colorClass,
}: {
  label: string;
  value: string | number;
  unit?: string;
  trend?: number;
  trendLabel?: string;
  icon: React.ElementType;
  colorClass: string;
}) {
  const isPositiveTrend = trend && trend > 0;
  const TrendIcon = isPositiveTrend ? TrendingUp : TrendingDown;
  const trendColor = isPositiveTrend ? 'text-green-600' : 'text-red-600';

  return (
    <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-5">
      <div className="flex items-center justify-between">
        <div className={`p-2 rounded-lg ${colorClass.replace('text-', 'bg-').replace('600', '100')} dark:bg-opacity-20`}>
          <Icon className={`h-5 w-5 ${colorClass}`} />
        </div>
        {trend !== undefined && (
          <div className={`flex items-center gap-1 text-xs ${trendColor}`}>
            <TrendIcon className="h-3 w-3" />
            <span>{Math.abs(trend).toFixed(1)}%</span>
          </div>
        )}
      </div>
      <div className="mt-4">
        <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">{label}</p>
        <div className="flex items-baseline gap-1 mt-1">
          <p className="text-2xl font-bold text-gray-900 dark:text-white">{value}</p>
          {unit && <span className="text-sm text-gray-500 dark:text-gray-400">{unit}</span>}
        </div>
        {trendLabel && (
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">{trendLabel}</p>
        )}
      </div>
    </div>
  );
}

function ToolUsageItem({ tool, maxCalls }: { tool: ToolUsage; maxCalls: number }) {
  const barWidth = Math.round((tool.calls / maxCalls) * 100);

  return (
    <div className="py-3">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <Cpu className="h-4 w-4 text-gray-400" />
          <span className="text-sm font-medium text-gray-900 dark:text-white">{tool.displayName}</span>
        </div>
        <span className="text-sm text-gray-600 dark:text-gray-300">{formatNumber(tool.calls)} calls</span>
      </div>
      <div className="flex items-center gap-3">
        <div className="flex-1 bg-gray-200 dark:bg-neutral-700 rounded-full h-2">
          <div
            className="bg-blue-500 h-2 rounded-full transition-all duration-300"
            style={{ width: `${barWidth}%` }}
          />
        </div>
        <span className="text-xs text-gray-500 dark:text-gray-400 w-16 text-right">
          {tool.avgLatency}ms avg
        </span>
      </div>
    </div>
  );
}

function UsageSparkline({ data }: { data: DailyUsage[] }) {
  const maxCalls = Math.max(...data.map(d => d.calls), 1);

  return (
    <div className="h-16 flex items-end gap-1">
      {data.map((day, idx) => (
        <div
          key={idx}
          className="bg-blue-500 dark:bg-blue-400 rounded-t flex-1 transition-all duration-300 hover:bg-blue-600"
          style={{ height: `${(day.calls / maxCalls) * 100}%`, minHeight: '4px' }}
          title={`${day.date}: ${formatNumber(day.calls)} calls`}
        />
      ))}
    </div>
  );
}

export function TenantDashboard() {
  const { isReady, user } = useAuth();
  const [metrics, setMetrics] = useState<TenantUsageMetrics | null>(null);
  const [topTools, setTopTools] = useState<ToolUsage[]>([]);
  const [dailyUsage, setDailyUsage] = useState<DailyUsage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [period, setPeriod] = useState<'7d' | '30d' | 'mtd'>('mtd');

  const tenantId = user?.tenant_id;

  const loadData = useCallback(async () => {
    if (!tenantId) return;

    try {
      // In production, these would be real API calls
      // For now, we simulate the data

      // Simulated metrics
      setMetrics({
        totalCalls: 45230 + Math.floor(Math.random() * 1000),
        callsTrend: 12.5,
        tokensConsumed: 1_234_567,
        tokensTrend: 8.3,
        slaCompliance: 99.95,
        estimatedCost: 42.50,
        costTrend: 5.2,
        avgLatency: 145,
        errorRate: 0.02,
      });

      // Simulated top tools
      setTopTools([
        { name: 'weather-api', displayName: 'Weather API', calls: 12450, percentage: 27.5, avgLatency: 120 },
        { name: 'translate-api', displayName: 'Translate API', calls: 8230, percentage: 18.2, avgLatency: 180 },
        { name: 'sentiment-analysis', displayName: 'Sentiment Analysis', calls: 6780, percentage: 15.0, avgLatency: 95 },
        { name: 'image-recognition', displayName: 'Image Recognition', calls: 5420, percentage: 12.0, avgLatency: 450 },
        { name: 'text-summarizer', displayName: 'Text Summarizer', calls: 4350, percentage: 9.6, avgLatency: 280 },
      ]);

      // Simulated daily usage (last 7 days)
      const days = period === '7d' ? 7 : period === '30d' ? 30 : new Date().getDate();
      setDailyUsage(
        Array.from({ length: days }, (_, i) => {
          const date = new Date();
          date.setDate(date.getDate() - (days - 1 - i));
          return {
            date: date.toLocaleDateString('fr-FR', { day: '2-digit', month: 'short' }),
            calls: 5000 + Math.floor(Math.random() * 3000),
            tokens: 150000 + Math.floor(Math.random() * 50000),
          };
        })
      );

      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load tenant metrics');
    } finally {
      setLoading(false);
    }
  }, [tenantId, period]);

  useEffect(() => {
    if (isReady && tenantId) loadData();
  }, [isReady, tenantId, loadData]);

  // Auto-refresh
  useEffect(() => {
    if (!isReady || !tenantId) return;
    const interval = setInterval(loadData, AUTO_REFRESH_INTERVAL);
    return () => clearInterval(interval);
  }, [isReady, tenantId, loadData]);

  const maxToolCalls = Math.max(...topTools.map(t => t.calls), 1);

  if (!tenantId) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center">
          <p className="text-gray-500 dark:text-gray-400">
            Tenant information not available. Please ensure you are logged in with a tenant account.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">My Usage</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Usage metrics and analytics for <span className="font-medium">{tenantId}</span>
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Period Selector */}
          <div className="flex rounded-lg border border-gray-300 dark:border-neutral-600 overflow-hidden">
            {(['7d', '30d', 'mtd'] as const).map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={`px-3 py-1.5 text-sm font-medium transition-colors ${
                  period === p
                    ? 'bg-blue-600 text-white'
                    : 'bg-white dark:bg-neutral-800 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-neutral-700'
                }`}
              >
                {p === 'mtd' ? 'This Month' : p}
              </button>
            ))}
          </div>
          <button
            onClick={loadData}
            disabled={loading}
            className="flex items-center gap-2 border border-gray-300 dark:border-neutral-600 text-gray-700 dark:text-gray-300 px-3 py-2 rounded-lg text-sm hover:bg-gray-50 dark:hover:bg-neutral-700 disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg flex items-center justify-between">
          <span className="text-sm">{error}</span>
          <button onClick={() => setError(null)} className="text-red-500 hover:text-red-700">
            &times;
          </button>
        </div>
      )}

      {loading ? (
        <div className="space-y-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <CardSkeleton key={i} className="h-32" />
            ))}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <CardSkeleton className="h-64" />
            <CardSkeleton className="h-64" />
          </div>
        </div>
      ) : metrics ? (
        <>
          {/* Key Metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <MetricCard
              label="API Calls"
              value={formatNumber(metrics.totalCalls)}
              trend={metrics.callsTrend}
              trendLabel="vs last period"
              icon={Activity}
              colorClass="text-blue-600"
            />
            <MetricCard
              label="Tokens Consumed"
              value={formatNumber(metrics.tokensConsumed)}
              trend={metrics.tokensTrend}
              trendLabel="vs last period"
              icon={Zap}
              colorClass="text-purple-600"
            />
            <MetricCard
              label="SLA Compliance"
              value={metrics.slaCompliance.toFixed(2)}
              unit="%"
              icon={CheckCircle}
              colorClass={metrics.slaCompliance >= 99.9 ? 'text-green-600' : 'text-yellow-600'}
            />
            <MetricCard
              label="Estimated Cost"
              value={formatCurrency(metrics.estimatedCost)}
              trend={metrics.costTrend}
              trendLabel="vs last period"
              icon={DollarSign}
              colorClass="text-orange-600"
            />
          </div>

          {/* Secondary Metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
              <div className="flex items-center justify-between">
                <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Avg Latency</p>
                <Clock className="h-4 w-4 text-gray-400" />
              </div>
              <p className="text-xl font-bold text-gray-900 dark:text-white mt-2">
                {metrics.avgLatency} <span className="text-sm font-normal text-gray-500">ms</span>
              </p>
            </div>
            <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
              <div className="flex items-center justify-between">
                <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Error Rate</p>
                <BarChart2 className="h-4 w-4 text-gray-400" />
              </div>
              <p className={`text-xl font-bold mt-2 ${metrics.errorRate < 0.1 ? 'text-green-600' : 'text-red-600'}`}>
                {metrics.errorRate.toFixed(2)} <span className="text-sm font-normal">%</span>
              </p>
            </div>
          </div>

          {/* Two Column Layout */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Top Tools */}
            <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase">
                  Top 5 Tools
                </h2>
                <a
                  href="/ai-tools/usage"
                  className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
                >
                  View All
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
              <div className="divide-y divide-gray-100 dark:divide-neutral-700">
                {topTools.map((tool) => (
                  <ToolUsageItem key={tool.name} tool={tool} maxCalls={maxToolCalls} />
                ))}
              </div>
            </div>

            {/* Usage Trend */}
            <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase">
                  Usage Trend ({period === 'mtd' ? 'This Month' : period})
                </h2>
              </div>
              <UsageSparkline data={dailyUsage} />
              <div className="flex items-center justify-between mt-4 text-xs text-gray-500 dark:text-gray-400">
                <span>{dailyUsage[0]?.date}</span>
                <span>{dailyUsage[dailyUsage.length - 1]?.date}</span>
              </div>
              <div className="mt-4 pt-4 border-t border-gray-100 dark:border-neutral-700">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-500 dark:text-gray-400">Total calls this period</span>
                  <span className="text-sm font-semibold text-gray-900 dark:text-white">
                    {formatNumber(dailyUsage.reduce((sum, d) => sum + d.calls, 0))}
                  </span>
                </div>
                <div className="flex items-center justify-between mt-2">
                  <span className="text-sm text-gray-500 dark:text-gray-400">Total tokens</span>
                  <span className="text-sm font-semibold text-gray-900 dark:text-white">
                    {formatNumber(dailyUsage.reduce((sum, d) => sum + d.tokens, 0))}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* SLA Summary */}
          <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
            <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase mb-4">
              SLA Summary
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-gray-500 dark:text-gray-400">Availability</span>
                  <span className="text-sm font-semibold text-green-600">99.99%</span>
                </div>
                <div className="w-full bg-gray-200 dark:bg-neutral-700 rounded-full h-2">
                  <div className="bg-green-500 h-2 rounded-full" style={{ width: '99.99%' }} />
                </div>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">Target: 99.9%</p>
              </div>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-gray-500 dark:text-gray-400">Latency P95</span>
                  <span className="text-sm font-semibold text-green-600">245ms</span>
                </div>
                <div className="w-full bg-gray-200 dark:bg-neutral-700 rounded-full h-2">
                  <div className="bg-green-500 h-2 rounded-full" style={{ width: '51%' }} />
                </div>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">Target: &lt; 500ms</p>
              </div>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-gray-500 dark:text-gray-400">Error Budget</span>
                  <span className="text-sm font-semibold text-green-600">85% remaining</span>
                </div>
                <div className="w-full bg-gray-200 dark:bg-neutral-700 rounded-full h-2">
                  <div className="bg-green-500 h-2 rounded-full" style={{ width: '85%' }} />
                </div>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">Resets in 24 days</p>
              </div>
            </div>
          </div>
        </>
      ) : (
        <div className="text-center py-12">
          <p className="text-gray-500 dark:text-gray-400">No usage data available.</p>
        </div>
      )}
    </div>
  );
}

export default TenantDashboard;
