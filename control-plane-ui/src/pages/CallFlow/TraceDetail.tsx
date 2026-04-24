import { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Clock,
  Shield,
  Server,
  RefreshCw,
  AlertTriangle,
  CheckCircle,
  Globe,
  Cpu,
  Network,
  Lock,
} from 'lucide-react';
import { StatCard } from '@stoa/shared/components/StatCard';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';

// ─── Types ───
// Canonical: `Schemas['TransactionDetailWithDemoResponse']` from the backend
// OpenAPI snapshot (see services/api/monitoring.ts).

import type { Schemas } from '@stoa/shared/api-types';
import type { MonitoringTransactionDetail } from '../../services/api/monitoring';

type TransactionDetail = MonitoringTransactionDetail;
type TransactionSpan = Schemas['TransactionSpan'];

// ─── Helpers ───

const SENSITIVE_HEADERS = ['authorization', 'cookie', 'x-api-key', 'set-cookie'];

function redactHeaders(
  headers: Record<string, unknown> | null | undefined
): Record<string, string> {
  if (!headers) return {};
  const result: Record<string, string> = {};
  for (const [key, value] of Object.entries(headers)) {
    if (SENSITIVE_HEADERS.includes(key.toLowerCase())) {
      result[key] = '••••••••';
    } else {
      result[key] = typeof value === 'string' ? value : String(value);
    }
  }
  return result;
}

/** Format duration: µs when < 1ms, ms with decimals when < 10ms, whole ms otherwise. */
function fmtDuration(ms: number): string {
  if (ms <= 0) return '0µs';
  if (ms < 0.01) return `${(ms * 1000).toFixed(0)}µs`;
  if (ms < 1) return `${(ms * 1000).toFixed(0)}µs`;
  if (ms < 10) return `${ms.toFixed(2)}ms`;
  if (ms < 100) return `${ms.toFixed(1)}ms`;
  return `${Math.round(ms)}ms`;
}

const SPAN_COLORS: Record<string, string> = {
  gateway_ingress: '#3B82F6',
  auth_validation: '#8B5CF6',
  rate_limiting: '#F59E0B',
  backend_call: '#10B981',
  database_query: '#06B6D4',
  response_transform: '#6366F1',
  tls_termination: '#EC4899',
  request_validation: '#14B8A6',
  token_exchange: '#A855F7',
  upstream_proxy: '#10B981',
  error: '#EF4444',
};

function spanColor(name: string, status: string): string {
  if (status === 'error') return SPAN_COLORS.error;
  return SPAN_COLORS[name] || '#6B7280';
}

function statusConfig(code: number): {
  label: string;
  bg: string;
  text: string;
  icon: typeof CheckCircle;
} {
  if (code >= 500)
    return {
      label: 'ERROR',
      bg: 'bg-red-100 dark:bg-red-900/30',
      text: 'text-red-700 dark:text-red-400',
      icon: AlertTriangle,
    };
  if (code >= 400)
    return {
      label: 'CLIENT ERROR',
      bg: 'bg-yellow-100 dark:bg-yellow-900/30',
      text: 'text-yellow-700 dark:text-yellow-400',
      icon: AlertTriangle,
    };
  return {
    label: 'SUCCESS',
    bg: 'bg-green-100 dark:bg-green-900/30',
    text: 'text-green-700 dark:text-green-400',
    icon: CheckCircle,
  };
}

// ─── Fetch (authenticated via apiService) ───

import { apiService } from '../../services/api';

async function fetchTraceDetail(traceId: string): Promise<TransactionDetail | null> {
  try {
    return await apiService.getTransactionDetail(traceId);
  } catch {
    return null;
  }
}

// ─── Sub-Components ───

