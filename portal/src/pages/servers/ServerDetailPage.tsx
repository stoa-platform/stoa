/**
 * Server Detail Page
 *
 * View MCP Server details and manage subscription with per-tool access control.
 */

import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  ArrowLeft,
  Server,
  Wrench,
  Shield,
  Key,
  CheckCircle,
  XCircle,
  Clock,
  AlertCircle,
  Loader2,
  Copy,
  Check,
  ExternalLink,
  RefreshCw,
  Settings,
  Users,
  Globe,
  Download,
  Terminal,
} from 'lucide-react';
import { config } from '../../config';
import { useAuth } from '../../contexts/AuthContext';
import { mcpServersService, MOCK_SERVERS } from '../../services/mcpServers';
import type { MCPServer, MCPServerSubscription } from '../../types';

export function ServerDetailPage() {
  const { serverId } = useParams<{ serverId: string }>();
  const { user, isAuthenticated, accessToken } = useAuth();

  const [server, setServer] = useState<MCPServer | null>(null);
  const [subscription, setSubscription] = useState<MCPServerSubscription | null>(null);
  const [selectedTools, setSelectedTools] = useState<Set<string>>(new Set());
  const [isLoading, setIsLoading] = useState(true);
  const [isSubscribing, setIsSubscribing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newApiKey, setNewApiKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [copiedConfig, setCopiedConfig] = useState<string | null>(null);

  // Load server and subscription
  useEffect(() => {
    if (!isAuthenticated || !accessToken || !serverId) return;

    async function loadData() {
      setIsLoading(true);
      setError(null);

      try {
        // Try API, fallback to mock
        let fetchedServer: MCPServer | undefined;
        try {
          fetchedServer = await mcpServersService.getServer(serverId!);
        } catch {
          fetchedServer = MOCK_SERVERS.find(s => s.id === serverId);
        }

        if (!fetchedServer) {
          setError('Server not found');
          return;
        }

        // Check if user can see this server
        if (!mcpServersService.canUserSeeServer(fetchedServer, user)) {
          setError('You do not have permission to view this server');
          return;
        }

        setServer(fetchedServer);

        // Select all tools by default for new subscriptions
        setSelectedTools(new Set(fetchedServer.tools.map(t => t.id)));

        // Try to fetch subscription
        try {
          const subs = await mcpServersService.getMyServerSubscriptions();
          const existingSub = subs.find(s => s.server_id === serverId);
          setSubscription(existingSub || null);
        } catch {
          setSubscription(null);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load server');
      } finally {
        setIsLoading(false);
      }
    }

    loadData();
  }, [isAuthenticated, accessToken, serverId, user]);

  // Toggle tool selection
  const toggleTool = (toolId: string) => {
    const newSet = new Set(selectedTools);
    if (newSet.has(toolId)) {
      newSet.delete(toolId);
    } else {
      newSet.add(toolId);
    }
    setSelectedTools(newSet);
  };

  // Select/deselect all tools
  const toggleAllTools = () => {
    if (!server) return;
    if (selectedTools.size === server.tools.length) {
      setSelectedTools(new Set());
    } else {
      setSelectedTools(new Set(server.tools.map(t => t.id)));
    }
  };

  // Subscribe to server
  const handleSubscribe = async () => {
    if (!server || selectedTools.size === 0) return;

    setIsSubscribing(true);
    setError(null);

    try {
      const result = await mcpServersService.subscribeToServer({
        server_id: server.id,
        plan: 'free',
        requested_tools: Array.from(selectedTools),
      });

      setSubscription(result);
      setNewApiKey(result.api_key);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to subscribe');
    } finally {
      setIsSubscribing(false);
    }
  };

  // Copy API key
  const copyApiKey = async () => {
    if (!newApiKey) return;
    await navigator.clipboard.writeText(newApiKey);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Copy config to clipboard
  const copyConfig = async (configType: string, content: string) => {
    await navigator.clipboard.writeText(content);
    setCopiedConfig(configType);
    setTimeout(() => setCopiedConfig(null), 2000);
  };

  // Generate Claude.ai MCP config (SSE transport for web)
  const generateClaudeConfig = (apiKey: string) => {
    const mcpUrl = config.mcp.baseUrl;
    return {
      mcpServers: {
        'stoa-platform': {
          url: `${mcpUrl}/mcp/sse`,
          transport: 'sse',
          headers: {
            'Authorization': `Bearer ${apiKey}`,
          },
        },
      },
    };
  };

  // Generate Claude Desktop config (stdio transport)
  const generateDesktopConfig = (apiKey: string) => {
    const mcpUrl = config.mcp.baseUrl;
    return {
      mcpServers: {
        'stoa-platform': {
          command: 'npx',
          args: ['-y', '@anthropic-ai/mcp-proxy', mcpUrl + '/mcp/sse'],
          env: {
            'STOA_API_KEY': apiKey,
          },
        },
      },
    };
  };

  // Get category icon
  const getCategoryIcon = (category: string) => {
    switch (category) {
      case 'platform':
        return Settings;
      case 'tenant':
        return Users;
      case 'public':
        return Globe;
      default:
        return Server;
    }
  };

  // Get tool access status from subscription
  const getToolAccessStatus = (toolId: string) => {
    if (!subscription) return null;
    return subscription.tool_access.find(ta => ta.tool_id === toolId);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="h-8 w-8 text-primary-600 animate-spin" />
      </div>
    );
  }

  if (error || !server) {
    return (
      <div className="space-y-6">
        <Link
          to="/servers"
          className="inline-flex items-center gap-2 text-gray-600 hover:text-gray-900"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Servers
        </Link>

        <div className="bg-red-50 border border-red-200 rounded-lg p-6">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
            <div>
              <h3 className="font-medium text-red-800">Error</h3>
              <p className="text-sm text-red-600 mt-1">{error || 'Server not found'}</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const CategoryIcon = getCategoryIcon(server.category);

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <Link
        to="/servers"
        className="inline-flex items-center gap-2 text-gray-600 hover:text-gray-900"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Servers
      </Link>

      {/* Server Header */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="flex items-start gap-4">
          <div className="p-3 bg-primary-50 rounded-lg">
            <CategoryIcon className="h-8 w-8 text-primary-600" />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-gray-900">{server.displayName}</h1>
              {server.version && (
                <span className="text-sm text-gray-400">v{server.version}</span>
              )}
              <span className={`px-2 py-1 text-xs font-medium rounded ${
                server.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'
              }`}>
                {server.status}
              </span>
            </div>
            <p className="text-gray-600 mt-2">{server.description}</p>
            <div className="flex items-center gap-4 mt-4 text-sm text-gray-500">
              <span className="inline-flex items-center gap-1">
                <Wrench className="h-4 w-4" />
                {server.tools.length} tools
              </span>
              <span className="capitalize bg-gray-100 px-2 py-1 rounded">
                {server.category}
              </span>
              {server.documentation_url && (
                <a
                  href={server.documentation_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-primary-600 hover:text-primary-700"
                >
                  Documentation
                  <ExternalLink className="h-3 w-3" />
                </a>
              )}
            </div>
          </div>

          {/* Subscription Status Badge */}
          {subscription && (
            <div className={`px-4 py-2 rounded-lg ${
              subscription.status === 'active'
                ? 'bg-green-50 border border-green-200'
                : 'bg-amber-50 border border-amber-200'
            }`}>
              <div className="flex items-center gap-2">
                {subscription.status === 'active' ? (
                  <CheckCircle className="h-5 w-5 text-green-600" />
                ) : (
                  <Clock className="h-5 w-5 text-amber-600" />
                )}
                <span className={`font-medium ${
                  subscription.status === 'active' ? 'text-green-700' : 'text-amber-700'
                }`}>
                  {subscription.status === 'active' ? 'Subscribed' : 'Pending'}
                </span>
              </div>
              {subscription.api_key_prefix && (
                <div className="text-xs text-gray-500 mt-1">
                  Key: {subscription.api_key_prefix}...
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* New API Key Alert with Claude.ai Configuration */}
      {newApiKey && (
        <div className="space-y-4">
          {/* API Key Section */}
          <div className="bg-green-50 border border-green-200 rounded-lg p-6">
            <div className="flex items-start gap-3">
              <Key className="h-5 w-5 text-green-600 mt-0.5" />
              <div className="flex-1">
                <h3 className="font-medium text-green-800">Subscription Created!</h3>
                <p className="text-sm text-green-600 mt-1">
                  Save your API key now. It will only be shown once.
                </p>
                <div className="mt-3 flex items-center gap-2">
                  <code className="flex-1 px-3 py-2 bg-white border border-green-200 rounded font-mono text-sm break-all">
                    {newApiKey}
                  </code>
                  <button
                    onClick={copyApiKey}
                    className="p-2 bg-green-100 hover:bg-green-200 rounded text-green-700 transition-colors"
                    title="Copy API key"
                  >
                    {copied ? <Check className="h-5 w-5" /> : <Copy className="h-5 w-5" />}
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Claude.ai Configuration Section */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
            <div className="flex items-start gap-3">
              <Terminal className="h-5 w-5 text-blue-600 mt-0.5" />
              <div className="flex-1">
                <h3 className="font-medium text-blue-800">Configure with Claude.ai</h3>
                <p className="text-sm text-blue-600 mt-1">
                  Add this MCP Server to Claude.ai to use the tools directly in your conversations.
                </p>

                {/* Claude.ai Web Config (Recommended) */}
                <div className="mt-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-gray-700 flex items-center gap-2">
                      <Globe className="h-4 w-4" />
                      Claude.ai (Web) - Recommended
                    </span>
                    <button
                      onClick={() => copyConfig('claude', JSON.stringify(generateClaudeConfig(newApiKey), null, 2))}
                      className="inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700"
                    >
                      {copiedConfig === 'claude' ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                      {copiedConfig === 'claude' ? 'Copied!' : 'Copy'}
                    </button>
                  </div>
                  <pre className="bg-gray-900 text-green-400 p-4 rounded-lg text-xs overflow-x-auto">
                    {JSON.stringify(generateClaudeConfig(newApiKey), null, 2)}
                  </pre>
                  <p className="text-xs text-gray-500 mt-2">
                    Go to <a href="https://claude.ai/settings/mcp" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">claude.ai/settings/mcp</a> and add this configuration.
                  </p>
                </div>

                {/* Claude Desktop Config */}
                <div className="mt-6">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-gray-700 flex items-center gap-2">
                      <Download className="h-4 w-4" />
                      Claude Desktop App
                    </span>
                    <button
                      onClick={() => copyConfig('desktop', JSON.stringify(generateDesktopConfig(newApiKey), null, 2))}
                      className="inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700"
                    >
                      {copiedConfig === 'desktop' ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                      {copiedConfig === 'desktop' ? 'Copied!' : 'Copy'}
                    </button>
                  </div>
                  <pre className="bg-gray-900 text-green-400 p-4 rounded-lg text-xs overflow-x-auto">
                    {JSON.stringify(generateDesktopConfig(newApiKey), null, 2)}
                  </pre>
                  <p className="text-xs text-gray-500 mt-2">
                    Add to <code className="bg-gray-100 px-1 rounded">~/Library/Application Support/Claude/claude_desktop_config.json</code> (macOS)
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tools List */}
      <div className="bg-white rounded-lg border border-gray-200">
        <div className="p-4 border-b border-gray-200 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900">Available Tools</h2>
          {!subscription && (
            <button
              onClick={toggleAllTools}
              className="text-sm text-primary-600 hover:text-primary-700"
            >
              {selectedTools.size === server.tools.length ? 'Deselect All' : 'Select All'}
            </button>
          )}
        </div>

        <div className="divide-y divide-gray-100">
          {server.tools.map((tool) => {
            const isSelected = selectedTools.has(tool.id);
            const accessStatus = getToolAccessStatus(tool.id);

            return (
              <div
                key={tool.id}
                className={`p-4 flex items-center gap-4 ${
                  !subscription ? 'cursor-pointer hover:bg-gray-50' : ''
                }`}
                onClick={() => !subscription && toggleTool(tool.id)}
                onKeyDown={(e) => e.key === 'Enter' && !subscription && toggleTool(tool.id)}
                role={!subscription ? 'button' : undefined}
                tabIndex={!subscription ? 0 : undefined}
                aria-pressed={!subscription ? isSelected : undefined}
              >
                {/* Selection Checkbox (only when not subscribed) */}
                {!subscription && (
                  <div className={`w-5 h-5 rounded border-2 flex items-center justify-center ${
                    isSelected
                      ? 'bg-primary-600 border-primary-600'
                      : 'border-gray-300'
                  }`}>
                    {isSelected && <Check className="h-3 w-3 text-white" />}
                  </div>
                )}

                {/* Tool Info */}
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <Wrench className="h-4 w-4 text-gray-400" />
                    <span className="font-medium text-gray-900">{tool.displayName}</span>
                    {tool.requires_approval && (
                      <span className="px-2 py-0.5 text-xs bg-amber-100 text-amber-700 rounded">
                        Requires Approval
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-gray-500 mt-1">{tool.description}</p>
                </div>

                {/* Access Status (only when subscribed) */}
                {subscription && accessStatus && (
                  <div className={`flex items-center gap-1 text-sm ${
                    accessStatus.status === 'enabled'
                      ? 'text-green-600'
                      : accessStatus.status === 'pending_approval'
                        ? 'text-amber-600'
                        : 'text-gray-400'
                  }`}>
                    {accessStatus.status === 'enabled' ? (
                      <><CheckCircle className="h-4 w-4" /> Enabled</>
                    ) : accessStatus.status === 'pending_approval' ? (
                      <><Clock className="h-4 w-4" /> Pending</>
                    ) : (
                      <><XCircle className="h-4 w-4" /> Disabled</>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Subscribe Button */}
      {!subscription && (
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-medium text-gray-900">Subscribe to {server.displayName}</h3>
              <p className="text-sm text-gray-500 mt-1">
                {selectedTools.size} of {server.tools.length} tools selected
              </p>
            </div>
            <button
              onClick={handleSubscribe}
              disabled={isSubscribing || selectedTools.size === 0}
              className="inline-flex items-center gap-2 px-6 py-3 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSubscribing ? (
                <>
                  <Loader2 className="h-5 w-5 animate-spin" />
                  Creating...
                </>
              ) : (
                <>
                  <Key className="h-5 w-5" />
                  Subscribe & Get API Key
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* Manage Subscription */}
      {subscription && (
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <h3 className="font-medium text-gray-900 mb-4">Subscription Management</h3>
          <div className="flex flex-wrap gap-3">
            <button className="inline-flex items-center gap-2 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors">
              <RefreshCw className="h-4 w-4" />
              Rotate API Key
            </button>
            <button className="inline-flex items-center gap-2 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors">
              <Shield className="h-4 w-4" />
              Request Additional Tools
            </button>
            <button className="inline-flex items-center gap-2 px-4 py-2 border border-red-300 text-red-700 rounded-lg hover:bg-red-50 transition-colors">
              <XCircle className="h-4 w-4" />
              Revoke Subscription
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default ServerDetailPage;
