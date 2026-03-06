import { useState, useCallback, useEffect, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { apiService } from '../../services/api';
import { GatewayRegistrationForm } from './GatewayRegistrationForm';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import { EmptyState } from '@stoa/shared/components/EmptyState';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import {
  RefreshCw,
  Activity,
  Server,
  ChevronRight,
  ExternalLink,
  Trash2,
  HeartPulse,
  Shield,
  Globe,
  Zap,
} from 'lucide-react';
import { Button } from '@stoa/shared/components/Button';
import type { GatewayInstance, GatewayInstanceStatus, GatewayMode } from '../../types';

// ---------------------------------------------------------------------------
// Constants — colors from shared constants (green=dev, amber=staging, red=prod)
// ---------------------------------------------------------------------------

import {
  ENV_ORDER as SHARED_ENV_ORDER,
  ENV_LABELS,
  ENV_COLORS as SHARED_COLORS,
  normalizeEnvironment,
  type CanonicalEnvironment,
} from '@stoa/shared/constants/environments';

type Environment = CanonicalEnvironment;

const ENV_ORDER = SHARED_ENV_ORDER;

const ENV_COLORS: Record<Environment, { dot: string; bg: string; text: string; border: string }> = {
  production: {
    dot: SHARED_COLORS.production.dot,
    bg: `${SHARED_COLORS.production.bg} ${SHARED_COLORS.production.bgDark}`,
    text: `${SHARED_COLORS.production.text} ${SHARED_COLORS.production.textDark}`,
    border: `${SHARED_COLORS.production.border} ${SHARED_COLORS.production.borderDark}`,
  },
  staging: {
    dot: SHARED_COLORS.staging.dot,
    bg: `${SHARED_COLORS.staging.bg} ${SHARED_COLORS.staging.bgDark}`,
    text: `${SHARED_COLORS.staging.text} ${SHARED_COLORS.staging.textDark}`,
    border: `${SHARED_COLORS.staging.border} ${SHARED_COLORS.staging.borderDark}`,
  },
  development: {
    dot: SHARED_COLORS.development.dot,
    bg: `${SHARED_COLORS.development.bg} ${SHARED_COLORS.development.bgDark}`,
    text: `${SHARED_COLORS.development.text} ${SHARED_COLORS.development.textDark}`,
    border: `${SHARED_COLORS.development.border} ${SHARED_COLORS.development.borderDark}`,
  },
};

const STATUS_CONFIG: Record<GatewayInstanceStatus, { dot: string; label: string; badge: string }> =
  {
    online: {
      dot: 'bg-green-500',
      label: 'Online',
      badge: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
    },
    offline: {
      dot: 'bg-neutral-400',
      label: 'Offline',
      badge: 'bg-neutral-100 text-neutral-600 dark:bg-neutral-700 dark:text-neutral-400',
    },
    degraded: {
      dot: 'bg-yellow-500',
      label: 'Degraded',
      badge: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
    },
    maintenance: {
      dot: 'bg-blue-500',
      label: 'Maintenance',
      badge: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
    },
  };

const TYPE_DISPLAY: Record<string, { label: string; icon: typeof Server }> = {
  stoa: { label: 'STOA', icon: Zap },
  stoa_edge_mcp: { label: 'STOA Edge MCP', icon: Zap },
  stoa_sidecar: { label: 'STOA Sidecar', icon: Shield },
  stoa_proxy: { label: 'STOA Proxy', icon: Globe },
  stoa_shadow: { label: 'STOA Shadow', icon: Activity },
  webmethods: { label: 'webMethods', icon: Server },
  kong: { label: 'Kong', icon: Server },
  apigee: { label: 'Apigee', icon: Server },
  aws_apigateway: { label: 'AWS API GW', icon: Server },
  azure_apim: { label: 'Azure APIM', icon: Server },
  gravitee: { label: 'Gravitee', icon: Server },
};

const MODE_LABELS: Record<GatewayMode, string> = {
  'edge-mcp': 'Edge MCP',
  sidecar: 'Sidecar',
  proxy: 'Proxy',
  shadow: 'Shadow',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Normalize the many env string variants to 3 canonical values. */
/** Delegate to shared normalizeEnvironment */
const normalizeEnv = normalizeEnvironment;

function isLive(gw: GatewayInstance): boolean {
  if (!gw.last_health_check) return false;
  return Date.now() - new Date(gw.last_health_check).getTime() < 90_000;
}

function isStoa(type: string): boolean {
  return type.startsWith('stoa');
}

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export function GatewayList() {
  const { isReady } = useAuth();
  const queryClient = useQueryClient();
  const toast = useToastActions();
  const [confirm, ConfirmDialog] = useConfirm();
  const [searchParams, setSearchParams] = useSearchParams();
  const [showForm, setShowForm] = useState(false);
  const [healthChecking, setHealthChecking] = useState<string | null>(null);
  const [selectedGateway, setSelectedGateway] = useState<GatewayInstance | null>(null);

  // Active environment tab
  const [activeEnv, setActiveEnv] = useState<Environment | 'all'>(() => {
    const param = searchParams.get('env');
    if (param && ENV_ORDER.includes(param as Environment)) return param as Environment;
    return 'all';
  });

  // Sync tab to URL
  useEffect(() => {
    const params = new URLSearchParams(searchParams);
    if (activeEnv === 'all') {
      params.delete('env');
    } else {
      params.set('env', activeEnv);
    }
    setSearchParams(params, { replace: true });
  }, [activeEnv, searchParams, setSearchParams]);

  const {
    data: gatewaysData,
    isLoading,
    error: queryError,
  } = useQuery({
    queryKey: ['gateways'],
    queryFn: () => apiService.getGatewayInstances(),
    enabled: isReady,
    refetchInterval: 30_000,
    staleTime: 10_000,
  });

  const gateways: GatewayInstance[] = gatewaysData?.items ?? [];
  const error = queryError
    ? (queryError as { response?: { data?: { detail?: string } } }).response?.data?.detail ||
      (queryError as Error).message ||
      'Failed to load gateways'
    : null;

  // Group gateways by normalized environment
  const envGroups = useMemo(() => {
    const groups: Record<Environment, GatewayInstance[]> = {
      production: [],
      staging: [],
      development: [],
    };
    for (const gw of gateways) {
      groups[normalizeEnv(gw.environment)].push(gw);
    }
    // Sort each group: STOA gateways first, then alphabetical
    for (const env of ENV_ORDER) {
      groups[env].sort((a, b) => {
        const aStoa = isStoa(a.gateway_type) ? 0 : 1;
        const bStoa = isStoa(b.gateway_type) ? 0 : 1;
        if (aStoa !== bStoa) return aStoa - bStoa;
        return a.display_name.localeCompare(b.display_name);
      });
    }
    return groups;
  }, [gateways]);

  // Stats per environment
  const envStats = useMemo(() => {
    const stats: Record<
      Environment,
      { total: number; online: number; offline: number; degraded: number }
    > = {
      production: { total: 0, online: 0, offline: 0, degraded: 0 },
      staging: { total: 0, online: 0, offline: 0, degraded: 0 },
      development: { total: 0, online: 0, offline: 0, degraded: 0 },
    };
    for (const gw of gateways) {
      const env = normalizeEnv(gw.environment);
      stats[env].total++;
      if (gw.status === 'online') stats[env].online++;
      else if (gw.status === 'degraded') stats[env].degraded++;
      else stats[env].offline++;
    }
    return stats;
  }, [gateways]);

  const visibleEnvs = activeEnv === 'all' ? ENV_ORDER : [activeEnv];

  const refetchGateways = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['gateways'] });
  }, [queryClient]);

  const handleHealthCheck = async (id: string) => {
    setHealthChecking(id);
    try {
      await apiService.checkGatewayHealth(id);
      refetchGateways();
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Health check failed';
      toast.error(message);
    } finally {
      setHealthChecking(null);
    }
  };

  const handleDelete = useCallback(
    async (id: string, name: string) => {
      const confirmed = await confirm({
        title: 'Delete Gateway',
        message: `Are you sure you want to delete "${name}"? This cannot be undone.`,
        confirmLabel: 'Delete',
        variant: 'danger',
      });
      if (!confirmed) return;
      try {
        await apiService.deleteGatewayInstance(id);
        toast.success(`Gateway "${name}" deleted`);
        if (selectedGateway?.id === id) setSelectedGateway(null);
        refetchGateways();
      } catch (err: unknown) {
        const message =
          (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          'Failed to delete gateway';
        toast.error(message);
      }
    },
    [confirm, toast, refetchGateways, selectedGateway]
  );

  const handleCreated = () => {
    setShowForm(false);
    refetchGateways();
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div className="h-8 w-48 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
          <div className="h-10 w-40 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3].map((i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Gateway Registry</h1>
          <p className="text-neutral-500 dark:text-neutral-400 mt-1">
            {gateways.length} gateways across{' '}
            {ENV_ORDER.filter((e) => envStats[e].total > 0).length} environments
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="secondary"
            size="sm"
            onClick={refetchGateways}
            icon={<RefreshCw className="w-4 h-4" />}
          >
            Refresh
          </Button>
          <Button
            variant={showForm ? 'secondary' : 'primary'}
            onClick={() => setShowForm(!showForm)}
          >
            {showForm ? 'Cancel' : '+ Register Gateway'}
          </Button>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 px-4 py-3 rounded-lg flex items-center justify-between">
          <span className="text-sm text-red-700 dark:text-red-400">{error}</span>
          <Button variant="secondary" size="sm" onClick={refetchGateways} className="ml-4">
            Retry
          </Button>
        </div>
      )}

      {/* Registration Form */}
      {showForm && (
        <GatewayRegistrationForm onCreated={handleCreated} onCancel={() => setShowForm(false)} />
      )}

      {/* Environment Tabs */}
      <div className="border-b border-neutral-200 dark:border-neutral-700">
        <nav className="flex gap-1 -mb-px" aria-label="Environment tabs">
          <EnvTab
            label="All"
            count={gateways.length}
            online={
              envStats.production.online + envStats.staging.online + envStats.development.online
            }
            isActive={activeEnv === 'all'}
            onClick={() => setActiveEnv('all')}
          />
          {ENV_ORDER.map((env) => (
            <EnvTab
              key={env}
              label={ENV_LABELS[env]}
              count={envStats[env].total}
              online={envStats[env].online}
              degraded={envStats[env].degraded}
              dotColor={ENV_COLORS[env].dot}
              isActive={activeEnv === env}
              onClick={() => setActiveEnv(env)}
            />
          ))}
        </nav>
      </div>

      {/* Gateway List by Environment */}
      {gateways.length === 0 ? (
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow">
          <EmptyState
            variant="servers"
            title="No gateways registered"
            description="Register your first gateway instance to start multi-gateway orchestration."
            action={{ label: 'Register Gateway', onClick: () => setShowForm(true) }}
          />
        </div>
      ) : (
        <div className="space-y-8">
          {visibleEnvs.map((env) => {
            const items = envGroups[env];
            if (items.length === 0) return null;
            return (
              <EnvironmentSection
                key={env}
                env={env}
                gateways={items}
                stats={envStats[env]}
                onSelect={setSelectedGateway}
                onHealthCheck={handleHealthCheck}
                onDelete={handleDelete}
                healthChecking={healthChecking}
                showHeader={activeEnv === 'all'}
              />
            );
          })}
        </div>
      )}

      {/* Gateway Detail Panel */}
      {selectedGateway && (
        <GatewayDetailPanel gateway={selectedGateway} onClose={() => setSelectedGateway(null)} />
      )}

      {ConfirmDialog}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Environment Tab
