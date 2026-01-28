// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * Export Config Modal (CAB-296)
 *
 * Allows users to export MCP configuration for Claude Desktop / Cursor.
 * Supports both API Key and OAuth2 (client credentials) authentication.
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  X,
  Download,
  Copy,
  Check,
  AlertCircle,
  FileJson,
  Terminal,
  Key,
  Shield,
  ExternalLink,
} from 'lucide-react';
import type { MCPSubscription } from '../../types';

interface ExportConfigModalProps {
  subscription: MCPSubscription;
  isOpen: boolean;
  onClose: () => void;
}

type AuthMethod = 'apiKey' | 'oauth2';

// STOA logo URL for Claude Desktop display
const STOA_LOGO_URL = 'https://raw.githubusercontent.com/stoa-platform/stoa/main/docs/assets/logo.svg';
const MCP_GATEWAY_URL = 'https://mcp.gostoa.dev';

export function ExportConfigModal({
  subscription,
  isOpen,
  onClose,
}: ExportConfigModalProps) {
  const [authMethod, setAuthMethod] = useState<AuthMethod>('oauth2');
  const [apiKey, setApiKey] = useState('');
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [copied, setCopied] = useState(false);

  // Generate slug from tool_id
  const toolSlug = subscription.tool_id
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9-]/g, '');

  const serverName = `stoa-${toolSlug}`;

  // Build MCP config based on auth method
  const buildConfig = () => {
    if (authMethod === 'apiKey' && apiKey.trim()) {
      // API Key auth - uses Bearer token directly
      return {
        mcpServers: {
          [serverName]: {
            url: `${MCP_GATEWAY_URL}/mcp/sse`,
            transport: 'sse',
            headers: {
              Authorization: `Bearer ${apiKey}`,
            },
            metadata: {
              icon: STOA_LOGO_URL,
              title: `STOA - ${subscription.tool_id}`,
            },
          },
        },
      };
    }

    if (authMethod === 'oauth2' && clientId.trim() && clientSecret.trim()) {
      // OAuth2 Client Credentials - uses Basic Auth
      // Note: Claude Desktop may need the bridge for this to work
      return {
        mcpServers: {
          [serverName]: {
            url: `${MCP_GATEWAY_URL}/mcp/sse`,
            transport: 'sse',
            headers: {
              Authorization: `Basic ${btoa(`${clientId}:${clientSecret}`)}`,
            },
            metadata: {
              icon: STOA_LOGO_URL,
              title: `STOA - ${subscription.tool_id}`,
            },
          },
        },
      };
    }

    return null;
  };

  const config = buildConfig();

  const handleDownload = () => {
    if (!config) return;

    const blob = new Blob([JSON.stringify(config, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'claude_desktop_config.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleCopy = async () => {
    if (!config) return;

    try {
      await navigator.clipboard.writeText(JSON.stringify(config, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API failed silently
    }
  };

  const handleClose = () => {
    setApiKey('');
    setClientId('');
    setClientSecret('');
    onClose();
  };

  if (!isOpen) return null;

  const isValid = authMethod === 'apiKey'
    ? apiKey.trim().length > 0
    : clientId.trim().length > 0 && clientSecret.trim().length > 0;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex min-h-full items-center justify-center p-4">
        {/* Backdrop */}
        <div
          className="fixed inset-0 bg-black/50 transition-opacity"
          onClick={handleClose}
          onKeyDown={(e) => e.key === 'Escape' && handleClose()}
          role="button"
          aria-label="Close modal"
          tabIndex={0}
        />

        {/* Modal */}
        <div className="relative bg-white rounded-xl shadow-xl max-w-lg w-full">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-primary-50 rounded-lg">
                <FileJson className="h-5 w-5 text-primary-600" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-gray-900">
                  Export MCP Config
                </h3>
                <p className="text-sm text-gray-500">
                  For Claude Desktop / Cursor
                </p>
              </div>
            </div>
            <button
              onClick={handleClose}
              className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Content */}
          <div className="px-6 py-4 space-y-4">
            {/* Tool Info */}
            <div className="bg-gray-50 rounded-lg p-4">
              <div className="flex items-center gap-3">
                <img
                  src={STOA_LOGO_URL}
                  alt="STOA"
                  className="h-8 w-8"
                  onError={(e) => {
                    e.currentTarget.style.display = 'none';
                  }}
                />
                <div>
                  <p className="text-sm text-gray-600">
                    <span className="font-medium">Tool:</span> {subscription.tool_id}
                  </p>
                  <p className="text-sm text-gray-600 mt-0.5">
                    <span className="font-medium">Key Prefix:</span>{' '}
                    <code className="bg-gray-100 px-1.5 py-0.5 rounded text-xs">
                      {subscription.api_key_prefix}...
                    </code>
                  </p>
                </div>
              </div>
            </div>

            {/* Auth Method Selection */}
            <div role="radiogroup" aria-labelledby="auth-method-label">
              <span id="auth-method-label" className="block text-sm font-medium text-gray-700 mb-2">
                Authentication Method
              </span>
              <div className="grid grid-cols-2 gap-3">
                <button
                  onClick={() => setAuthMethod('oauth2')}
                  className={`flex items-center gap-2 p-3 rounded-lg border-2 transition-colors ${
                    authMethod === 'oauth2'
                      ? 'border-primary-500 bg-primary-50 text-primary-700'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <Shield className="h-4 w-4" />
                  <div className="text-left">
                    <p className="text-sm font-medium">OAuth2</p>
                    <p className="text-xs opacity-70">Client Credentials</p>
                  </div>
                </button>
                <button
                  onClick={() => setAuthMethod('apiKey')}
                  className={`flex items-center gap-2 p-3 rounded-lg border-2 transition-colors ${
                    authMethod === 'apiKey'
                      ? 'border-primary-500 bg-primary-50 text-primary-700'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <Key className="h-4 w-4" />
                  <div className="text-left">
                    <p className="text-sm font-medium">API Key</p>
                    <p className="text-xs opacity-70">Bearer Token</p>
                  </div>
                </button>
              </div>
            </div>

            {/* Auth Inputs */}
            {authMethod === 'apiKey' ? (
              <div>
                <label
                  htmlFor="apiKey"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  API Key
                </label>
                <input
                  id="apiKey"
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="stoa_sk_..."
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 font-mono text-sm"
                />
                <p className="mt-1 text-xs text-gray-500">
                  Use "Reveal Key" first if you don't have your API key.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                <div>
                  <label
                    htmlFor="clientId"
                    className="block text-sm font-medium text-gray-700 mb-1"
                  >
                    Client ID
                  </label>
                  <input
                    id="clientId"
                    type="text"
                    value={clientId}
                    onChange={(e) => setClientId(e.target.value)}
                    placeholder="stoa-mcp-client"
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm"
                  />
                </div>
                <div>
                  <label
                    htmlFor="clientSecret"
                    className="block text-sm font-medium text-gray-700 mb-1"
                  >
                    Client Secret
                  </label>
                  <input
                    id="clientSecret"
                    type="password"
                    value={clientSecret}
                    onChange={(e) => setClientSecret(e.target.value)}
                    placeholder="your-client-secret"
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 font-mono text-sm"
                  />
                </div>
                <div className="flex items-center justify-between">
                  <p className="text-xs text-gray-500">
                    Create service accounts in your profile.
                  </p>
                  <Link
                    to="/service-accounts"
                    onClick={handleClose}
                    className="inline-flex items-center gap-1 text-xs text-primary-600 hover:text-primary-700 font-medium"
                  >
                    Manage Service Accounts
                    <ExternalLink className="h-3 w-3" />
                  </Link>
                </div>
              </div>
            )}

            {/* Config Preview */}
            {config && (
              <>
                <div className="bg-green-50 border border-green-200 rounded-lg p-3">
                  <p className="text-sm text-green-700 flex items-center gap-2">
                    <Check className="h-4 w-4" />
                    Config ready to download!
                  </p>
                </div>

                <div>
                  <span className="block text-sm font-medium text-gray-700 mb-1">
                    Configuration Preview
                  </span>
                  <pre className="bg-gray-900 text-green-400 p-4 rounded-lg text-xs overflow-x-auto max-h-48">
                    {JSON.stringify(config, null, 2)}
                  </pre>
                </div>
              </>
            )}

            {/* Instructions */}
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
              <h4 className="text-sm font-medium text-blue-800 mb-2 flex items-center gap-2">
                <Terminal className="h-4 w-4" />
                How to use
              </h4>
              <ol className="text-sm text-blue-700 list-decimal list-inside space-y-1">
                <li>Fill in your credentials above</li>
                <li>Download or copy the config</li>
                <li>
                  Merge into your{' '}
                  <code className="bg-blue-100 px-1 rounded">
                    claude_desktop_config.json
                  </code>
                </li>
                <li>Restart Claude Desktop / Cursor</li>
              </ol>
            </div>

            {!isValid && (
              <div className="flex items-start gap-2 p-3 bg-amber-50 border border-amber-200 rounded-lg">
                <AlertCircle className="h-5 w-5 text-amber-500 flex-shrink-0 mt-0.5" />
                <div className="text-sm text-amber-700">
                  {authMethod === 'apiKey' ? (
                    <p>Use "Reveal Key" first if you don't have your API key saved.</p>
                  ) : (
                    <p>
                      Don't have credentials?{' '}
                      <Link
                        to="/service-accounts"
                        onClick={handleClose}
                        className="text-amber-800 underline hover:no-underline font-medium"
                      >
                        Create a Service Account
                      </Link>{' '}
                      to get your client_id and client_secret.
                    </p>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-200 bg-gray-50 rounded-b-xl">
            <button
              onClick={handleClose}
              className="px-4 py-2 text-gray-700 hover:text-gray-900 font-medium transition-colors"
            >
              Close
            </button>

            <button
              onClick={handleCopy}
              disabled={!config}
              className="inline-flex items-center gap-2 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {copied ? (
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

            <button
              onClick={handleDownload}
              disabled={!config}
              className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <Download className="h-4 w-4" />
              Download
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ExportConfigModal;
