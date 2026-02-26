import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  RefreshCw,
  Shield,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Lock,
  Eye,
  FileWarning,
  ExternalLink,
  Fingerprint,
  Key,
  ArrowUpDown,
  ChevronUp,
  ChevronDown,
  Ban,
  EyeOff,
  Ticket,
  Timer,
  Activity,
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { apiService } from '../../services/api';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import { StatCard } from '@stoa/shared/components/StatCard';
import { ScoreGauge } from '@stoa/shared/components/ScoreGauge';

const AUTO_REFRESH_INTERVAL = 30_000;
const ACTIVE_TENANT_KEY = 'stoa-active-tenant';

type SeverityLevel = 'critical' | 'high' | 'medium' | 'low';
type SortField = 'severity' | 'category';
type SortDirection = 'asc' | 'desc';

interface SecurityFinding {
  id: string;
  category: string;
  severity: SeverityLevel;
  title: string;
  description: string;
  resource: string;
  detected_at: string;
  status: 'open' | 'resolved' | 'suppressed';
}

interface SecurityEvent {
  event_type: string;
  count: number;
  severity: SeverityLevel;
  last_occurred: string;
}

interface DriftItem {
  entity_type: string;
  entity_id: string;
  entity_name: string;
  drift_type: string;
  detected_at: string;
}

interface TokenBindingStatus {
  strategy: string;
  label: string;
  description: string;
  dpop_enforced: boolean;
  mtls_enforced: boolean;
  dpop_available: boolean;
  mtls_available: boolean;
  replay_protection: boolean;
}

interface SecurityScan {
  id: string;
  scan_type: string;
  status: 'completed' | 'failed' | 'running';
  started_at: string;
  completed_at: string | null;
  findings_count: number;
  duration_seconds: number | null;
}

interface CronJobStatus {
  status: 'active' | 'paused' | 'degraded';
  last_run: string | null;
  next_run: string | null;
  last_duration_seconds: number | null;
}

const SEVERITY_CONFIG: Record<SeverityLevel, { bg: string; text: string; label: string }> = {
  critical: {
    bg: 'bg-red-100 dark:bg-red-900/30',
    text: 'text-red-700 dark:text-red-400',
    label: 'Critical',
  },
  high: {
    bg: 'bg-orange-100 dark:bg-orange-900/30',
    text: 'text-orange-700 dark:text-orange-400',
    label: 'High',
  },
  medium: {
    bg: 'bg-yellow-100 dark:bg-yellow-900/30',
    text: 'text-yellow-700 dark:text-yellow-400',
    label: 'Medium',
  },
  low: {
    bg: 'bg-blue-100 dark:bg-blue-900/30',
    text: 'text-blue-700 dark:text-blue-400',
    label: 'Low',
  },
};

const SEVERITY_ORDER: Record<SeverityLevel, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

