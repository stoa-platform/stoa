// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * API Key Modal Component
 *
 * Displays the API key after subscription creation.
 * The key is shown only ONCE and must be copied before closing.
 *
 * Reference: Linear CAB-292
 */

import { useState } from 'react';
import {
  X,
  Key,
  Copy,
  CheckCircle,
  AlertTriangle,
  ExternalLink,
  Download,
} from 'lucide-react';

interface ApiKeyModalProps {
  isOpen: boolean;
  onClose: () => void;
  apiKey: string;
  toolId: string;
  toolName?: string;
}

export function ApiKeyModal({
  isOpen,
  onClose,
  apiKey,
  toolId,
  toolName,
}: ApiKeyModalProps) {
  const [copied, setCopied] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(apiKey);
      setCopied(true);
      setTimeout(() => setCopied(false), 3000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const handleDownloadConfig = () => {
    const config = {
      mcpServers: {
        stoa: {
          command: 'npx',
          args: ['-y', '@anthropic/mcp-client', 'stdio'],
          env: {
            STOA_API_KEY: apiKey,
            STOA_MCP_URL: 'https://mcp.gostoa.dev',
          },
        },
      },
    };

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

  const handleClose = () => {
    if (acknowledged) {
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
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
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="relative bg-white rounded-xl shadow-xl max-w-lg w-full">
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-gray-200">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-green-100 rounded-lg">
                <CheckCircle className="h-6 w-6 text-green-600" />
              </div>
              <div>
                <h2 className="text-xl font-semibold text-gray-900">
                  Subscription Created
                </h2>
                <p className="text-sm text-gray-500 mt-0.5">
                  {toolName || toolId}
                </p>
              </div>
            </div>
            {acknowledged && (
              <button
                onClick={handleClose}
                className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            )}
          </div>

          {/* Content */}
          <div className="p-6 space-y-6">
            {/* Warning */}
            <div className="flex items-start gap-3 p-4 bg-amber-50 border border-amber-200 rounded-lg">
              <AlertTriangle className="h-5 w-5 text-amber-500 mt-0.5 flex-shrink-0" />
              <div>
                <h4 className="font-medium text-amber-800">
                  Save Your API Key Now
                </h4>
                <p className="text-sm text-amber-700 mt-1">
                  This API key will only be shown <strong>once</strong>. Make sure to copy
                  and store it securely before closing this modal. You will not be able
                  to retrieve it later.
                </p>
              </div>
            </div>

            {/* API Key Display */}
            <div>
              <span id="api-key-label" className="block text-sm font-medium text-gray-700 mb-2">
                Your API Key
              </span>
              <div className="relative">
                <div className="flex items-center gap-2">
                  <div className="flex-1 flex items-center gap-2 px-4 py-3 bg-gray-900 rounded-lg">
                    <Key className="h-4 w-4 text-gray-400 flex-shrink-0" />
                    <code className="flex-1 text-sm font-mono text-green-400 break-all select-all">
                      {apiKey}
                    </code>
                  </div>
                  <button
                    onClick={handleCopy}
                    className={`p-3 rounded-lg transition-colors ${
                      copied
                        ? 'bg-green-100 text-green-600'
                        : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                    }`}
                    title={copied ? 'Copied!' : 'Copy to clipboard'}
                  >
                    {copied ? (
                      <CheckCircle className="h-5 w-5" />
                    ) : (
                      <Copy className="h-5 w-5" />
                    )}
                  </button>
                </div>
                {copied && (
                  <p className="mt-2 text-sm text-green-600 font-medium">
                    Copied to clipboard!
                  </p>
                )}
              </div>
            </div>

            {/* Quick Actions */}
            <div className="flex flex-wrap gap-3">
              <button
                onClick={handleDownloadConfig}
                className="inline-flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors text-sm font-medium"
              >
                <Download className="h-4 w-4" />
                Download Config
              </button>
              <a
                href="/subscriptions"
                className="inline-flex items-center gap-2 px-4 py-2 text-primary-600 hover:text-primary-700 hover:bg-primary-50 rounded-lg transition-colors text-sm font-medium"
              >
                <ExternalLink className="h-4 w-4" />
                View Subscriptions
              </a>
            </div>

            {/* Usage Example */}
            <div>
              <span className="block text-sm font-medium text-gray-700 mb-2">
                Usage Example
              </span>
              <div className="bg-gray-900 rounded-lg p-4 overflow-x-auto">
                <pre className="text-sm text-gray-100 font-mono whitespace-pre-wrap">
{`# Use with Claude Desktop
# Add to ~/.config/claude/claude_desktop_config.json

# Or use the API directly:
curl -X POST https://mcp.gostoa.dev/mcp/v1/invoke \\
  -H "Authorization: Bearer ${apiKey.substring(0, 8)}..." \\
  -H "Content-Type: application/json" \\
  -d '{"tool": "${toolId}", "args": {}}'`}
                </pre>
              </div>
            </div>

            {/* Acknowledgment */}
            <label className="flex items-start gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={acknowledged}
                onChange={(e) => setAcknowledged(e.target.checked)}
                className="mt-1 h-4 w-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
              />
              <span className="text-sm text-gray-700">
                I have copied and securely stored my API key. I understand that this
                key will not be shown again.
              </span>
            </label>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end gap-3 p-6 border-t border-gray-200">
            <button
              onClick={handleClose}
              disabled={!acknowledged}
              className={`px-6 py-2 rounded-lg font-medium transition-colors ${
                acknowledged
                  ? 'bg-primary-600 text-white hover:bg-primary-700'
                  : 'bg-gray-200 text-gray-400 cursor-not-allowed'
              }`}
            >
              Done
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ApiKeyModal;
