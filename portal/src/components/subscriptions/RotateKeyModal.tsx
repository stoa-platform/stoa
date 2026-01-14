/**
 * API Key Rotation Modal Component (CAB-314)
 *
 * Allows users to rotate their API key with a configurable grace period.
 * The old key remains valid during the grace period, allowing a smooth transition.
 *
 * Flow:
 * 1. User selects grace period (1-168 hours, default 24h)
 * 2. Confirmation warning about grace period
 * 3. New key is generated and displayed (shown only ONCE!)
 * 4. Email notification sent with new key
 *
 * Reference: Linear CAB-314
 */

import { useState } from 'react';
import {
  X,
  Key,
  Copy,
  CheckCircle,
  AlertTriangle,
  RefreshCw,
  Clock,
  Loader2,
  Download,
  Mail,
  Shield,
} from 'lucide-react';
import type { MCPSubscription, KeyRotationResponse } from '../../types';

interface RotateKeyModalProps {
  isOpen: boolean;
  onClose: () => void;
  subscription: MCPSubscription;
  onRotate: (gracePeriodHours: number) => Promise<KeyRotationResponse>;
  isRotating?: boolean;
}

type ModalStep = 'confirm' | 'success';

export function RotateKeyModal({
  isOpen,
  onClose,
  subscription,
  onRotate,
  isRotating = false,
}: RotateKeyModalProps) {
  const [step, setStep] = useState<ModalStep>('confirm');
  const [gracePeriodHours, setGracePeriodHours] = useState(24);
  const [rotationResult, setRotationResult] = useState<KeyRotationResponse | null>(null);
  const [copied, setCopied] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleRotate = async () => {
    try {
      setError(null);
      const result = await onRotate(gracePeriodHours);
      setRotationResult(result);
      setStep('success');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to rotate API key');
    }
  };

  const handleCopy = async () => {
    if (!rotationResult) return;
    try {
      await navigator.clipboard.writeText(rotationResult.new_api_key);
      setCopied(true);
      setTimeout(() => setCopied(false), 3000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const handleDownloadConfig = () => {
    if (!rotationResult) return;

    const config = {
      mcpServers: {
        stoa: {
          command: 'npx',
          args: ['-y', '@anthropic/mcp-client', 'stdio'],
          env: {
            STOA_API_KEY: rotationResult.new_api_key,
            STOA_MCP_URL: 'https://mcp.stoa.cab-i.com',
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
    if (step === 'success' && !acknowledged) return;
    setStep('confirm');
    setRotationResult(null);
    setCopied(false);
    setAcknowledged(false);
    setError(null);
    onClose();
  };

  const formatExpiryDate = (isoDate: string) => {
    return new Date(isoDate).toLocaleString(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    });
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 transition-opacity"
        onClick={step === 'confirm' ? handleClose : undefined}
        onKeyDown={(e) => e.key === 'Escape' && step === 'confirm' && handleClose()}
        role="button"
        aria-label="Close modal"
        tabIndex={step === 'confirm' ? 0 : -1}
      />

      {/* Modal */}
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="relative bg-white rounded-xl shadow-xl max-w-lg w-full">
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-gray-200">
            <div className="flex items-center gap-3">
              <div className={`p-2 rounded-lg ${step === 'success' ? 'bg-green-100' : 'bg-primary-100'}`}>
                {step === 'success' ? (
                  <CheckCircle className="h-6 w-6 text-green-600" />
                ) : (
                  <RefreshCw className="h-6 w-6 text-primary-600" />
                )}
              </div>
              <div>
                <h2 className="text-xl font-semibold text-gray-900">
                  {step === 'success' ? 'Key Rotated Successfully' : 'Rotate API Key'}
                </h2>
                <p className="text-sm text-gray-500 mt-0.5">
                  {subscription.tool_id}
                </p>
              </div>
            </div>
            {(step === 'confirm' || acknowledged) && (
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
            {step === 'confirm' ? (
              <>
                {/* Info about grace period */}
                <div className="flex items-start gap-3 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                  <Shield className="h-5 w-5 text-blue-500 mt-0.5 flex-shrink-0" />
                  <div>
                    <h4 className="font-medium text-blue-800">
                      Grace Period for Seamless Transition
                    </h4>
                    <p className="text-sm text-blue-700 mt-1">
                      During the grace period, <strong>both old and new keys</strong> will be accepted.
                      This allows you to update your applications without downtime.
                    </p>
                  </div>
                </div>

                {/* Grace period selection */}
                <div>
                  <label htmlFor="grace-period-select" className="block text-sm font-medium text-gray-700 mb-2">
                    Grace Period Duration
                  </label>
                  <div className="flex items-center gap-3">
                    <Clock className="h-5 w-5 text-gray-400" aria-hidden="true" />
                    <select
                      id="grace-period-select"
                      value={gracePeriodHours}
                      onChange={(e) => setGracePeriodHours(parseInt(e.target.value))}
                      className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                    >
                      <option value={1}>1 hour</option>
                      <option value={6}>6 hours</option>
                      <option value={12}>12 hours</option>
                      <option value={24}>24 hours (Recommended)</option>
                      <option value={48}>48 hours</option>
                      <option value={72}>72 hours (3 days)</option>
                      <option value={168}>168 hours (7 days)</option>
                    </select>
                  </div>
                  <p className="mt-2 text-sm text-gray-500">
                    Your old key will remain valid until{' '}
                    <strong>
                      {new Date(Date.now() + gracePeriodHours * 60 * 60 * 1000).toLocaleString()}
                    </strong>
                  </p>
                </div>

                {/* Email notification info */}
                <div className="flex items-start gap-3 p-4 bg-gray-50 border border-gray-200 rounded-lg">
                  <Mail className="h-5 w-5 text-gray-500 mt-0.5 flex-shrink-0" />
                  <div>
                    <h4 className="font-medium text-gray-800">
                      Email Notification
                    </h4>
                    <p className="text-sm text-gray-600 mt-1">
                      A notification will be sent to your email with the new API key
                      for your records.
                    </p>
                  </div>
                </div>

                {/* Warning */}
                <div className="flex items-start gap-3 p-4 bg-amber-50 border border-amber-200 rounded-lg">
                  <AlertTriangle className="h-5 w-5 text-amber-500 mt-0.5 flex-shrink-0" />
                  <div>
                    <h4 className="font-medium text-amber-800">
                      Important
                    </h4>
                    <p className="text-sm text-amber-700 mt-1">
                      After the grace period ends, the old key will be <strong>permanently invalidated</strong>.
                      Make sure to update all your applications before then.
                    </p>
                  </div>
                </div>

                {/* Error display */}
                {error && (
                  <div className="flex items-start gap-3 p-4 bg-red-50 border border-red-200 rounded-lg">
                    <AlertTriangle className="h-5 w-5 text-red-500 mt-0.5 flex-shrink-0" />
                    <div>
                      <h4 className="font-medium text-red-800">Error</h4>
                      <p className="text-sm text-red-700 mt-1">{error}</p>
                    </div>
                  </div>
                )}
              </>
            ) : (
              <>
                {/* Success: Warning to save key */}
                <div className="flex items-start gap-3 p-4 bg-amber-50 border border-amber-200 rounded-lg">
                  <AlertTriangle className="h-5 w-5 text-amber-500 mt-0.5 flex-shrink-0" />
                  <div>
                    <h4 className="font-medium text-amber-800">
                      Save Your New API Key Now
                    </h4>
                    <p className="text-sm text-amber-700 mt-1">
                      This API key will only be shown <strong>once</strong>. Make sure to copy
                      and store it securely before closing this modal.
                    </p>
                  </div>
                </div>

                {/* New API Key Display */}
                {rotationResult && (
                  <div>
                    <span className="block text-sm font-medium text-gray-700 mb-2">
                      Your New API Key
                    </span>
                    <div className="relative">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 flex items-center gap-2 px-4 py-3 bg-gray-900 rounded-lg">
                          <Key className="h-4 w-4 text-gray-400 flex-shrink-0" />
                          <code className="flex-1 text-sm font-mono text-green-400 break-all select-all">
                            {rotationResult.new_api_key}
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
                )}

                {/* Grace Period Info */}
                {rotationResult && (
                  <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                    <div className="flex items-center gap-2 mb-2">
                      <Clock className="h-4 w-4 text-blue-600" />
                      <span className="font-medium text-blue-800">Grace Period Active</span>
                    </div>
                    <p className="text-sm text-blue-700">
                      Your old key will remain valid until{' '}
                      <strong>{formatExpiryDate(rotationResult.old_key_expires_at)}</strong>.
                      You have <strong>{rotationResult.grace_period_hours} hours</strong> to update your applications.
                    </p>
                    <p className="text-sm text-blue-600 mt-2">
                      This is rotation #{rotationResult.rotation_count} for this subscription.
                    </p>
                  </div>
                )}

                {/* Quick Actions */}
                <div className="flex flex-wrap gap-3">
                  <button
                    onClick={handleDownloadConfig}
                    className="inline-flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors text-sm font-medium"
                  >
                    <Download className="h-4 w-4" />
                    Download Config
                  </button>
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
                    I have copied and securely stored my new API key. I understand that
                    I need to update my applications before the grace period ends.
                  </span>
                </label>
              </>
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end gap-3 p-6 border-t border-gray-200">
            {step === 'confirm' ? (
              <>
                <button
                  onClick={handleClose}
                  disabled={isRotating}
                  className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg transition-colors font-medium"
                >
                  Cancel
                </button>
                <button
                  onClick={handleRotate}
                  disabled={isRotating}
                  className="inline-flex items-center gap-2 px-6 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors font-medium disabled:opacity-50"
                >
                  {isRotating ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Rotating...
                    </>
                  ) : (
                    <>
                      <RefreshCw className="h-4 w-4" />
                      Rotate Key
                    </>
                  )}
                </button>
              </>
            ) : (
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
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default RotateKeyModal;