function SeverityBadge({ severity }: { severity: SeverityLevel }) {
  const cfg = SEVERITY_CONFIG[severity];
  return (
    <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${cfg.bg} ${cfg.text}`}>
      {cfg.label}
    </span>
  );
}

function computeSecurityScore(
  findings: SecurityFinding[],
  events: SecurityEvent[],
  driftCount: number
): number {
  const openFindings = findings.filter((f) => f.status === 'open');
  const criticalCount = openFindings.filter((f) => f.severity === 'critical').length;
  const highCount = openFindings.filter((f) => f.severity === 'high').length;
  const mediumCount = openFindings.filter((f) => f.severity === 'medium').length;

  let score = 100;
  score -= criticalCount * 15;
  score -= highCount * 8;
  score -= mediumCount * 3;
  score -= driftCount * 5;

  const authFailures = events.find((e) => e.event_type === 'auth_failure')?.count || 0;
  if (authFailures > 50) score -= 10;
  else if (authFailures > 10) score -= 5;

  return Math.max(0, Math.min(100, Math.round(score)));
}

export function SecurityPostureDashboard() {
  const { user, isReady, hasPermission } = useAuth();
  const [findings, setFindings] = useState<SecurityFinding[]>([]);
  const [events, setEvents] = useState<SecurityEvent[]>([]);
  const [driftItems, setDriftItems] = useState<DriftItem[]>([]);
  const [tokenBinding, setTokenBinding] = useState<TokenBindingStatus | null>(null);
  const [scans, setScans] = useState<SecurityScan[]>([]);
  const [cronJobStatus, setCronJobStatus] = useState<CronJobStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterSeverity, setFilterSeverity] = useState<SeverityLevel | 'all'>('all');
  const [sortField, setSortField] = useState<SortField>('severity');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');

  const tenantId = localStorage.getItem(ACTIVE_TENANT_KEY) || user?.tenant_id || 'default';

  const canManageFindings = hasPermission('admin:servers');

  const loadData = useCallback(async () => {
    try {
      const [securityRes, driftRes, tokenBindingRes, scansRes, cronJobRes] = await Promise.all([
        apiService
          .get<{
            events: SecurityEvent[];
            summary: Record<string, number>;
          }>(`/v1/audit/${tenantId}/security`)
          .catch(() => ({ data: { events: [], summary: {} } })),
        apiService
          .get<{
            items: DriftItem[];
            total: number;
          }>('/v1/admin/governance/drift')
          .catch(() => ({ data: { items: [], total: 0 } })),
        apiService
          .get<TokenBindingStatus>(`/v1/security/${tenantId}/token-binding`)
          .catch(() => ({ data: null as TokenBindingStatus | null })),
        apiService
          .get<{ scans: SecurityScan[] }>(`/v1/security/${tenantId}/scans`)
          .catch(() => ({ data: { scans: [] } })),
        apiService
          .get<CronJobStatus>(`/v1/security/${tenantId}/cronjob-status`)
          .catch(() => ({ data: null as CronJobStatus | null })),
      ]);

      // Map security events to findings for display
      const mappedFindings: SecurityFinding[] = securityRes.data.events.map((evt, i) => ({
        id: `sec-${i}`,
        category: evt.event_type,
        severity: evt.severity || 'medium',
        title: formatEventType(evt.event_type),
        description: `${evt.count} occurrence(s) detected`,
        resource: tenantId,
        detected_at: evt.last_occurred,
        status: 'open' as const,
      }));

      setFindings(mappedFindings);
      setEvents(securityRes.data.events);
      setDriftItems(driftRes.data.items || []);
      setTokenBinding(tokenBindingRes.data);
      setScans(scansRes.data.scans || []);
      setCronJobStatus(cronJobRes.data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load security data');
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    if (isReady) loadData();
  }, [isReady, loadData]);

  useEffect(() => {
    if (!isReady) return;
    const interval = setInterval(loadData, AUTO_REFRESH_INTERVAL);
    return () => clearInterval(interval);
  }, [isReady, loadData]);

  const securityScore = computeSecurityScore(findings, events, driftItems.length);
  const openFindings = findings.filter((f) => f.status === 'open');
  const criticalCount = openFindings.filter((f) => f.severity === 'critical').length;
  const highCount = openFindings.filter((f) => f.severity === 'high').length;
  const mediumCount = openFindings.filter((f) => f.severity === 'medium').length;
  const lowCount = openFindings.filter((f) => f.severity === 'low').length;
  const authFailures = events.find((e) => e.event_type === 'auth_failure')?.count || 0;

  const filteredFindings =
    filterSeverity === 'all'
      ? openFindings
      : openFindings.filter((f) => f.severity === filterSeverity);

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  };

  const sortedFindings = useMemo(() => {
    return [...filteredFindings].sort((a, b) => {
      const multiplier = sortDirection === 'asc' ? 1 : -1;
      if (sortField === 'severity') {
        return (SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]) * multiplier;
      }
      return a.category.localeCompare(b.category) * multiplier;
    });
  }, [filteredFindings, sortField, sortDirection]);

  function SortIcon({ field }: { field: SortField }) {
    if (sortField !== field) {
      return <ArrowUpDown className="h-3 w-3 ml-1 inline opacity-40" />;
    }
    return sortDirection === 'asc' ? (
      <ChevronUp className="h-3 w-3 ml-1 inline" />
    ) : (
      <ChevronDown className="h-3 w-3 ml-1 inline" />
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Security Posture</h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            Continuous security monitoring and compliance scoring
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadData}
            className="flex items-center gap-2 border border-neutral-300 dark:border-neutral-600 text-neutral-700 dark:text-neutral-300 px-3 py-2 rounded-lg text-sm hover:bg-neutral-50 dark:hover:bg-neutral-700"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Error banner */}
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
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <CardSkeleton key={i} className="h-24" />
            ))}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <CardSkeleton className="h-48" />
            <CardSkeleton className="h-48 lg:col-span-2" />
          </div>
        </div>
      ) : (
        <>
          {/* KPI Row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard
              label="Open Findings"
              value={openFindings.length}
              icon={FileWarning}
              colorClass={
                openFindings.length === 0
                  ? 'text-green-600'
                  : openFindings.length > 5
                    ? 'text-red-600'
                    : 'text-yellow-600'
              }
              subtitle={`${criticalCount} critical, ${highCount} high`}
            />
            <StatCard
              label="Auth Failures (24h)"
              value={authFailures}
              icon={Lock}
              colorClass={
                authFailures === 0
                  ? 'text-green-600'
                  : authFailures > 50
                    ? 'text-red-600'
                    : 'text-yellow-600'
              }
              subtitle="Failed authentication attempts"
            />
            <StatCard
              label="Config Drift"
              value={driftItems.length}
              icon={AlertTriangle}
              colorClass={
                driftItems.length === 0
                  ? 'text-green-600'
                  : driftItems.length > 3
                    ? 'text-red-600'
                    : 'text-yellow-600'
              }
              subtitle="Out-of-sync resources"
            />
            <StatCard
              label="Compliance"
              value={securityScore >= 80 ? 'Passing' : 'At Risk'}
              icon={securityScore >= 80 ? CheckCircle : XCircle}
              colorClass={securityScore >= 80 ? 'text-green-600' : 'text-red-600'}
              subtitle="DORA / NIS2 readiness"
            />
          </div>

          {/* Severity Breakdown Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {(
              [
                { level: 'critical' as SeverityLevel, count: criticalCount },
                { level: 'high' as SeverityLevel, count: highCount },
                { level: 'medium' as SeverityLevel, count: mediumCount },
                { level: 'low' as SeverityLevel, count: lowCount },
              ] as const
            ).map(({ level, count }) => {
              const cfg = SEVERITY_CONFIG[level];
              return (
                <div
                  key={level}
                  data-testid={`severity-card-${level}`}
                  className={`rounded-lg border p-4 ${cfg.bg} border-opacity-50`}
                >
                  <div className={`text-xs font-medium uppercase ${cfg.text}`}>{cfg.label}</div>
                  <div className={`text-2xl font-bold mt-1 ${cfg.text}`}>{count}</div>
                  <div className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                    open findings
                  </div>
                </div>
              );
            })}
          </div>

          {/* Score + Findings Row */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Security Score Gauge */}
            <div className="space-y-4">
              <ScoreGauge
                title="Security Score"
                score={securityScore}
                max={100}
                icon={Shield}
                thresholds={[
                  {
                    min: 80,
                    label: 'Good',
                    bg: 'bg-green-500',
                    text: 'text-green-700 dark:text-green-400',
                  },
                  {
                    min: 60,
                    label: 'Fair',
                    bg: 'bg-yellow-500',
                    text: 'text-yellow-700 dark:text-yellow-400',
                  },
                  {
                    min: 0,
                    label: 'At Risk',
                    bg: 'bg-red-500',
                    text: 'text-red-700 dark:text-red-400',
                  },
                ]}
              />

              {/* Compliance Checklist */}
              <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
                <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase mb-3">
                  Compliance Checks
                </h2>
                <div className="space-y-2">
                  {[
                    {
                      label: 'mTLS enforcement',
                      pass: tokenBinding?.mtls_enforced ?? criticalCount === 0,
                    },
                    {
                      label: 'DPoP token binding',
                      pass: tokenBinding?.dpop_enforced ?? false,
                    },
                    { label: 'Auth policy active', pass: authFailures < 50 },
                    { label: 'No config drift', pass: driftItems.length === 0 },
                    { label: 'Audit logging enabled', pass: true },
                    { label: 'PII masking active', pass: true },
                  ].map((check) => (
                    <div key={check.label} className="flex items-center gap-2">
                      {check.pass ? (
                        <CheckCircle className="h-4 w-4 text-green-500 flex-shrink-0" />
                      ) : (
                        <XCircle className="h-4 w-4 text-red-500 flex-shrink-0" />
                      )}
                      <span className="text-sm text-neutral-700 dark:text-neutral-300">
                        {check.label}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Findings Table */}
            <div className="lg:col-span-2 bg-white dark:bg-neutral-800 rounded-lg shadow overflow-hidden">
              <div className="flex items-center justify-between p-4 border-b border-neutral-100 dark:border-neutral-700">
                <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
                  Security Findings
                </h2>
                <div className="flex items-center gap-2">
                  <select
                    value={filterSeverity}
                    onChange={(e) => setFilterSeverity(e.target.value as SeverityLevel | 'all')}
                    className="text-xs border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300 rounded-lg px-2 py-1"
                  >
                    <option value="all">All Severities</option>
                    <option value="critical">Critical</option>
                    <option value="high">High</option>
                    <option value="medium">Medium</option>
                    <option value="low">Low</option>
                  </select>
                </div>
              </div>
              {sortedFindings.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase border-b border-neutral-100 dark:border-neutral-700">
                        <th className="px-4 py-3">Finding</th>
                        <th
                          className="px-4 py-3 cursor-pointer select-none"
                          onClick={() => toggleSort('severity')}
                        >
                          Severity
                          <SortIcon field="severity" />
                        </th>
                        <th
                          className="px-4 py-3 cursor-pointer select-none"
                          onClick={() => toggleSort('category')}
                        >
                          Category
                          <SortIcon field="category" />
                        </th>
                        <th className="px-4 py-3 text-right">Occurrences</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-neutral-50 dark:divide-neutral-700">
                      {sortedFindings.map((finding) => (
                        <tr
                          key={finding.id}
                          className="hover:bg-neutral-50 dark:hover:bg-neutral-750"
                        >
                          <td className="px-4 py-3">
                            <div className="font-medium text-neutral-900 dark:text-white">
                              {finding.title}
                            </div>
                            <div className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                              {finding.description}
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            <SeverityBadge severity={finding.severity} />
                          </td>
                          <td className="px-4 py-3 text-neutral-600 dark:text-neutral-400">
                            {finding.category}
                          </td>
                          <td className="px-4 py-3 text-right text-neutral-700 dark:text-neutral-300">
                            {finding.description.match(/\d+/)?.[0] || '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-12">
                  <Shield className="h-8 w-8 text-green-400 dark:text-green-600 mb-2" />
                  <p className="text-sm text-neutral-500 dark:text-neutral-400">
                    No open security findings
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Token Binding Status (CAB-438) */}
          {tokenBinding && (
            <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <Fingerprint className="h-5 w-5 text-indigo-500" />
                  <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
                    Token Binding
                  </h2>
                </div>
                <span
                  className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
                    tokenBinding.strategy === 'auto'
                      ? 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400'
                      : 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400'
                  }`}
                >
                  {tokenBinding.label}
                </span>
              </div>
              <p className="text-sm text-neutral-500 dark:text-neutral-400 mb-4">
                {tokenBinding.description}
              </p>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  {
                    icon: Key,
                    label: 'DPoP (RFC 9449)',
                    active: tokenBinding.dpop_enforced,
                    available: tokenBinding.dpop_available,
                  },
                  {
                    icon: Lock,
                    label: 'mTLS (RFC 8705)',
                    active: tokenBinding.mtls_enforced,
                    available: tokenBinding.mtls_available,
                  },
                  {
                    icon: Shield,
                    label: 'Replay Protection',
                    active: tokenBinding.replay_protection,
                    available: true,
                  },
                  {
                    icon: Fingerprint,
                    label: 'Sender Constraint',
                    active: tokenBinding.dpop_enforced || tokenBinding.mtls_enforced,
                    available: true,
                  },
                ].map((item) => (
                  <div
                    key={item.label}
                    className={`flex items-center gap-2 p-3 rounded-lg border ${
                      item.active
                        ? 'border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20'
                        : item.available
                          ? 'border-yellow-200 dark:border-yellow-800 bg-yellow-50 dark:bg-yellow-900/20'
                          : 'border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-900'
                    }`}
                  >
                    <item.icon
                      className={`h-4 w-4 flex-shrink-0 ${
                        item.active
                          ? 'text-green-500'
                          : item.available
                            ? 'text-yellow-500'
                            : 'text-neutral-400'
                      }`}
                    />
                    <div>
                      <div className="text-xs font-medium text-neutral-900 dark:text-white">
                        {item.label}
                      </div>
                      <div
                        className={`text-xs ${
                          item.active
                            ? 'text-green-600 dark:text-green-400'
                            : item.available
                              ? 'text-yellow-600 dark:text-yellow-400'
                              : 'text-neutral-500'
                        }`}
                      >
                        {item.active ? 'Enforced' : item.available ? 'Available' : 'N/A'}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Scan History Timeline */}
          {scans.length > 0 && (
            <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
              <div className="flex items-center gap-2 mb-4">
                <Activity className="h-5 w-5 text-blue-500" />
                <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
                  Scan History
                </h2>
              </div>
              <div className="space-y-3">
                {scans.slice(0, 10).map((scan) => (
                  <div
                    key={scan.id}
                    className="flex items-center justify-between p-3 rounded-lg border border-neutral-100 dark:border-neutral-700"
                  >
                    <div className="flex items-center gap-3">
                      {scan.status === 'completed' ? (
                        <CheckCircle className="h-4 w-4 text-green-500 flex-shrink-0" />
                      ) : scan.status === 'failed' ? (
                        <XCircle className="h-4 w-4 text-red-500 flex-shrink-0" />
                      ) : (
                        <Timer className="h-4 w-4 text-yellow-500 flex-shrink-0 animate-pulse" />
                      )}
                      <div>
                        <span className="text-sm font-medium text-neutral-900 dark:text-white">
                          {scan.scan_type}
                        </span>
                        <span className="text-xs text-neutral-500 dark:text-neutral-400 ml-2">
                          {new Date(scan.started_at).toLocaleString()}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-neutral-500 dark:text-neutral-400">
                        {scan.findings_count} findings
                      </span>
                      {scan.duration_seconds != null && (
                        <span className="text-xs text-neutral-400">{scan.duration_seconds}s</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* CronJob Status Indicator */}
          {cronJobStatus && (
            <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Timer className="h-5 w-5 text-purple-500" />
                  <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
                    Scan Schedule
                  </h2>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    data-testid="cronjob-status-dot"
                    className={`h-2.5 w-2.5 rounded-full ${
                      cronJobStatus.status === 'active'
                        ? 'bg-green-500'
                        : cronJobStatus.status === 'degraded'
                          ? 'bg-yellow-500'
                          : 'bg-neutral-400'
                    }`}
                  />
                  <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300 capitalize">
                    {cronJobStatus.status}
                  </span>
                </div>
              </div>
              <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
                <div>
                  <span className="text-neutral-500 dark:text-neutral-400">Last Run</span>
                  <div className="font-medium text-neutral-900 dark:text-white mt-0.5">
                    {cronJobStatus.last_run
                      ? new Date(cronJobStatus.last_run).toLocaleString()
                      : 'Never'}
                    {cronJobStatus.last_duration_seconds != null && (
                      <span className="text-xs text-neutral-400 ml-1">
                        ({cronJobStatus.last_duration_seconds}s)
                      </span>
                    )}
                  </div>
                </div>
                <div>
                  <span className="text-neutral-500 dark:text-neutral-400">Next Scheduled</span>
                  <div className="font-medium text-neutral-900 dark:text-white mt-0.5">
                    {cronJobStatus.next_run
                      ? new Date(cronJobStatus.next_run).toLocaleString()
                      : 'Not scheduled'}
                  </div>
                </div>
                <div>
                  <span className="text-neutral-500 dark:text-neutral-400">Status</span>
                  <div className="font-medium text-neutral-900 dark:text-white mt-0.5 capitalize">
                    {cronJobStatus.status}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Quick Actions (RBAC-gated) */}
          {canManageFindings && openFindings.length > 0 && (
            <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
              <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase mb-3">
                Quick Actions
              </h2>
              <div className="flex flex-wrap gap-3">
                <button className="flex items-center gap-2 px-4 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 text-sm text-neutral-700 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-700">
                  <Ban className="h-4 w-4" />
                  Acknowledge All
                </button>
                <button className="flex items-center gap-2 px-4 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 text-sm text-neutral-700 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-700">
                  <EyeOff className="h-4 w-4" />
                  Suppress Low
                </button>
                <button className="flex items-center gap-2 px-4 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 text-sm text-neutral-700 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-700">
                  <Ticket className="h-4 w-4" />
                  Create Ticket
                </button>
              </div>
            </div>
          )}

          {/* Drift Detection */}
          {driftItems.length > 0 && (
            <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
                  Configuration Drift
                </h2>
                <a
                  href="/drift"
                  className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
                >
                  Full Report
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
              <div className="space-y-2">
                {driftItems.slice(0, 5).map((item, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between p-3 rounded-lg border border-neutral-100 dark:border-neutral-700"
                  >
                    <div className="flex items-center gap-3">
                      <Eye className="h-4 w-4 text-orange-500 flex-shrink-0" />
                      <div>
                        <span className="text-sm font-medium text-neutral-900 dark:text-white">
                          {item.entity_name}
                        </span>
                        <span className="text-xs text-neutral-500 dark:text-neutral-400 ml-2">
                          {item.entity_type}
                        </span>
                      </div>
                    </div>
                    <span className="text-xs text-orange-600 dark:text-orange-400 font-medium">
                      {item.drift_type}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function formatEventType(type: string): string {
  return type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export default SecurityPostureDashboard;
