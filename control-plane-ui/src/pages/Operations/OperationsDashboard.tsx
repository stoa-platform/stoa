import { useState, useEffect, useCallback } from 'react';
import {
  RefreshCw,
  Activity,
  CheckCircle,
  XCircle,
  Clock,
  ExternalLink,
  Shield,
  BarChart3,
  Siren,
  Gauge,
  Layers,
  Award,
  Zap,
  AlertTriangle,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { apiService } from '../../services/api';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import type { PlatformStatusResponse } from '../../types';
import { config } from '../../config';
import { observabilityPath } from '../../utils/navigation';
import { MetricCard } from '../../components/metrics/MetricCard';

const AUTO_REFRESH_INTERVAL = 30_000; // 30 seconds

const dashboards = config.services.grafana.dashboards;

// PromQL queries — combines Gateway (stoa_http_requests_total, label: status)
// and Control Plane API (stoa_control_plane_http_requests_total, label: status_code)
export const QUERIES = {
  // SLO: availability = 1 - error_rate across both Gateway + API (1h window)
  availability:
    '(1 - (sum(increase(stoa_http_requests_total{status=~"5.."}[1h])) + sum(increase(stoa_control_plane_http_requests_total{status_code=~"5.."}[1h])) or vector(0)) / (sum(increase(stoa_http_requests_total[1h])) + sum(increase(stoa_control_plane_http_requests_total[1h])) or vector(1))) * 100',
  // SLO: error rate percentage (Gateway + API combined)
  errorRate:
    '((sum(increase(stoa_http_requests_total{status=~"5.."}[1h])) or vector(0)) + (sum(increase(stoa_control_plane_http_requests_total{status_code=~"5.."}[1h])) or vector(0))) / ((sum(increase(stoa_http_requests_total[1h])) or vector(1)) + (sum(increase(stoa_control_plane_http_requests_total[1h])) or vector(1))) * 100',
  // SLO: p95 latency in ms (Gateway — primary user-facing)
  latencyP95:
    'histogram_quantile(0.95, sum(rate(stoa_http_request_duration_seconds_bucket[1h])) by (le)) * 1000 or vector(0)',
  // SLO: error budget remaining (target 99.9%, 24h rolling — 30d needs longer retention)
  errorBudget:
    '(1 - ((sum(increase(stoa_http_requests_total{status=~"5.."}[24h])) or vector(0)) / (sum(increase(stoa_http_requests_total[24h])) or vector(1))) / 0.001) * 100',
  // Platform health: total requests/h (shows activity, not CUJ)
  platformRequests: 'sum(increase(stoa_control_plane_http_requests_total[1h])) or vector(0)',
  // API backend: requests in progress
  apiInProgress: 'sum(stoa_control_plane_http_requests_in_progress) or vector(0)',
  // MCP: active tool calls
  mcpToolCalls: 'sum(increase(stoa_mcp_tools_calls_total[1h])) or vector(0)',
};

interface RecentDeployment {
  id: string;
  name: string;
  version: string;
  status: 'synced' | 'syncing' | 'failed' | 'pending';
  timestamp: string;
}

function DeploymentItem({ deployment }: { deployment: RecentDeployment }) {
  const statusCfg = {
    synced: {
      icon: CheckCircle,
      color: 'text-green-600',
      bg: 'bg-green-100 dark:bg-green-900/30',
    },
    syncing: {
      icon: RefreshCw,
      color: 'text-blue-600',
      bg: 'bg-blue-100 dark:bg-blue-900/30',
    },
    failed: {
      icon: XCircle,
      color: 'text-red-600',
      bg: 'bg-red-100 dark:bg-red-900/30',
    },
    pending: {
      icon: Clock,
      color: 'text-yellow-600',
      bg: 'bg-yellow-100 dark:bg-yellow-900/30',
    },
  };

  const cfg = statusCfg[deployment.status];
  const Icon = cfg.icon;

  return (
    <div className="flex items-center gap-3 py-2">
      <div className={`p-1.5 rounded ${cfg.bg}`}>
        <Icon
          className={`h-4 w-4 ${cfg.color} ${deployment.status === 'syncing' ? 'animate-spin' : ''}`}
        />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-neutral-900 dark:text-white truncate">
          {deployment.name}{' '}
          <span className="text-neutral-500 dark:text-neutral-400">v{deployment.version}</span>
        </p>
        <p className="text-xs text-neutral-500 dark:text-neutral-400">{deployment.timestamp}</p>
      </div>
    </div>
  );
}

function QuickLinkButton({
  label,
  icon: Icon,
  href,
  onClick,
}: {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  href?: string;
  onClick?: () => void;
}) {
  const cls =
    'inline-flex items-center gap-2 px-4 py-2.5 rounded-lg border border-neutral-200 dark:border-neutral-700 hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors text-sm font-medium text-neutral-700 dark:text-neutral-300';

  if (href) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" className={cls}>
        <Icon className="h-4 w-4" />
        {label}
        <ExternalLink className="h-3 w-3 text-neutral-400" />
      </a>
    );
  }

  return (
    <button onClick={onClick} className={cls}>
      <Icon className="h-4 w-4" />
      {label}
    </button>
  );
}

