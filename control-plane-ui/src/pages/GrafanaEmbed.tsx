import { useState } from 'react';
import { config } from '../config';
import { ExternalLink, RefreshCw, Maximize2, Minimize2 } from 'lucide-react';

/**
 * GrafanaEmbed - Embedded Grafana dashboard view
 * Part of CAB-1108 Phase 2: Console Integration
 */
export function GrafanaEmbed() {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [key, setKey] = useState(0); // For forcing iframe reload

  const grafanaUrl = config.services.grafana.url;

  const handleIframeLoad = () => {
    setIsLoading(false);
    setError(null);
  };

  const handleIframeError = () => {
    setIsLoading(false);
    setError('Failed to load Grafana. Please check your connection.');
  };

  const handleRefresh = () => {
    setIsLoading(true);
    setError(null);
    setKey(prev => prev + 1);
  };

  const handleOpenExternal = () => {
    window.open(grafanaUrl, '_blank', 'noopener,noreferrer');
  };

  return (
    <div className={`${isFullscreen ? 'fixed inset-0 z-50 bg-white dark:bg-neutral-900' : 'space-y-4'}`}>
      {/* Header */}
      <div className={`flex items-center justify-between ${isFullscreen ? 'p-4 border-b border-gray-200 dark:border-neutral-700' : ''}`}>
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            STOA Observability
          </h1>
          <p className="text-gray-500 dark:text-neutral-400 mt-1">
            Platform metrics, dashboards, and monitoring
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleRefresh}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-gray-700 dark:text-neutral-300 bg-white dark:bg-neutral-800 border border-gray-300 dark:border-neutral-600 rounded-lg hover:bg-gray-50 dark:hover:bg-neutral-700 transition-colors"
            title="Refresh"
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">Refresh</span>
          </button>
          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-gray-700 dark:text-neutral-300 bg-white dark:bg-neutral-800 border border-gray-300 dark:border-neutral-600 rounded-lg hover:bg-gray-50 dark:hover:bg-neutral-700 transition-colors"
            title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
          >
            {isFullscreen ? (
              <Minimize2 className="h-4 w-4" />
            ) : (
              <Maximize2 className="h-4 w-4" />
            )}
            <span className="hidden sm:inline">{isFullscreen ? 'Exit' : 'Fullscreen'}</span>
          </button>
          <button
            onClick={handleOpenExternal}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 transition-colors"
            title="Open in new tab"
          >
            <ExternalLink className="h-4 w-4" />
            <span className="hidden sm:inline">Open in Grafana</span>
          </button>
        </div>
      </div>

      {/* Iframe Container */}
      <div
        className={`relative bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 overflow-hidden ${
          isFullscreen ? 'flex-1 m-4 mb-4' : ''
        }`}
        style={{ height: isFullscreen ? 'calc(100vh - 120px)' : 'calc(100vh - 220px)' }}
      >
        {/* Loading State */}
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-50 dark:bg-neutral-900 z-10">
            <div className="text-center">
              <div className="w-12 h-12 border-4 border-primary-600 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
              <p className="text-gray-500 dark:text-neutral-400">Loading Grafana...</p>
            </div>
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-50 dark:bg-neutral-900 z-10">
            <div className="text-center max-w-md px-4">
              <div className="w-16 h-16 bg-red-100 dark:bg-red-900/30 rounded-full flex items-center justify-center mx-auto mb-4">
                <span className="text-2xl">⚠️</span>
              </div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                Unable to Load Grafana
              </h3>
              <p className="text-gray-500 dark:text-neutral-400 mb-4">{error}</p>
              <div className="flex gap-2 justify-center">
                <button
                  onClick={handleRefresh}
                  className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700"
                >
                  Try Again
                </button>
                <button
                  onClick={handleOpenExternal}
                  className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-neutral-300 bg-white dark:bg-neutral-800 border border-gray-300 dark:border-neutral-600 rounded-lg hover:bg-gray-50 dark:hover:bg-neutral-700"
                >
                  Open in New Tab
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Grafana Iframe */}
        <iframe
          key={key}
          src={grafanaUrl}
          title="STOA Observability - Grafana"
          className="w-full h-full border-0"
          onLoad={handleIframeLoad}
          onError={handleIframeError}
          sandbox="allow-same-origin allow-scripts allow-popups allow-forms allow-downloads"
          referrerPolicy="no-referrer-when-downgrade"
        />
      </div>
    </div>
  );
}

export default GrafanaEmbed;
