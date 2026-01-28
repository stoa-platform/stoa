// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * Credentials Viewer Component
 *
 * Displays and manages application credentials (Client ID / Client Secret).
 */

import { useState } from 'react';
import { Eye, EyeOff, Copy, Check, RefreshCw, AlertTriangle, Key } from 'lucide-react';

interface CredentialsViewerProps {
  clientId: string;
  clientSecret?: string | null;
  onRegenerateSecret?: () => Promise<string | undefined>;
  isRegenerating?: boolean;
  showSecretOnce?: boolean; // For newly created apps where secret is shown once
}

export function CredentialsViewer({
  clientId,
  clientSecret,
  onRegenerateSecret,
  isRegenerating = false,
  showSecretOnce = false,
}: CredentialsViewerProps) {
  const [showSecret, setShowSecret] = useState(showSecretOnce);
  const [copiedField, setCopiedField] = useState<'id' | 'secret' | null>(null);
  const [showRegenerateConfirm, setShowRegenerateConfirm] = useState(false);
  const [newSecret, setNewSecret] = useState<string | null>(null);

  const copyToClipboard = async (value: string, field: 'id' | 'secret') => {
    await navigator.clipboard.writeText(value);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 2000);
  };

  const handleRegenerateSecret = async () => {
    if (onRegenerateSecret) {
      const secret = await onRegenerateSecret();
      if (secret) {
        setNewSecret(secret);
        setShowSecret(true);
      }
      setShowRegenerateConfirm(false);
    }
  };

  const displaySecret = newSecret || clientSecret;
  const maskedSecret = displaySecret ? '••••••••••••••••••••••••••••••••' : null;

  return (
    <div className="space-y-4">
      {/* Client ID */}
      <div>
        <span id="client-id-label" className="block text-sm font-medium text-gray-700 mb-1">
          Client ID
        </span>
        <div className="flex items-center gap-2">
          <div
            className="flex-1 flex items-center gap-2 px-4 py-2 bg-gray-50 border border-gray-200 rounded-lg font-mono text-sm"
            aria-labelledby="client-id-label"
          >
            <Key className="h-4 w-4 text-gray-400" aria-hidden="true" />
            <span className="flex-1 truncate">{clientId}</span>
          </div>
          <button
            onClick={() => copyToClipboard(clientId, 'id')}
            className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
            title="Copy Client ID"
          >
            {copiedField === 'id' ? (
              <Check className="h-5 w-5 text-green-500" />
            ) : (
              <Copy className="h-5 w-5" />
            )}
          </button>
        </div>
      </div>

      {/* Client Secret */}
      <div>
        <span id="client-secret-label" className="block text-sm font-medium text-gray-700 mb-1">
          Client Secret
        </span>
        {displaySecret ? (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <div className="flex-1 flex items-center gap-2 px-4 py-2 bg-gray-50 border border-gray-200 rounded-lg font-mono text-sm">
                <Key className="h-4 w-4 text-gray-400" />
                <span className="flex-1 truncate">
                  {showSecret ? displaySecret : maskedSecret}
                </span>
              </div>
              <button
                onClick={() => setShowSecret(!showSecret)}
                className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
                title={showSecret ? 'Hide secret' : 'Show secret'}
              >
                {showSecret ? (
                  <EyeOff className="h-5 w-5" />
                ) : (
                  <Eye className="h-5 w-5" />
                )}
              </button>
              <button
                onClick={() => copyToClipboard(displaySecret, 'secret')}
                className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
                title="Copy Client Secret"
              >
                {copiedField === 'secret' ? (
                  <Check className="h-5 w-5 text-green-500" />
                ) : (
                  <Copy className="h-5 w-5" />
                )}
              </button>
            </div>

            {/* Warning for new secret */}
            {(showSecretOnce || newSecret) && (
              <div className="flex items-start gap-2 p-3 bg-amber-50 border border-amber-200 rounded-lg">
                <AlertTriangle className="h-5 w-5 text-amber-500 mt-0.5" />
                <div className="text-sm text-amber-700">
                  <strong>Important:</strong> This secret will only be shown once. Make sure to copy
                  and store it securely now.
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-2 px-4 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-500">
            <Key className="h-4 w-4 text-gray-400" />
            <span>Secret is hidden. Regenerate to get a new one.</span>
          </div>
        )}

        {/* Regenerate button */}
        {onRegenerateSecret && (
          <div className="mt-3">
            {!showRegenerateConfirm ? (
              <button
                onClick={() => setShowRegenerateConfirm(true)}
                disabled={isRegenerating}
                className="inline-flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900 disabled:opacity-50"
              >
                <RefreshCw className={`h-4 w-4 ${isRegenerating ? 'animate-spin' : ''}`} />
                Regenerate Secret
              </button>
            ) : (
              <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
                <div className="flex items-start gap-2 mb-3">
                  <AlertTriangle className="h-5 w-5 text-red-500 mt-0.5" />
                  <div>
                    <p className="text-sm font-medium text-red-800">
                      Are you sure you want to regenerate the secret?
                    </p>
                    <p className="text-sm text-red-600 mt-1">
                      This will invalidate the current secret. Any applications using it will stop working.
                    </p>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={handleRegenerateSecret}
                    disabled={isRegenerating}
                    className="inline-flex items-center gap-2 px-3 py-1.5 bg-red-600 text-white text-sm font-medium rounded-lg hover:bg-red-700 disabled:opacity-50"
                  >
                    {isRegenerating ? (
                      <>
                        <RefreshCw className="h-4 w-4 animate-spin" />
                        Regenerating...
                      </>
                    ) : (
                      'Yes, Regenerate'
                    )}
                  </button>
                  <button
                    onClick={() => setShowRegenerateConfirm(false)}
                    disabled={isRegenerating}
                    className="px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-red-100 rounded-lg disabled:opacity-50"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default CredentialsViewer;
