import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, ExternalLink, Gauge, BarChart3 } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { apiService } from '../../services/api';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import { EmptyState } from '@stoa/shared/components/EmptyState';
import { useNavigate } from 'react-router-dom';
import { config } from '../../config';
import { observabilityPath } from '../../utils/navigation';
import type { AggregatedMetrics } from '../../types';

const AUTO_REFRESH_INTERVAL = 30_000;

const overallStatusConfig: Record<string, { label: string; color: string; bg: string }> = {
  healthy: {
    label: 'HEALTHY',
    color: 'text-green-700 dark:text-green-400',
    bg: 'bg-green-100 dark:bg-green-900/30',
  },
  degraded: {
    label: 'DEGRADED',
    color: 'text-yellow-700 dark:text-yellow-400',
    bg: 'bg-yellow-100 dark:bg-yellow-900/30',
  },
  critical: {
    label: 'CRITICAL',
    color: 'text-red-700 dark:text-red-400',
    bg: 'bg-red-100 dark:bg-red-900/30',
  },
  unknown: {
    label: 'UNKNOWN',
    color: 'text-neutral-700 dark:text-neutral-400',
    bg: 'bg-neutral-100 dark:bg-neutral-700',
  },
};

function StatCard({ label, count, color }: { label: string; count: number; color: string }) {
  return (
    <div className="bg-white dark:bg-neutral-800 rounded-lg shadow px-4 py-3">
      <p className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
        {label}
      </p>
      <p className={`text-2xl font-bold ${color}`}>{count}</p>
    </div>
  );
}

function ProgressBar({ label, percentage }: { label: string; percentage: number }) {
  const barColor =
    percentage >= 80 ? 'bg-green-500' : percentage >= 50 ? 'bg-yellow-500' : 'bg-red-500';

  return (
    <div className="bg-white dark:bg-neutral-800 rounded-lg shadow px-4 py-3">
      <div className="flex items-center justify-between mb-1">
        <p className="text-sm font-medium text-neutral-700 dark:text-neutral-300">{label}</p>
        <p className="text-sm font-bold text-neutral-900 dark:text-white">{percentage}%</p>
      </div>
      <div className="w-full bg-neutral-200 dark:bg-neutral-700 rounded-full h-2.5">
        <div
          className={`h-2.5 rounded-full ${barColor}`}
          style={{ width: `${Math.min(percentage, 100)}%` }}
        />
      </div>
    </div>
  );
}

function APDEXGauge({ score }: { score: number }) {
  // APDEX color thresholds: Excellent (>0.94), Good (0.85-0.94), Fair (0.70-0.84), Poor (<0.70)
  const getColor = (value: number) => {
    if (value >= 0.94)
      return { bg: 'bg-green-500', text: 'text-green-700 dark:text-green-400', label: 'Excellent' };
    if (value >= 0.85)
      return { bg: 'bg-blue-500', text: 'text-blue-700 dark:text-blue-400', label: 'Good' };
    if (value >= 0.7)
      return { bg: 'bg-yellow-500', text: 'text-yellow-700 dark:text-yellow-400', label: 'Fair' };
    return { bg: 'bg-red-500', text: 'text-red-700 dark:text-red-400', label: 'Poor' };
  };

  const colorConfig = getColor(score);
  const percentage = Math.min(score * 100, 100);

  return (
    <div className="bg-white dark:bg-neutral-800 rounded-lg shadow px-4 py-4">
      <div className="flex items-center gap-2 mb-2">
        <Gauge className="h-4 w-4 text-neutral-500 dark:text-neutral-400" />
        <p className="text-sm font-medium text-neutral-700 dark:text-neutral-300">APDEX Score</p>
      </div>
      <div className="flex items-end gap-3">
        <span className={`text-3xl font-bold ${colorConfig.text}`}>{score.toFixed(2)}</span>
        <span
          className={`text-xs font-medium px-2 py-0.5 rounded-full ${colorConfig.bg} text-white`}
        >
          {colorConfig.label}
        </span>
      </div>
      <div className="w-full bg-neutral-200 dark:bg-neutral-700 rounded-full h-2 mt-3">
        <div
          className={`h-2 rounded-full ${colorConfig.bg} transition-all duration-500`}
          style={{ width: `${percentage}%` }}
        />
      </div>
      <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-2">
        Target: 0.94 (Excellent) | T=500ms
      </p>
    </div>
  );
}

