// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
import { useState } from 'react';
import { X } from 'lucide-react';
import { externalMcpServersService } from '../../services/externalMcpServersApi';
import type {
  ExternalMCPServerCreate,
  ExternalMCPServerUpdate,
  ExternalMCPServer,
  ExternalMCPTransport,
  ExternalMCPAuthType,
} from '../../types';

interface ExternalMCPServerModalProps {
  server?: ExternalMCPServer;
  onClose: () => void;
  onSubmit: (data: ExternalMCPServerCreate | ExternalMCPServerUpdate) => Promise<void>;
}

const transportOptions: { value: ExternalMCPTransport; label: string; description: string }[] = [
  { value: 'sse', label: 'SSE', description: 'Server-Sent Events (Claude Desktop compatible)' },
  { value: 'http', label: 'HTTP', description: 'HTTP JSON-RPC' },
  { value: 'websocket', label: 'WebSocket', description: 'WebSocket transport' },
];

const authTypeOptions: { value: ExternalMCPAuthType; label: string; description: string }[] = [
  { value: 'none', label: 'None', description: 'No authentication required' },
  { value: 'api_key', label: 'API Key', description: 'API key in request header' },
  { value: 'bearer_token', label: 'Bearer Token', description: 'Bearer token authentication' },
  { value: 'oauth2', label: 'OAuth2', description: 'OAuth2 client credentials flow' },
];

