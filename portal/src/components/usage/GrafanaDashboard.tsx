import { useState } from 'react';
import { AlertTriangle, BarChart3 } from 'lucide-react';

interface GrafanaDashboardProps {
  url: string;
  title?: string;
  className?: string;
}

export function GrafanaDashboard({
  url,
  title = 'Analytics Dashboard',
  className,
}: GrafanaDashboardProps) {
  const [hasError, setHasError] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  if (!url) {
    return (
      <div
        className={`mt-6 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 p-8 text-center ${className ?? ''}`}
        data-testid="grafana-disabled"
      >
        <BarChart3 className="h-10 w-10 mx-auto text-neutral-300 dark:text-neutral-600" />
        <p className="mt-3 text-sm text-neutral-500 dark:text-neutral-400">
          Analytics dashboard is not configured. Set <code>VITE_GRAFANA_URL</code> to enable.
        </p>
      </div>
    );
  }

  if (hasError) {
    return (
      <div
        className={`mt-6 rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 p-8 text-center ${className ?? ''}`}
        data-testid="grafana-error"
      >
        <AlertTriangle className="h-10 w-10 mx-auto text-red-400 dark:text-red-500" />
        <p className="mt-3 text-sm text-red-600 dark:text-red-400">
          Failed to load analytics dashboard.
        </p>
      </div>
    );
  }

  return (
    <div className={`mt-6 ${className ?? ''}`} data-testid="grafana-dashboard">
      <h2 className="text-lg font-semibold text-neutral-900 dark:text-white mb-4">{title}</h2>
      {isLoading && (
        <div className="h-96 rounded-lg bg-neutral-100 dark:bg-neutral-800 animate-pulse" />
      )}
      <iframe
        src={url}
        title={title}
        className={`w-full h-96 rounded-lg border border-neutral-200 dark:border-neutral-700 ${isLoading ? 'hidden' : ''}`}
        sandbox="allow-scripts allow-same-origin"
        onLoad={() => setIsLoading(false)}
        onError={() => {
          setIsLoading(false);
          setHasError(true);
        }}
      />
    </div>
  );
}
