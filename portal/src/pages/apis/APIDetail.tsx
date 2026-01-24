/**
 * API Detail Page
 *
 * Displays detailed information about an API including its OpenAPI spec,
 * endpoints, and subscription options.
 */

import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  ArrowLeft,
  BookOpen,
  Tag,
  Clock,
  ExternalLink,
  Code2,
  PlayCircle,
  FileJson,
  Loader2,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Copy,
  Check,
  CreditCard,
} from 'lucide-react';
import { useAPI, useOpenAPISpec } from '../../hooks/useAPIs';
import { useSubscribe, SubscribeToAPIResponse } from '../../hooks/useSubscriptions';
import { SubscribeModal, SubscribeFormData } from '../../components/subscriptions/SubscribeModal';
import { config } from '../../config';
import type { APIEndpoint } from '../../types';

type TabType = 'overview' | 'endpoints' | 'openapi';

const methodColors: Record<string, string> = {
  GET: 'bg-green-100 text-green-800',
  POST: 'bg-blue-100 text-blue-800',
  PUT: 'bg-amber-100 text-amber-800',
  PATCH: 'bg-orange-100 text-orange-800',
  DELETE: 'bg-red-100 text-red-800',
};

export function APIDetail() {
  const { id } = useParams<{ id: string }>();
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [expandedEndpoints, setExpandedEndpoints] = useState<Set<string>>(new Set());
  const [copiedSpec, setCopiedSpec] = useState(false);
  const [isSubscribeModalOpen, setIsSubscribeModalOpen] = useState(false);
  const [subscribeError, setSubscribeError] = useState<string | null>(null);
  const [subscriptionResult, setSubscriptionResult] = useState<SubscribeToAPIResponse | null>(null);
  const [copiedApiKey, setCopiedApiKey] = useState(false);

  const { data: api, isLoading, isError, error } = useAPI(id);
  const { data: openApiSpec, isLoading: specLoading } = useOpenAPISpec(id);
  const subscribeMutation = useSubscribe();

  const handleSubscribe = async (data: SubscribeFormData) => {
    setSubscribeError(null);
    if (!api) {
      setSubscribeError('API not loaded');
      return;
    }
    try {
      const result = await subscribeMutation.mutateAsync({
        applicationId: data.applicationId,
        applicationName: data.applicationName,
        apiId: data.apiId,
        apiName: api.name,
        apiVersion: api.version,
        tenantId: api.tenantId || 'default',
        planName: data.plan,
      });
      setSubscriptionResult(result);
      setIsSubscribeModalOpen(false);
    } catch (err) {
      setSubscribeError((err as Error)?.message || 'Failed to subscribe to API');
    }
  };

  const statusColors = {
    published: 'bg-green-100 text-green-800',
    deprecated: 'bg-amber-100 text-amber-800',
    draft: 'bg-gray-100 text-gray-800',
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'long',
      day: 'numeric',
      year: 'numeric',
    });
  };

  const toggleEndpoint = (endpointId: string) => {
    setExpandedEndpoints((prev) => {
      const next = new Set(prev);
      if (next.has(endpointId)) {
        next.delete(endpointId);
      } else {
        next.add(endpointId);
      }
      return next;
    });
  };

  const copyOpenAPISpec = async () => {
    if (openApiSpec) {
      await navigator.clipboard.writeText(JSON.stringify(openApiSpec, null, 2));
      setCopiedSpec(true);
      setTimeout(() => setCopiedSpec(false), 2000);
    }
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center">
          <Loader2 className="h-8 w-8 text-primary-600 animate-spin mx-auto mb-4" />
          <p className="text-gray-500">Loading API details...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (isError || !api) {
    return (
      <div className="space-y-6">
        <Link
          to="/apis"
          className="inline-flex items-center text-sm text-gray-600 hover:text-gray-900"
        >
          <ArrowLeft className="h-4 w-4 mr-1" />
          Back to API Catalog
        </Link>

        <div className="bg-red-50 border border-red-200 rounded-lg p-6">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
            <div>
              <h3 className="font-medium text-red-800">Failed to load API</h3>
              <p className="text-sm text-red-600 mt-1">
                {(error as Error)?.message || 'The API could not be found or you do not have access to it.'}
              </p>
              <Link
                to="/apis"
                className="mt-3 inline-block px-4 py-2 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 text-sm font-medium transition-colors"
              >
                Return to Catalog
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const tabs: { id: TabType; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
    { id: 'overview', label: 'Overview', icon: BookOpen },
    { id: 'endpoints', label: 'Endpoints', icon: Code2 },
    { id: 'openapi', label: 'OpenAPI Spec', icon: FileJson },
  ];

  return (
    <div className="space-y-6">
      {/* Back link */}
      <Link
        to="/apis"
        className="inline-flex items-center text-sm text-gray-600 hover:text-gray-900"
      >
        <ArrowLeft className="h-4 w-4 mr-1" />
        Back to API Catalog
      </Link>

      {/* Header */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-2xl font-bold text-gray-900">{api.name}</h1>
              <span className={`px-2 py-1 text-xs font-medium rounded-full ${statusColors[api.status]}`}>
                {api.status}
              </span>
            </div>
            <p className="text-gray-500 mb-4">Version {api.version}</p>
            <p className="text-gray-700">{api.description || 'No description available'}</p>

            {/* Tags */}
            <div className="flex flex-wrap gap-2 mt-4">
              {api.category && (
                <span className="inline-flex items-center gap-1 px-3 py-1 bg-primary-50 text-primary-700 text-sm rounded-full">
                  <Tag className="h-3 w-3" />
                  {api.category}
                </span>
              )}
              {api.tags?.map((tag) => (
                <span
                  key={tag}
                  className="px-3 py-1 bg-gray-100 text-gray-600 text-sm rounded-full"
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>

          {/* Actions */}
          <div className="flex flex-col gap-2">
            {config.features.enableSubscriptions && api.status === 'published' && (
              <button
                onClick={() => setIsSubscribeModalOpen(true)}
                className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
              >
                <CreditCard className="h-4 w-4" />
                Subscribe
              </button>
            )}
            {config.features.enableAPITesting && (
              <Link
                to={`/apis/${api.id}/test`}
                className="inline-flex items-center justify-center gap-2 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
              >
                <PlayCircle className="h-4 w-4" />
                Try this API
              </Link>
            )}
            {api.documentation && (
              <a
                href={api.documentation}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center justify-center gap-2 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
              >
                <ExternalLink className="h-4 w-4" />
                Documentation
              </a>
            )}
          </div>
        </div>

        {/* Metadata */}
        <div className="flex items-center gap-6 mt-6 pt-6 border-t border-gray-100 text-sm text-gray-500">
          <div className="flex items-center gap-1">
            <Clock className="h-4 w-4" />
            Updated {formatDate(api.updatedAt)}
          </div>
          {api.tenantName && (
            <div>
              Provider: <span className="text-gray-700">{api.tenantName}</span>
            </div>
          )}
          {api.endpoints && (
            <div>
              <span className="text-gray-700">{api.endpoints.length}</span> endpoint{api.endpoints.length !== 1 ? 's' : ''}
            </div>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-8">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 py-3 border-b-2 text-sm font-medium transition-colors ${
                  activeTab === tab.id
                    ? 'border-primary-500 text-primary-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                <Icon className="h-4 w-4" />
                {tab.label}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Tab Content */}
      <div className="bg-white rounded-lg border border-gray-200">
        {/* Overview Tab */}
        {activeTab === 'overview' && (
          <div className="p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">About this API</h2>
            <div className="prose prose-gray max-w-none">
              <p>{api.description || 'No detailed description available for this API.'}</p>
            </div>

            {/* Quick Start */}
            <div className="mt-8">
              <h3 className="text-md font-semibold text-gray-900 mb-3">Quick Start</h3>
              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-sm text-gray-600 mb-3">
                  To use this API, you'll need to:
                </p>
                <ol className="list-decimal list-inside space-y-2 text-sm text-gray-700">
                  <li>Create an application to get client credentials</li>
                  <li>Subscribe your application to this API</li>
                  <li>Use your credentials to authenticate requests</li>
                </ol>
                <div className="mt-4">
                  <Link
                    to="/apps"
                    className="text-sm text-primary-600 hover:text-primary-700 font-medium"
                  >
                    Go to My Applications &rarr;
                  </Link>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Endpoints Tab */}
        {activeTab === 'endpoints' && (
          <div className="divide-y divide-gray-200">
            {api.endpoints && api.endpoints.length > 0 ? (
              api.endpoints.map((endpoint: APIEndpoint, index: number) => {
                const endpointId = `${endpoint.method}-${endpoint.path}-${index}`;
                const isExpanded = expandedEndpoints.has(endpointId);

                return (
                  <div key={endpointId} className="p-4">
                    <button
                      onClick={() => toggleEndpoint(endpointId)}
                      className="w-full flex items-center justify-between text-left"
                    >
                      <div className="flex items-center gap-3">
                        <span className={`px-2 py-1 text-xs font-mono font-semibold rounded ${methodColors[endpoint.method] || 'bg-gray-100 text-gray-800'}`}>
                          {endpoint.method}
                        </span>
                        <span className="font-mono text-sm text-gray-700">{endpoint.path}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-gray-500">{endpoint.summary}</span>
                        {isExpanded ? (
                          <ChevronDown className="h-4 w-4 text-gray-400" />
                        ) : (
                          <ChevronRight className="h-4 w-4 text-gray-400" />
                        )}
                      </div>
                    </button>

                    {isExpanded && (
                      <div className="mt-4 pl-16 space-y-4">
                        {endpoint.summary && (
                          <p className="text-sm text-gray-600">{endpoint.summary}</p>
                        )}

                        {endpoint.parameters && endpoint.parameters.length > 0 && (
                          <div>
                            <h4 className="text-sm font-medium text-gray-900 mb-2">Parameters</h4>
                            <div className="bg-gray-50 rounded-lg overflow-hidden">
                              <table className="min-w-full text-sm">
                                <thead>
                                  <tr className="border-b border-gray-200">
                                    <th className="px-3 py-2 text-left font-medium text-gray-500">Name</th>
                                    <th className="px-3 py-2 text-left font-medium text-gray-500">Type</th>
                                    <th className="px-3 py-2 text-left font-medium text-gray-500">Required</th>
                                    <th className="px-3 py-2 text-left font-medium text-gray-500">Description</th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-200">
                                  {endpoint.parameters.map((param, pIndex) => (
                                    <tr key={pIndex}>
                                      <td className="px-3 py-2 font-mono text-gray-700">{param.name}</td>
                                      <td className="px-3 py-2 text-gray-500">{param.in}</td>
                                      <td className="px-3 py-2">
                                        {param.required ? (
                                          <span className="text-red-600">Yes</span>
                                        ) : (
                                          <span className="text-gray-400">No</span>
                                        )}
                                      </td>
                                      <td className="px-3 py-2 text-gray-600">{param.description || '-'}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        )}

                        {endpoint.responses && Object.keys(endpoint.responses).length > 0 && (
                          <div>
                            <h4 className="text-sm font-medium text-gray-900 mb-2">Responses</h4>
                            <div className="space-y-2">
                              {Object.entries(endpoint.responses).map(([code, response]) => (
                                <div key={code} className="flex items-start gap-2 text-sm">
                                  <span className={`px-2 py-0.5 rounded font-mono text-xs ${
                                    code.startsWith('2') ? 'bg-green-100 text-green-800' :
                                    code.startsWith('4') ? 'bg-amber-100 text-amber-800' :
                                    code.startsWith('5') ? 'bg-red-100 text-red-800' :
                                    'bg-gray-100 text-gray-800'
                                  }`}>
                                    {code}
                                  </span>
                                  <span className="text-gray-600">{response.description || 'No description'}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })
            ) : (
              <div className="p-12 text-center">
                <Code2 className="h-8 w-8 text-gray-300 mx-auto mb-3" />
                <p className="text-gray-500">No endpoint information available</p>
                <p className="text-sm text-gray-400 mt-1">Check the OpenAPI spec tab for full API documentation</p>
              </div>
            )}
          </div>
        )}

        {/* OpenAPI Spec Tab */}
        {activeTab === 'openapi' && (
          <div className="p-6">
            {specLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-6 w-6 text-primary-600 animate-spin" />
              </div>
            ) : openApiSpec ? (
              <div>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-gray-900">OpenAPI Specification</h3>
                  <button
                    onClick={copyOpenAPISpec}
                    className="inline-flex items-center gap-2 px-3 py-1.5 text-sm text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
                  >
                    {copiedSpec ? (
                      <>
                        <Check className="h-4 w-4 text-green-500" />
                        Copied!
                      </>
                    ) : (
                      <>
                        <Copy className="h-4 w-4" />
                        Copy
                      </>
                    )}
                  </button>
                </div>
                <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-auto max-h-[600px] text-sm">
                  <code>{JSON.stringify(openApiSpec, null, 2)}</code>
                </pre>
              </div>
            ) : (
              <div className="text-center py-12">
                <FileJson className="h-8 w-8 text-gray-300 mx-auto mb-3" />
                <p className="text-gray-500">No OpenAPI specification available</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Subscribe Modal */}
      <SubscribeModal
        isOpen={isSubscribeModalOpen}
        onClose={() => {
          setIsSubscribeModalOpen(false);
          setSubscribeError(null);
        }}
        onSubmit={handleSubscribe}
        api={api}
        isLoading={subscribeMutation.isPending}
        error={subscribeError}
      />

      {/* Subscription Success Modal - Shows API Key (only once!) */}
      {subscriptionResult && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div
            className="fixed inset-0 bg-black/50 transition-opacity"
            onClick={() => setSubscriptionResult(null)}
          />
          <div className="flex min-h-full items-center justify-center p-4">
            <div className="relative bg-white rounded-xl shadow-xl max-w-md w-full p-6">
              <div className="text-center mb-6">
                <div className="mx-auto w-12 h-12 bg-green-100 rounded-full flex items-center justify-center mb-4">
                  <Check className="h-6 w-6 text-green-600" />
                </div>
                <h2 className="text-xl font-semibold text-gray-900">
                  Subscription Created!
                </h2>
                <p className="text-sm text-gray-500 mt-1">
                  Your API key is shown below. Save it now - it won't be shown again.
                </p>
              </div>

              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-4">
                <div className="flex items-start gap-2">
                  <AlertCircle className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />
                  <p className="text-sm text-amber-800">
                    <strong>Important:</strong> Copy and save this API key now. For security reasons, it cannot be displayed again.
                  </p>
                </div>
              </div>

              <div className="mb-6">
                <span className="block text-sm font-medium text-gray-700 mb-2">
                  Your API Key
                </span>
                <div className="flex items-center gap-2">
                  <code className="flex-1 px-3 py-2 bg-gray-100 border border-gray-300 rounded-lg text-sm font-mono break-all" aria-label="API Key">
                    {subscriptionResult.apiKey}
                  </code>
                  <button
                    onClick={async () => {
                      await navigator.clipboard.writeText(subscriptionResult.apiKey);
                      setCopiedApiKey(true);
                      setTimeout(() => setCopiedApiKey(false), 2000);
                    }}
                    className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg"
                  >
                    {copiedApiKey ? (
                      <Check className="h-5 w-5 text-green-500" />
                    ) : (
                      <Copy className="h-5 w-5" />
                    )}
                  </button>
                </div>
              </div>

              <button
                onClick={() => setSubscriptionResult(null)}
                className="w-full px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default APIDetail;
