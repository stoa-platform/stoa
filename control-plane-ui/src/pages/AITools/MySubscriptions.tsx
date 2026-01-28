// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Bell,
  Wrench,
  ExternalLink,
  AlertCircle,
  RefreshCw,
  Clock,
  Activity,
  Trash2,
} from 'lucide-react';
import { mcpGatewayService } from '../../services/mcpGatewayApi';
import type { ToolSubscription, MCPTool } from '../../types';

export function MySubscriptions() {
  const navigate = useNavigate();

  // State
  const [subscriptions, setSubscriptions] = useState<ToolSubscription[]>([]);
  const [tools, setTools] = useState<Map<string, MCPTool>>(new Map());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [unsubscribing, setUnsubscribing] = useState<string | null>(null);

  // Load data
  useEffect(() => {
    async function loadSubscriptions() {
      try {
        setLoading(true);
        setError(null);

        const subs = await mcpGatewayService.getMySubscriptions();
        setSubscriptions(subs);

        // Load tool details for each subscription
        const toolMap = new Map<string, MCPTool>();
        await Promise.all(
          subs.map(async (sub) => {
            try {
              const tool = await mcpGatewayService.getTool(sub.toolName);
              toolMap.set(sub.toolName, tool);
            } catch {
              // Tool might have been deleted
            }
          })
        );
        setTools(toolMap);
      } catch (err) {
        console.error('Failed to load subscriptions:', err);
        setError(err instanceof Error ? err.message : 'Failed to load subscriptions');
      } finally {
        setLoading(false);
      }
    }

    loadSubscriptions();
  }, []);

  // Handlers
  const handleUnsubscribe = async (subscription: ToolSubscription) => {
    try {
      setUnsubscribing(subscription.id);
      await mcpGatewayService.unsubscribeTool(subscription.id);
      setSubscriptions((prev) => prev.filter((s) => s.id !== subscription.id));
    } catch (err) {
      console.error('Failed to unsubscribe:', err);
    } finally {
      setUnsubscribing(null);
    }
  };

  const statusColors: Record<string, string> = {
    active: 'bg-green-100 text-green-800',
    suspended: 'bg-yellow-100 text-yellow-800',
    pending: 'bg-gray-100 text-gray-800',
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">My Subscriptions</h1>
          <p className="text-sm text-gray-500 mt-1">
            Manage your subscribed AI tools
          </p>
        </div>
        <Link
          to="/ai-tools"
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 transition-colors"
        >
          <Wrench className="h-4 w-4" />
          Browse Catalog
        </Link>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
          <AlertCircle className="h-5 w-5 flex-shrink-0" />
          <span className="text-sm">{error}</span>
        </div>
      )}

      {/* Subscriptions List */}
      {subscriptions.length > 0 ? (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Tool
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Usage
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Subscribed
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {subscriptions.map((sub) => {
                const tool = tools.get(sub.toolName);
                return (
                  <tr key={sub.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className="p-2 bg-blue-50 rounded-lg">
                          <Wrench className="h-5 w-5 text-blue-600" />
                        </div>
                        <div>
                          <button
                            onClick={() => navigate(`/ai-tools/${encodeURIComponent(sub.toolName)}`)}
                            className="font-medium text-gray-900 hover:text-blue-600"
                          >
                            {sub.toolName}
                          </button>
                          {tool && (
                            <p className="text-sm text-gray-500 line-clamp-1 max-w-xs">
                              {tool.description}
                            </p>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${statusColors[sub.status]}`}>
                        {sub.status}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2 text-sm text-gray-600">
                        <Activity className="h-4 w-4 text-gray-400" />
                        <span>{sub.usageCount} calls</span>
                        {sub.usageLimit && (
                          <span className="text-gray-400">
                            / {sub.usageLimit} limit
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2 text-sm text-gray-500">
                        <Clock className="h-4 w-4" />
                        {new Date(sub.subscribedAt).toLocaleDateString()}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => navigate(`/ai-tools/${encodeURIComponent(sub.toolName)}`)}
                          className="p-2 text-gray-400 hover:text-gray-600 transition-colors"
                          title="View details"
                        >
                          <ExternalLink className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => handleUnsubscribe(sub)}
                          disabled={unsubscribing === sub.id}
                          className="p-2 text-red-400 hover:text-red-600 transition-colors disabled:opacity-50"
                          title="Unsubscribe"
                        >
                          {unsubscribing === sub.id ? (
                            <RefreshCw className="h-4 w-4 animate-spin" />
                          ) : (
                            <Trash2 className="h-4 w-4" />
                          )}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="text-center py-12 bg-white rounded-lg border border-gray-200">
          <Bell className="h-12 w-12 text-gray-300 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">No subscriptions yet</h3>
          <p className="text-sm text-gray-500 mb-4">
            Subscribe to AI tools from the catalog to start using them
          </p>
          <Link
            to="/ai-tools"
            className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 transition-colors"
          >
            <Wrench className="h-4 w-4" />
            Browse Tool Catalog
          </Link>
        </div>
      )}

      {/* Help Section */}
      {subscriptions.length > 0 && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <h4 className="font-medium text-blue-900 mb-2">Using Subscribed Tools</h4>
          <p className="text-sm text-blue-700">
            Subscribed tools are automatically available in your MCP client (Claude Desktop, Cursor, etc.).
            Configure your client to connect to the STOA MCP Gateway to start using these tools.
            Visit any tool's "Quick Start" tab for setup instructions.
          </p>
        </div>
      )}
    </div>
  );
}
