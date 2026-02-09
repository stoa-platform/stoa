/**
 * Consumer Credentials Modal
 *
 * One-time display of OAuth2 credentials after consumer registration.
 * The secret is only shown once — the user must copy it.
 *
 * Reference: CAB-1121 Phase 5
 */

import { useState } from 'react';
import { X, Copy, Check, AlertTriangle, Key, Terminal } from 'lucide-react';
import type { ConsumerCredentials } from '../../types';

interface CredentialsModalProps {
  isOpen: boolean;
  onClose: () => void;
  credentials: ConsumerCredentials;
  consumerName: string;
}

export function CredentialsModal({
  isOpen,
  onClose,
  credentials,
  consumerName,
}: CredentialsModalProps) {
  const [copiedField, setCopiedField] = useState<string | null>(null);

  const copyToClipboard = async (value: string, field: string) => {
    await navigator.clipboard.writeText(value);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 2000);
  };

  const curlSnippet = `curl -X POST ${credentials.token_endpoint} \\
  -d "grant_type=${credentials.grant_type}" \\
  -d "client_id=${credentials.client_id}" \\
  -d "client_secret=${credentials.client_secret}"`;

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="fixed inset-0 bg-black/50 transition-opacity" aria-hidden="true" />

      <div className="flex min-h-full items-center justify-center p-4">
        <div className="relative bg-white dark:bg-neutral-800 rounded-xl shadow-xl max-w-lg w-full">
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-neutral-700">
            <div>
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                Consumer Credentials
              </h2>
              <p className="text-sm text-gray-500 dark:text-neutral-400 mt-1">{consumerName}</p>
            </div>
            <button
              onClick={onClose}
              className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-neutral-200 hover:bg-gray-100 dark:hover:bg-neutral-700 rounded-lg transition-colors"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Content */}
          <div className="p-6 space-y-4">
            {/* Warning */}
            <div className="flex items-start gap-2 p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg">
              <AlertTriangle className="h-5 w-5 text-amber-500 mt-0.5 flex-shrink-0" />
              <div className="text-sm text-amber-700 dark:text-amber-300">
                <strong>Save these credentials now.</strong> The client secret will not be shown
                again. Store it securely.
              </div>
            </div>

            {/* Client ID */}
            <CredentialField
              label="Client ID"
              value={credentials.client_id}
              fieldKey="client_id"
              copiedField={copiedField}
              onCopy={copyToClipboard}
            />

            {/* Client Secret */}
            <CredentialField
              label="Client Secret"
              value={credentials.client_secret}
              fieldKey="client_secret"
              copiedField={copiedField}
              onCopy={copyToClipboard}
            />

            {/* Token Endpoint */}
            <CredentialField
              label="Token Endpoint"
              value={credentials.token_endpoint}
              fieldKey="token_endpoint"
              copiedField={copiedField}
              onCopy={copyToClipboard}
            />

            {/* Grant Type */}
            <div>
              <span className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1">
                Grant Type
              </span>
              <div className="px-4 py-2 bg-gray-50 dark:bg-neutral-900 border border-gray-200 dark:border-neutral-700 rounded-lg font-mono text-sm text-gray-700 dark:text-neutral-300">
                {credentials.grant_type}
              </div>
            </div>

            {/* cURL snippet */}
            <div>
              <div className="flex items-center gap-2 mb-1">
                <Terminal className="h-4 w-4 text-gray-500 dark:text-neutral-400" />
                <span className="text-sm font-medium text-gray-700 dark:text-neutral-300">
                  Quick Test
                </span>
              </div>
              <div className="relative">
                <pre className="px-4 py-3 bg-gray-900 dark:bg-neutral-950 text-green-400 text-xs rounded-lg overflow-x-auto">
                  {curlSnippet}
                </pre>
                <button
                  onClick={() => copyToClipboard(curlSnippet, 'curl')}
                  className="absolute top-2 right-2 p-1.5 bg-gray-700 hover:bg-gray-600 rounded text-gray-300 transition-colors"
                  title="Copy cURL command"
                >
                  {copiedField === 'curl' ? (
                    <Check className="h-3.5 w-3.5 text-green-400" />
                  ) : (
                    <Copy className="h-3.5 w-3.5" />
                  )}
                </button>
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="flex justify-end p-6 border-t border-gray-200 dark:border-neutral-700">
            <button
              onClick={onClose}
              className="px-4 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700 transition-colors"
            >
              Done
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function CredentialField({
  label,
  value,
  fieldKey,
  copiedField,
  onCopy,
}: {
  label: string;
  value: string;
  fieldKey: string;
  copiedField: string | null;
  onCopy: (value: string, field: string) => void;
}) {
  return (
    <div>
      <span className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1">
        {label}
      </span>
      <div className="flex items-center gap-2">
        <div className="flex-1 flex items-center gap-2 px-4 py-2 bg-gray-50 dark:bg-neutral-900 border border-gray-200 dark:border-neutral-700 rounded-lg font-mono text-sm">
          <Key className="h-4 w-4 text-gray-400 dark:text-neutral-500 flex-shrink-0" />
          <span className="flex-1 truncate text-gray-700 dark:text-neutral-300">{value}</span>
        </div>
        <button
          onClick={() => onCopy(value, fieldKey)}
          className="p-2 text-gray-500 hover:text-gray-700 dark:text-neutral-400 dark:hover:text-neutral-200 hover:bg-gray-100 dark:hover:bg-neutral-700 rounded-lg transition-colors"
          title={`Copy ${label}`}
        >
          {copiedField === fieldKey ? (
            <Check className="h-5 w-5 text-green-500" />
          ) : (
            <Copy className="h-5 w-5" />
          )}
        </button>
      </div>
    </div>
  );
}

export default CredentialsModal;
