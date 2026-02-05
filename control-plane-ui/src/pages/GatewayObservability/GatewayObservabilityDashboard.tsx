import { useState, useEffect, useCallback } from 'react';
import { RefreshCw } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { apiService } from '../../services/api';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import type { AggregatedMetrics } from '../../types';

const AUTO_REFRESH_INTERVAL = 30_000;

const overallStatusConfig: Record<string, { label: string; color: string; bg: string }> = {
  healthy: { label: 'HEALTHY', color: 'text-green-700', bg: 'bg-green-100' },
  degraded: { label: 'DEGRADED', color: 'text-yellow-700', bg: 'bg-yellow-100' },
  critical: { label: 'CRITICAL', color: 'text-red-700', bg: 'bg-red-100' },
  unknown: { label: 'UNKNOWN', color: 'text-gray-700', bg: 'bg-gray-100' },
};

function StatCard({
  label,
  count,
  color,
}: {
  label: string;
  count: number;
  color: string;
}) {
  return (
    <div className="bg-white rounded-lg shadow px-4 py-3">
      <p className="text-xs font-medium text-gray-500 uppercase">{label}</p>
      <p className={`text-2xl font-bold ${color}`}>{count}</p>
    </div>
  );
}

function ProgressBar({ label, percentage }: { label: string; percentage: number }) {
  const barColor =
    percentage >= 80 ? 'bg-green-500' : percentage >= 50 ? 'bg-yellow-500' : 'bg-red-500';

  return (
    <div className="bg-white rounded-lg shadow px-4 py-3">
      <div className="flex items-center justify-between mb-1">
        <p className="text-sm font-medium text-gray-700">{label}</p>
        <p className="text-sm font-bold text-gray-900">{percentage}%</p>
      </div>
      <div className="w-full bg-gray-200 rounded-full h-2.5">
        <div
          className={`h-2.5 rounded-full ${barColor}`}
          style={{ width: `${Math.min(percentage, 100)}%` }}
        />
      </div>
    </div>
  );
}

export function GatewayObservabilityDashboard() {
  const { isReady } = useAuth();
  const [metrics, setMetrics] = useState<AggregatedMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const result = await apiService.getGatewayAggregatedMetrics();
      setMetrics(result);
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
          <h1 className="text-2xl font-bold text-gray-900">Gateway Observability</h1>
          <p className="text-sm text-gray-500 mt-1">
            Health and sync metrics across all gateway instances
          </p>
        </div>
        <button
          onClick={loadData}
          className="flex items-center gap-2 border border-gray-300 text-gray-700 px-3 py-2 rounded-lg text-sm hover:bg-gray-50"
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center justify-between">
          <span className="text-sm">{error}</span>
          <button onClick={() => setError(null)} className="text-red-500 hover:text-red-700">
            &times;
          </button>
        </div>
      )}

      {loading ? (
        <div className="space-y-6">
          <div className="h-8 w-32 bg-gray-200 rounded-full animate-pulse" />
          <div>
            <div className="h-4 w-32 bg-gray-200 rounded animate-pulse mb-3" />
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              {[1, 2, 3, 4, 5].map((i) => (
                <CardSkeleton key={i} className="h-20" />
              ))}
            </div>
          </div>
          <div>
            <div className="h-4 w-24 bg-gray-200 rounded animate-pulse mb-3" />
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
            <h2 className="text-sm font-semibold text-gray-700 uppercase mb-3">Gateway Health</h2>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <StatCard
                label="Total"
                count={metrics.health.total_gateways}
                color="text-gray-900"
              />
              <StatCard label="Online" count={metrics.health.online} color="text-green-600" />
              <StatCard label="Degraded" count={metrics.health.degraded} color="text-yellow-600" />
              <StatCard label="Offline" count={metrics.health.offline} color="text-red-600" />
              <StatCard
                label="Maintenance"
                count={metrics.health.maintenance}
                color="text-gray-600"
              />
            </div>
          </div>

          {/* Sync Status Cards */}
          <div>
            <h2 className="text-sm font-semibold text-gray-700 uppercase mb-3">
              Deployment Sync Status
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
              <StatCard
                label="Total"
                count={metrics.sync.total_deployments}
                color="text-gray-900"
              />
              <StatCard label="Synced" count={metrics.sync.synced} color="text-green-600" />
              <StatCard label="Pending" count={metrics.sync.pending} color="text-yellow-600" />
              <StatCard label="Syncing" count={metrics.sync.syncing} color="text-blue-600" />
              <StatCard label="Drifted" count={metrics.sync.drifted} color="text-orange-600" />
              <StatCard label="Error" count={metrics.sync.error} color="text-red-600" />
              <StatCard label="Deleting" count={metrics.sync.deleting ?? 0} color="text-gray-600" />
            </div>
          </div>

          {/* Progress Bars */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <ProgressBar label="Gateway Health" percentage={metrics.health.health_percentage} />
            <ProgressBar label="Sync Coverage" percentage={metrics.sync.sync_percentage} />
          </div>
        </>
      ) : (
        <div className="text-center py-12">
          <p className="text-gray-500">No metrics data available.</p>
        </div>
      )}
    </div>
  );
}
