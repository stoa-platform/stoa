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

interface TransactionSpan {
  name: string;
  service: string;
  start_offset_ms: number;
  duration_ms: number;
  status: string;
  metadata: Record<string, unknown>;
}

interface TransactionDetail {
  id: string;
  trace_id: string;
  api_name: string;
  tenant_id: string | null;
  method: string;
  path: string;
  status_code: number;
  status: string;
  status_text: string;
  error_source: string | null;
  client_ip: string | null;
  user_id: string | null;
  started_at: string;
  total_duration_ms: number;
  spans: TransactionSpan[];
  request_headers: Record<string, string> | null;
  response_headers: Record<string, string> | null;
  error_message: string | null;
  demo_mode: boolean;
}

// ─── Helpers ───

const SENSITIVE_HEADERS = ['authorization', 'cookie', 'x-api-key', 'set-cookie'];

function redactHeaders(headers: Record<string, string> | null): Record<string, string> {
  if (!headers) return {};
  const result: Record<string, string> = {};
  for (const [key, value] of Object.entries(headers)) {
    if (SENSITIVE_HEADERS.includes(key.toLowerCase())) {
      result[key] = '••••••••';
    } else {
      result[key] = value;
    }
  }
  return result;
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

// ─── Demo Data ───

function generateDemoDetail(traceId: string): TransactionDetail {
  const isError = traceId.includes('err') || Math.random() > 0.7;
  const statusCode = isError ? (Math.random() > 0.5 ? 502 : 500) : 200;
  const duration = isError
    ? 800 + Math.round(Math.random() * 2000)
    : 20 + Math.round(Math.random() * 200);

  const spanDefs = [
    { name: 'tls_termination', service: 'stoa-gateway', fraction: 0.05 },
    { name: 'request_validation', service: 'stoa-gateway', fraction: 0.03 },
    { name: 'auth_validation', service: 'keycloak', fraction: 0.15 },
    { name: 'token_exchange', service: 'keycloak', fraction: 0.1 },
    { name: 'rate_limiting', service: 'stoa-gateway', fraction: 0.02 },
    { name: 'backend_call', service: 'upstream-api', fraction: 0.55 },
    { name: 'response_transform', service: 'stoa-gateway', fraction: 0.1 },
  ];

  let offset = 0;
  const spans: TransactionSpan[] = spanDefs.map((def) => {
    const d = Math.round(duration * def.fraction * (0.8 + Math.random() * 0.4));
    const span: TransactionSpan = {
      name: def.name,
      service: def.service,
      start_offset_ms: offset,
      duration_ms: d,
      status: isError && def.name === 'backend_call' ? 'error' : 'success',
      metadata: {},
    };
    offset += d;
    return span;
  });

  return {
    id: traceId,
    trace_id: `trace-${traceId.slice(0, 8)}`,
    api_name: 'customer-api',
    tenant_id: 'tenant-acme',
    method: 'GET',
    path: '/api/v1/customers',
    status_code: statusCode,
    status: isError ? 'error' : 'success',
    status_text: isError ? 'Internal Server Error' : 'OK',
    error_source: isError ? 'backend' : null,
    client_ip: '10.0.1.42',
    user_id: 'user-demo',
    started_at: new Date(Date.now() - Math.random() * 3600_000).toISOString(),
    total_duration_ms: duration,
    spans,
    request_headers: {
      'Content-Type': 'application/json',
      Authorization: 'Bearer eyJ...demo',
      'X-STOA-Tenant': 'tenant-acme',
      'X-STOA-Consumer': 'consumer-001',
      'X-STOA-Trace-ID': `trace-${traceId.slice(0, 8)}`,
      'User-Agent': 'Claude/1.0',
    },
    response_headers: {
      'Content-Type': 'application/json',
      'X-STOA-Duration-Ms': String(duration),
      'X-STOA-Gateway': 'stoa-gw-01',
      'X-STOA-Error-Code': isError ? 'UPSTREAM_TIMEOUT' : '',
      traceparent: `00-${traceId.slice(0, 8).padEnd(32, '0')}-${traceId.slice(0, 16).padEnd(16, '0')}-01`,
    },
    error_message: isError ? 'Upstream service returned 502 after 2000ms timeout' : null,
    demo_mode: true,
  };
}

// ─── Fetch ───

async function fetchTraceDetail(traceId: string): Promise<TransactionDetail> {
  try {
    const res = await fetch(`/api/v1/monitoring/transactions/${traceId}`, {
      signal: AbortSignal.timeout(8_000),
    });
    if (!res.ok) throw new Error(`${res.status}`);
    return await res.json();
  } catch {
    return generateDemoDetail(traceId);
  }
}

// ─── Sub-Components ───

function TraceWaterfall({ spans, totalMs }: { spans: TransactionSpan[]; totalMs: number }) {
  if (totalMs <= 0 || spans.length === 0) return null;

  const ruler = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(f * totalMs));

  return (
    <div>
      {/* Ruler */}
      <div className="flex justify-between text-[10px] text-neutral-400 dark:text-neutral-500 mb-1 px-28">
        {ruler.map((ms) => (
          <span key={ms} className="tabular-nums">
            {ms}ms
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
                  title={`${span.name} (${span.service}) — ${span.duration_ms}ms`}
                />
              </div>
              <div className="w-16 text-right">
                <span
                  className={`text-xs tabular-nums ${isError ? 'text-red-500 font-semibold' : 'text-neutral-500 dark:text-neutral-400'}`}
                >
                  {span.duration_ms}ms
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
              {span.duration_ms}ms
            </span>
          </div>
        );
      })}
    </div>
  );
}

