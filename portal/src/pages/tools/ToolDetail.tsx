/**
 * Tool Detail Page
 *
 * Displays detailed information about an MCP Tool with subscribe functionality.
 */

import { useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Wrench,
  Star,
  Clock,
  Tag,
  ExternalLink,
  AlertCircle,
  Loader2,
  CreditCard,
  Code,
  RefreshCw,
  CheckCircle,
} from 'lucide-react';
import { useTool, useToolSchema, useSubscribeToTool } from '../../hooks/useTools';
import { SubscribeToToolModal } from '../../components/tools/SubscribeToToolModal';
import { ApiKeyModal } from '../../components/subscriptions/ApiKeyModal';
import { config } from '../../config';

type ToolStatus = 'active' | 'deprecated' | 'beta';

const statusConfig: Record<ToolStatus, {
  label: string;
  color: string;
  bg: string;
}> = {
  active: { label: 'Active', color: 'text-green-700', bg: 'bg-green-100' },
  beta: { label: 'Beta', color: 'text-amber-700', bg: 'bg-amber-100' },
  deprecated: { label: 'Deprecated', color: 'text-red-700', bg: 'bg-red-100' },
};

export function ToolDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [isSubscribeModalOpen, setIsSubscribeModalOpen] = useState(false);
  const [subscribeError, setSubscribeError] = useState<string | null>(null);
  const [showSchema, setShowSchema] = useState(false);
  const [apiKeyModalData, setApiKeyModalData] = useState<{
    isOpen: boolean;
    apiKey: string;
    toolId: string;
  }>({ isOpen: false, apiKey: '', toolId: '' });

  const {
    data: tool,
    isLoading,
    isError,
    error,
    refetch,
  } = useTool(id);

  const {
    data: schema,
    isLoading: schemaLoading,
  } = useToolSchema(showSchema ? id : undefined);

  const subscribeMutation = useSubscribeToTool();

  const handleSubscribe = async (data: { toolId: string; plan: 'free' | 'basic' | 'premium' }) => {
    setSubscribeError(null);
    try {
      const result = await subscribeMutation.mutateAsync(data);
      setIsSubscribeModalOpen(false);
      // Show API Key modal with the one-time key
      setApiKeyModalData({
        isOpen: true,
        apiKey: result.api_key,
        toolId: data.toolId,
      });
    } catch (err) {
      setSubscribeError((err as Error)?.message || 'Failed to subscribe to tool');
    }
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin text-primary-600 mx-auto mb-4" />
          <p className="text-gray-500">Loading tool details...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (isError || !tool) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-6">
        <div className="flex items-start gap-3">
          <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
          <div>
            <h3 className="font-medium text-red-800">Failed to load tool</h3>
            <p className="text-sm text-red-600 mt-1">
              {(error as Error)?.message || 'Tool not found or an unexpected error occurred'}
            </p>
            <div className="flex gap-3 mt-4">
              <button
                onClick={() => refetch()}
                className="px-4 py-2 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 text-sm font-medium transition-colors"
              >
                Try Again
              </button>
              <button
                onClick={() => navigate('/tools')}
                className="px-4 py-2 text-red-700 hover:bg-red-100 rounded-lg text-sm font-medium transition-colors"
              >
                Back to Catalog
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const status = statusConfig[tool.status as ToolStatus] || statusConfig.active;

  return (
    <div className="space-y-6">
      {/* Back Button */}
      <Link
        to="/tools"
        className="inline-flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900 transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Tools Catalog
      </Link>

      {/* Header Card */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-6">
          {/* Tool Info */}
          <div className="flex-1">
            <div className="flex items-start gap-4">
              <div className="p-3 bg-primary-50 rounded-xl">
                <Wrench className="h-8 w-8 text-primary-600" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-3 flex-wrap">
                  <h1 className="text-2xl font-bold text-gray-900">{tool.displayName}</h1>
                  <span className={`px-2.5 py-1 text-xs font-medium rounded-full ${status.bg} ${status.color}`}>
                    {status.label}
                  </span>
                </div>
                <p className="text-sm text-gray-500 mt-1">
                  <code className="bg-gray-100 px-2 py-0.5 rounded">{tool.name}</code>
                  {' '}v{tool.version}
                </p>
                <p className="text-gray-600 mt-3">{tool.description}</p>
              </div>
            </div>

            {/* Meta Info */}
            <div className="flex flex-wrap items-center gap-4 mt-6 text-sm text-gray-500">
              {tool.category && (
                <div className="flex items-center gap-1.5">
                  <Tag className="h-4 w-4" />
                  <span>{tool.category}</span>
                </div>
              )}
              {tool.rateLimit && (
                <div className="flex items-center gap-1.5">
                  <Clock className="h-4 w-4" />
                  <span>{tool.rateLimit.requests} requests/{tool.rateLimit.period}</span>
                </div>
              )}
              {tool.pricing && (
                <div className="flex items-center gap-1.5">
                  <Star className="h-4 w-4 text-amber-400" />
                  <span className="capitalize">{tool.pricing.model}</span>
                </div>
              )}
            </div>

            {/* Tags */}
            {tool.tags && tool.tags.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-4">
                {tool.tags.map((tag) => (
                  <span
                    key={tag}
                    className="px-2 py-1 text-xs bg-gray-100 text-gray-600 rounded"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="flex flex-col gap-3 sm:flex-row lg:flex-col lg:items-end">
            {config.features.enableSubscriptions && tool.status !== 'deprecated' && (
              <button
                onClick={() => setIsSubscribeModalOpen(true)}
                className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors font-medium"
              >
                <CreditCard className="h-4 w-4" />
                Subscribe
              </button>
            )}
            <button
              onClick={() => refetch()}
              className="inline-flex items-center justify-center gap-2 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
            >
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          </div>
        </div>
      </div>

      {/* Endpoint Info */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Endpoint Configuration</h2>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-500 mb-1">Endpoint URL</label>
            <div className="flex items-center gap-2">
              <code className="flex-1 px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm font-mono text-gray-800 overflow-x-auto">
                {tool.endpoint}
              </code>
              <span className="px-2 py-1 text-xs font-medium bg-blue-100 text-blue-700 rounded uppercase">
                {tool.method}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Input/Output Schema */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Schema</h2>
          <button
            onClick={() => setShowSchema(!showSchema)}
            className="inline-flex items-center gap-2 text-sm text-primary-600 hover:text-primary-700 font-medium"
          >
            <Code className="h-4 w-4" />
            {showSchema ? 'Hide Schema' : 'Show Schema'}
          </button>
        </div>

        {showSchema && (
          <div className="space-y-4">
            {schemaLoading ? (
              <div className="flex items-center gap-2 text-gray-500">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading schema...
              </div>
            ) : (
              <>
                {/* Input Schema */}
                <div>
                  <h3 className="text-sm font-medium text-gray-700 mb-2">Input Schema</h3>
                  <pre className="p-4 bg-gray-50 border border-gray-200 rounded-lg overflow-x-auto text-sm">
                    {tool.inputSchema
                      ? JSON.stringify(tool.inputSchema, null, 2)
                      : schema
                      ? JSON.stringify(schema, null, 2)
                      : 'No input schema defined'}
                  </pre>
                </div>

                {/* Output Schema */}
                {tool.outputSchema && (
                  <div>
                    <h3 className="text-sm font-medium text-gray-700 mb-2">Output Schema</h3>
                    <pre className="p-4 bg-gray-50 border border-gray-200 rounded-lg overflow-x-auto text-sm">
                      {JSON.stringify(tool.outputSchema, null, 2)}
                    </pre>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {!showSchema && (
          <p className="text-sm text-gray-500">
            Click "Show Schema" to view the tool's input and output schema definitions.
          </p>
        )}
      </div>

      {/* Usage Example */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Usage Example</h2>
        <div className="bg-gray-900 rounded-lg p-4 overflow-x-auto">
          <pre className="text-sm text-gray-100 font-mono">
{`// MCP Client Usage
const response = await mcpClient.callTool({
  name: "${tool.name}",
  arguments: {
    // Add your input parameters here
  }
});

console.log(response);`}
          </pre>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Quick Actions</h2>
        <div className="flex flex-wrap gap-3">
          <Link
            to="/subscriptions"
            className="inline-flex items-center gap-2 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors text-sm font-medium"
          >
            <CheckCircle className="h-4 w-4" />
            View My Subscriptions
          </Link>
          {tool.endpoint && (
            <a
              href={tool.endpoint}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors text-sm font-medium"
            >
              <ExternalLink className="h-4 w-4" />
              Open Endpoint
            </a>
          )}
        </div>
      </div>

      {/* Subscribe Modal */}
      {tool && (
        <SubscribeToToolModal
          isOpen={isSubscribeModalOpen}
          onClose={() => {
            setIsSubscribeModalOpen(false);
            setSubscribeError(null);
          }}
          onSubmit={handleSubscribe}
          tool={tool}
          isLoading={subscribeMutation.isPending}
          error={subscribeError}
        />
      )}

      {/* API Key Modal - shown after successful subscription */}
      <ApiKeyModal
        isOpen={apiKeyModalData.isOpen}
        onClose={() => setApiKeyModalData({ isOpen: false, apiKey: '', toolId: '' })}
        apiKey={apiKeyModalData.apiKey}
        toolId={apiKeyModalData.toolId}
        toolName={tool?.displayName || tool?.name}
      />
    </div>
  );
}

export default ToolDetail;