export function ExternalMCPServerModal({ server, onClose, onSubmit }: ExternalMCPServerModalProps) {
  const isEdit = !!server;

  const [formData, setFormData] = useState<ExternalMCPServerCreate>({
    name: server?.name || '',
    display_name: server?.display_name || '',
    description: server?.description || '',
    icon: server?.icon || '',
    base_url: server?.base_url || '',
    transport: server?.transport || 'sse',
    auth_type: server?.auth_type || 'none',
    tool_prefix: server?.tool_prefix || '',
    credentials: {},
  });

  const [credentialApiKey, setCredentialApiKey] = useState('');
  const [credentialBearerToken, setCredentialBearerToken] = useState('');
  const [credentialOAuth2, setCredentialOAuth2] = useState({
    client_id: '',
    client_secret: '',
    token_url: '',
    scope: '',
  });

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [testing, setTesting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      // Build credentials based on auth type
      let credentials = undefined;
      if (formData.auth_type === 'api_key' && credentialApiKey) {
        credentials = { api_key: credentialApiKey };
      } else if (formData.auth_type === 'bearer_token' && credentialBearerToken) {
        credentials = { bearer_token: credentialBearerToken };
      } else if (formData.auth_type === 'oauth2' && credentialOAuth2.client_id) {
        credentials = { oauth2: credentialOAuth2 };
      }

      const submitData = {
        ...formData,
        credentials,
      };

      await onSubmit(submitData);
    } catch (err: any) {
      setError(err.message || 'Failed to save server');
    } finally {
      setLoading(false);
    }
  };

  const handleTestConnection = async () => {
    if (!server) return;

    setTesting(true);
    setTestResult(null);

    try {
      const result = await externalMcpServersService.testConnection(server.id);
      setTestResult({
        success: result.success,
        message: result.success
          ? `Connected! ${result.tools_discovered !== undefined ? `Found ${result.tools_discovered} tools.` : ''} Latency: ${result.latency_ms}ms`
          : `Failed: ${result.error}`,
      });
    } catch (err: any) {
      setTestResult({
        success: false,
        message: err.message || 'Connection test failed',
      });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex justify-between items-center px-6 py-4 border-b">
          <h2 className="text-lg font-semibold text-gray-900">
            {isEdit ? 'Edit External MCP Server' : 'Add External MCP Server'}
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* Error Alert */}
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
              {error}
            </div>
          )}

          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              placeholder="linear"
              required
              disabled={isEdit}
              pattern="^[a-z][a-z0-9-_]*$"
              title="Lowercase letters, numbers, hyphens, and underscores. Must start with a letter."
            />
            <p className="text-xs text-gray-500 mt-1">Unique identifier (slug). Used for tool prefixes.</p>
          </div>

          {/* Display Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Display Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={formData.display_name}
              onChange={(e) => setFormData({ ...formData, display_name: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              placeholder="Linear"
              required
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <textarea
              value={formData.description || ''}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              rows={2}
              placeholder="Issue tracking for modern software teams"
            />
          </div>

          {/* Base URL */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Base URL <span className="text-red-500">*</span>
            </label>
            <input
              type="url"
              value={formData.base_url}
              onChange={(e) => setFormData({ ...formData, base_url: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              placeholder="https://mcp.linear.app/sse"
              required
            />
          </div>

          {/* Transport */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Transport</label>
            <select
              value={formData.transport}
              onChange={(e) => setFormData({ ...formData, transport: e.target.value as ExternalMCPTransport })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              {transportOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label} - {opt.description}
                </option>
              ))}
            </select>
          </div>

          {/* Auth Type */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Authentication</label>
            <select
              value={formData.auth_type}
              onChange={(e) => setFormData({ ...formData, auth_type: e.target.value as ExternalMCPAuthType })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              {authTypeOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label} - {opt.description}
                </option>
              ))}
            </select>
          </div>

          {/* Credentials - API Key */}
          {formData.auth_type === 'api_key' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">API Key</label>
              <input
                type="password"
                value={credentialApiKey}
                onChange={(e) => setCredentialApiKey(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="Enter API key"
              />
              <p className="text-xs text-gray-500 mt-1">Stored securely in Vault. Leave empty to keep existing.</p>
            </div>
          )}

          {/* Credentials - Bearer Token */}
          {formData.auth_type === 'bearer_token' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Bearer Token</label>
              <input
                type="password"
                value={credentialBearerToken}
                onChange={(e) => setCredentialBearerToken(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="Enter bearer token"
              />
              <p className="text-xs text-gray-500 mt-1">Stored securely in Vault. Leave empty to keep existing.</p>
            </div>
          )}

          {/* Credentials - OAuth2 */}
          {formData.auth_type === 'oauth2' && (
            <div className="space-y-3 p-4 bg-gray-50 rounded-lg">
              <h4 className="text-sm font-medium text-gray-700">OAuth2 Configuration</h4>
              <div>
                <label className="block text-xs text-gray-600 mb-1">Client ID</label>
                <input
                  type="text"
                  value={credentialOAuth2.client_id}
                  onChange={(e) => setCredentialOAuth2({ ...credentialOAuth2, client_id: e.target.value })}
                  className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
                  placeholder="Client ID"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-600 mb-1">Client Secret</label>
                <input
                  type="password"
                  value={credentialOAuth2.client_secret}
                  onChange={(e) => setCredentialOAuth2({ ...credentialOAuth2, client_secret: e.target.value })}
                  className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
                  placeholder="Client Secret"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-600 mb-1">Token URL</label>
                <input
                  type="url"
                  value={credentialOAuth2.token_url}
                  onChange={(e) => setCredentialOAuth2({ ...credentialOAuth2, token_url: e.target.value })}
                  className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
                  placeholder="https://auth.example.com/oauth/token"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-600 mb-1">Scope (optional)</label>
                <input
                  type="text"
                  value={credentialOAuth2.scope}
                  onChange={(e) => setCredentialOAuth2({ ...credentialOAuth2, scope: e.target.value })}
                  className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
                  placeholder="read write"
                />
              </div>
            </div>
          )}

          {/* Tool Prefix */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Tool Prefix</label>
            <input
              type="text"
              value={formData.tool_prefix || ''}
              onChange={(e) => setFormData({ ...formData, tool_prefix: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              placeholder={formData.name || 'linear'}
            />
            <p className="text-xs text-gray-500 mt-1">
              Tools will be named: <code className="bg-gray-100 px-1 rounded">{formData.tool_prefix || formData.name || 'prefix'}__tool_name</code>
            </p>
          </div>

          {/* Icon URL */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Icon URL</label>
            <input
              type="url"
              value={formData.icon || ''}
              onChange={(e) => setFormData({ ...formData, icon: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              placeholder="https://example.com/icon.png"
            />
          </div>

          {/* Test Connection Result */}
          {testResult && (
            <div className={`px-4 py-3 rounded-lg text-sm ${testResult.success ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>
              {testResult.message}
            </div>
          )}
        </form>

        {/* Footer */}
        <div className="flex justify-between items-center px-6 py-4 border-t bg-gray-50">
          <div>
            {isEdit && (
              <button
                type="button"
                onClick={handleTestConnection}
                disabled={testing}
                className="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-white disabled:opacity-50"
              >
                {testing ? 'Testing...' : 'Test Connection'}
              </button>
            )}
          </div>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-white"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {loading ? 'Saving...' : isEdit ? 'Update Server' : 'Create Server'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