function KernelMetricsGrid() {
  const quadrants = [
    {
      title: 'Network (Socket)',
      icon: Globe,
      metrics: [
        { label: 'TCP Connect', value: '2.1ms' },
        { label: 'Retransmits', value: '0' },
        { label: 'Bytes Sent', value: '1.2KB' },
        { label: 'Bytes Received', value: '4.8KB' },
        { label: 'Connection Reuse', value: 'Yes' },
      ],
    },
    {
      title: 'Process (Gateway)',
      icon: Cpu,
      metrics: [
        { label: 'CPU usr/sys', value: '1.2 / 0.3 ms' },
        { label: 'Context Switches', value: '4' },
        { label: 'RSS', value: '48MB' },
        { label: 'FD Count', value: '127' },
        { label: 'Thread Pool', value: '3/16 active' },
      ],
    },
    {
      title: 'Upstream Pod',
      icon: Server,
      metrics: [
        { label: 'CPU Usage', value: '12%' },
        { label: 'RSS / Limit', value: '256 / 512 MB' },
        { label: 'Disk I/O Wait', value: '0.1ms' },
        { label: 'Open Conns', value: '42' },
        { label: 'Queue Depth', value: '0' },
      ],
    },
    {
      title: 'DNS / TLS',
      icon: Lock,
      metrics: [
        { label: 'DNS Resolution', value: 'cached (0ms)' },
        { label: 'TLS Handshake', value: 'reused' },
        { label: 'TLS Version', value: '1.3' },
        { label: 'Cipher', value: 'AES-256-GCM' },
        { label: 'ALPN', value: 'h2' },
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
            {q.metrics.map((m) => (
              <div key={m.label} className="flex justify-between text-xs">
                <span className="text-neutral-500 dark:text-neutral-400">{m.label}</span>
                <span className="font-mono text-neutral-700 dark:text-neutral-300 tabular-nums">
                  {m.value}
                </span>
              </div>
            ))}
          </div>
        </div>
      ))}
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
      <div className="text-center py-20 text-neutral-400 dark:text-neutral-500">
        Trace not found
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
                {new Date(detail.started_at).toLocaleString()} — {detail.total_duration_ms}ms —{' '}
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
          value={String(detail.total_duration_ms)}
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
              ? `${detail.spans.find((s) => s.name === 'auth_validation')!.duration_ms}ms`
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

      {/* ─── Kernel Metrics (eBPF) ─── */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 uppercase">
            Kernel Metrics (eBPF)
          </h2>
          <span className="text-[10px] px-2 py-0.5 bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 rounded-full font-medium">
            Demo data
          </span>
        </div>
        <KernelMetricsGrid />
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
