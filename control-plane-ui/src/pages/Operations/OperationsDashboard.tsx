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
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { apiService } from '../../services/api';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import type { PlatformStatusResponse } from '../../types';
import { config } from '../../config';
import { observabilityPath } from '../../utils/navigation';
import { GrafanaPanel } from '../../components/GrafanaPanel';

const AUTO_REFRESH_INTERVAL = 30_000; // 30 seconds

const panels = config.services.grafana.panels;
const dashboards = config.services.grafana.dashboards;

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

export function OperationsDashboard() {
  const navigate = useNavigate();
  const { isReady, hasRole } = useAuth();
  const [platformStatus, setPlatformStatus] = useState<PlatformStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  const canViewTrafficSecurity = hasRole('cpi-admin') || hasRole('devops');

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
            Platform health, SLO metrics, and deployment overview
          </p>
        </div>
        <div className="flex items-center gap-3">
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
              <CardSkeleton key={i} className="h-52" />
            ))}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <CardSkeleton className="h-64" />
            <CardSkeleton className="h-64" />
          </div>
        </div>
      ) : (
        <>
          {/* SLO Overview — Grafana Panel Embeds (visible to all authenticated users) */}
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
              <GrafanaPanel
                dashboardUid={panels.sloAvailability.uid}
                panelId={panels.sloAvailability.panelId}
                title="Availability"
                height={180}
              />
              <GrafanaPanel
                dashboardUid={panels.sloErrorRate.uid}
                panelId={panels.sloErrorRate.panelId}
                title="Error Rate"
                height={180}
              />
              <GrafanaPanel
                dashboardUid={panels.sloLatencyP95.uid}
                panelId={panels.sloLatencyP95.panelId}
                title="P95 Latency"
                height={180}
              />
              <GrafanaPanel
                dashboardUid={panels.sloErrorBudget.uid}
                panelId={panels.sloErrorBudget.panelId}
                title="Error Budget"
                height={180}
              />
            </div>
          </section>

          {/* Platform Health — ArgoCD status (real data) + CUJ Health (Grafana) */}
          <section>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
                Platform Health
              </h2>
              <button
                onClick={() => navigate(observabilityPath(dashboards.platformHealth))}
                className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
              >
                View Platform Health dashboard
                <ExternalLink className="h-3 w-3" />
              </button>
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* ArgoCD Component Status */}
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
                        <span className="text-sm text-neutral-900 dark:text-white">
                          {comp.name}
                        </span>
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
              {/* CUJ Health — Grafana embed */}
              <GrafanaPanel
                dashboardUid={panels.platformCujPassing.uid}
                panelId={panels.platformCujPassing.panelId}
                title="CUJ Health"
                height={240}
              />
            </div>
          </section>

          {/* Traffic & Security — restricted to cpi-admin and devops */}
          {canViewTrafficSecurity && (
            <section>
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
                  Traffic & Security
                </h2>
                <button
                  onClick={() => navigate(observabilityPath(dashboards.incidentResponse))}
                  className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
                >
                  View Incident Response dashboard
                  <ExternalLink className="h-3 w-3" />
                </button>
              </div>
              <div className="space-y-4">
                <GrafanaPanel
                  dashboardUid={panels.errorRateTimeseries.uid}
                  panelId={panels.errorRateTimeseries.panelId}
                  title="Error Rate over Time"
                  height={250}
                />
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <GrafanaPanel
                    dashboardUid={panels.activeConnections.uid}
                    panelId={panels.activeConnections.panelId}
                    title="Active Connections"
                    height={180}
                  />
                  <GrafanaPanel
                    dashboardUid={panels.securityEvents.uid}
                    panelId={panels.securityEvents.panelId}
                    title="Security Events"
                    height={180}
                  />
                  <GrafanaPanel
                    dashboardUid={panels.fleetRps.uid}
                    panelId={panels.fleetRps.panelId}
                    title="Fleet RPS"
                    height={180}
                  />
                </div>
              </div>
            </section>
          )}

          {/* Recent Deployments — ArgoCD events (real data) */}
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
                label="Incident Response"
                icon={Siren}
                onClick={() => navigate(observabilityPath(dashboards.incidentResponse))}
              />
              <QuickLinkButton
                label="Gateway Fleet"
                icon={Layers}
                onClick={() => navigate(observabilityPath(dashboards.gatewayFleet))}
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