function TraceWaterfall({ spans, totalMs }: { spans: TransactionSpan[]; totalMs: number }) {
  if (totalMs <= 0 || spans.length === 0) return null;

  const ruler = [0, 0.25, 0.5, 0.75, 1].map((f) => f * totalMs);

  return (
    <div>
      {/* Ruler */}
      <div className="flex justify-between text-[10px] text-neutral-400 dark:text-neutral-500 mb-1 px-28">
        {ruler.map((ms, idx) => (
          <span key={idx} className="tabular-nums">
            {fmtDuration(ms)}
          </span>
        ))}
      </div>

      {/* Spans */}
      <div className="space-y-1">
        {spans.map((span, i) => {
          const left = (span.start_offset_ms / totalMs) * 100;
          const width = Math.max((span.duration_ms / totalMs) * 100, 1);
          const isError = span.status === 'error';

          return (
            <div key={i} className="flex items-center gap-2">
              <div className="w-28 text-right">
                <span className="text-xs font-mono text-neutral-600 dark:text-neutral-400 truncate block">
                  {span.name.replace(/_/g, ' ')}
                </span>
              </div>
              <div className="flex-1 relative h-6 bg-neutral-100 dark:bg-neutral-700 rounded overflow-hidden">
                <div
                  className={`absolute top-0.5 bottom-0.5 rounded ${isError ? 'animate-pulse' : ''}`}
                  style={{
                    left: `${left}%`,
                    width: `${width}%`,
                    backgroundColor: spanColor(span.name, span.status),
                  }}
                  title={`${span.name} (${span.service}) — ${fmtDuration(span.duration_ms)}`}
                />
              </div>
              <div className="w-16 text-right">
                <span
                  className={`text-xs tabular-nums ${isError ? 'text-red-500 font-semibold' : 'text-neutral-500 dark:text-neutral-400'}`}
                >
                  {fmtDuration(span.duration_ms)}
                </span>
              </div>
              <div className="w-20 text-right">
                <span className="text-[10px] text-neutral-400 dark:text-neutral-500 truncate block">
                  {span.service}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function HeadersPanel({ headers, title }: { headers: Record<string, string>; title: string }) {
  const entries = Object.entries(headers).filter(([, v]) => v !== '');

  if (entries.length === 0) {
    return (
      <div className="text-sm text-neutral-400 dark:text-neutral-500 py-4 text-center">
        No {title.toLowerCase()} available
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {entries.map(([key, value]) => (
        <div
          key={key}
          className="flex gap-2 text-xs py-1 border-b border-neutral-100 dark:border-neutral-700 last:border-0"
        >
          <span className="font-mono font-semibold text-neutral-600 dark:text-neutral-300 min-w-[180px] break-all">
            {key}
          </span>
          <span
            className={`font-mono break-all ${value === '••••••••' ? 'text-neutral-400 italic' : 'text-neutral-500 dark:text-neutral-400'}`}
          >
            {value}
          </span>
        </div>
      ))}
    </div>
  );
}

function MiddlewarePipeline({ spans }: { spans: TransactionSpan[] }) {
  return (
    <div className="space-y-2">
      {spans.map((span, i) => {
        const isError = span.status === 'error';
        return (
          <div
            key={i}
            className={`flex items-center gap-3 px-3 py-2 rounded-lg ${
              isError
                ? 'bg-red-50 dark:bg-red-900/10 border border-red-200 dark:border-red-800'
                : 'bg-neutral-50 dark:bg-neutral-800/50'
            }`}
          >
            <span className="text-sm">
              {isError ? (
                <AlertTriangle className="h-4 w-4 text-red-500" />
              ) : (
                <CheckCircle className="h-4 w-4 text-green-500" />
              )}
            </span>
            <div className="flex-1">
              <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300 capitalize">
                {span.name.replace(/_/g, ' ')}
              </span>
              <span className="text-xs text-neutral-400 dark:text-neutral-500 ml-2">
                ({span.service})
              </span>
            </div>
            <span
              className={`text-xs tabular-nums font-medium ${isError ? 'text-red-600' : 'text-neutral-500 dark:text-neutral-400'}`}
            >
              {fmtDuration(span.duration_ms)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/** Extract kernel metrics from span metadata (real data from gateway OTLP spans). */
function extractKernelMetrics(spans: TransactionSpan[]): Record<string, string | undefined> {
  const m: Record<string, string | undefined> = {};
  for (const span of spans) {
    if (!span.metadata) continue;
    for (const [key, val] of Object.entries(span.metadata)) {
      if (val !== undefined && val !== null && val !== '') {
        m[key] = String(val);
      }
    }
  }
  return m;
}

function formatBytes(bytes: string | undefined): string {
  if (!bytes) return 'N/A';
  const n = Number(bytes);
  if (isNaN(n)) return bytes;
  if (n >= 1024 * 1024 * 1024) return `${(n / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  if (n >= 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(0)} MB`;
  if (n >= 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${n} B`;
}

function MetricValue({ value }: { value: string | undefined }) {
  const isNA = !value || value === 'N/A';
  return (
    <span
      className={`font-mono tabular-nums ${isNA ? 'text-neutral-400 dark:text-neutral-500 italic' : 'text-neutral-700 dark:text-neutral-300'}`}
    >
      {value || 'N/A'}
    </span>
  );
}

function KernelMetricsGrid({ spans }: { spans: TransactionSpan[] }) {
  const m = extractKernelMetrics(spans);
  const hasAnyReal = Object.keys(m).some(
    (k) => k.startsWith('upstream.') || k.startsWith('process.')
  );

  const rttMs = m['upstream.rtt_ms'];
  const poolReuse = m['upstream.pool_reuse'];
  const cbState = m['upstream.cb_state'];
  const activeConns = m['upstream.active_conns'];
  const rssBytesRaw = m['process.rss_bytes'];
  const fdCount = m['process.fd_count'];
  const threadCount = m['process.thread_count'];

  const quadrants = [
    {
      title: 'Network (Upstream)',
      icon: Globe,
      metrics: [
        { label: 'Upstream RTT', value: rttMs ? `${rttMs}ms` : undefined },
        {
          label: 'Connection Reuse',
          value: poolReuse === 'true' ? 'Yes' : poolReuse === 'false' ? 'No' : undefined,
        },
        { label: 'Circuit Breaker', value: cbState },
      ],
    },
    {
      title: 'Process (Gateway)',
      icon: Cpu,
      metrics: [
        {
          label: 'RSS',
          value: formatBytes(rssBytesRaw) !== 'N/A' ? formatBytes(rssBytesRaw) : undefined,
        },
        { label: 'FD Count', value: fdCount && fdCount !== '0' ? fdCount : undefined },
        { label: 'Threads', value: threadCount && threadCount !== '0' ? threadCount : undefined },
      ],
    },
    {
      title: 'Connection Pool',
      icon: Server,
      metrics: [
        {
          label: 'Active Conns',
          value: activeConns != null ? activeConns : undefined,
        },
        {
          label: 'Pool Reuse',
          value: poolReuse === 'true' ? 'Yes' : poolReuse === 'false' ? 'No' : undefined,
        },
        { label: 'Upstream RTT', value: rttMs ? `${rttMs}ms` : undefined },
      ],
    },
    {
      title: 'Resilience',
      icon: Lock,
      metrics: [
        { label: 'Circuit Breaker', value: cbState },
        {
          label: 'RSS Pressure',
          value:
            rssBytesRaw && Number(rssBytesRaw) > 0
              ? Number(rssBytesRaw) > 256 * 1024 * 1024
                ? 'High'
                : 'Normal'
              : undefined,
        },
        {
          label: 'Open FDs',
          value:
            fdCount && Number(fdCount) > 0
              ? Number(fdCount) > 1000
                ? 'High'
                : 'Normal'
              : undefined,
        },
      ],
    },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {quadrants.map((q) => (
        <div key={q.title} className="bg-neutral-50 dark:bg-neutral-800/50 rounded-lg p-3">
          <div className="flex items-center gap-2 mb-3">
            <q.icon className="h-4 w-4 text-neutral-500" />
            <h4 className="text-xs font-semibold text-neutral-600 dark:text-neutral-400 uppercase">
              {q.title}
            </h4>
          </div>
          <div className="space-y-1.5">
            {q.metrics.map((metric) => (
              <div key={metric.label} className="flex justify-between text-xs">
                <span className="text-neutral-500 dark:text-neutral-400">{metric.label}</span>
                <MetricValue value={metric.value} />
              </div>
            ))}
          </div>
        </div>
      ))}
      {!hasAnyReal && (
        <p className="col-span-2 text-xs text-neutral-400 italic text-center">
          No gateway metrics available for this trace.
        </p>
      )}
    </div>
  );
}

// ─── Main Component ───

export function TraceDetail() {
  const { traceId } = useParams<{ traceId: string }>();
  const navigate = useNavigate();
  const [state, setState] = useState<{ detail: TransactionDetail | null; loading: boolean }>({
    detail: null,
    loading: true,
  });
  const [headerTab, setHeaderTab] = useState<'request' | 'response'>('request');

  useEffect(() => {
    if (!traceId) return;
    let cancelled = false;
    fetchTraceDetail(traceId).then((d) => {
      if (!cancelled) setState({ detail: d, loading: false });
    });
    return () => {
      cancelled = true;
    };
  }, [traceId]);

  const { detail, loading } = state;

  const requestHeaders = useMemo(
    () => redactHeaders(detail?.request_headers ?? null),
    [detail?.request_headers]
  );
  const responseHeaders = useMemo(
    () => redactHeaders(detail?.response_headers ?? null),
    [detail?.response_headers]
  );

  if (loading) {
    return (
      <div className="space-y-6">
        <CardSkeleton className="h-16" />
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <CardSkeleton key={i} className="h-20" />
          ))}
        </div>
        <CardSkeleton className="h-[300px]" />
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="text-center py-20">
        <AlertTriangle className="h-8 w-8 text-neutral-300 dark:text-neutral-600 mx-auto mb-3" />
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          Trace not found — it may have expired or the trace ID is invalid
        </p>
        <button
          onClick={() => navigate('/call-flow')}
          className="mt-4 inline-flex items-center gap-1.5 text-sm text-blue-600 dark:text-blue-400 hover:underline"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Call Flow
        </button>
      </div>
    );
  }

  const sc = statusConfig(detail.status_code);
  const StatusIcon = sc.icon;

  return (
    <div className="space-y-6">
      {/* ─── Breadcrumb + Banner ─── */}
      <div>
        <button
          onClick={() => navigate('/call-flow')}
          className="flex items-center gap-1.5 text-sm text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 mb-3"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Call Flow
        </button>

        <div
          className={`${sc.bg} border ${detail.status_code >= 400 ? 'border-red-200 dark:border-red-800' : 'border-green-200 dark:border-green-800'} rounded-lg px-5 py-4 flex items-center justify-between flex-wrap gap-3`}
        >
          <div className="flex items-center gap-3">
            <StatusIcon className={`h-6 w-6 ${sc.text}`} />
            <div>
              <div className="flex items-center gap-2">
                <span className={`text-sm font-bold ${sc.text}`}>{sc.label}</span>
                <span className="text-sm font-mono text-neutral-600 dark:text-neutral-300">
                  {detail.method} {detail.path}
                </span>
              </div>
              <div className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                {new Date(detail.started_at).toLocaleString()} —{' '}
                {fmtDuration(detail.total_duration_ms)} —{' '}
                <span className="font-mono">{detail.trace_id}</span>
              </div>
            </div>
          </div>
          <span
            className={`inline-flex items-center px-2.5 py-1 text-xs font-bold rounded-full ${sc.bg} ${sc.text}`}
          >
            {detail.status_code} {detail.status_text}
          </span>
        </div>
      </div>

      {/* ─── 6 Summary Cards ─── */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <StatCard
          label="Status"
          value={String(detail.status_code)}
          subtitle={detail.status_text}
          colorClass={sc.text}
        />
        <StatCard
          label="Duration"
          value={fmtDuration(detail.total_duration_ms)}
          unit="ms"
          icon={Clock}
          colorClass={detail.total_duration_ms > 500 ? 'text-red-600' : 'text-green-600'}
          subtitle="Total request time"
        />
        <StatCard
          label="Gateway"
          value="stoa-gw"
          icon={Network}
          colorClass="text-blue-600"
          subtitle="edge-mcp mode"
        />
        <StatCard
          label="Auth"
          value={
            detail.spans.find((s) => s.name === 'auth_validation')?.duration_ms
              ? fmtDuration(detail.spans.find((s) => s.name === 'auth_validation')!.duration_ms)
              : '--'
          }
          icon={Shield}
          colorClass="text-purple-600"
          subtitle="Keycloak OIDC"
        />
        <StatCard
          label="Upstream"
          value={detail.spans.find((s) => s.name === 'backend_call')?.service || '--'}
          icon={Server}
          colorClass={detail.error_source === 'backend' ? 'text-red-600' : 'text-green-600'}
          subtitle={detail.error_source === 'backend' ? 'Error source' : 'Healthy'}
        />
        <StatCard
          label="Retries"
          value="0 / 3"
          icon={RefreshCw}
          colorClass="text-neutral-500"
          subtitle="No retries needed"
        />
      </div>

      {/* ─── Error message ─── */}
      {detail.error_message && (
        <div className="bg-red-50 dark:bg-red-900/10 border border-red-200 dark:border-red-800 rounded-lg px-4 py-3">
          <div className="flex items-center gap-2 mb-1">
            <AlertTriangle className="h-4 w-4 text-red-500" />
            <span className="text-sm font-semibold text-red-700 dark:text-red-400">Error</span>
          </div>
          <p className="text-sm text-red-600 dark:text-red-300 font-mono">{detail.error_message}</p>
        </div>
      )}

      {/* ─── Trace Waterfall ─── */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
        <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase mb-4">
          Trace Waterfall
        </h2>
        <TraceWaterfall spans={detail.spans} totalMs={detail.total_duration_ms} />
      </div>

      {/* ─── Request / Response Headers ─── */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
            Request / Response
          </h2>
          <div className="flex gap-1 bg-neutral-100 dark:bg-neutral-700 rounded-lg p-0.5">
            {(['request', 'response'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setHeaderTab(tab)}
                className={`px-3 py-1 text-xs font-medium rounded-md transition-colors capitalize ${
                  headerTab === tab
                    ? 'bg-white dark:bg-neutral-600 text-neutral-900 dark:text-white shadow-sm'
                    : 'text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200'
                }`}
              >
                {tab} Headers
              </button>
            ))}
          </div>
        </div>
        <HeadersPanel
          headers={headerTab === 'request' ? requestHeaders : responseHeaders}
          title={headerTab === 'request' ? 'Request Headers' : 'Response Headers'}
        />
      </div>

      {/* ─── Kernel Metrics ─── */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
            Gateway Metrics
          </h2>
        </div>
        <KernelMetricsGrid spans={detail.spans} />
      </div>

      {/* ─── Middleware Pipeline ─── */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
        <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase mb-4">
          Middleware Pipeline
        </h2>
        <MiddlewarePipeline spans={detail.spans} />
      </div>

      {/* ─── Correlated Events ─── */}
      {detail.status_code >= 400 && (
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
          <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase mb-4">
            Similar Errors (Last Hour)
          </h2>
          <div className="text-sm text-neutral-500 dark:text-neutral-400">
            <span className="font-semibold text-red-500">3</span> similar errors on{' '}
            <span className="font-mono">{detail.path}</span> with status{' '}
            <span className="font-mono">{detail.status_code}</span> in the last hour.
          </div>
        </div>
      )}
    </div>
  );
}

export default TraceDetail;
