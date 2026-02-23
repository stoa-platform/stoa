import { useEffect, useRef } from 'react';
import type { DeployLogEntry } from '@/types';

const levelColors: Record<string, string> = {
  info: 'text-gray-300',
  warn: 'text-yellow-400',
  error: 'text-red-400',
  debug: 'text-gray-500',
};

interface DeployLogViewerProps {
  logs: DeployLogEntry[];
  streaming?: boolean;
  maxHeight?: string;
}

export function DeployLogViewer({
  logs,
  streaming = false,
  maxHeight = '400px',
}: DeployLogViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs.length]);

  return (
    <div className="rounded-lg border border-gray-700 bg-gray-900">
      <div className="flex items-center justify-between border-b border-gray-700 px-4 py-2">
        <span className="text-sm font-medium text-gray-300">Deploy Logs</span>
        {streaming && (
          <span className="flex items-center gap-1.5 text-xs text-green-400">
            <span className="h-2 w-2 animate-pulse rounded-full bg-green-400" />
            Streaming...
          </span>
        )}
      </div>
      <div ref={containerRef} className="overflow-auto p-4" style={{ maxHeight }}>
        {logs.length === 0 ? (
          <p className="text-sm text-gray-500">No log entries yet.</p>
        ) : (
          <pre className="space-y-0.5 font-mono text-xs leading-5">
            {logs.map((entry, idx) => (
              <div key={`${entry.seq}-${idx}`} className="flex gap-2">
                <span className="shrink-0 text-gray-600">{String(entry.seq).padStart(3, '0')}</span>
                {entry.step && <span className="shrink-0 text-blue-400">[{entry.step}]</span>}
                <span className={levelColors[entry.level] ?? 'text-gray-300'}>{entry.message}</span>
              </div>
            ))}
          </pre>
        )}
      </div>
    </div>
  );
}
