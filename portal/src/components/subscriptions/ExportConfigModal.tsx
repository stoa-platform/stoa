/**
 * Export Config Modal (CAB-296)
 *
 * Allows users to export MCP configuration for Claude Desktop / Cursor.
 * Uses OAuth2 (client credentials) authentication.
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
  ExternalLink,
} from 'lucide-react';
import type { MCPSubscription } from '../../types';

interface ExportConfigModalProps {
  subscription: MCPSubscription;
  isOpen: boolean;
  onClose: () => void;
}

// STOA logo URL for Claude Desktop display
const STOA_LOGO_URL =
  'https://raw.githubusercontent.com/stoa-platform/stoa/main/docs/assets/logo.svg';
const MCP_GATEWAY_URL = 'https://mcp.gostoa.dev';

export function ExportConfigModal({ subscription, isOpen, onClose }: ExportConfigModalProps) {
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [copied, setCopied] = useState(false);

  // Generate slug from tool_id
  const toolSlug = subscription.tool_id
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9-]/g, '');

  const serverName = `stoa-${toolSlug}`;

  // Build MCP config using OAuth2 client credentials
  const buildConfig = () => {
    if (clientId.trim() && clientSecret.trim()) {
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
    setClientId('');
    setClientSecret('');
    onClose();
  };

  if (!isOpen) return null;

  const isValid = clientId.trim().length > 0 && clientSecret.trim().length > 0;

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
        <div className="relative bg-white dark:bg-neutral-800 rounded-xl shadow-xl max-w-lg w-full">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-200 dark:border-neutral-700">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-primary-50 dark:bg-primary-900/30 rounded-lg">
                <FileJson className="h-5 w-5 text-primary-600 dark:text-primary-400" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-neutral-900 dark:text-white">
                  Export MCP Config
                </h3>
                <p className="text-sm text-neutral-500 dark:text-neutral-400">
                  For Claude Desktop / Cursor
                </p>
              </div>
            </div>
            <button
              onClick={handleClose}
              className="p-2 text-neutral-400 dark:text-neutral-500 hover:text-neutral-600 dark:hover:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded-lg transition-colors"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Content */}
          <div className="px-6 py-4 space-y-4">
            {/* Tool Info */}
            <div className="bg-neutral-50 dark:bg-neutral-900 rounded-lg p-4">
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
                  <p className="text-sm text-neutral-600 dark:text-neutral-400">
                    <span className="font-medium">Tool:</span> {subscription.tool_id}
                  </p>
                </div>
              </div>
            </div>

            {/* OAuth2 Credentials */}
            <div className="space-y-3">
              <div>
                <label
                  htmlFor="clientId"
                  className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1"
                >
                  Client ID
                </label>
                <input
                  id="clientId"
                  type="text"
                  value={clientId}
                  onChange={(e) => setClientId(e.target.value)}
                  placeholder="stoa-mcp-client"
                  className="w-full px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm dark:bg-neutral-800 dark:text-white"
                />
              </div>
              <div>
                <label
                  htmlFor="clientSecret"
                  className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1"
                >
                  Client Secret
                </label>
                <input
                  id="clientSecret"
                  type="password"
                  value={clientSecret}
                  onChange={(e) => setClientSecret(e.target.value)}
                  placeholder="your-client-secret"
                  className="w-full px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 font-mono text-sm dark:bg-neutral-800 dark:text-white"
                />
              </div>
              <div className="flex items-center justify-between">
                <p className="text-xs text-neutral-500 dark:text-neutral-400">
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

            {/* Config Preview */}
            {config && (
              <>
                <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-3">
                  <p className="text-sm text-green-700 dark:text-green-400 flex items-center gap-2">
                    <Check className="h-4 w-4" />
                    Config ready to download!
                  </p>
                </div>

                <div>
                  <span className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                    Configuration Preview
                  </span>
                  <pre className="bg-neutral-900 text-green-400 p-4 rounded-lg text-xs overflow-x-auto max-h-48">
                    {JSON.stringify(config, null, 2)}
                  </pre>
                </div>
              </>
            )}

            {/* Instructions */}
            <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
              <h4 className="text-sm font-medium text-blue-800 dark:text-blue-300 mb-2 flex items-center gap-2">
                <Terminal className="h-4 w-4" />
                How to use
              </h4>
              <ol className="text-sm text-blue-700 dark:text-blue-400 list-decimal list-inside space-y-1">
                <li>Fill in your credentials above</li>
                <li>Download or copy the config</li>
                <li>
                  Merge into your{' '}
                  <code className="bg-blue-100 dark:bg-blue-900/40 px-1 rounded">
                    claude_desktop_config.json
                  </code>
                </li>
                <li>Restart Claude Desktop / Cursor</li>
              </ol>
            </div>

            {!isValid && (
              <div className="flex items-start gap-2 p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg">
                <AlertCircle className="h-5 w-5 text-amber-500 flex-shrink-0 mt-0.5" />
                <div className="text-sm text-amber-700 dark:text-amber-400">
                  <p>
                    Don't have credentials?{' '}
                    <Link
                      to="/service-accounts"
                      onClick={handleClose}
                      className="text-amber-800 dark:text-amber-300 underline hover:no-underline font-medium"
                    >
                      Create a Service Account
                    </Link>{' '}
                    to get your client_id and client_secret.
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-900 rounded-b-xl">
            <button
              onClick={handleClose}
              className="px-4 py-2 text-neutral-700 dark:text-neutral-300 hover:text-neutral-900 dark:hover:text-white font-medium transition-colors"
            >
              Close
            </button>

            <button
              onClick={handleCopy}
              disabled={!config}
              className="inline-flex items-center gap-2 px-4 py-2 border border-neutral-300 dark:border-neutral-600 text-neutral-700 dark:text-neutral-300 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
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
