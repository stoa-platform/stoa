import { AlertTriangle } from 'lucide-react';

export interface TraceSpan {
  name: string;
  service: string;
  startOffsetMs: number;
  durationMs: number;
  status: 'success' | 'error' | 'timeout';
}

export interface TraceEntry {
  id: string;
  route: string;
  method: string;
  mode: string;
  statusCode: number;
  durationMs: number;
  timestamp: string;
  spans: TraceSpan[];
}

interface LiveTracesProps {
  traces: TraceEntry[];
  onSelectTrace?: (traceId: string) => void;
}

const SPAN_COLORS: Record<string, string> = {
  gateway_ingress: '#3B82F6',
  auth_validation: '#8B5CF6',
  rate_limiting: '#F59E0B',
  backend_call: '#10B981',
  database_query: '#06B6D4',
  response_transform: '#6366F1',
  error: '#EF4444',
};

function spanColor(name: string, status: string): string {
  if (status === 'error') return SPAN_COLORS.error;
  return SPAN_COLORS[name] || '#6B7280';
}

function statusBadge(code: number): { bg: string; text: string } {
  if (code >= 500)
    return { bg: 'bg-red-100 dark:bg-red-900/30', text: 'text-red-700 dark:text-red-400' };
  if (code >= 400)
    return {
      bg: 'bg-yellow-100 dark:bg-yellow-900/30',
      text: 'text-yellow-700 dark:text-yellow-400',
    };
  return { bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-700 dark:text-green-400' };
}

function modeBadge(mode: string): { bg: string; text: string } {
  const map: Record<string, { bg: string; text: string }> = {
    'edge-mcp': { bg: 'bg-blue-100 dark:bg-blue-900/30', text: 'text-blue-700 dark:text-blue-300' },
    sidecar: {
      bg: 'bg-green-100 dark:bg-green-900/30',
      text: 'text-green-700 dark:text-green-300',
    },
    connect: {
      bg: 'bg-orange-100 dark:bg-orange-900/30',
      text: 'text-orange-700 dark:text-orange-300',
    },
  };
  return (
    map[mode] || {
      bg: 'bg-neutral-100 dark:bg-neutral-800',
      text: 'text-neutral-600 dark:text-neutral-400',
    }
  );
}

function formatTimestamp(ts: string): string {
  const d = new Date(ts);
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}`;
}

function WaterfallBar({ spans, totalMs }: { spans: TraceSpan[]; totalMs: number }) {
  if (totalMs <= 0 || spans.length === 0) return <div className="h-4" />;

  return (
    <div className="relative h-4 w-full bg-neutral-100 dark:bg-neutral-700 rounded overflow-hidden">
      {spans.map((span, i) => {
        const left = (span.startOffsetMs / totalMs) * 100;
        const width = Math.max((span.durationMs / totalMs) * 100, 1);
        return (
          <div
            key={i}
            className="absolute top-0 h-full rounded-sm"
            style={{
              left: `${left}%`,
              width: `${width}%`,
              backgroundColor: spanColor(span.name, span.status),
            }}
            title={`${span.name} (${span.service}) — ${span.durationMs}ms`}
          />
        );
      })}
    </div>
  );
}

export function LiveTraces({ traces, onSelectTrace }: LiveTracesProps) {
  if (traces.length === 0) {
    return (
      <div className="h-[200px] flex items-center justify-center text-sm text-neutral-400 dark:text-neutral-500">
        No recent traces
      </div>
    );
  }

  return (
    <div>
      {/* Span legend */}
      <div className="flex flex-wrap gap-3 mb-3">
        {Object.entries(SPAN_COLORS).map(([name, color]) => (
          <div key={name} className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: color }} />
            <span className="text-[10px] text-neutral-500 dark:text-neutral-400 capitalize">
              {name.replace(/_/g, ' ')}
            </span>
          </div>
        ))}
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-neutral-500 dark:text-neutral-400 border-b border-neutral-200 dark:border-neutral-700">
              <th className="pb-2 pr-2 font-medium">Time</th>
              <th className="pb-2 pr-2 font-medium">Route</th>
              <th className="pb-2 pr-2 font-medium">Mode</th>
              <th className="pb-2 pr-2 font-medium w-[30%]">Trace Waterfall</th>
              <th className="pb-2 pr-2 font-medium text-right">Duration</th>
              <th className="pb-2 font-medium text-right">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
            {traces.map((t) => {
              const isError = t.statusCode >= 400;
              const sb = statusBadge(t.statusCode);
              const mb = modeBadge(t.mode);

              return (
                <tr
                  key={t.id}
                  className={`${
                    isError
                      ? 'bg-red-50/50 dark:bg-red-900/10'
                      : 'hover:bg-neutral-50 dark:hover:bg-neutral-800/50'
                  } cursor-pointer transition-colors`}
                  onClick={() => onSelectTrace?.(t.id)}
                >
                  <td className="py-2 pr-2 text-xs text-neutral-500 dark:text-neutral-400 tabular-nums">
                    {formatTimestamp(t.timestamp)}
                  </td>
                  <td className="py-2 pr-2">
                    <div className="flex items-center gap-1.5">
                      {isError && <AlertTriangle className="h-3 w-3 text-red-500 flex-shrink-0" />}
                      <span className="font-mono text-xs text-neutral-700 dark:text-neutral-300 truncate max-w-[180px]">
                        {t.method} {t.route}
                      </span>
                    </div>
                  </td>
                  <td className="py-2 pr-2">
                    <span
                      className={`inline-flex px-1.5 py-0.5 text-[10px] font-medium rounded ${mb.bg} ${mb.text}`}
                    >
                      {t.mode === 'edge-mcp' ? 'Gateway' : t.mode}
                    </span>
                  </td>
                  <td className="py-2 pr-2">
                    <WaterfallBar spans={t.spans} totalMs={t.durationMs} />
                  </td>
                  <td className="py-2 pr-2 text-right text-xs tabular-nums text-neutral-700 dark:text-neutral-300">
                    {t.durationMs}ms
                  </td>
                  <td className="py-2 text-right">
                    <span
                      className={`inline-flex px-1.5 py-0.5 text-[10px] font-medium rounded ${sb.bg} ${sb.text}`}
                    >
                      {t.statusCode}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
