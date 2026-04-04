import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { apiService } from '../../services/api';
import { SubNav } from '../../components/SubNav';
import { gatewayTabs } from '../../components/subNavGroups';
import { RefreshCw, Shield, Lock, Key, Users, AlertTriangle } from 'lucide-react';

interface GatewayInstance {
  id: string;
  name: string;
  display_name?: string;
  gateway_type: string;
  mode?: string;
  status: string;
  capabilities?: string[];
}

interface SecurityMetrics {
  gateway_health: {
    total: number;
    online: number;
    offline: number;
    degraded: number;
  };
  auth_summary: {
    total_gateways: number;
    oauth_enabled: number;
    mtls_capable: number;
  };
}

export function GatewaySecurityDashboard() {
  const { isReady } = useAuth();
  const [metrics, setMetrics] = useState<SecurityMetrics | null>(null);
  const [gateways, setGateways] = useState<GatewayInstance[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [_healthSummary, gwData] = await Promise.all([
        apiService.getGatewayHealthSummary().catch(() => null),
        apiService.getGatewayInstances().catch(() => ({ items: [] })),
      ]);
      const items: GatewayInstance[] = gwData?.items || gwData || [];
      setGateways(items);

      const online = items.filter((g) => g.status === 'online').length;
      const offline = items.filter((g) => g.status === 'offline').length;
      const degraded = items.filter((g) => g.status === 'degraded').length;

      setMetrics({
        gateway_health: {
          total: items.length,
          online,
          offline,
          degraded,
        },
        auth_summary: {
          total_gateways: items.length,
          oauth_enabled: items.filter(
            (g) => g.capabilities?.includes('oidc') || g.gateway_type === 'stoa'
          ).length,
          mtls_capable: items.filter(
            (g) => g.capabilities?.includes('mtls') || g.gateway_type === 'stoa'
          ).length,
        },
      });
      setError(null);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load security metrics';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isReady) loadData();
  }, [isReady, loadData]);

  useEffect(() => {
    if (!isReady) return;
    const interval = setInterval(loadData, 30_000);
    return () => clearInterval(interval);
  }, [isReady, loadData]);

  return (
    <div className="space-y-6">
      <SubNav tabs={gatewayTabs} />

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Gateway Security</h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            Authentication, authorization, and transport security posture
          </p>
        </div>
        <button
          onClick={loadData}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-neutral-200 dark:border-neutral-700 hover:bg-neutral-50 dark:hover:bg-neutral-800"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 dark:bg-red-900/20 p-4 text-red-700 dark:text-red-400">
          <AlertTriangle className="inline h-4 w-4 mr-2" />
          {error}
        </div>
      )}

      {/* Security Posture Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <SecurityCard
          icon={Shield}
          title="Gateway Health"
          value={`${metrics?.gateway_health.online || 0}/${metrics?.gateway_health.total || 0}`}
          subtitle="Online gateways"
          status={
            metrics?.gateway_health.offline
              ? 'warning'
              : metrics?.gateway_health.online
                ? 'healthy'
                : 'neutral'
          }
          loading={loading}
        />
        <SecurityCard
          icon={Lock}
          title="OAuth/OIDC"
          value={`${metrics?.auth_summary.oauth_enabled || 0}`}
          subtitle="OAuth-enabled gateways"
          status="healthy"
          loading={loading}
        />
        <SecurityCard
          icon={Key}
          title="mTLS Capable"
          value={`${metrics?.auth_summary.mtls_capable || 0}`}
          subtitle="mTLS-ready gateways"
          status="healthy"
          loading={loading}
        />
        <SecurityCard
          icon={Users}
          title="RBAC"
          value="4 roles"
          subtitle="cpi-admin, tenant-admin, devops, viewer"
          status="healthy"
          loading={loading}
        />
      </div>

      {/* Security Features Table */}
      <div className="bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700">
        <div className="px-4 py-3 border-b border-neutral-200 dark:border-neutral-700">
          <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">
            Security Features per Gateway
          </h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-neutral-50 dark:bg-neutral-800">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-neutral-500">Gateway</th>
                <th className="px-4 py-3 text-left font-medium text-neutral-500">Type</th>
                <th className="px-4 py-3 text-left font-medium text-neutral-500">Mode</th>
                <th className="px-4 py-3 text-center font-medium text-neutral-500">OAuth</th>
                <th className="px-4 py-3 text-center font-medium text-neutral-500">mTLS</th>
                <th className="px-4 py-3 text-center font-medium text-neutral-500">DPoP</th>
                <th className="px-4 py-3 text-center font-medium text-neutral-500">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
              {gateways.map((gw) => (
                <tr key={gw.id} className="hover:bg-neutral-50 dark:hover:bg-neutral-800/50">
                  <td className="px-4 py-3 font-medium text-neutral-900 dark:text-white">
                    {gw.display_name || gw.name}
                  </td>
                  <td className="px-4 py-3 text-neutral-500">{gw.gateway_type}</td>
                  <td className="px-4 py-3 text-neutral-500">{gw.mode || '—'}</td>
                  <td className="px-4 py-3 text-center">
                    <FeatureBadge
                      enabled={gw.capabilities?.includes('oidc') || gw.gateway_type === 'stoa'}
                    />
                  </td>
                  <td className="px-4 py-3 text-center">
                    <FeatureBadge enabled={gw.gateway_type === 'stoa'} />
                  </td>
                  <td className="px-4 py-3 text-center">
                    <FeatureBadge enabled={gw.gateway_type === 'stoa'} />
                  </td>
                  <td className="px-4 py-3 text-center">
                    <StatusBadge status={gw.status} />
                  </td>
                </tr>
              ))}
              {gateways.length === 0 && !loading && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-neutral-400">
                    No gateways registered
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function SecurityCard({
  icon: Icon,
  title,
  value,
  subtitle,
  status,
  loading,
}: {
  icon: React.FC<{ className?: string }>;
  title: string;
  value: string;
  subtitle: string;
  status: 'healthy' | 'warning' | 'critical' | 'neutral';
  loading: boolean;
}) {
  const statusColors = {
    healthy: 'text-green-600 bg-green-50 dark:bg-green-900/20',
    warning: 'text-amber-600 bg-amber-50 dark:bg-amber-900/20',
    critical: 'text-red-600 bg-red-50 dark:bg-red-900/20',
    neutral: 'text-neutral-600 bg-neutral-50 dark:bg-neutral-800',
  };

  if (loading) {
    return (
      <div className="bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 animate-pulse">
        <div className="h-4 w-24 bg-neutral-200 dark:bg-neutral-700 rounded mb-3" />
        <div className="h-8 w-16 bg-neutral-200 dark:bg-neutral-700 rounded mb-2" />
        <div className="h-3 w-32 bg-neutral-200 dark:bg-neutral-700 rounded" />
      </div>
    );
  }

  return (
    <div
      className={`rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 ${statusColors[status]}`}
    >
      <div className="flex items-center gap-2 mb-2">
        <Icon className="h-4 w-4" />
        <span className="text-sm font-medium">{title}</span>
      </div>
      <p className="text-2xl font-bold">{value}</p>
      <p className="text-xs mt-1 opacity-75">{subtitle}</p>
    </div>
  );
}

function FeatureBadge({ enabled }: { enabled: boolean }) {
  return enabled ? (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">
      ✓
    </span>
  ) : (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-neutral-100 text-neutral-400 dark:bg-neutral-800 dark:text-neutral-500">
      —
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    online: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
    offline: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
    degraded: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  };
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${colors[status] || colors.offline}`}
    >
      {status}
    </span>
  );
}
