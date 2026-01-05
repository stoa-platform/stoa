/**
 * API Testing Sandbox Page
 *
 * Interactive sandbox for testing API endpoints with environment selection,
 * request building, and response viewing.
 */

import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  ArrowLeft,
  FlaskConical,
  BookOpen,
  AlertCircle,
  Loader2,
  History,
  Trash2,
} from 'lucide-react';
import { useAPI } from '../../hooks/useAPIs';
import { config } from '../../config';
import {
  EnvironmentSelector,
  RequestBuilder,
  ResponseViewer,
  SandboxConfirmationModal,
} from '../../components/testing';
import type { Environment } from '../../components/testing';
import type { RequestConfig } from '../../components/testing';
import type { ResponseData } from '../../components/testing';

// Define available environments based on portal mode
const getAvailableEnvironments = (): Environment[] => {
  const isProductionPortal = config.portalMode === 'production';

  if (isProductionPortal) {
    return [
      {
        id: 'prod',
        name: 'prod',
        displayName: 'Production',
        baseUrl: `https://apis.${config.baseDomain}`,
        isProduction: true,
      },
    ];
  }

  // Non-production portal has multiple environments
  const envList = config.testing?.availableEnvironments || ['dev'];
  return envList.map((env) => ({
    id: env,
    name: env,
    displayName: env === 'dev' ? 'Development' : env.charAt(0).toUpperCase() + env.slice(1),
    baseUrl: `https://apis.${env === 'prod' ? '' : env + '.'}${config.baseDomain}`,
    isProduction: env === 'prod',
  }));
};

interface TestHistoryItem {
  id: string;
  timestamp: Date;
  method: string;
  path: string;
  status: number;
  timing: number;
}