export function GatewayObservabilityDashboard() {
  const navigate = useNavigate();
  const { isReady } = useAuth();
  const [metrics, setMetrics] = useState<AggregatedMetrics | null>(null);
  const [apdexScore, setApdexScore] = useState(0.92); // Default fallback
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      // Fetch gateway metrics and APDEX in parallel
      const [gatewayMetrics, businessMetrics] = await Promise.all([
        apiService.getGatewayAggregatedMetrics(),
        apiService.getBusinessMetrics().catch(() => null),
      ]);

      setMetrics(gatewayMetrics);

      // Update APDEX score from business metrics if available
      if (businessMetrics?.apdex_score) {
        setApdexScore(businessMetrics.apdex_score);
      }

      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load metrics');
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

  const statusCfg = overallStatusConfig[metrics?.overall_status || 'unknown'];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">
            Gateway Observability
          </h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            Health and sync metrics across all gateway instances
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() =>
              navigate(observabilityPath(`${config.services.grafana.url}/d/stoa-gateway-overview`))
            }
            className="flex items-center gap-2 bg-orange-500 text-white px-3 py-2 rounded-lg text-sm hover:bg-orange-600 transition-colors"
          >
            <ExternalLink className="h-4 w-4" />
            Open in Grafana
          </button>
          <button
            onClick={loadData}
            className="flex items-center gap-2 border border-neutral-300 dark:border-neutral-600 text-neutral-700 dark:text-neutral-300 px-3 py-2 rounded-lg text-sm hover:bg-neutral-50 dark:hover:bg-neutral-700"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg flex items-center justify-between">
          <span className="text-sm">{error}</span>
          <button
            onClick={() => setError(null)}
            className="text-red-500 hover:text-red-700 dark:hover:text-red-300"
          >
            &times;
          </button>
        </div>
      )}

      {loading ? (
        <div className="space-y-6">
          <div className="h-8 w-32 bg-neutral-200 dark:bg-neutral-700 rounded-full animate-pulse" />
          <div>
            <div className="h-4 w-32 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse mb-3" />
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              {[1, 2, 3, 4, 5].map((i) => (
                <CardSkeleton key={i} className="h-20" />
              ))}
            </div>
          </div>
          <div>
            <div className="h-4 w-24 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse mb-3" />
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              {[1, 2, 3].map((i) => (
                <CardSkeleton key={i} className="h-16" />
              ))}
            </div>
          </div>
        </div>
      ) : metrics ? (
        <>
          {/* Overall Status Badge */}
          <div className="flex items-center gap-3">
            <span
              className={`inline-flex items-center rounded-full px-4 py-1.5 text-sm font-bold ${statusCfg.color} ${statusCfg.bg}`}
            >
              {statusCfg.label}
            </span>
          </div>

          {/* Gateway Health Cards */}
          <div>
            <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase mb-3">
              Gateway Health
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <StatCard
                label="Total"
                count={metrics.health.total_gateways}
                color="text-neutral-900 dark:text-white"
              />
              <StatCard label="Online" count={metrics.health.online} color="text-green-600" />
              <StatCard label="Degraded" count={metrics.health.degraded} color="text-yellow-600" />
              <StatCard label="Offline" count={metrics.health.offline} color="text-red-600" />
              <StatCard
                label="Maintenance"
                count={metrics.health.maintenance}
                color="text-neutral-600 dark:text-neutral-400"
              />
            </div>
          </div>

          {/* Sync Status Cards */}
          <div>
            <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase mb-3">
              Deployment Sync Status
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
              <StatCard
                label="Total"
                count={metrics.sync.total_deployments}
                color="text-neutral-900 dark:text-white"
              />
              <StatCard label="Synced" count={metrics.sync.synced} color="text-green-600" />
              <StatCard label="Pending" count={metrics.sync.pending} color="text-yellow-600" />
              <StatCard label="Syncing" count={metrics.sync.syncing} color="text-blue-600" />
              <StatCard label="Drifted" count={metrics.sync.drifted} color="text-orange-600" />
              <StatCard label="Error" count={metrics.sync.error} color="text-red-600" />
              <StatCard
                label="Deleting"
                count={metrics.sync.deleting ?? 0}
                color="text-neutral-600 dark:text-neutral-400"
              />
            </div>
          </div>

          {/* Progress Bars and APDEX */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <ProgressBar label="Gateway Health" percentage={metrics.health.health_percentage} />
            <ProgressBar label="Sync Coverage" percentage={metrics.sync.sync_percentage} />
            <APDEXGauge score={apdexScore} />
          </div>
        </>
      ) : (
        <EmptyState
          title="No metrics data available"
          description="Gateway metrics will appear here once gateways are registered and reporting."
          illustration={<BarChart3 className="h-12 w-12" />}
        />
      )}
    </div>
  );
}
