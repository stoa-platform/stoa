/**
 * Tool Detail Page (CAB-312)
 *
 * Displays detailed information about an MCP Tool with:
 * - Header with name, description, category, subscribe button
 * - Input Schema viewer (required vs optional fields)
 * - Usage Statistics
 * - Try It form for testing
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
  Play,
  FileJson,
  BookOpen,
} from 'lucide-react';
import { useTool, useToolSchema, useSubscribeToTool } from '../../hooks/useTools';
import { SubscribeToToolModal, SchemaViewer, UsageStats, TryItForm } from '../../components/tools';
import { ApiKeyModal } from '../../components/subscriptions/ApiKeyModal';
import { config } from '../../config';
import { toolsService } from '../../services/tools';

type ToolStatus = 'active' | 'deprecated' | 'beta';
type TabType = 'overview' | 'schema' | 'try-it';

const statusConfig: Record<ToolStatus, {
  label: string;
  color: string;
  bg: string;
}> = {
  active: { label: 'Active', color: 'text-green-700', bg: 'bg-green-100' },
  beta: { label: 'Beta', color: 'text-amber-700', bg: 'bg-amber-100' },
  deprecated: { label: 'Deprecated', color: 'text-red-700', bg: 'bg-red-100' },
};

const tabs: { id: TabType; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: 'overview', label: 'Overview', icon: BookOpen },
  { id: 'schema', label: 'Schema', icon: FileJson },
  { id: 'try-it', label: 'Try It', icon: Play },
];

export function ToolDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [isSubscribeModalOpen, setIsSubscribeModalOpen] = useState(false);
  const [subscribeError, setSubscribeError] = useState<string | null>(null);
  const [isInvoking, setIsInvoking] = useState(false);
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
  } = useToolSchema(id);

  const subscribeMutation = useSubscribeToTool();

  const handleSubscribe = async (data: { toolId: string; plan: 'free' | 'basic' | 'premium' }) => {
    setSubscribeError(null);
    try {
      const result = await subscribeMutation.mutateAsync(data);
      setIsSubscribeModalOpen(false);
      setApiKeyModalData({
        isOpen: true,
        apiKey: result.api_key,
        toolId: data.toolId,
      });
    } catch (err) {
      setSubscribeError((err as Error)?.message || 'Failed to subscribe to tool');
    }
  };

  const handleInvokeTool = async (args: Record<string, unknown>) => {
    if (!id) return;
    setIsInvoking(true);
    try {
      const result = await toolsService.invokeTool(id, args);
      return result;
    } finally {
      setIsInvoking(false);
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
  const inputSchema = tool.inputSchema || schema;

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
                  <h1 className="text-2xl font-bold text-gray-900">{tool.displayName || tool.name}</h1>
                  <span className={`px-2.5 py-1 text-xs font-medium rounded-full ${status.bg} ${status.color}`}>
                    {status.label}
                  </span>
                </div>
                <p className="text-sm text-gray-500 mt-1">
                  <code className="bg-gray-100 px-2 py-0.5 rounded">{tool.name}</code>
                  {tool.version && <span className="ml-2">v{tool.version}</span>}
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
              {inputSchema?.properties && (
                <div className="flex items-center gap-1.5">
                  <Code className="h-4 w-4" />
                  <span>{Object.keys(inputSchema.properties).length} parameters</span>
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

      {/* Tabs Navigation */}
      <div className="bg-white rounded-lg border border-gray-200">
        <div className="border-b border-gray-200">
          <nav className="flex -mb-px">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 px-6 py-4 text-sm font-medium border-b-2 transition-colors ${
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
        <div className="p-6">
          {/* Overview Tab */}
          {activeTab === 'overview' && (
            <div className="space-y-6">
              {/* Endpoint Info */}
              {tool.endpoint && (
                <div>
                  <h3 className="text-sm font-medium text-gray-700 mb-3">Endpoint Configuration</h3>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm font-mono text-gray-800 overflow-x-auto">
                      {tool.endpoint}
                    </code>
                    {tool.method && (
                      <span className="px-2 py-1 text-xs font-medium bg-blue-100 text-blue-700 rounded uppercase">
                        {tool.method}
                      </span>
                    )}
                  </div>
                </div>
              )}

              {/* Usage Stats */}
              <UsageStats
                stats={{
                  callsThisMonth: 1247,
                  callsToday: 89,
                  avgLatencyMs: 142,
                  successRate: 99.2,
                  lastCalledAt: new Date(Date.now() - 3600000).toISOString(),
                  trend: 'up',
                  errorCount: 10,
                }}
              />

              {/* Usage Example */}
              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-3">Usage Example</h3>
                <div className="bg-gray-900 rounded-lg p-4 overflow-x-auto">
                  <pre className="text-sm text-gray-100 font-mono">
{`// MCP Client Usage
const response = await mcpClient.callTool({
  name: "${tool.name}",
  arguments: {
${inputSchema?.properties ? Object.entries(inputSchema.properties).slice(0, 3).map(([key, prop]) =>
    `    ${key}: ${prop.type === 'string' ? '"example"' : prop.type === 'number' ? '123' : prop.type === 'boolean' ? 'true' : '...'}`
  ).join(',\n') : '    // Add your input parameters here'}
  }
});

console.log(response);`}
                  </pre>
                </div>
              </div>

              {/* Quick Actions */}
              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-3">Quick Actions</h3>
                <div className="flex flex-wrap gap-3">
                  <Link
                    to="/subscriptions"
                    className="inline-flex items-center gap-2 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors text-sm font-medium"
                  >
                    <CheckCircle className="h-4 w-4" />
                    View My Subscriptions
                  </Link>
                  <button
                    onClick={() => setActiveTab('try-it')}
                    className="inline-flex items-center gap-2 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors text-sm font-medium"
                  >
                    <Play className="h-4 w-4" />
                    Try This Tool
                  </button>
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
            </div>
          )}

          {/* Schema Tab */}
          {activeTab === 'schema' && (
            <div className="space-y-6">
              {schemaLoading ? (
                <div className="flex items-center gap-2 text-gray-500 py-8 justify-center">
                  <Loader2 className="h-5 w-5 animate-spin" />
                  Loading schema...
                </div>
              ) : (
                <>
                  {/* Input Schema */}
                  <SchemaViewer
                    schema={inputSchema}
                    title="Input Schema"
                  />

                  {/* Output Schema */}
                  {tool.outputSchema && (
                    <div>
                      <h3 className="text-sm font-medium text-gray-700 mb-3">Output Schema</h3>
                      <pre className="p-4 bg-gray-900 text-gray-100 rounded-lg overflow-x-auto text-sm font-mono">
                        {JSON.stringify(tool.outputSchema, null, 2)}
                      </pre>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {/* Try It Tab */}
          {activeTab === 'try-it' && (
            <TryItForm
              schema={inputSchema}
              toolName={tool.name}
              onInvoke={handleInvokeTool}
              isLoading={isInvoking}
            />
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
