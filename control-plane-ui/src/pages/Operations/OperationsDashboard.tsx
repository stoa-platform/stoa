import { useState, useEffect, useCallback } from 'react';
import {
  RefreshCw,
  Activity,
  AlertTriangle,
  Clock,
  CheckCircle,
  XCircle,
  TrendingUp,
  TrendingDown,
  ExternalLink,
  Zap,
  Shield,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { apiService } from '../../services/api';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import type { AggregatedMetrics, PlatformStatusResponse } from '../../types';
import { config } from '../../config';
import { observabilityPath } from '../../utils/navigation';

const AUTO_REFRESH_INTERVAL = 15_000; // 15 seconds for operations

// Simulated metrics - in production, these would come from Prometheus
interface OperationsMetrics {
  errorRate: number; // percentage
  p95Latency: number; // ms
  requestsPerMinute: number;
  activeAlerts: number;
  uptime: number; // percentage
}

interface RecentDeployment {
  id: string;
  name: string;
  version: string;
  status: 'synced' | 'syncing' | 'failed' | 'pending';
  timestamp: string;
}

// Metric thresholds
const thresholds = {
  errorRate: { good: 0.1, warning: 1 },
  p95Latency: { good: 300, warning: 500 },
  uptime: { good: 99.9, warning: 99 },
};

function getStatusColor(
  value: number,
  threshold: { good: number; warning: number },
  inverse = false
) {
  if (inverse) {
    if (value >= threshold.good) return 'text-green-600';
    if (value >= threshold.warning) return 'text-yellow-600';
    return 'text-red-600';
  }
  if (value <= threshold.good) return 'text-green-600';
  if (value <= threshold.warning) return 'text-yellow-600';
  return 'text-red-600';
}

function StatCard({
  label,
  value,
  unit,
  icon: Icon,
  trend,
  colorClass,
  subtitle,
}: {
  label: string;
  value: string | number;
  unit?: string;
  icon: React.ElementType;
  trend?: 'up' | 'down' | 'stable';
  colorClass?: string;
  subtitle?: string;
}) {
  const TrendIcon = trend === 'up' ? TrendingUp : trend === 'down' ? TrendingDown : null;

  return (
    <div className="bg-white dark:bg-neutral-800 rounded-lg shadow px-4 py-4 flex items-start gap-4">
      <div
        className={`p-2 rounded-lg ${colorClass?.includes('green') ? 'bg-green-100 dark:bg-green-900/30' : colorClass?.includes('red') ? 'bg-red-100 dark:bg-red-900/30' : colorClass?.includes('yellow') ? 'bg-yellow-100 dark:bg-yellow-900/30' : 'bg-blue-100 dark:bg-blue-900/30'}`}
      >
        <Icon className={`h-5 w-5 ${colorClass || 'text-blue-600 dark:text-blue-400'}`} />
      </div>
      <div className="flex-1">
        <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">{label}</p>
        <div className="flex items-baseline gap-1">
          <p className={`text-2xl font-bold ${colorClass || 'text-gray-900 dark:text-white'}`}>
            {value}
          </p>
          {unit && <span className="text-sm text-gray-500 dark:text-gray-400">{unit}</span>}
          {TrendIcon && (
            <TrendIcon
              className={`h-4 w-4 ml-1 ${trend === 'up' ? 'text-red-500' : 'text-green-500'}`}
            />
          )}
        </div>
        {subtitle && <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{subtitle}</p>}
      </div>
    </div>
  );
}

function DeploymentItem({ deployment }: { deployment: RecentDeployment }) {
  const statusConfig = {
    synced: { icon: CheckCircle, color: 'text-green-600', bg: 'bg-green-100 dark:bg-green-900/30' },
    syncing: { icon: RefreshCw, color: 'text-blue-600', bg: 'bg-blue-100 dark:bg-blue-900/30' },
    failed: { icon: XCircle, color: 'text-red-600', bg: 'bg-red-100 dark:bg-red-900/30' },
    pending: { icon: Clock, color: 'text-yellow-600', bg: 'bg-yellow-100 dark:bg-yellow-900/30' },
  };

  const config = statusConfig[deployment.status];
  const Icon = config.icon;

  return (
    <div className="flex items-center gap-3 py-2">
      <div className={`p-1.5 rounded ${config.bg}`}>
        <Icon
          className={`h-4 w-4 ${config.color} ${deployment.status === 'syncing' ? 'animate-spin' : ''}`}
        />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
          {deployment.name}{' '}
          <span className="text-gray-500 dark:text-gray-400">v{deployment.version}</span>
        </p>
        <p className="text-xs text-gray-500 dark:text-gray-400">{deployment.timestamp}</p>
      </div>
    </div>
  );
}

export function OperationsDashboard() {
  const navigate = useNavigate();
  const { isReady } = useAuth();
  const [gatewayMetrics, setGatewayMetrics] = useState<AggregatedMetrics | null>(null);
  const [platformStatus, setPlatformStatus] = useState<PlatformStatusResponse | null>(null);
  const [operationsMetrics, setOperationsMetrics] = useState<OperationsMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  const loadData = useCallback(async () => {
    try {
      // Load gateway metrics and platform status in parallel
      const [metrics, status] = await Promise.all([
        apiService.getGatewayAggregatedMetrics().catch(() => null),
        apiService
          .get<PlatformStatusResponse>('/v1/platform/status')
          .then((r) => r.data)
          .catch(() => null),
      ]);

      setGatewayMetrics(metrics);
      setPlatformStatus(status);

      // Fetch real operations metrics from API (CAB-Observability)
      try {
        const opsMetrics = await apiService.getOperationsMetrics();
        setOperationsMetrics({
          errorRate: opsMetrics.error_rate,
          p95Latency: opsMetrics.p95_latency_ms,
          requestsPerMinute: opsMetrics.requests_per_minute,
          activeAlerts: opsMetrics.active_alerts,
          uptime: opsMetrics.uptime,
        });
      } catch (err) {
        console.warn('Operations metrics unavailable, using defaults');
        // Fallback to defaults if API unavailable
        setOperationsMetrics({
          errorRate: 0,
          p95Latency: 0,
          requestsPerMinute: 0,
          activeAlerts: 0,
          uptime: 100,
        });
      }

      setError(null);
      setLastRefresh(new Date());
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load operations data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isReady) loadData();
  }, [isReady, loadData]);

  // Auto-refresh
  useEffect(() => {
    if (!isReady) return;
    const interval = setInterval(loadData, AUTO_REFRESH_INTERVAL);
    return () => clearInterval(interval);
  }, [isReady, loadData]);

  // Generate recent deployments from platform events
  const recentDeployments: RecentDeployment[] =
    platformStatus?.events?.slice(0, 5).map((event, idx) => ({
      id: String(event.id || idx),
      name: event.component,
      version: event.revision?.slice(0, 7) || 'latest',
      status:
        event.status === 'Synced'
          ? 'synced'
          : event.status === 'Syncing'
            ? 'syncing'
            : event.status === 'Failed'
              ? 'failed'
              : 'pending',
      timestamp: new Date(event.timestamp).toLocaleString('fr-FR', {
        day: '2-digit',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
      }),
    })) || [];

  // Calculate platform health
  const healthyComponents =
    platformStatus?.gitops?.components?.filter((c) => c.health_status === 'Healthy').length || 0;
  const totalComponents = platformStatus?.gitops?.components?.length || 1;
  const platformHealth = Math.round((healthyComponents / totalComponents) * 100);

  // External links
  const grafanaUrl =
    platformStatus?.external_links?.grafana ||
    `${config.services.grafana.url}/d/stoa-incident-response`;
  const prometheusUrl =
    platformStatus?.external_links?.prometheus || config.services.prometheus.url;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Operations Dashboard</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Platform health, performance metrics, and incident overview
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-400 dark:text-gray-500">
            Last refresh: {lastRefresh.toLocaleTimeString('fr-FR')}
          </span>
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
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">
            {[1, 2, 3, 4, 5].map((i) => (
              <CardSkeleton key={i} className="h-24" />
            ))}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <CardSkeleton className="h-64" />
            <CardSkeleton className="h-64" />
          </div>
        </div>
      ) : (
        <>
          {/* Key Metrics */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
            <StatCard
              label="Platform Health"
              value={`${platformHealth}%`}
              icon={Shield}
              colorClass={
                platformHealth >= 100
                  ? 'text-green-600'
                  : platformHealth >= 80
                    ? 'text-yellow-600'
                    : 'text-red-600'
              }
              subtitle={`${healthyComponents}/${totalComponents} components`}
            />
            <StatCard
              label="Error Rate (5m)"
              value={operationsMetrics?.errorRate.toFixed(2) || '0.00'}
              unit="%"
              icon={AlertTriangle}
              colorClass={getStatusColor(operationsMetrics?.errorRate || 0, thresholds.errorRate)}
              trend={
                operationsMetrics?.errorRate && operationsMetrics.errorRate > 0.5 ? 'up' : 'stable'
              }
            />
            <StatCard
              label="P95 Latency"
              value={Math.round(operationsMetrics?.p95Latency || 0)}
              unit="ms"
              icon={Clock}
              colorClass={getStatusColor(operationsMetrics?.p95Latency || 0, thresholds.p95Latency)}
            />
            <StatCard
              label="Active Alerts"
              value={operationsMetrics?.activeAlerts || 0}
              icon={Zap}
              colorClass={operationsMetrics?.activeAlerts === 0 ? 'text-green-600' : 'text-red-600'}
            />
            <StatCard
              label="Requests/min"
              value={operationsMetrics?.requestsPerMinute || 0}
              icon={Activity}
              colorClass="text-blue-600"
            />
          </div>

          {/* Gateway Health Summary */}
          {gatewayMetrics && (
            <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase">
                  Gateway Health
                </h2>
                <a
                  href="/gateway-observability"
                  className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
                >
                  View Details
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                <div className="text-center">
                  <p className="text-2xl font-bold text-gray-900 dark:text-white">
                    {gatewayMetrics.health.total_gateways}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Total</p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold text-green-600">
                    {gatewayMetrics.health.online}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Online</p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold text-yellow-600">
                    {gatewayMetrics.health.degraded}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Degraded</p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold text-red-600">{gatewayMetrics.health.offline}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Offline</p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold text-gray-600 dark:text-gray-400">
                    {gatewayMetrics.health.maintenance}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Maintenance</p>
                </div>
              </div>
            </div>
          )}

          {/* Two Column Layout */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Recent Deployments */}
            <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase">
                  Recent Deployments
                </h2>
                <a
                  href="/gateway-deployments"
                  className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
                >
                  View All
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
              {recentDeployments.length > 0 ? (
                <div className="divide-y divide-gray-100 dark:divide-neutral-700">
                  {recentDeployments.map((deployment) => (
                    <DeploymentItem key={deployment.id} deployment={deployment} />
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-8">
                  No recent deployments
                </p>
              )}
            </div>

            {/* Active Incidents / Alerts */}
            <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase">
                  Active Incidents
                </h2>
                <button
                  onClick={() => navigate(observabilityPath(grafanaUrl))}
                  className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
                >
                  Open Grafana
                  <ExternalLink className="h-3 w-3" />
                </button>
              </div>
              {operationsMetrics?.activeAlerts === 0 ? (
                <div className="flex flex-col items-center justify-center py-8">
                  <div className="w-12 h-12 bg-green-100 dark:bg-green-900/30 rounded-full flex items-center justify-center mb-3">
                    <CheckCircle className="h-6 w-6 text-green-600" />
                  </div>
                  <p className="text-sm font-medium text-green-600">All Systems Operational</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    No active incidents at this time
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {/* Simulated alert items */}
                  <div className="flex items-start gap-3 p-3 bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-200 dark:border-red-800">
                    <AlertTriangle className="h-5 w-5 text-red-600 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="text-sm font-medium text-red-800 dark:text-red-300">
                        High Error Rate on MCP Gateway
                      </p>
                      <p className="text-xs text-red-600 dark:text-red-400 mt-0.5">
                        Error rate exceeded 1% threshold
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Quick Links to Observability Tools */}
          <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
            <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase mb-4">
              Observability Tools
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <button
                onClick={() => navigate(observabilityPath(grafanaUrl))}
                className="flex items-center gap-3 p-3 rounded-lg border border-gray-200 dark:border-neutral-700 hover:bg-gray-50 dark:hover:bg-neutral-700 transition-colors text-left"
              >
                <div className="w-10 h-10 bg-orange-100 dark:bg-orange-900/30 rounded-lg flex items-center justify-center">
                  <Activity className="h-5 w-5 text-orange-600" />
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">Grafana</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Dashboards</p>
                </div>
                <ExternalLink className="h-4 w-4 text-gray-400 ml-auto" />
              </button>
              <button
                onClick={() => navigate(observabilityPath(prometheusUrl))}
                className="flex items-center gap-3 p-3 rounded-lg border border-gray-200 dark:border-neutral-700 hover:bg-gray-50 dark:hover:bg-neutral-700 transition-colors text-left"
              >
                <div className="w-10 h-10 bg-red-100 dark:bg-red-900/30 rounded-lg flex items-center justify-center">
                  <TrendingUp className="h-5 w-5 text-red-600" />
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">Prometheus</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Metrics</p>
                </div>
                <ExternalLink className="h-4 w-4 text-gray-400 ml-auto" />
              </button>
              <a
                href="/monitoring"
                className="flex items-center gap-3 p-3 rounded-lg border border-gray-200 dark:border-neutral-700 hover:bg-gray-50 dark:hover:bg-neutral-700 transition-colors"
              >
                <div className="w-10 h-10 bg-blue-100 dark:bg-blue-900/30 rounded-lg flex items-center justify-center">
                  <Zap className="h-5 w-5 text-blue-600" />
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">
                    API Monitoring
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Tracing</p>
                </div>
              </a>
              <a
                href="/mcp/errors"
                className="flex items-center gap-3 p-3 rounded-lg border border-gray-200 dark:border-neutral-700 hover:bg-gray-50 dark:hover:bg-neutral-700 transition-colors"
              >
                <div className="w-10 h-10 bg-purple-100 dark:bg-purple-900/30 rounded-lg flex items-center justify-center">
                  <AlertTriangle className="h-5 w-5 text-purple-600" />
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">
                    Error Snapshots
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Debugging</p>
                </div>
              </a>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default OperationsDashboard;
