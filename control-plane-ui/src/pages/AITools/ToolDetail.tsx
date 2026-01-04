import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  ArrowLeft,
  Wrench,
  Tag,
  ExternalLink,
  Clock,
  Bell,
  BellOff,
  Code,
  FileJson,
  PlayCircle,
  AlertCircle,
  CheckCircle,
} from 'lucide-react';
import { mcpGatewayService } from '../../services/mcpGatewayApi';
import { ToolSchemaViewer, SchemaJsonViewer, QuickStartGuide } from '../../components/tools';
import type { MCPTool, ToolSubscription, ToolUsageSummary } from '../../types';

type TabType = 'overview' | 'schema' | 'quickstart' | 'usage';

export function ToolDetail() {
  const { toolName } = useParams<{ toolName: string }>();
  const navigate = useNavigate();

  // State
  const [tool, setTool] = useState<MCPTool | null>(null);
  const [subscription, setSubscription] = useState<ToolSubscription | null>(null);
  const [usage, setUsage] = useState<ToolUsageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [subscribing, setSubscribing] = useState(false);

  // Load data
  useEffect(() => {
    async function loadTool() {
      if (!toolName) return;

      try {
        setLoading(true);
        setError(null);

        const [toolData, subscriptions, usageData] = await Promise.all([
          mcpGatewayService.getTool(toolName),
          mcpGatewayService.getMySubscriptions().catch(() => []),
          mcpGatewayService.getToolUsage(toolName, { period: 'month' }).catch(() => null),
        ]);

        setTool(toolData);
        setSubscription(subscriptions.find((s) => s.toolName === toolName) || null);
        setUsage(usageData);
      } catch (err) {
        console.error('Failed to load tool:', err);
        setError(err instanceof Error ? err.message : 'Failed to load tool');
      } finally {
        setLoading(false);
      }
    }

    loadTool();
  }, [toolName]);

  // Handlers
  const handleSubscribe = async () => {
    if (!tool) return;

    try {
      setSubscribing(true);
      if (subscription) {
        await mcpGatewayService.unsubscribeTool(subscription.id);
        setSubscription(null);
      } else {
        const newSub = await mcpGatewayService.subscribeTool({ toolName: tool.name });
        setSubscription(newSub);
      }
    } catch (err) {
      console.error('Failed to update subscription:', err);
    } finally {
      setSubscribing(false);
    }
  };

  const methodColors: Record<string, string> = {
    GET: 'bg-green-100 text-green-800 border-green-200',
    POST: 'bg-blue-100 text-blue-800 border-blue-200',
    PUT: 'bg-yellow-100 text-yellow-800 border-yellow-200',
    PATCH: 'bg-orange-100 text-orange-800 border-orange-200',
    DELETE: 'bg-red-100 text-red-800 border-red-200',
  };

  const tabs: { id: TabType; label: string; icon: React.ReactNode }[] = [
    { id: 'overview', label: 'Overview', icon: <Wrench className="h-4 w-4" /> },
    { id: 'schema', label: 'Schema', icon: <FileJson className="h-4 w-4" /> },
    { id: 'quickstart', label: 'Quick Start', icon: <PlayCircle className="h-4 w-4" /> },
    { id: 'usage', label: 'Usage', icon: <Clock className="h-4 w-4" /> },
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    );
  }

  if (error || !tool) {
    return (
      <div className="space-y-6">
        <button
          onClick={() => navigate('/ai-tools')}
          className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to catalog
        </button>

        <div className="flex items-center gap-2 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
          <AlertCircle className="h-5 w-5 flex-shrink-0" />
          <span className="text-sm">{error || 'Tool not found'}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm">
        <Link to="/ai-tools" className="text-gray-500 hover:text-gray-700">
          AI Tools
        </Link>
        <span className="text-gray-300">/</span>
        <span className="text-gray-900 font-medium">{tool.name}</span>
      </nav>

      {/* Header */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="flex items-start justify-between">
          <div className="flex items-start gap-4">
            <div className="p-3 bg-blue-50 rounded-lg">
              <Wrench className="h-8 w-8 text-blue-600" />
            </div>
            <div>
              <div className="flex items-center gap-3 mb-1">
                <h1 className="text-2xl font-bold text-gray-900">{tool.name}</h1>
                <span
                  className={`px-2.5 py-0.5 rounded border text-sm font-medium ${
                    methodColors[tool.method] || 'bg-gray-100 text-gray-800 border-gray-200'
                  }`}
                >
                  {tool.method}
                </span>
                <span className="text-sm text-gray-500">v{tool.version}</span>
              </div>
              <p className="text-gray-600 max-w-2xl">{tool.description}</p>

              {/* Metadata */}
              <div className="flex flex-wrap items-center gap-4 mt-4">
                {tool.tags.length > 0 && (
                  <div className="flex items-center gap-2">
                    {tool.tags.map((tag) => (
                      <span
                        key={tag}
                        className="inline-flex items-center gap-1 px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs"
                      >
                        <Tag className="h-3 w-3" />
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
                {tool.tenantId && (
                  <span className="text-xs text-gray-400">Tenant: {tool.tenantId}</span>
                )}
                {tool.endpoint && (
                  <span className="flex items-center gap-1 text-xs text-gray-400">
                    <ExternalLink className="h-3 w-3" />
                    API-backed
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Subscribe Button */}
          <button
            onClick={handleSubscribe}
            disabled={subscribing}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              subscription
                ? 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                : 'bg-blue-600 text-white hover:bg-blue-700'
            } ${subscribing ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            {subscription ? (
              <>
                <BellOff className="h-4 w-4" />
                Unsubscribe
              </>
            ) : (
              <>
                <Bell className="h-4 w-4" />
                Subscribe
              </>
            )}
          </button>
        </div>

        {/* Subscription Status */}
        {subscription && (
          <div className="mt-4 pt-4 border-t border-gray-100">
            <div className="flex items-center gap-2 text-sm text-green-600">
              <CheckCircle className="h-4 w-4" />
              <span>Subscribed since {new Date(subscription.subscribedAt).toLocaleDateString()}</span>
              {subscription.usageCount > 0 && (
                <span className="text-gray-400 ml-2">
                  {subscription.usageCount} calls made
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-6">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-1 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.id
                  ? 'text-blue-600 border-blue-600'
                  : 'text-gray-500 border-transparent hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab Content */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        {activeTab === 'overview' && (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-medium text-gray-900 mb-2">Description</h3>
              <p className="text-gray-600">{tool.description}</p>
            </div>

            <div>
              <h3 className="text-lg font-medium text-gray-900 mb-3">Parameters</h3>
              <ToolSchemaViewer schema={tool.inputSchema} title="Input Parameters" />
            </div>

            {tool.endpoint && (
              <div>
                <h3 className="text-lg font-medium text-gray-900 mb-2">Backend Endpoint</h3>
                <code className="block px-4 py-3 bg-gray-100 rounded-lg text-sm font-mono text-gray-800">
                  {tool.method} {tool.endpoint}
                </code>
              </div>
            )}
          </div>
        )}

        {activeTab === 'schema' && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-medium text-gray-900">JSON Schema</h3>
              <button
                onClick={() => navigator.clipboard.writeText(JSON.stringify(tool.inputSchema, null, 2))}
                className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-600 hover:text-gray-900 transition-colors"
              >
                <Code className="h-4 w-4" />
                Copy JSON
              </button>
            </div>
            <SchemaJsonViewer schema={tool.inputSchema} />
          </div>
        )}

        {activeTab === 'quickstart' && <QuickStartGuide tool={tool} />}

        {activeTab === 'usage' && (
          <div className="space-y-6">
            {usage ? (
              <>
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  <div className="p-4 bg-gray-50 rounded-lg">
                    <div className="text-sm text-gray-500 mb-1">Total Calls</div>
                    <div className="text-2xl font-bold text-gray-900">{usage.totalCalls.toLocaleString()}</div>
                  </div>
                  <div className="p-4 bg-gray-50 rounded-lg">
                    <div className="text-sm text-gray-500 mb-1">Success Rate</div>
                    <div className="text-2xl font-bold text-green-600">
                      {(usage.successRate * 100).toFixed(1)}%
                    </div>
                  </div>
                  <div className="p-4 bg-gray-50 rounded-lg">
                    <div className="text-sm text-gray-500 mb-1">Avg Latency</div>
                    <div className="text-2xl font-bold text-gray-900">{usage.avgLatencyMs.toFixed(0)}ms</div>
                  </div>
                  <div className="p-4 bg-gray-50 rounded-lg">
                    <div className="text-sm text-gray-500 mb-1">Cost Units</div>
                    <div className="text-2xl font-bold text-purple-600">${usage.totalCostUnits.toFixed(4)}</div>
                  </div>
                </div>

                <div className="text-sm text-gray-500">
                  Usage data for the last {usage.period} ({usage.startDate} - {usage.endDate})
                </div>
              </>
            ) : (
              <div className="text-center py-8 text-gray-500">
                <Clock className="h-12 w-12 mx-auto mb-4 text-gray-300" />
                <p>No usage data available yet.</p>
                <p className="text-sm mt-1">Start using this tool to see usage statistics.</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
