import { useEffect, useRef } from 'react';
import { clsx } from 'clsx';
import type { DeploymentLog } from '../types';

const levelStyles: Record<string, { text: string; icon: string }> = {
  info: { text: 'text-neutral-400 dark:text-neutral-500', icon: 'text-blue-400' },
  warn: { text: 'text-yellow-600 dark:text-yellow-400', icon: 'text-yellow-500' },
  error: { text: 'text-red-500 dark:text-red-400', icon: 'text-red-500' },
  debug: { text: 'text-neutral-500 dark:text-neutral-600', icon: 'text-neutral-400' },
};

function formatLogTime(isoString: string): string {
  return new Date(isoString).toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

interface DeployLogViewerProps {
  logs: DeploymentLog[];
  maxHeight?: string;
}

export function DeployLogViewer({ logs, maxHeight = '300px' }: DeployLogViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const autoScrollRef = useRef(true);

  useEffect(() => {
    const el = containerRef.current;
    if (el && autoScrollRef.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [logs.length]);

  const handleScroll = () => {
    const el = containerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    autoScrollRef.current = atBottom;
  };

  if (logs.length === 0) {
    return (
      <div className="rounded-lg bg-neutral-900 dark:bg-neutral-950 p-4 text-center text-sm text-neutral-500">
        Waiting for deploy logs...
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className="rounded-lg bg-neutral-900 dark:bg-neutral-950 overflow-auto font-mono text-xs leading-5"
      style={{ maxHeight }}
    >
      <div className="p-3 space-y-0.5">
        {logs.map((log) => {
          const style = levelStyles[log.level] || levelStyles.info;
          return (
            <div key={log.id} className="flex gap-2">
              <span className="text-neutral-600 dark:text-neutral-600 shrink-0 select-none">
                {formatLogTime(log.created_at)}
              </span>
              <span
                className={clsx(
                  'uppercase w-12 shrink-0 text-right select-none font-semibold',
                  style.icon
                )}
              >
                {log.level}
              </span>
              {log.step && (
                <span className="text-purple-400 dark:text-purple-300 shrink-0">[{log.step}]</span>
              )}
              <span className={clsx('break-all', style.text)}>{log.message}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
