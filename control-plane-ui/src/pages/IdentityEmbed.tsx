import { useState } from 'react';
import { config } from '../config';
import { ExternalLink, RefreshCw, Maximize2, Minimize2, Shield } from 'lucide-react';
import { useServiceHealth } from '../hooks/useServiceHealth';
import { ServiceUnavailable } from '../components/ServiceUnavailable';

/**
 * IdentityEmbed - Embedded Keycloak account console view
 * Part of CAB-1108 Phase 3: Console Integration via reverse proxy
 *
 * The nginx reverse proxy strips X-Frame-Options from Keycloak responses,
 * allowing seamless iframe embedding within the Console.
 */
export function IdentityEmbed() {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [key, setKey] = useState(0);

  const keycloakAccountUrl = `${config.keycloak.url}/realms/${config.keycloak.realm}/account`;
  const { status: serviceStatus, retry: retryHealth } = useServiceHealth(keycloakAccountUrl);

  const handleIframeLoad = () => {
    setIsLoading(false);
  };

  const handleRefresh = () => {
    setIsLoading(true);
    setKey((prev) => prev + 1);
  };

  const handleOpenExternal = () => {
    window.open(keycloakAccountUrl, '_blank', 'noopener,noreferrer');
  };

  if (serviceStatus === 'unavailable') {
    return (
      <ServiceUnavailable
        serviceName="Keycloak"
        description="The identity provider is not reachable. It may not be deployed or is temporarily unavailable."
        icon={Shield}
        externalUrl={keycloakAccountUrl}
        configHint="Deploy Keycloak and ensure the realm is accessible at the configured URL"
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
        className={`flex items-center justify-between ${isFullscreen ? 'p-4 border-b border-gray-200 dark:border-neutral-700' : ''}`}
      >
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-purple-100 dark:bg-purple-900/30 rounded-lg flex items-center justify-center">
            <Shield className="h-5 w-5 text-purple-600 dark:text-purple-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
              Identity Management
            </h1>
            <p className="text-gray-500 dark:text-neutral-400 mt-0.5">
              Manage your account, security settings, and sessions
            </p>
          </div>
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
            {isFullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
            <span className="hidden sm:inline">{isFullscreen ? 'Exit' : 'Fullscreen'}</span>
          </button>
          <button
            onClick={handleOpenExternal}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-white bg-purple-600 rounded-lg hover:bg-purple-700 transition-colors"
            title="Open in new tab"
          >
            <ExternalLink className="h-4 w-4" />
            <span className="hidden sm:inline">Open in Keycloak</span>
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
        {(isLoading || serviceStatus === 'checking') && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-50 dark:bg-neutral-900 z-10">
            <div className="text-center">
              <div className="w-12 h-12 border-4 border-purple-600 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
              <p className="text-gray-500 dark:text-neutral-400">Loading Identity Management...</p>
            </div>
          </div>
        )}

        {/* Keycloak Account Console Iframe */}
        {serviceStatus === 'available' && (
          <iframe
            key={key}
            src={keycloakAccountUrl}
            title="STOA Identity Management - Keycloak"
            className="w-full h-full border-0"
            onLoad={handleIframeLoad}
            sandbox="allow-same-origin allow-scripts allow-popups allow-forms"
            referrerPolicy="no-referrer-when-downgrade"
          />
        )}
      </div>
    </div>
  );
}

export default IdentityEmbed;
