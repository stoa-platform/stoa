/**
 * Proxy Owner Dashboard — CPI infrastructure overview (CAB-1545)
 *
 * Platform-level view for CPI admins: gateway health, policy enforcement,
 * cross-tenant traffic overview, and embedded Grafana panels.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  RefreshCw,
  Server,
  Shield,
  Activity,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  ArrowUpRight,
  ArrowDownRight,
  ExternalLink,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { apiService } from '../../services/api';
import { config } from '../../config';
import { PermissionGate } from '../../components/PermissionGate';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import { observabilityPath } from '../../utils/navigation';

const AUTO_REFRESH_INTERVAL = 30_000; // 30s — infrastructure metrics refresh faster

// ── Types ────────────────────────────────────────────────────────────

interface GatewayHealth {
  id: string;
  name: string;
  status: 'online' | 'degraded' | 'offline';
}

// ── Helpers ──────────────────────────────────────────────────────────

const STATUS_CONFIG = {
  online: {
    icon: CheckCircle2,
    color: 'text-green-600 dark:text-green-400',
    bg: 'bg-green-100 dark:bg-green-900/30',
    label: 'Online',
  },
  degraded: {
    icon: AlertTriangle,
    color: 'text-amber-600 dark:text-amber-400',
    bg: 'bg-amber-100 dark:bg-amber-900/30',
    label: 'Degraded',
  },
  offline: {
    icon: XCircle,
    color: 'text-red-600 dark:text-red-400',
    bg: 'bg-red-100 dark:bg-red-900/30',
    label: 'Offline',
  },
} as const;

// ── KPI Card (reuse pattern from BusinessDashboard) ─────────────────

function KPICard({
  label,
  value,
  subtitle,
  icon: Icon,
  iconBg,
  iconColor,
  trend,
}: {
  label: string;
  value: string | number;
  subtitle?: string;
  icon: React.ElementType;
  iconBg: string;
  iconColor: string;
  trend?: { value: number; label: string };
}) {
  return (
    <div className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none p-4">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-neutral-500 dark:text-neutral-400">{label}</p>
          <p className="text-2xl font-bold text-neutral-900 dark:text-white mt-1">{value}</p>
          {subtitle && (
            <p className="text-xs text-neutral-400 dark:text-neutral-500 mt-0.5">{subtitle}</p>
          )}
        </div>
        <div className={`p-2 rounded-lg ${iconBg}`}>
          <Icon className={`w-5 h-5 ${iconColor}`} />
        </div>
      </div>
      {trend && (
        <div className="flex items-center gap-1 mt-2">
          {trend.value >= 0 ? (
            <ArrowUpRight className="w-3 h-3 text-green-600" />
          ) : (
            <ArrowDownRight className="w-3 h-3 text-red-600" />
          )}
          <span
            className={`text-xs font-medium ${trend.value >= 0 ? 'text-green-600' : 'text-red-600'}`}
          >
            {Math.abs(trend.value)}%
          </span>
          <span className="text-xs text-neutral-400 dark:text-neutral-500">{trend.label}</span>
        </div>
      )}
    </div>
  );
}

// ── Gateway Status Row ──────────────────────────────────────────────

function GatewayRow({ gw }: { gw: GatewayHealth }) {
  const cfg = STATUS_CONFIG[gw.status];
  const StatusIcon = cfg.icon;

  return (
    <tr className="hover:bg-neutral-50 dark:hover:bg-neutral-750">
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <StatusIcon className={`w-4 h-4 ${cfg.color}`} />
          <span className="text-sm font-medium text-neutral-900 dark:text-white">{gw.name}</span>
        </div>
      </td>
      <td className="px-4 py-3">
        <span
          className={`inline-flex px-2 py-0.5 text-xs font-medium rounded-full ${cfg.bg} ${cfg.color}`}
        >
          {cfg.label}
        </span>
      </td>
    </tr>
  );
}

// ── Main Component ──────────────────────────────────────────────────

export function ProxyOwnerDashboard() {
  const { hasPermission, user } = useAuth();
  const navigate = useNavigate();
  const isAdmin = hasPermission('tenants:read');

  const [gateways, setGateways] = useState<GatewayHealth[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());
  const mountedRef = useRef(true);

  const loadData = useCallback(async () => {
    try {
      setError(null);

      // Fetch gateway instances for health overview
      const gwResponse = await apiService.get('/v1/admin/gateways');
      const instances = gwResponse.data?.items || gwResponse.data || [];

      // Map real gateway data — only use fields actually returned by the API
      const gwHealth: GatewayHealth[] = instances.map(
        (inst: {
          id: string;
          name: string;
          display_name?: string;
          status: string;
          base_url?: string;
        }) => ({
          id: inst.id,
          name: inst.display_name || inst.name,
          status:
            inst.status === 'online' ? 'online' : inst.status === 'error' ? 'offline' : 'degraded',
        })
      );
      setGateways(gwHealth);

      if (!mountedRef.current) return;
      setLastRefresh(new Date());
    } catch (err) {
      if (!mountedRef.current) return;
      setError(err instanceof Error ? err.message : 'Failed to load dashboard data');
    } finally {
      if (mountedRef.current) setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    loadData();
    const interval = setInterval(loadData, AUTO_REFRESH_INTERVAL);
    return () => {
      mountedRef.current = false;
      clearInterval(interval);
    };
  }, [loadData]);

  const onlineCount = gateways.filter((g) => g.status === 'online').length;
  const degradedCount = gateways.filter((g) => g.status === 'degraded').length;
  const offlineCount = gateways.filter((g) => g.status === 'offline').length;
  void offlineCount; // reserved for future offline-count KPI card

  const grafanaUrl = `${config.services.grafana.url}/d/gateway-overview`;
  const tenantFilter = user?.tenant_id ? `&var-tenant=${user.tenant_id}` : '';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">
            Proxy Owner Dashboard
          </h1>
          <p className="text-neutral-500 dark:text-neutral-400 mt-1">
            Gateway infrastructure health, policy enforcement, and traffic overview
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-neutral-400 dark:text-neutral-500">
            Last refresh: {lastRefresh.toLocaleTimeString()}
          </span>
          <button
            onClick={loadData}
            className="p-2 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-700 transition-colors"
            aria-label="Refresh dashboard"
          >
            <RefreshCw className="w-4 h-4 text-neutral-500 dark:text-neutral-400" />
          </button>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
          <p className="text-sm text-red-800 dark:text-red-300">{error}</p>
        </div>
      )}

      {/* KPI Row */}
      {isLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KPICard
            label="Gateways Online"
            value={`${onlineCount}/${gateways.length}`}
            subtitle={degradedCount > 0 ? `${degradedCount} degraded` : undefined}
            icon={Server}
            iconBg="bg-green-100 dark:bg-green-900/30"
            iconColor="text-green-600 dark:text-green-400"
          />
          <KPICard
            label="Active Policies"
            value="--"
            subtitle="Metrics not yet available"
            icon={Shield}
            iconBg="bg-neutral-100 dark:bg-neutral-700"
            iconColor="text-neutral-400"
          />
          <KPICard
            label="Requests (24h)"
            value="--"
            subtitle="Metrics not yet available"
            icon={Activity}
            iconBg="bg-neutral-100 dark:bg-neutral-700"
            iconColor="text-neutral-400"
          />
          <KPICard
            label="Violations (24h)"
            value="--"
            subtitle="Metrics not yet available"
            icon={AlertTriangle}
            iconBg="bg-neutral-100 dark:bg-neutral-700"
            iconColor="text-neutral-400"
          />
        </div>
      )}

      {/* Gateway Health Table */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none overflow-hidden">
        <div className="px-4 py-3 border-b border-neutral-200 dark:border-neutral-700">
          <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">
            Gateway Instances
          </h2>
        </div>
        {isLoading ? (
          <div className="p-8 text-center text-neutral-500 dark:text-neutral-400">Loading...</div>
        ) : gateways.length === 0 ? (
          <div className="p-8 text-center text-neutral-500 dark:text-neutral-400">
            No gateway instances registered
          </div>
        ) : (
          <table className="min-w-full divide-y divide-neutral-200 dark:divide-neutral-700">
            <thead className="bg-neutral-50 dark:bg-neutral-900">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                  Instance
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                  Status
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-200 dark:divide-neutral-700">
              {gateways.map((gw) => (
                <GatewayRow key={gw.id} gw={gw} />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Two-column layout — traffic & policy metrics not yet available */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <PermissionGate permission="tenants:read">
          <div className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none p-6">
            <h2 className="text-lg font-semibold text-neutral-900 dark:text-white mb-4">
              Cross-Tenant Traffic
            </h2>
            <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg px-4 py-3">
              <p className="text-sm text-amber-700 dark:text-amber-400">
                Traffic metrics are not yet available. Per-gateway Prometheus instrumentation is
                required.
              </p>
            </div>
          </div>
        </PermissionGate>

        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none p-6">
          <h2 className="text-lg font-semibold text-neutral-900 dark:text-white mb-4">
            Policy Enforcement
          </h2>
          <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg px-4 py-3">
            <p className="text-sm text-amber-700 dark:text-amber-400">
              Policy metrics are not yet available. Enforcement counters will appear once policy
              evaluation is instrumented.
            </p>
          </div>
        </div>
      </div>

      {/* Grafana Embed — admin only, tenant-scoped */}
      <PermissionGate
        permission="tenants:read"
        fallback={
          <div className="bg-neutral-50 dark:bg-neutral-800/50 rounded-lg p-6 text-center">
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              Infrastructure metrics require platform admin access.
            </p>
          </div>
        }
      >
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">
              Infrastructure Metrics
            </h2>
          </div>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mb-4">
            View gateway health dashboards, latency distributions, and error rates in Grafana.
          </p>
          <button
            onClick={() => navigate(observabilityPath(`${grafanaUrl}?orgId=1${tenantFilter}`))}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-orange-500 rounded-lg hover:bg-orange-600 transition-colors"
          >
            <Activity className="h-4 w-4" />
            Open in Grafana
            <ExternalLink className="h-3 w-3" />
          </button>
        </div>
      </PermissionGate>

      {/* Gateway link for non-admins */}
      {!isAdmin && (
        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
          <p className="text-sm text-blue-800 dark:text-blue-300">
            Showing gateway data for your tenant. Contact a platform admin for cross-tenant metrics.
          </p>
        </div>
      )}
    </div>
  );
}
