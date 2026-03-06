/**
 * API Traffic Dashboard — Per-backend proxy observability (CAB-1730)
 *
 * Shows real-time metrics for each proxy backend routed through the STOA Gateway:
 * calls/min, latency P95, error rate, circuit breaker status, and health checks.
 * Embeds a Grafana dashboard for deep-dive analysis.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  RefreshCw,
  Activity,
  Clock,
  AlertTriangle,
  ShieldOff,
  ShieldCheck,
  CheckCircle2,
  XCircle,
  ExternalLink,
  Zap,
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { config } from '../../config';
import { PermissionGate } from '../../components/PermissionGate';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import {
  proxyBackendService,
  type ProxyBackendResponse,
  type ProxyBackendHealthStatus,
} from '../../services/proxyBackendService';

const AUTO_REFRESH_INTERVAL = 30_000;

// ── Types ────────────────────────────────────────────────────────────

interface BackendTrafficRow {
  backend: ProxyBackendResponse;
  health: ProxyBackendHealthStatus | null;
}

// ── Helpers ──────────────────────────────────────────────────────────

function formatNumber(num: number): string {
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(1)}M`;
  if (num >= 1_000) return `${(num / 1_000).toFixed(1)}K`;
  return num.toString();
}

function formatLatency(ms: number | null): string {
  if (ms === null) return '—';
  if (ms < 1) return '<1ms';
  return `${Math.round(ms)}ms`;
}

// ── KPI Card ─────────────────────────────────────────────────────────

function KPICard({
  label,
  value,
  subtitle,
  icon: Icon,
  iconBg,
  iconColor,
}: {
  label: string;
  value: string | number;
  subtitle?: string;
  icon: React.ElementType;
  iconBg: string;
  iconColor: string;
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
    </div>
  );
}

// ── Backend Row ──────────────────────────────────────────────────────

function BackendRow({ row }: { row: BackendTrafficRow }) {
  const { backend, health } = row;
  const isHealthy = health?.healthy ?? null;
  const cbEnabled = backend.circuit_breaker_enabled;

  return (
    <tr className="hover:bg-neutral-50 dark:hover:bg-neutral-750">
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          {isHealthy === true && <CheckCircle2 className="w-4 h-4 text-green-600" />}
          {isHealthy === false && <XCircle className="w-4 h-4 text-red-600" />}
          {isHealthy === null && (
            <div className="w-4 h-4 rounded-full bg-neutral-300 dark:bg-neutral-600" />
          )}
          <div>
            <span className="text-sm font-medium text-neutral-900 dark:text-white">
              {backend.display_name || backend.name}
            </span>
            <p className="text-xs text-neutral-400 dark:text-neutral-500">{backend.base_url}</p>
          </div>
        </div>
      </td>
      <td className="px-4 py-3">
        <span
          className={`inline-flex px-2 py-0.5 text-xs font-medium rounded-full ${
            backend.status === 'active'
              ? 'bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400'
              : 'bg-neutral-100 dark:bg-neutral-700 text-neutral-500 dark:text-neutral-400'
          }`}
        >
          {backend.status}
        </span>
      </td>
      <td className="px-4 py-3 text-sm text-neutral-600 dark:text-neutral-300">
        {backend.rate_limit_rpm > 0 ? `${formatNumber(backend.rate_limit_rpm)}/min` : 'Unlimited'}
      </td>
      <td className="px-4 py-3 text-sm text-neutral-600 dark:text-neutral-300">
        {formatLatency(health?.latency_ms ?? null)}
      </td>
      <td className="px-4 py-3">
        {cbEnabled ? (
          <span className="inline-flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
            <ShieldCheck className="w-3.5 h-3.5" />
            On
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 text-xs text-neutral-400 dark:text-neutral-500">
            <ShieldOff className="w-3.5 h-3.5" />
            Off
          </span>
        )}
      </td>
      <td className="px-4 py-3 text-sm text-neutral-600 dark:text-neutral-300">
        {backend.auth_type.replace('_', ' ')}
      </td>
      <td className="px-4 py-3 text-sm text-neutral-600 dark:text-neutral-300">
        {backend.timeout_secs}s
      </td>
    </tr>
  );
}

// ── Main Component ──────────────────────────────────────────────────

export function ApiTrafficDashboard() {
  const { user } = useAuth();

  const [rows, setRows] = useState<BackendTrafficRow[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());
  const mountedRef = useRef(true);

  const loadData = useCallback(async () => {
    try {
      setError(null);

      const listResp = await proxyBackendService.list();
      const backends = listResp.items;

      // Fetch health in parallel for all backends
      const healthResults = await Promise.allSettled(
        backends.map((b) => proxyBackendService.healthCheck(b.id))
      );

      const trafficRows: BackendTrafficRow[] = backends.map((backend, i) => ({
        backend,
        health: healthResults[i].status === 'fulfilled' ? healthResults[i].value : null,
      }));

      if (!mountedRef.current) return;
      setRows(trafficRows);
      setLastRefresh(new Date());
    } catch (err) {
      if (!mountedRef.current) return;
      setError(err instanceof Error ? err.message : 'Failed to load API traffic data');
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

  const activeCount = rows.filter((r) => r.backend.status === 'active').length;
  const healthyCount = rows.filter((r) => r.health?.healthy).length;
  const cbEnabledCount = rows.filter((r) => r.backend.circuit_breaker_enabled).length;
  const avgLatency =
    rows.length > 0
      ? rows.reduce((sum, r) => sum + (r.health?.latency_ms ?? 0), 0) /
          rows.filter((r) => r.health?.latency_ms != null).length || 0
      : 0;

  const grafanaBaseUrl = config?.services?.grafana?.url || '';
  const tenantFilter = user?.tenant_id ? `&var-tenant=${user.tenant_id}` : '';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">API Traffic</h1>
          <p className="text-neutral-500 dark:text-neutral-400 mt-1">
            Per-backend proxy metrics, health status, and circuit breaker state
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
            label="Active Backends"
            value={`${activeCount}/${rows.length}`}
            subtitle={`${rows.length - activeCount} disabled`}
            icon={Activity}
            iconBg="bg-blue-100 dark:bg-blue-900/30"
            iconColor="text-blue-600 dark:text-blue-400"
          />
          <KPICard
            label="Healthy"
            value={`${healthyCount}/${rows.length}`}
            subtitle={
              healthyCount < rows.length ? `${rows.length - healthyCount} unhealthy` : 'All passing'
            }
            icon={CheckCircle2}
            iconBg="bg-green-100 dark:bg-green-900/30"
            iconColor="text-green-600 dark:text-green-400"
          />
          <KPICard
            label="Avg Latency"
            value={formatLatency(avgLatency || null)}
            subtitle="Health check round-trip"
            icon={Clock}
            iconBg="bg-purple-100 dark:bg-purple-900/30"
            iconColor="text-purple-600 dark:text-purple-400"
          />
          <KPICard
            label="Circuit Breakers"
            value={`${cbEnabledCount}/${rows.length}`}
            subtitle={
              cbEnabledCount < rows.length
                ? `${rows.length - cbEnabledCount} unprotected`
                : 'All protected'
            }
            icon={Zap}
            iconBg="bg-amber-100 dark:bg-amber-900/30"
            iconColor="text-amber-600 dark:text-amber-400"
          />
        </div>
      )}

      {/* Backend Table */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none overflow-hidden">
        <div className="px-4 py-3 border-b border-neutral-200 dark:border-neutral-700">
          <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">Proxy Backends</h2>
        </div>
        {isLoading ? (
          <div className="p-8 text-center text-neutral-500 dark:text-neutral-400">Loading...</div>
        ) : rows.length === 0 ? (
          <div className="p-8 text-center text-neutral-500 dark:text-neutral-400">
            No proxy backends registered. Run{' '}
            <code className="text-xs">seed-proxy-backends.sh</code> to populate.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-neutral-200 dark:divide-neutral-700">
              <thead className="bg-neutral-50 dark:bg-neutral-900">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                    Backend
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                    Status
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                    Rate Limit
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                    Latency
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                    Circuit Breaker
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                    Auth
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                    Timeout
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-200 dark:divide-neutral-700">
                {rows.map((row) => (
                  <BackendRow key={row.backend.id} row={row} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Grafana Embed — admin only */}
      <PermissionGate
        permission="tenants:read"
        fallback={
          <div className="bg-neutral-50 dark:bg-neutral-800/50 rounded-lg p-6 text-center">
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              Detailed traffic metrics require platform admin access.
            </p>
          </div>
        }
      >
        {grafanaBaseUrl ? (
          <div className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none overflow-hidden">
            <div className="px-4 py-3 border-b border-neutral-200 dark:border-neutral-700 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">
                Traffic Metrics
              </h2>
              <a
                href={`${grafanaBaseUrl}/d/stoa-dogfooding?orgId=1${tenantFilter}`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700 dark:text-blue-400"
              >
                Open in Grafana
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>
            <iframe
              src={`${grafanaBaseUrl}/d-solo/stoa-dogfooding/stoa-api-proxy-traffic?orgId=1&panelId=1&theme=light${tenantFilter}`}
              className="w-full h-80 border-0"
              title="API proxy traffic metrics"
              loading="lazy"
            />
          </div>
        ) : (
          <div className="bg-neutral-50 dark:bg-neutral-800/50 rounded-lg p-6 text-center">
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              Grafana not configured. Set <code className="text-xs">grafana.url</code> in platform
              settings.
            </p>
          </div>
        )}
      </PermissionGate>

      {/* Circuit breaker alert info */}
      {rows.some((r) => r.health?.healthy === false && r.backend.circuit_breaker_enabled) && (
        <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-medium text-amber-800 dark:text-amber-300">
              Circuit breaker may be open
            </p>
            <p className="text-sm text-amber-700 dark:text-amber-400 mt-1">
              One or more backends with circuit breakers enabled are reporting unhealthy. Requests
              may be falling back to direct connections.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
