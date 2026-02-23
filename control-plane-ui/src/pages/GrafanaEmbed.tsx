import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { config } from '../config';
import { isAllowedEmbedUrl } from '../utils/navigation';
import { ExternalLink, RefreshCw, Maximize2, Minimize2, Gauge } from 'lucide-react';
import { useServiceHealth } from '../hooks/useServiceHealth';
import { ServiceUnavailable } from '../components/ServiceUnavailable';

/**
 * GrafanaEmbed - Embedded Grafana / Prometheus dashboard view
 * Part of CAB-1108 Phase 2: Console Integration
 *
 * Supports deep-linking via ?url= query parameter.
 * Example: /observability?url=https://grafana.gostoa.dev/d/stoa-gateway-overview
 */
export function GrafanaEmbed() {
  const [searchParams] = useSearchParams();
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [key, setKey] = useState(0);

  const targetUrl = searchParams.get('url');
  const iframeUrl =
    targetUrl && isAllowedEmbedUrl(targetUrl) ? targetUrl : config.services.grafana.url;

  const isPrometheus = iframeUrl.includes('prometheus');
  const serviceLabel = isPrometheus ? 'Prometheus' : 'Grafana';

  const { status: serviceStatus, retry: retryHealth } = useServiceHealth(iframeUrl);

  const handleIframeLoad = () => {
    setIsLoading(false);
  };

  const handleRefresh = () => {
    setIsLoading(true);
    setKey((prev) => prev + 1);
  };

  const handleOpenExternal = () => {
    window.open(iframeUrl, '_blank', 'noopener,noreferrer');
  };

  if (serviceStatus === 'unavailable') {
    return (
      <ServiceUnavailable
        serviceName={serviceLabel}
        description={`${serviceLabel} is not reachable. It may not be deployed or the proxy is not configured.`}
        icon={Gauge}
        externalUrl={iframeUrl}
        configHint="Deploy Grafana with Keycloak OIDC and set GF_SERVER_SERVE_FROM_SUB_PATH=true"
        onRetry={retryHealth}
      />
    );
  }

  return (
    <div
      className={`${isFullscreen ? 'fixed inset-0 z-50 bg-white dark:bg-neutral-900' : 'space-y-4'}`}
    >
      {/* Header */}
      <div
        className={`flex items-center justify-between ${isFullscreen ? 'p-4 border-b border-neutral-200 dark:border-neutral-700' : ''}`}
      >
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">
            STOA Observability
          </h1>
          <p className="text-neutral-500 dark:text-neutral-400 mt-1">
            Platform metrics, dashboards, and monitoring
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleRefresh}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-neutral-700 dark:text-neutral-300 bg-white dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors"
            title="Refresh"
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">Refresh</span>
          </button>
          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-neutral-700 dark:text-neutral-300 bg-white dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors"
            title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
          >
            {isFullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
            <span className="hidden sm:inline">{isFullscreen ? 'Exit' : 'Fullscreen'}</span>
          </button>
          <button
            onClick={handleOpenExternal}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 transition-colors"
            title="Open in new tab"
          >
            <ExternalLink className="h-4 w-4" />
            <span className="hidden sm:inline">Open in {serviceLabel}</span>
          </button>
        </div>
      </div>

      {/* Iframe Container */}
      <div
        className={`relative bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 overflow-hidden ${
          isFullscreen ? 'flex-1 m-4 mb-4' : ''
        }`}
        style={{ height: isFullscreen ? 'calc(100vh - 120px)' : 'calc(100vh - 220px)' }}
      >
        {/* Loading State */}
        {(isLoading || serviceStatus === 'checking') && (
          <div className="absolute inset-0 flex items-center justify-center bg-neutral-50 dark:bg-neutral-900 z-10">
            <div className="text-center">
              <div className="w-12 h-12 border-4 border-primary-600 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
              <p className="text-neutral-500 dark:text-neutral-400">Loading {serviceLabel}...</p>
            </div>
          </div>
        )}

        {/* Iframe */}
        {serviceStatus === 'available' && (
          <iframe
            key={key}
            src={iframeUrl}
            title={`STOA Observability - ${serviceLabel}`}
            className="w-full h-full border-0"
            onLoad={handleIframeLoad}
            sandbox="allow-same-origin allow-scripts allow-popups allow-forms allow-downloads"
            referrerPolicy="no-referrer-when-downgrade"
          />
        )}
      </div>
    </div>
  );
}

export default GrafanaEmbed;
