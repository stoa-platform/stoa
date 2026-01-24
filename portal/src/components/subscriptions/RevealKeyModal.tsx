/**
 * Reveal API Key Modal
 *
 * Securely reveals the API key for a subscription.
 * If TOTP is required, prompts for 2FA code.
 * Shows the key with a countdown timer for security.
 *
 * Reference: CAB-XXX - Secure API Key Management with Vault & 2FA
 */

import { useState, useEffect, useCallback } from 'react';
import {
  X,
  Key,
  Eye,
  EyeOff,
  Copy,
  Check,
  AlertTriangle,
  Loader2,
  Shield,
  Clock,
} from 'lucide-react';
import { useRevealApiKey } from '../../hooks/useSubscriptions';
import type { MCPSubscription } from '../../types';

interface RevealKeyModalProps {
  subscription: MCPSubscription;
  isOpen: boolean;
  onClose: () => void;
}

export function RevealKeyModal({ subscription, isOpen, onClose }: RevealKeyModalProps) {
  const [apiKey, setApiKey] = useState<string | null>(null);
  const [isKeyVisible, setIsKeyVisible] = useState(false);
  const [copied, setCopied] = useState(false);
  const [countdown, setCountdown] = useState(30);
  const [totpCode, setTotpCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [needsTotp, setNeedsTotp] = useState(false);

  const revealMutation = useRevealApiKey();

  // Reset state when modal opens/closes
  useEffect(() => {
    if (!isOpen) {
      setApiKey(null);
      setIsKeyVisible(false);
      setCopied(false);
      setCountdown(30);
      setTotpCode('');
      setError(null);
      setNeedsTotp(false);
    }
  }, [isOpen]);

  // Countdown timer when key is revealed
  useEffect(() => {
    if (!apiKey || countdown <= 0) return;

    const timer = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          // Hide key when timer expires
          setApiKey(null);
          setIsKeyVisible(false);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [apiKey, countdown]);

  const handleRevealKey = useCallback(async () => {
    setError(null);
    try {
      const response = await revealMutation.mutateAsync({
        id: subscription.id,
        totpCode: totpCode || undefined,
      });
      setApiKey(response.api_key);
      setCountdown(response.expires_in || 30);
      setIsKeyVisible(true);
      setNeedsTotp(false);
    } catch (err: unknown) {
      const error = err as { response?: { status?: number; data?: { detail?: string }; headers?: { get?: (key: string) => string | null } } };
      // Check if TOTP is required
      if (error?.response?.status === 403) {
        const stepUpHeader = error.response?.headers?.get?.('X-Step-Up-Auth');
        if (stepUpHeader === 'totp' || error.response?.data?.detail?.includes('TOTP')) {
          setNeedsTotp(true);
          setError('Please enter your 2FA code to reveal the API key.');
          return;
        }
      }
      setError(error?.response?.data?.detail || 'Failed to reveal API key. Please try again.');
    }
  }, [subscription.id, totpCode, revealMutation]);

  const handleCopyKey = useCallback(async () => {
    if (!apiKey) return;
    try {
      await navigator.clipboard.writeText(apiKey);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError('Failed to copy to clipboard');
    }
  }, [apiKey]);

  const maskKey = (key: string) => {
    // Show first 12 chars (stoa_sk_XXXX) and last 4, mask the rest
    if (key.length <= 20) return key;
    return `${key.slice(0, 12)}${'*'.repeat(key.length - 16)}${key.slice(-4)}`;
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
        onKeyDown={(e) => e.key === 'Escape' && onClose()}
        role="button"
        aria-label="Close modal"
        tabIndex={0}
      />

      {/* Modal */}
      <div className="relative bg-white rounded-xl shadow-2xl max-w-md w-full mx-4 overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary-50 rounded-lg">
              <Key className="h-5 w-5 text-primary-600" />
            </div>
            <div>
              <h2 className="font-semibold text-gray-900">Reveal API Key</h2>
              <p className="text-sm text-gray-500">{subscription.tool_id}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-4">
          {/* Security warning */}
          {!apiKey && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
              <div className="flex gap-3">
                <AlertTriangle className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />
                <div className="text-sm">
                  <p className="font-medium text-amber-800">Security Notice</p>
                  <p className="text-amber-700 mt-1">
                    Your API key will be visible for 30 seconds after reveal.
                    Make sure no one can see your screen.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* TOTP input (if required) */}
          {(needsTotp || subscription.totp_required) && !apiKey && (
            <div className="space-y-2">
              <label htmlFor="totp-input" className="flex items-center gap-2 text-sm font-medium text-gray-700">
                <Shield className="h-4 w-4 text-primary-500" aria-hidden="true" />
                2FA Verification Required
              </label>
              <input
                id="totp-input"
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                maxLength={6}
                placeholder="Enter 6-digit code"
                value={totpCode}
                onChange={(e) => {
                  const value = e.target.value.replace(/\D/g, '');
                  setTotpCode(value);
                  setError(null);
                }}
                className="w-full px-4 py-3 text-center text-2xl font-mono tracking-widest border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                // eslint-disable-next-line jsx-a11y/no-autofocus
                autoFocus
              />
              <p className="text-xs text-gray-500">
                Enter the code from your authenticator app
              </p>
            </div>
          )}

          {/* Error message */}
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm">
              {error}
            </div>
          )}

          {/* Revealed key display */}
          {apiKey && (
            <div className="space-y-4">
              {/* Countdown timer */}
              <div className="flex items-center justify-center gap-2 text-amber-600">
                <Clock className="h-4 w-4" />
                <span className="font-medium">
                  Hiding in {countdown} second{countdown !== 1 ? 's' : ''}
                </span>
              </div>

              {/* Key display */}
              <div className="relative">
                <div className="bg-gray-900 rounded-lg p-4 font-mono text-sm break-all">
                  <code className="text-green-400">
                    {isKeyVisible ? apiKey : maskKey(apiKey)}
                  </code>
                </div>

                {/* Action buttons */}
                <div className="absolute top-2 right-2 flex gap-1">
                  <button
                    onClick={() => setIsKeyVisible(!isKeyVisible)}
                    className="p-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg transition-colors"
                    title={isKeyVisible ? 'Hide key' : 'Show key'}
                  >
                    {isKeyVisible ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </button>
                  <button
                    onClick={handleCopyKey}
                    className="p-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg transition-colors"
                    title="Copy to clipboard"
                  >
                    {copied ? (
                      <Check className="h-4 w-4 text-green-400" />
                    ) : (
                      <Copy className="h-4 w-4" />
                    )}
                  </button>
                </div>
              </div>

              {/* Copy confirmation */}
              {copied && (
                <p className="text-center text-sm text-green-600 font-medium">
                  Copied to clipboard!
                </p>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-200 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
          >
            {apiKey ? 'Close' : 'Cancel'}
          </button>
          {!apiKey && (
            <button
              onClick={handleRevealKey}
              disabled={revealMutation.isPending || (needsTotp && totpCode.length !== 6)}
              className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {revealMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Verifying...
                </>
              ) : (
                <>
                  <Eye className="h-4 w-4" />
                  Reveal Key
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default RevealKeyModal;
