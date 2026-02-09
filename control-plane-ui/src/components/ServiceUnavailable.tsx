import type { LucideIcon } from 'lucide-react';
import { ExternalLink, RefreshCw } from 'lucide-react';

interface ServiceUnavailableProps {
  serviceName: string;
  description: string;
  icon: LucideIcon;
  externalUrl?: string;
  configHint?: string;
  onRetry?: () => void;
}

/**
 * Fallback UI shown when an embedded service (Grafana, OpenSearch, etc.)
 * is not reachable. Provides retry, direct link, and config guidance.
 */
export function ServiceUnavailable({
  serviceName,
  description,
  icon: Icon,
  externalUrl,
  configHint,
  onRetry,
}: ServiceUnavailableProps) {
  return (
    <div className="flex items-center justify-center min-h-[400px]">
      <div className="text-center max-w-md px-6">
        <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gray-100 dark:bg-neutral-800 flex items-center justify-center">
          <Icon className="h-8 w-8 text-gray-400 dark:text-neutral-500" />
        </div>
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
          {serviceName} is not available
        </h2>
        <p className="text-gray-500 dark:text-neutral-400 mb-6">{description}</p>

        {configHint && (
          <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg px-4 py-3 mb-6 text-left">
            <p className="text-sm text-amber-700 dark:text-amber-400">
              <strong>Configuration hint:</strong> {configHint}
            </p>
          </div>
        )}

        <div className="flex items-center justify-center gap-3">
          {onRetry && (
            <button
              onClick={onRetry}
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 dark:text-neutral-300 bg-white dark:bg-neutral-800 border border-gray-300 dark:border-neutral-600 rounded-lg hover:bg-gray-50 dark:hover:bg-neutral-700 transition-colors"
            >
              <RefreshCw className="h-4 w-4" />
              Retry
            </button>
          )}
          {externalUrl && (
            <a
              href={externalUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 transition-colors"
            >
              <ExternalLink className="h-4 w-4" />
              Open Directly
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