// Format helpers
const fmtPercent = (v: number | null) => (v === null ? '--' : `${v.toFixed(2)}%`);
const fmtMs = (v: number | null) => (v === null ? '--' : v < 1 ? '<1 ms' : `${v.toFixed(0)} ms`);
const fmtBudget = (v: number | null) =>
  v === null ? '--' : v > 100 ? '100%' : v < 0 ? '0%' : `${v.toFixed(1)}%`;
const fmtCount = (v: number | null) => (v === null ? '--' : v.toFixed(0));

export function OperationsDashboard() {
  const navigate = useNavigate();
  const { isReady } = useAuth();
  const [platformStatus, setPlatformStatus] = useState<PlatformStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  const loadData = useCallback(async () => {
    try {
      const status = await apiService
        .get<PlatformStatusResponse>('/v1/platform/status')
        .then((r) => r.data)
        .catch(() => null);

      setPlatformStatus(status);
      setError(null);
      setLastRefresh(new Date());
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setError(axiosErr.response?.data?.detail || 'Failed to load operations data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isReady) loadData();
  }, [isReady, loadData]);

  useEffect(() => {
    if (!isReady) return;
    const interval = setInterval(loadData, AUTO_REFRESH_INTERVAL);
    return () => clearInterval(interval);
  }, [isReady, loadData]);

  // Recent deployments from ArgoCD events
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

  // ArgoCD component health
  const healthyComponents =
    platformStatus?.gitops?.components?.filter((c) => c.health_status === 'Healthy').length || 0;
  const totalComponents = platformStatus?.gitops?.components?.length || 1;
  const platformHealth = Math.round((healthyComponents / totalComponents) * 100);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">
            Operations Dashboard
          </h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            SLO metrics, ArgoCD status, and deployment overview
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/observability')}
            className="text-sm text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
          >
            Full metrics <ExternalLink className="h-3 w-3" />
          </button>
          <span className="text-xs text-neutral-400 dark:text-neutral-500">
            Last refresh: {lastRefresh.toLocaleTimeString('fr-FR')}
          </span>
          <button
            onClick={loadData}
            disabled={loading}
            className="flex items-center gap-2 border border-neutral-300 dark:border-neutral-600 text-neutral-700 dark:text-neutral-300 px-3 py-2 rounded-lg text-sm hover:bg-neutral-50 dark:hover:bg-neutral-700 disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 px-4 py-3 rounded-lg flex items-center justify-between">
          <span className="text-sm text-red-700 dark:text-red-400">{error}</span>
          <div className="flex items-center gap-2">
            <button
              onClick={loadData}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-red-700 dark:text-red-300 bg-white dark:bg-neutral-800 border border-red-300 dark:border-red-700 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Retry
            </button>
            <button
              onClick={() => setError(null)}
              className="text-red-500 hover:text-red-700 dark:hover:text-red-300 text-lg leading-none"
            >
              &times;
            </button>
          </div>
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
      ) : (
        <>
          {/* SLO Overview */}
          <section>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
                SLO Overview
              </h2>
              <button
                onClick={() => navigate(observabilityPath(dashboards.slo))}
                className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
              >
                View full SLO dashboard
                <ExternalLink className="h-3 w-3" />
              </button>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <MetricCard
                label="Availability"
                query={QUERIES.availability}
                format={fmtPercent}
                color="#10b981"
                icon={CheckCircle}
              />
              <MetricCard
                label="Error Rate"
                query={QUERIES.errorRate}
                format={fmtPercent}
                color="#ef4444"
                icon={AlertTriangle}
              />
              <MetricCard
                label="P95 Latency"
                query={QUERIES.latencyP95}
                format={fmtMs}
                color="#f59e0b"
                icon={Clock}
              />
              <MetricCard
                label="Error Budget"
                query={QUERIES.errorBudget}
                format={fmtBudget}
                color="#8b5cf6"
                icon={Gauge}
              />
            </div>
          </section>

          {/* Platform Health — ArgoCD status */}
          <section>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
                ArgoCD Components
              </h2>
              <button
                onClick={() => navigate(observabilityPath(dashboards.platformHealth))}
                className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
              >
                View Platform Health dashboard
                <ExternalLink className="h-3 w-3" />
              </button>
            </div>
            <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
              <div className="flex items-center gap-2 mb-4">
                <Shield className="h-4 w-4 text-neutral-500" />
                <h3 className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
                  ArgoCD Components — {platformHealth}% Healthy
                </h3>
              </div>
              {platformStatus?.gitops?.components ? (
                <div className="space-y-2">
                  {platformStatus.gitops.components.map((comp) => (
                    <div key={comp.name} className="flex items-center justify-between py-1.5">
                      <span className="text-sm text-neutral-900 dark:text-white">{comp.name}</span>
                      <div className="flex items-center gap-2">
                        <span
                          className={`text-xs px-2 py-0.5 rounded-full ${
                            comp.sync_status === 'Synced'
                              ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                              : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
                          }`}
                        >
                          {comp.sync_status}
                        </span>
                        <span
                          className={`text-xs px-2 py-0.5 rounded-full ${
                            comp.health_status === 'Healthy'
                              ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                              : comp.health_status === 'Degraded'
                                ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
                                : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                          }`}
                        >
                          {comp.health_status}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-neutral-500 dark:text-neutral-400 text-center py-4">
                  ArgoCD status unavailable
                </p>
              )}
            </div>
          </section>

          {/* Platform Activity — real Prometheus metrics */}
          <section>
            <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase mb-3">
              Platform Activity
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <MetricCard
                label="API Requests/h"
                query={QUERIES.platformRequests}
                format={fmtCount}
                color="#3b82f6"
                icon={BarChart3}
              />
              <MetricCard
                label="API In Progress"
                query={QUERIES.apiInProgress}
                format={fmtCount}
                color="#10b981"
                icon={Activity}
              />
              <MetricCard
                label="MCP Tool Calls/h"
                query={QUERIES.mcpToolCalls}
                format={fmtCount}
                color="#8b5cf6"
                icon={Zap}
              />
            </div>
          </section>

          {/* Recent Deployments */}
          <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
                Recent Deployments
              </h2>
            </div>
            {recentDeployments.length > 0 ? (
              <div className="divide-y divide-neutral-100 dark:divide-neutral-700">
                {recentDeployments.map((deployment) => (
                  <DeploymentItem key={deployment.id} deployment={deployment} />
                ))}
              </div>
            ) : (
              <p className="text-sm text-neutral-500 dark:text-neutral-400 text-center py-8">
                No recent deployments
              </p>
            )}
          </div>

          {/* Quick Links to Grafana Dashboards */}
          <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
            <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase mb-4">
              Observability Dashboards
            </h2>
            <div className="flex flex-wrap gap-3">
              <QuickLinkButton
                label="SLO Dashboard"
                icon={Gauge}
                onClick={() => navigate(observabilityPath(dashboards.slo))}
              />
              <QuickLinkButton
                label="Gateway RED Method"
                icon={Siren}
                onClick={() => navigate(observabilityPath(dashboards.gatewayRed))}
              />
              <QuickLinkButton
                label="Control Plane API"
                icon={Layers}
                onClick={() => navigate(observabilityPath(dashboards.controlPlaneApi))}
              />
              <QuickLinkButton
                label="Platform Overview"
                icon={Activity}
                onClick={() => navigate(observabilityPath(dashboards.platformOverview))}
              />
              <QuickLinkButton
                label="Arena Benchmark"
                icon={Award}
                onClick={() => navigate(observabilityPath(dashboards.gatewayArena))}
              />
              <QuickLinkButton
                label="Service Health"
                icon={Activity}
                onClick={() => navigate(observabilityPath(dashboards.serviceHealth))}
              />
              <QuickLinkButton
                label="Logs Explorer"
                icon={BarChart3}
                href={config.services.logs.url}
              />
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default OperationsDashboard;
