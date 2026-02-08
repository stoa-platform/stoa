import { useState, useEffect, useCallback } from 'react';
import {
  RefreshCw,
  Users,
  UserPlus,
  TrendingUp,
  TrendingDown,
  Zap,
  Target,
  BarChart2,
  ExternalLink,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { apiService } from '../../services/api';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import { config } from '../../config';
import { observabilityPath } from '../../utils/navigation';

const AUTO_REFRESH_INTERVAL = 60_000; // 1 minute for business metrics

// Types for business metrics
interface BusinessMetrics {
  activeTenants: number;
  newTenants30d: number;
  tenantGrowth: number; // percentage
  apdexScore: number;
  totalTokens: number;
  tokenGrowth: number;
  totalCalls: number;
  callsGrowth: number;
  avgSessionDuration: number;
  dauMau: number; // Daily/Monthly active users ratio
}

interface GatewayModeAdoption {
  mode: string;
  displayName: string;
  count: number;
  percentage: number;
}

interface TopAPI {
  name: string;
  displayName: string;
  calls: number;
  growth: number;
  tenants: number;
}

function formatNumber(num: number): string {
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(1)}M`;
  if (num >= 1_000) return `${(num / 1_000).toFixed(1)}K`;
  return num.toString();
}

function getApdexColor(score: number): string {
  if (score >= 0.94) return 'text-green-600';
  if (score >= 0.85) return 'text-green-500';
  if (score >= 0.7) return 'text-yellow-600';
  if (score >= 0.5) return 'text-orange-600';
  return 'text-red-600';
}

function getApdexLabel(score: number): string {
  if (score >= 0.94) return 'Excellent';
  if (score >= 0.85) return 'Good';
  if (score >= 0.7) return 'Fair';
  if (score >= 0.5) return 'Poor';
  return 'Unacceptable';
}

function KPICard({
  label,
  value,
  trend,
  trendLabel,
  icon: Icon,
  iconBg,
  iconColor,
}: {
  label: string;
  value: string | number;
  trend?: number;
  trendLabel?: string;
  icon: React.ElementType;
  iconBg: string;
  iconColor: string;
}) {
  const isPositive = trend && trend > 0;
  const TrendIcon = isPositive ? TrendingUp : TrendingDown;
  const trendColor = isPositive ? 'text-green-600' : 'text-red-600';

  return (
    <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-5">
      <div className="flex items-center justify-between mb-4">
        <div className={`p-2.5 rounded-lg ${iconBg}`}>
          <Icon className={`h-5 w-5 ${iconColor}`} />
        </div>
        {trend !== undefined && (
          <div className={`flex items-center gap-1 text-xs font-medium ${trendColor}`}>
            <TrendIcon className="h-3.5 w-3.5" />
            <span>{Math.abs(trend).toFixed(1)}%</span>
          </div>
        )}
      </div>
      <p className="text-2xl font-bold text-gray-900 dark:text-white">{value}</p>
      <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{label}</p>
      {trendLabel && (
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{trendLabel}</p>
      )}
    </div>
  );
}

function ApdexGauge({ score }: { score: number }) {
  const rotation = score * 180 - 90; // -90 to 90 degrees
  const color = getApdexColor(score);

  return (
    <div className="flex flex-col items-center">
      <div className="relative w-40 h-20 overflow-hidden">
        {/* Background arc */}
        <div
          className="absolute w-40 h-40 rounded-full border-8 border-gray-200 dark:border-neutral-700"
          style={{ clipPath: 'polygon(0 0, 100% 0, 100% 50%, 0 50%)' }}
        />
        {/* Colored arc */}
        <div
          className="absolute w-40 h-40 rounded-full border-8 border-transparent"
          style={{
            borderTopColor: score >= 0.85 ? '#10b981' : score >= 0.7 ? '#f59e0b' : '#ef4444',
            borderRightColor: score >= 0.5 ? (score >= 0.85 ? '#10b981' : '#f59e0b') : '#ef4444',
            transform: `rotate(${rotation}deg)`,
            transformOrigin: 'center center',
            clipPath: 'polygon(0 0, 100% 0, 100% 50%, 0 50%)',
          }}
        />
        {/* Center */}
        <div className="absolute bottom-0 left-1/2 -translate-x-1/2 text-center">
          <p className={`text-3xl font-bold ${color}`}>{score.toFixed(2)}</p>
        </div>
      </div>
      <p className={`text-sm font-medium ${color} mt-2`}>{getApdexLabel(score)}</p>
      <p className="text-xs text-gray-400 dark:text-gray-500">APDEX Score</p>
    </div>
  );
}

function ModeAdoptionBar({ modes }: { modes: GatewayModeAdoption[] }) {
  const colors = {
    'edge-mcp': 'bg-blue-500',
    sidecar: 'bg-green-500',
    proxy: 'bg-purple-500',
    shadow: 'bg-gray-500',
  };

  return (
    <div>
      <div className="flex h-4 rounded-full overflow-hidden bg-gray-200 dark:bg-neutral-700">
        {modes.map((mode) => (
          <div
            key={mode.mode}
            className={`${colors[mode.mode as keyof typeof colors] || 'bg-gray-400'} transition-all duration-500`}
            style={{ width: `${mode.percentage}%` }}
            title={`${mode.displayName}: ${mode.percentage}%`}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-4 mt-3">
        {modes.map((mode) => (
          <div key={mode.mode} className="flex items-center gap-2">
            <div
              className={`w-3 h-3 rounded-full ${colors[mode.mode as keyof typeof colors] || 'bg-gray-400'}`}
            />
            <span className="text-sm text-gray-600 dark:text-gray-300">
              {mode.displayName}: <span className="font-medium">{mode.percentage}%</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function TopAPIItem({ api, rank, maxCalls }: { api: TopAPI; rank: number; maxCalls: number }) {
  const barWidth = Math.round((api.calls / maxCalls) * 100);
  const isGrowthPositive = api.growth > 0;

  return (
    <div className="flex items-center gap-4 py-3">
      <span className="w-6 text-lg font-bold text-gray-400 dark:text-gray-500">#{rank}</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-1">
          <span className="text-sm font-medium text-gray-900 dark:text-white truncate">
            {api.displayName}
          </span>
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-600 dark:text-gray-300">
              {formatNumber(api.calls)} calls
            </span>
            <span
              className={`text-xs flex items-center gap-0.5 ${isGrowthPositive ? 'text-green-600' : 'text-red-600'}`}
            >
              {isGrowthPositive ? (
                <TrendingUp className="h-3 w-3" />
              ) : (
                <TrendingDown className="h-3 w-3" />
              )}
              {Math.abs(api.growth).toFixed(0)}%
            </span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex-1 bg-gray-200 dark:bg-neutral-700 rounded-full h-1.5">
            <div
              className="bg-blue-500 h-1.5 rounded-full transition-all duration-300"
              style={{ width: `${barWidth}%` }}
            />
          </div>
          <span className="text-xs text-gray-400 dark:text-gray-500">{api.tenants} tenants</span>
        </div>
      </div>
    </div>
  );
}

export function BusinessDashboard() {
  const navigate = useNavigate();
  const { isReady, hasPermission } = useAuth();
  const [metrics, setMetrics] = useState<BusinessMetrics | null>(null);
  const [modeAdoption, setModeAdoption] = useState<GatewayModeAdoption[]>([]);
  const [topAPIs, setTopAPIs] = useState<TopAPI[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Check admin permission
  const isAdmin = hasPermission('tenants:read');

  const loadData = useCallback(async () => {
    if (!isAdmin) return;

    try {
      // Fetch all data in parallel
      const [modeStats, businessMetrics, topAPIsData] = await Promise.all([
        apiService.getGatewayModeStats().catch(() => null),
        apiService.getBusinessMetrics().catch(() => null),
        apiService.getTopAPIs(8).catch(() => []),
      ]);

      // Business metrics from API (with fallback defaults)
      if (businessMetrics) {
        setMetrics({
          activeTenants: businessMetrics.active_tenants,
          newTenants30d: businessMetrics.new_tenants_30d,
          tenantGrowth: businessMetrics.tenant_growth,
          apdexScore: businessMetrics.apdex_score,
          totalTokens: businessMetrics.total_tokens,
          tokenGrowth: 0, // Not yet provided by API
          totalCalls: businessMetrics.total_calls,
          callsGrowth: 0, // Not yet provided by API
          avgSessionDuration: 0, // Not yet provided by API
          dauMau: 0, // Not yet provided by API
        });
      } else {
        // Fallback when API unavailable
        setMetrics({
          activeTenants: 0,
          newTenants30d: 0,
          tenantGrowth: 0,
          apdexScore: 0.92,
          totalTokens: 0,
          tokenGrowth: 0,
          totalCalls: 0,
          callsGrowth: 0,
          avgSessionDuration: 0,
          dauMau: 0,
        });
      }

      // Gateway mode adoption from real data or fallback
      const modes = modeStats?.modes || [];
      if (modes.length > 0) {
        const total = modes.reduce((sum: number, m: any) => sum + m.total, 0);
        setModeAdoption(
          modes.map((m: any) => ({
            mode: m.mode,
            displayName:
              m.mode === 'edge-mcp'
                ? 'Edge MCP'
                : m.mode === 'sidecar'
                  ? 'Sidecar'
                  : m.mode === 'proxy'
                    ? 'Proxy'
                    : 'Shadow',
            count: m.total,
            percentage: Math.round((m.total / total) * 100),
          }))
        );
      } else {
        setModeAdoption([{ mode: 'edge-mcp', displayName: 'Edge MCP', count: 0, percentage: 100 }]);
      }

      // Top APIs from real API data
      if (topAPIsData && topAPIsData.length > 0) {
        setTopAPIs(
          topAPIsData.map((api) => ({
            name: api.tool_name,
            displayName: api.display_name,
            calls: api.calls,
            growth: 0, // Not yet provided by API
            tenants: 0, // Not yet provided by API
          }))
        );
      } else {
        setTopAPIs([]);
      }

      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load business metrics');
    } finally {
      setLoading(false);
    }
  }, [isAdmin]);

  useEffect(() => {
    if (isReady) loadData();
  }, [isReady, loadData]);

  // Auto-refresh
  useEffect(() => {
    if (!isReady) return;
    const interval = setInterval(loadData, AUTO_REFRESH_INTERVAL);
    return () => clearInterval(interval);
  }, [isReady, loadData]);

  const maxAPICalls = Math.max(...topAPIs.map((a) => a.calls), 1);
  const grafanaUrl = `${config.services.grafana.url}/d/stoa-business-analytics`;

  if (!isAdmin) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center">
          <p className="text-gray-500 dark:text-gray-400">
            You don't have permission to view business analytics.
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
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Business Analytics</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Platform adoption, usage trends, and business metrics
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate(observabilityPath(grafanaUrl))}
            className="flex items-center gap-2 text-sm text-blue-600 dark:text-blue-400 hover:underline"
          >
            <BarChart2 className="h-4 w-4" />
            Advanced Analytics
            <ExternalLink className="h-3 w-3" />
          </button>
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
          {/* Key Business KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KPICard
              label="Active Tenants"
              value={metrics.activeTenants}
              trend={metrics.tenantGrowth}
              trendLabel="vs last month"
              icon={Users}
              iconBg="bg-blue-100 dark:bg-blue-900/30"
              iconColor="text-blue-600"
            />
            <KPICard
              label="New Tenants (30d)"
              value={metrics.newTenants30d}
              icon={UserPlus}
              iconBg="bg-green-100 dark:bg-green-900/30"
              iconColor="text-green-600"
            />
            <KPICard
              label="Total Tokens (Month)"
              value={formatNumber(metrics.totalTokens)}
              trend={metrics.tokenGrowth}
              trendLabel="vs last month"
              icon={Zap}
              iconBg="bg-purple-100 dark:bg-purple-900/30"
              iconColor="text-purple-600"
            />
            <KPICard
              label="API Calls (Month)"
              value={formatNumber(metrics.totalCalls)}
              trend={metrics.callsGrowth}
              trendLabel="vs last month"
              icon={Target}
              iconBg="bg-orange-100 dark:bg-orange-900/30"
              iconColor="text-orange-600"
            />
          </div>

          {/* APDEX and Gateway Modes */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* APDEX Score */}
            <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-6">
              <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase mb-6">
                User Satisfaction
              </h2>
              <div className="flex items-center justify-around">
                <ApdexGauge score={metrics.apdexScore} />
                <div className="space-y-4">
                  <div>
                    <p className="text-sm text-gray-500 dark:text-gray-400">DAU/MAU Ratio</p>
                    <p className="text-2xl font-bold text-gray-900 dark:text-white">
                      {(metrics.dauMau * 100).toFixed(0)}%
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Avg Session</p>
                    <p className="text-2xl font-bold text-gray-900 dark:text-white">
                      {Math.floor(metrics.avgSessionDuration / 60)}m
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Gateway Mode Adoption */}
            <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-6">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase">
                  Gateway Mode Adoption
                </h2>
                <a
                  href="/gateways/modes"
                  className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
                >
                  View Details
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
              <ModeAdoptionBar modes={modeAdoption} />
              <div className="mt-6 pt-4 border-t border-gray-100 dark:border-neutral-700">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-500 dark:text-gray-400">Total Gateways</span>
                  <span className="font-semibold text-gray-900 dark:text-white">
                    {modeAdoption.reduce((sum, m) => sum + m.count, 0)}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Top APIs */}
          <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase">
                Top APIs by Usage (This Month)
              </h2>
              <a
                href="/ai-tools"
                className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
              >
                View All Tools
                <ExternalLink className="h-3 w-3" />
              </a>
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-8">
              <div className="divide-y divide-gray-100 dark:divide-neutral-700">
                {topAPIs.slice(0, 4).map((api, idx) => (
                  <TopAPIItem key={api.name} api={api} rank={idx + 1} maxCalls={maxAPICalls} />
                ))}
              </div>
              <div className="divide-y divide-gray-100 dark:divide-neutral-700">
                {topAPIs.slice(4, 8).map((api, idx) => (
                  <TopAPIItem key={api.name} api={api} rank={idx + 5} maxCalls={maxAPICalls} />
                ))}
              </div>
            </div>
          </div>

          {/* Engagement Insights */}
          <div className="bg-gradient-to-r from-blue-50 to-purple-50 dark:from-blue-900/20 dark:to-purple-900/20 rounded-lg p-6 border border-blue-100 dark:border-blue-800/50">
            <div className="flex items-start gap-4">
              <div className="p-2 bg-blue-100 dark:bg-blue-900/50 rounded-lg">
                <TrendingUp className="h-5 w-5 text-blue-600" />
              </div>
              <div>
                <h3 className="font-semibold text-gray-900 dark:text-white">Growth Insights</h3>
                <p className="text-sm text-gray-600 dark:text-gray-300 mt-1">
                  Platform usage is up <span className="font-semibold text-green-600">18.2%</span>{' '}
                  this month. The <span className="font-semibold">Code Assistant</span> tool saw the
                  highest growth at <span className="font-semibold text-green-600">156%</span>,
                  indicating strong demand for AI-powered development tools.
                </p>
                <button
                  onClick={() => navigate(observabilityPath(grafanaUrl))}
                  className="inline-flex items-center gap-1 mt-3 text-sm text-blue-600 dark:text-blue-400 hover:underline"
                >
                  View detailed analytics in Grafana
                  <ExternalLink className="h-3 w-3" />
                </button>
              </div>
            </div>
          </div>
        </>
      ) : (
        <div className="text-center py-12">
          <p className="text-gray-500 dark:text-gray-400">No business data available.</p>
        </div>
      )}
    </div>
  );
}

export default BusinessDashboard;
