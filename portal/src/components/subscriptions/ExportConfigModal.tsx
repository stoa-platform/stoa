/**
 * Export Config Modal (CAB-296)
 *
 * Allows users to export MCP configuration for Claude Desktop / Cursor.
 * User enters their API key to generate a ready-to-use config.
 */

import { useState } from 'react';
import {
  X,
  Download,
  Copy,
  Check,
  AlertCircle,
  FileJson,
  Terminal,
} from 'lucide-react';
import type { MCPSubscription } from '../../types';

interface ExportConfigModalProps {
  subscription: MCPSubscription;
  isOpen: boolean;
  onClose: () => void;
}

export function ExportConfigModal({
  subscription,
  isOpen,
  onClose,
}: ExportConfigModalProps) {
  const [apiKey, setApiKey] = useState('');
  const [copied, setCopied] = useState(false);

  // Generate slug from tool_id
  const toolSlug = subscription.tool_id
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9-]/g, '');

  // Build MCP config with the entered API key
  const config = apiKey.trim()
    ? {
        mcpServers: {
          [`stoa-${toolSlug}`]: {
            url: `https://mcp.stoa.cab-i.com/tools/${toolSlug}`,
            headers: {
              Authorization: `Bearer ${apiKey}`,
            },
          },
        },
      }
    : null;

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
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex min-h-full items-center justify-center p-4">
        {/* Backdrop */}
        <div
          className="fixed inset-0 bg-black/50 transition-opacity"
          onClick={handleClose}
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
              <p className="text-sm text-gray-600">
                <span className="font-medium">Tool:</span> {subscription.tool_id}
              </p>
              <p className="text-sm text-gray-600 mt-1">
                <span className="font-medium">Key Prefix:</span>{' '}
                <code className="bg-gray-100 px-1.5 py-0.5 rounded text-xs">
                  {subscription.api_key_prefix}...
                </code>
              </p>
            </div>

            {/* API Key Input */}
            <div>
              <label
                htmlFor="apiKey"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                Enter your API Key
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
                Enter your API key to generate a ready-to-use config file.
              </p>
            </div>

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
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Configuration Preview
                  </label>
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
                <li>Enter your API key above</li>
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

            {!apiKey.trim() && (
              <div className="flex items-start gap-2 p-3 bg-amber-50 border border-amber-200 rounded-lg">
                <AlertCircle className="h-5 w-5 text-amber-500 flex-shrink-0 mt-0.5" />
                <p className="text-sm text-amber-700">
                  Use "Reveal Key" first if you don't have your API key saved.
                </p>
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
