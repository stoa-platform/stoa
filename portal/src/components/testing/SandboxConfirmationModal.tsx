/**
 * Sandbox Confirmation Modal
 *
 * Warning modal for production portal users before making API test requests.
 * Requires explicit confirmation that they understand they're testing production APIs.
 */

import { useState } from 'react';
import { AlertTriangle, X, Shield, CheckCircle } from 'lucide-react';

interface SandboxConfirmationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  environmentName: string;
}

export function SandboxConfirmationModal({
  isOpen,
  onClose,
  onConfirm,
  environmentName,
}: SandboxConfirmationModalProps) {
  const [understood, setUnderstood] = useState(false);

  if (!isOpen) return null;

  const handleConfirm = () => {
    if (understood) {
      onConfirm();
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 transition-opacity"
        onClick={onClose}
        onKeyDown={(e) => e.key === 'Escape' && onClose()}
        role="button"
        aria-label="Close modal"
        tabIndex={0}
      />

      {/* Modal */}
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="relative bg-white dark:bg-neutral-800 rounded-xl shadow-xl max-w-lg w-full transform transition-all">
          {/* Close button */}
          <button
            onClick={onClose}
            className="absolute top-4 right-4 p-1 text-neutral-400 dark:text-neutral-500 hover:text-neutral-600 dark:hover:text-neutral-300 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>

          {/* Header */}
          <div className="px-6 pt-6 pb-4">
            <div className="flex items-center gap-4">
              <div className="flex-shrink-0 p-3 bg-amber-100 dark:bg-amber-900/30 rounded-full">
                <AlertTriangle className="h-6 w-6 text-amber-600" />
              </div>
              <div>
                <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">
                  Production Environment Warning
                </h2>
                <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
                  You are about to test against <strong>{environmentName}</strong>
                </p>
              </div>
            </div>
          </div>

          {/* Content */}
          <div className="px-6 pb-4">
            <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-4 mb-4">
              <h3 className="font-medium text-amber-800 dark:text-amber-400 mb-2">Please note:</h3>
              <ul className="space-y-2 text-sm text-amber-700 dark:text-amber-400">
                <li className="flex items-start gap-2">
                  <Shield className="h-4 w-4 mt-0.5 flex-shrink-0" />
                  <span>
                    API requests will be made against <strong>real production endpoints</strong>
                  </span>
                </li>
                <li className="flex items-start gap-2">
                  <Shield className="h-4 w-4 mt-0.5 flex-shrink-0" />
                  <span>
                    Your requests will be <strong>logged for audit purposes</strong>
                  </span>
                </li>
                <li className="flex items-start gap-2">
                  <Shield className="h-4 w-4 mt-0.5 flex-shrink-0" />
                  <span>
                    POST, PUT, DELETE operations may <strong>modify production data</strong>
                  </span>
                </li>
                <li className="flex items-start gap-2">
                  <Shield className="h-4 w-4 mt-0.5 flex-shrink-0" />
                  <span>
                    Rate limits and quotas are <strong>shared with production traffic</strong>
                  </span>
                </li>
              </ul>
            </div>

            <p className="text-sm text-neutral-600 dark:text-neutral-400 mb-4">
              For safe testing without affecting production, consider using a non-production
              environment through the Development Portal at{' '}
              <code className="bg-neutral-100 dark:bg-neutral-700 px-1.5 py-0.5 rounded text-xs dark:text-white">
                portal.dev.gostoa.dev
              </code>
            </p>

            {/* Confirmation Checkbox */}
            <label className="flex items-start gap-3 p-3 bg-neutral-50 dark:bg-neutral-900 rounded-lg cursor-pointer hover:bg-neutral-100 dark:hover:bg-neutral-700 transition-colors">
              <input
                type="checkbox"
                checked={understood}
                onChange={(e) => setUnderstood(e.target.checked)}
                className="h-5 w-5 mt-0.5 rounded border-neutral-300 dark:border-neutral-600 text-primary-600 focus:ring-primary-500"
              />
              <span className="text-sm text-neutral-700 dark:text-neutral-300">
                I understand I am testing against a <strong>production environment</strong>
                and my requests may affect production data and be logged for audit purposes.
              </span>
            </label>
          </div>

          {/* Footer */}
          <div className="px-6 py-4 bg-neutral-50 dark:bg-neutral-900 rounded-b-xl flex items-center justify-end gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded-lg transition-colors font-medium"
            >
              Cancel
            </button>
            <button
              onClick={handleConfirm}
              disabled={!understood}
              className={`
                inline-flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors
                ${
                  understood
                    ? 'bg-amber-600 text-white hover:bg-amber-700'
                    : 'bg-neutral-200 dark:bg-neutral-600 text-neutral-400 dark:text-neutral-400 cursor-not-allowed'
                }
              `}
            >
              <CheckCircle className="h-4 w-4" />I Understand, Continue
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default SandboxConfirmationModal;
