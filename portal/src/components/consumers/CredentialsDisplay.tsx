/**
 * Credentials Display Component
 *
 * Displays consumer OAuth credentials after activation (CAB-1121).
 * Shows client_id, client_secret (one-time), and token endpoint.
 */

import { useState } from 'react';
import { Copy, Check, Eye, EyeOff, AlertTriangle, Key, Globe } from 'lucide-react';
import type { ConsumerCredentials } from '../../types';

interface CredentialsDisplayProps {
  credentials: ConsumerCredentials;
}

export function CredentialsDisplay({ credentials }: CredentialsDisplayProps) {
  const [showSecret, setShowSecret] = useState(true);
  const [copiedField, setCopiedField] = useState<string | null>(null);

  const copyToClipboard = async (value: string, field: string) => {
    await navigator.clipboard.writeText(value);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 2000);
  };

  const maskedSecret = credentials.client_secret.replace(/./g, '*');

  return (
    <div className="space-y-4">
      {/* One-time warning */}
      <div className="flex items-start gap-2 p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg">
        <AlertTriangle className="h-5 w-5 text-amber-500 mt-0.5 flex-shrink-0" />
        <div className="text-sm text-amber-700 dark:text-amber-300">
          <strong>Important:</strong> The client secret is only shown once. Copy and store it
          securely now. You will not be able to retrieve it again.
        </div>
      </div>

      {/* Client ID */}
      <div>
        <span className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1">
          Client ID
        </span>
        <div className="flex items-center gap-2">
          <div className="flex-1 flex items-center gap-2 px-4 py-2 bg-gray-50 dark:bg-neutral-700 border border-gray-200 dark:border-neutral-600 rounded-lg font-mono text-sm text-gray-900 dark:text-white">
            <Key className="h-4 w-4 text-gray-400 dark:text-neutral-500 flex-shrink-0" />
            <span className="flex-1 truncate">{credentials.client_id}</span>
          </div>
          <button
            onClick={() => copyToClipboard(credentials.client_id, 'client_id')}
            className="p-2 text-gray-500 hover:text-gray-700 dark:hover:text-neutral-200 hover:bg-gray-100 dark:hover:bg-neutral-700 rounded-lg transition-colors"
            title="Copy Client ID"
          >
            {copiedField === 'client_id' ? (
              <Check className="h-5 w-5 text-green-500" />
            ) : (
              <Copy className="h-5 w-5" />
            )}
          </button>
        </div>
      </div>

      {/* Client Secret */}
      <div>
        <span className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1">
          Client Secret
        </span>
        <div className="flex items-center gap-2">
          <div className="flex-1 flex items-center gap-2 px-4 py-2 bg-gray-50 dark:bg-neutral-700 border border-gray-200 dark:border-neutral-600 rounded-lg font-mono text-sm text-gray-900 dark:text-white">
            <Key className="h-4 w-4 text-gray-400 dark:text-neutral-500 flex-shrink-0" />
            <span className="flex-1 truncate">
              {showSecret ? credentials.client_secret : maskedSecret}
            </span>
          </div>
          <button
            onClick={() => setShowSecret(!showSecret)}
            className="p-2 text-gray-500 hover:text-gray-700 dark:hover:text-neutral-200 hover:bg-gray-100 dark:hover:bg-neutral-700 rounded-lg transition-colors"
            title={showSecret ? 'Hide secret' : 'Show secret'}
          >
            {showSecret ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
          </button>
          <button
            onClick={() => copyToClipboard(credentials.client_secret, 'client_secret')}
            className="p-2 text-gray-500 hover:text-gray-700 dark:hover:text-neutral-200 hover:bg-gray-100 dark:hover:bg-neutral-700 rounded-lg transition-colors"
            title="Copy Client Secret"
          >
            {copiedField === 'client_secret' ? (
              <Check className="h-5 w-5 text-green-500" />
            ) : (
              <Copy className="h-5 w-5" />
            )}
          </button>
        </div>
      </div>

      {/* Token Endpoint */}
      <div>
        <span className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1">
          Token Endpoint
        </span>
        <div className="flex items-center gap-2">
          <div className="flex-1 flex items-center gap-2 px-4 py-2 bg-gray-50 dark:bg-neutral-700 border border-gray-200 dark:border-neutral-600 rounded-lg font-mono text-sm text-gray-900 dark:text-white">
            <Globe className="h-4 w-4 text-gray-400 dark:text-neutral-500 flex-shrink-0" />
            <span className="flex-1 truncate">{credentials.token_endpoint}</span>
          </div>
          <button
            onClick={() => copyToClipboard(credentials.token_endpoint, 'token_endpoint')}
            className="p-2 text-gray-500 hover:text-gray-700 dark:hover:text-neutral-200 hover:bg-gray-100 dark:hover:bg-neutral-700 rounded-lg transition-colors"
            title="Copy Token Endpoint"
          >
            {copiedField === 'token_endpoint' ? (
              <Check className="h-5 w-5 text-green-500" />
            ) : (
              <Copy className="h-5 w-5" />
            )}
          </button>
        </div>
      </div>

      {/* Grant Type */}
      <div className="text-sm text-gray-500 dark:text-neutral-400">
        Grant Type: <span className="font-mono">{credentials.grant_type}</span>
      </div>
    </div>
  );
}

export default CredentialsDisplay;