// ---------------------------------------------------------------------------

function EnvTab({
  label,
  count,
  online,
  degraded,
  dotColor,
  isActive,
  onClick,
}: {
  label: string;
  count: number;
  online: number;
  degraded?: number;
  dotColor?: string;
  isActive: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`
        relative px-4 py-3 text-sm font-medium transition-colors whitespace-nowrap
        ${
          isActive
            ? 'text-neutral-900 dark:text-white border-b-2 border-neutral-900 dark:border-white'
            : 'text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300 border-b-2 border-transparent'
        }
      `}
    >
      <span className="flex items-center gap-2">
        {dotColor && <span className={`w-2 h-2 rounded-full ${dotColor}`} />}
        {label}
        <span
          className={`
            text-xs px-1.5 py-0.5 rounded-full
            ${isActive ? 'bg-neutral-200 dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300' : 'bg-neutral-100 dark:bg-neutral-800 text-neutral-500 dark:text-neutral-500'}
          `}
        >
          {count}
        </span>
        {count > 0 && (
          <span className="flex items-center gap-1 text-xs">
            <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
            <span className="text-green-600 dark:text-green-400">{online}</span>
            {(degraded ?? 0) > 0 && (
              <>
                <span className="w-1.5 h-1.5 rounded-full bg-yellow-500" />
                <span className="text-yellow-600 dark:text-yellow-400">{degraded}</span>
              </>
            )}
          </span>
        )}
      </span>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Environment Section
// ---------------------------------------------------------------------------

function EnvironmentSection({
  env,
  gateways,
  stats,
  onSelect,
  onHealthCheck,
  onDelete,
  healthChecking,
  showHeader,
}: {
  env: Environment;
  gateways: GatewayInstance[];
  stats: { total: number; online: number; offline: number; degraded: number };
  onSelect: (gw: GatewayInstance) => void;
  onHealthCheck: (id: string) => void;
  onDelete: (id: string, name: string) => void;
  healthChecking: string | null;
  showHeader: boolean;
}) {
  const colors = ENV_COLORS[env];

  return (
    <div>
      {showHeader && (
        <div className="flex items-center gap-3 mb-3">
          <div className="flex items-center gap-2">
            <span className={`w-3 h-3 rounded-full ${colors.dot}`} />
            <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">
              {ENV_LABELS[env]}
            </h2>
          </div>
          <div className="flex items-center gap-3 text-xs text-neutral-500 dark:text-neutral-400">
            <span>{stats.total} gateways</span>
            <span className="text-neutral-300 dark:text-neutral-600">|</span>
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
              {stats.online} online
            </span>
            {stats.degraded > 0 && (
              <span className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-yellow-500" />
                {stats.degraded} degraded
              </span>
            )}
            {stats.offline > 0 && (
              <span className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-neutral-400" />
                {stats.offline} offline
              </span>
            )}
          </div>
        </div>
      )}

      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow overflow-hidden border border-neutral-200 dark:border-neutral-700">
        <div className="divide-y divide-neutral-100 dark:divide-neutral-700/50">
          {gateways.map((gw) => (
            <GatewayRow
              key={gw.id}
              gw={gw}
              onSelect={() => onSelect(gw)}
              onHealthCheck={() => onHealthCheck(gw.id)}
              onDelete={() => onDelete(gw.id, gw.name)}
              isChecking={healthChecking === gw.id}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Gateway Row
// ---------------------------------------------------------------------------

function GatewayRow({
  gw,
  onSelect,
  onHealthCheck,
  onDelete,
  isChecking,
}: {
  gw: GatewayInstance;
  onSelect: () => void;
  onHealthCheck: () => void;
  onDelete: () => void;
  isChecking: boolean;
}) {
  const status = STATUS_CONFIG[gw.status];
  const typeInfo = TYPE_DISPLAY[gw.gateway_type] ?? { label: gw.gateway_type, icon: Server };
  const TypeIcon = typeInfo.icon;
  const live = isLive(gw);

  return (
    <div
      className="group flex items-center gap-4 px-5 py-4 hover:bg-neutral-50 dark:hover:bg-neutral-750 cursor-pointer transition-colors"
      onClick={onSelect}
    >
      {/* Status indicator */}
      <div className="flex-shrink-0 relative">
        <div
          className={`w-10 h-10 rounded-lg flex items-center justify-center ${
            isStoa(gw.gateway_type)
              ? 'bg-indigo-100 dark:bg-indigo-900/30'
              : 'bg-neutral-100 dark:bg-neutral-700'
          }`}
        >
          <TypeIcon
            className={`w-5 h-5 ${
              isStoa(gw.gateway_type)
                ? 'text-indigo-600 dark:text-indigo-400'
                : 'text-neutral-500 dark:text-neutral-400'
            }`}
          />
        </div>
        {/* Status dot overlaid on icon */}
        <span
          className={`absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-white dark:border-neutral-800 ${status.dot} ${live ? 'animate-pulse' : ''}`}
          title={live ? `${status.label} (live heartbeat)` : status.label}
        />
      </div>

      {/* Name + type */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-medium text-neutral-900 dark:text-white truncate">
            {gw.display_name}
          </span>
          {gw.mode && (
            <span className="flex-shrink-0 text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400">
              {MODE_LABELS[gw.mode] ?? gw.mode}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 mt-0.5">
          <span className="text-xs text-neutral-500 dark:text-neutral-400">{typeInfo.label}</span>
          <span className="text-neutral-300 dark:text-neutral-600">&middot;</span>
          <span className="text-xs font-mono text-neutral-400 dark:text-neutral-500 truncate">
            {gw.base_url.replace(/^https?:\/\//, '')}
          </span>
        </div>
      </div>

      {/* Status badge */}
      <div className="flex-shrink-0 hidden sm:block">
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full ${status.badge}`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${status.dot}`} />
          {status.label}
        </span>
      </div>

      {/* Last check */}
      <div className="flex-shrink-0 hidden md:block text-right w-20">
        {gw.last_health_check ? (
          <span className="text-xs text-neutral-400 dark:text-neutral-500">
            {timeAgo(gw.last_health_check)}
          </span>
        ) : (
          <span className="text-xs text-neutral-300 dark:text-neutral-600">never</span>
        )}
      </div>

      {/* Actions */}
      <div className="flex-shrink-0 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onHealthCheck();
          }}
          disabled={isChecking}
          className="p-1.5 rounded-md text-neutral-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:text-blue-400 dark:hover:bg-blue-900/20 disabled:opacity-50 transition-colors"
          title="Health check"
        >
          <HeartPulse className={`w-4 h-4 ${isChecking ? 'animate-pulse' : ''}`} />
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          className="p-1.5 rounded-md text-neutral-400 hover:text-red-600 hover:bg-red-50 dark:hover:text-red-400 dark:hover:bg-red-900/20 transition-colors"
          title="Delete"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>

      {/* Chevron */}
      <ChevronRight className="w-4 h-4 text-neutral-300 dark:text-neutral-600 flex-shrink-0" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Detail Panel (slide-over)
// ---------------------------------------------------------------------------

function GatewayDetailPanel({
  gateway: gw,
  onClose,
}: {
  gateway: GatewayInstance;
  onClose: () => void;
}) {
  const hd = (gw.health_details ?? {}) as Record<string, unknown>;
  const errorRate = typeof hd.error_rate === 'number' ? hd.error_rate : null;
  const status = STATUS_CONFIG[gw.status];
  const typeInfo = TYPE_DISPLAY[gw.gateway_type] ?? { label: gw.gateway_type, icon: Server };
  const live = isLive(gw);

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      onClick={onClose}
      data-testid="gateway-detail-overlay"
    >
      <div className="fixed inset-0 bg-black/30" />

      <div
        className="relative w-full max-w-md bg-white dark:bg-neutral-800 shadow-xl overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
        data-testid="gateway-detail-panel"
      >
        {/* Header */}
        <div className="sticky top-0 bg-white dark:bg-neutral-800 border-b dark:border-neutral-700 px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 min-w-0">
              <span
                className={`flex-shrink-0 w-3 h-3 rounded-full ${status.dot} ${live ? 'animate-pulse' : ''}`}
              />
              <h2 className="text-lg font-semibold text-neutral-900 dark:text-white truncate">
                {gw.display_name}
              </h2>
            </div>
            <button
              onClick={onClose}
              className="text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 text-xl leading-none ml-2"
              aria-label="Close"
            >
              &times;
            </button>
          </div>
          <div className="flex items-center gap-2 mt-1">
            <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${status.badge}`}>
              {status.label}
            </span>
            {gw.mode && (
              <span className="px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider rounded bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400">
                {MODE_LABELS[gw.mode] ?? gw.mode}
              </span>
            )}
            <span className="text-xs text-neutral-400">{typeInfo.label}</span>
          </div>
        </div>

        <div className="px-6 py-5 space-y-6">
          {/* Heartbeat Metrics */}
          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-500 dark:text-neutral-400 mb-3">
              Heartbeat
            </h3>
            <div className="grid grid-cols-3 gap-2">
              <MetricCard
                label="Uptime"
                value={
                  typeof hd.uptime_seconds === 'number' ? formatUptime(hd.uptime_seconds) : '--'
                }
              />
              <MetricCard
                label="Routes"
                value={hd.routes_count != null ? String(hd.routes_count) : '--'}
              />
              <MetricCard
                label="Error Rate"
                value={errorRate !== null ? `${(errorRate * 100).toFixed(1)}%` : '--'}
                warn={errorRate !== null && errorRate > 0.05}
              />
            </div>
          </section>

          {/* Instance Info */}
          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-500 dark:text-neutral-400 mb-3">
              Configuration
            </h3>
            <dl className="space-y-3 text-sm">
              <DetailRow label="Name" value={gw.name} mono />
              <DetailRow label="Type" value={typeInfo.label} />
              <DetailRow label="Environment" value={gw.environment} />
              <DetailRow
                label="Base URL"
                value={
                  <a
                    href={gw.base_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 font-mono text-xs text-blue-600 dark:text-blue-400 hover:underline truncate max-w-[220px]"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {gw.base_url.replace(/^https?:\/\//, '')}
                    <ExternalLink className="w-3 h-3 flex-shrink-0" />
                  </a>
                }
              />
              {gw.tenant_id && <DetailRow label="Tenant" value={gw.tenant_id} />}
              {gw.version && <DetailRow label="Version" value={gw.version} mono />}
              <DetailRow label="Created" value={new Date(gw.created_at).toLocaleDateString()} />
              {gw.last_health_check && (
                <DetailRow label="Last Check" value={timeAgo(gw.last_health_check)} />
              )}
            </dl>
          </section>

          {/* Capabilities */}
          {gw.capabilities.length > 0 && (
            <section>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-500 dark:text-neutral-400 mb-2">
                Capabilities
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {gw.capabilities.map((cap) => (
                  <span
                    key={cap}
                    className="px-2 py-1 bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300 text-xs rounded-md"
                  >
                    {cap}
                  </span>
                ))}
              </div>
            </section>
          )}

          {/* Tags */}
          {gw.tags.length > 0 && (
            <section>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-500 dark:text-neutral-400 mb-2">
                Tags
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {gw.tags.map((tag) => (
                  <span
                    key={tag}
                    className="px-2 py-1 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 text-xs rounded-md"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </section>
          )}

          {/* Raw Health Details */}
          {Object.keys(hd).length > 0 && (
            <section>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-500 dark:text-neutral-400 mb-2">
                Health Details
              </h3>
              <pre className="text-xs bg-neutral-50 dark:bg-neutral-900 rounded-lg p-3 overflow-x-auto text-neutral-700 dark:text-neutral-300">
                {JSON.stringify(hd, null, 2)}
              </pre>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Small UI atoms
// ---------------------------------------------------------------------------

function MetricCard({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="bg-neutral-50 dark:bg-neutral-700/50 rounded-lg p-3">
      <dt className="text-[11px] text-neutral-500 dark:text-neutral-400">{label}</dt>
      <dd
        className={`text-base font-semibold mt-0.5 ${warn ? 'text-orange-600 dark:text-orange-400' : 'text-neutral-900 dark:text-white'}`}
      >
        {value}
      </dd>
    </div>
  );
}

function DetailRow({
  label,
  value,
  mono,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex justify-between items-center">
      <dt className="text-neutral-500 dark:text-neutral-400">{label}</dt>
      <dd
        className={`text-neutral-900 dark:text-white text-right truncate max-w-[60%] ${mono ? 'font-mono text-xs' : ''}`}
      >
        {value}
      </dd>
    </div>
  );
}