export function APITestingSandbox() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: api, isLoading: apiLoading, isError, error } = useAPI(id);

  const environments = getAvailableEnvironments();
  const [selectedEnvironment, setSelectedEnvironment] = useState<Environment | null>(
    environments[0] || null
  );

  const [response, setResponse] = useState<ResponseData | null>(null);
  const [isRequestLoading, setIsRequestLoading] = useState(false);

  // Sandbox confirmation for production
  const [showConfirmation, setShowConfirmation] = useState(false);
  const [sessionConfirmed, setSessionConfirmed] = useState(false);
  const [pendingRequest, setPendingRequest] = useState<RequestConfig | null>(null);

  // Test history
  const [testHistory, setTestHistory] = useState<TestHistoryItem[]>([]);

  const isProductionPortal = config.portalMode === 'production';
  const requireConfirmation = isProductionPortal && config.testing?.requireSandboxConfirmation;

  // Reset confirmation when environment changes
  useEffect(() => {
    if (selectedEnvironment?.isProduction) {
      // Keep session confirmed if already confirmed
    } else {
      setSessionConfirmed(false);
    }
  }, [selectedEnvironment]);

  const executeRequest = async (requestConfig: RequestConfig) => {
    if (!selectedEnvironment) return;

    // Check if we need confirmation for production
    if (requireConfirmation && selectedEnvironment.isProduction && !sessionConfirmed) {
      setPendingRequest(requestConfig);
      setShowConfirmation(true);
      return;
    }

    setIsRequestLoading(true);
    setResponse(null);

    const startTime = performance.now();

    try {
      // Build the full URL with query params
      let url = `${selectedEnvironment.baseUrl}${requestConfig.path}`;
      const enabledParams = requestConfig.queryParams.filter((p) => p.enabled && p.key);
      if (enabledParams.length > 0) {
        const params = new URLSearchParams();
        enabledParams.forEach((p) => params.append(p.key, p.value));
        url += `?${params.toString()}`;
      }

      // Build headers
      const headers: Record<string, string> = {};
      requestConfig.headers
        .filter((h) => h.enabled && h.key)
        .forEach((h) => {
          headers[h.key] = h.value;
        });

      // Make the request
      const fetchResponse = await fetch(url, {
        method: requestConfig.method,
        headers,
        body: ['POST', 'PUT', 'PATCH'].includes(requestConfig.method) && requestConfig.body
          ? requestConfig.body
          : undefined,
        credentials: 'include', // Include cookies for auth
      });

      const endTime = performance.now();
      const totalTime = endTime - startTime;

      // Parse response headers
      const responseHeaders: Record<string, string> = {};
      fetchResponse.headers.forEach((value, key) => {
        responseHeaders[key] = value;
      });

      // Parse response body
      let body: unknown;
      const contentType = fetchResponse.headers.get('content-type');
      if (contentType?.includes('application/json')) {
        body = await fetchResponse.json();
      } else {
        body = await fetchResponse.text();
      }

      const responseData: ResponseData = {
        status: fetchResponse.status,
        statusText: fetchResponse.statusText,
        headers: responseHeaders,
        body,
        timing: {
          total: totalTime,
        },
      };

      setResponse(responseData);

      // Add to history
      setTestHistory((prev) => [
        {
          id: Date.now().toString(),
          timestamp: new Date(),
          method: requestConfig.method,
          path: requestConfig.path,
          status: fetchResponse.status,
          timing: totalTime,
        },
        ...prev.slice(0, 9), // Keep last 10
      ]);
    } catch (err) {
      const endTime = performance.now();
      const totalTime = endTime - startTime;

      setResponse({
        status: 0,
        statusText: 'Network Error',
        headers: {},
        body: null,
        timing: { total: totalTime },
        error: (err as Error).message || 'Failed to make request',
      });
    } finally {
      setIsRequestLoading(false);
    }
  };

  const handleConfirmSandbox = () => {
    setSessionConfirmed(true);
    setShowConfirmation(false);

    // Execute pending request
    if (pendingRequest) {
      executeRequest(pendingRequest);
      setPendingRequest(null);
    }
  };

  const clearHistory = () => {
    setTestHistory([]);
  };

  // Loading state
  if (apiLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin text-primary-600 mx-auto mb-4" />
          <p className="text-gray-500">Loading API details...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (isError || !api) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-6">
        <div className="flex items-start gap-3">
          <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
          <div>
            <h3 className="font-medium text-red-800">Failed to load API</h3>
            <p className="text-sm text-red-600 mt-1">
              {(error as Error)?.message || 'API not found or an unexpected error occurred'}
            </p>
            <button
              onClick={() => navigate('/apis')}
              className="mt-4 px-4 py-2 text-red-700 hover:bg-red-100 rounded-lg text-sm font-medium transition-colors"
            >
              Back to API Catalog
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Get default path from API endpoints
  const defaultPath = api.endpoints?.[0]?.path || '/';

  return (
    <div className="space-y-6">
      {/* Back Button */}
      <Link
        to={`/apis/${id}`}
        className="inline-flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900 transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to API Details
      </Link>

      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-primary-50 rounded-xl">
            <FlaskConical className="h-8 w-8 text-primary-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">API Testing Sandbox</h1>
            <p className="text-gray-500 mt-1">
              Test <span className="font-medium text-gray-700">{api.name}</span> endpoints
            </p>
          </div>
        </div>

        <Link
          to={`/apis/${id}`}
          className="inline-flex items-center gap-2 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors text-sm font-medium"
        >
          <BookOpen className="h-4 w-4" />
          View API Documentation
        </Link>
      </div>

      {/* Production Warning Banner */}
      {isProductionPortal && selectedEnvironment?.isProduction && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-amber-600 mt-0.5 flex-shrink-0" />
            <div>
              <h3 className="font-medium text-amber-800">Production Environment</h3>
              <p className="text-sm text-amber-700 mt-1">
                You are testing against the production API. Requests are logged and may affect
                production data.
                {sessionConfirmed && ' Session confirmed for this testing session.'}
              </p>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Panel - Request */}
        <div className="lg:col-span-2 space-y-6">
          {/* Environment Selector */}
          <div className="bg-white rounded-lg border border-gray-200 p-4">
            <EnvironmentSelector
              environments={environments}
              selectedEnvironment={selectedEnvironment}
              onSelect={setSelectedEnvironment}
            />
          </div>

          {/* Request Builder */}
          <div className="bg-white rounded-lg border border-gray-200 p-4">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Request</h2>
            <RequestBuilder
              baseUrl={selectedEnvironment?.baseUrl || ''}
              initialPath={defaultPath}
              onSubmit={executeRequest}
              isLoading={isRequestLoading}
              disabled={!selectedEnvironment}
            />
          </div>

          {/* Response Viewer */}
          <div>
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Response</h2>
            <ResponseViewer response={response} isLoading={isRequestLoading} />
          </div>
        </div>

        {/* Right Panel - History & Info */}
        <div className="space-y-6">
          {/* Test History */}
          <div className="bg-white rounded-lg border border-gray-200 p-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-gray-900 flex items-center gap-2">
                <History className="h-4 w-4" />
                Recent Tests
              </h3>
              {testHistory.length > 0 && (
                <button
                  onClick={clearHistory}
                  className="text-xs text-gray-500 hover:text-gray-700 flex items-center gap-1"
                >
                  <Trash2 className="h-3 w-3" />
                  Clear
                </button>
              )}
            </div>

            {testHistory.length === 0 ? (
              <p className="text-sm text-gray-500 text-center py-4">No recent tests</p>
            ) : (
              <div className="space-y-2">
                {testHistory.map((item) => (
                  <div
                    key={item.id}
                    className="flex items-center justify-between py-2 px-2 rounded hover:bg-gray-50 text-sm"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span
                        className={`
                        px-1.5 py-0.5 text-xs font-medium rounded
                        ${item.method === 'GET' ? 'bg-green-100 text-green-700' : ''}
                        ${item.method === 'POST' ? 'bg-blue-100 text-blue-700' : ''}
                        ${item.method === 'PUT' ? 'bg-amber-100 text-amber-700' : ''}
                        ${item.method === 'DELETE' ? 'bg-red-100 text-red-700' : ''}
                        ${item.method === 'PATCH' ? 'bg-purple-100 text-purple-700' : ''}
                      `}
                      >
                        {item.method}
                      </span>
                      <span className="text-gray-600 truncate" title={item.path}>
                        {item.path}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <span
                        className={`
                        text-xs font-medium
                        ${item.status >= 200 && item.status < 300 ? 'text-green-600' : ''}
                        ${item.status >= 400 ? 'text-red-600' : ''}
                        ${item.status >= 300 && item.status < 400 ? 'text-blue-600' : ''}
                      `}
                      >
                        {item.status}
                      </span>
                      <span className="text-xs text-gray-400">
                        {item.timing < 1000
                          ? `${item.timing.toFixed(0)}ms`
                          : `${(item.timing / 1000).toFixed(1)}s`}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* API Info */}
          <div className="bg-white rounded-lg border border-gray-200 p-4">
            <h3 className="font-semibold text-gray-900 mb-3">API Information</h3>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-gray-500">Name</dt>
                <dd className="text-gray-900 font-medium">{api.name}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Version</dt>
                <dd className="text-gray-900">{api.version}</dd>
              </div>
              {api.category && (
                <div className="flex justify-between">
                  <dt className="text-gray-500">Category</dt>
                  <dd className="text-gray-900">{api.category}</dd>
                </div>
              )}
              <div className="flex justify-between">
                <dt className="text-gray-500">Endpoints</dt>
                <dd className="text-gray-900">{api.endpoints?.length || 0}</dd>
              </div>
            </dl>
          </div>

          {/* Tips */}
          <div className="bg-blue-50 rounded-lg border border-blue-200 p-4">
            <h3 className="font-medium text-blue-900 mb-2">Testing Tips</h3>
            <ul className="text-sm text-blue-700 space-y-1">
              <li>• Use query params for filtering results</li>
              <li>• Add Authorization header for protected endpoints</li>
              <li>• Check response headers for rate limit info</li>
              <li>• Use "Format JSON" to prettify request body</li>
            </ul>
          </div>
        </div>
      </div>

      {/* Sandbox Confirmation Modal */}
      <SandboxConfirmationModal
        isOpen={showConfirmation}
        onClose={() => {
          setShowConfirmation(false);
          setPendingRequest(null);
        }}
        onConfirm={handleConfirmSandbox}
        environmentName={selectedEnvironment?.displayName || 'Production'}
      />
    </div>
  );
}

export default APITestingSandbox;
