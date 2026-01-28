// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * DisableBindingModal Component
 *
 * Confirmation modal shown before disabling a protocol binding that has active traffic.
 * Warns users about potential impact on active integrations.
 */

import React from 'react';
import { AlertTriangle, X } from 'lucide-react';
import type { ProtocolBinding } from '../../types';

interface DisableBindingModalProps {
  /** The binding to disable, or null if modal should be hidden */
  binding: ProtocolBinding | null;
  /** Callback when user confirms disabling */
  onConfirm: () => void;
  /** Callback when user cancels or closes modal */
  onCancel: () => void;
  /** Whether the disable action is in progress */
  isLoading?: boolean;
}

/**
 * Protocol label mapping for display
 */
const protocolLabels: Record<string, string> = {
  rest: 'REST',
  graphql: 'GraphQL',
  grpc: 'gRPC',
  mcp: 'MCP',
  kafka: 'Kafka',
};

export const DisableBindingModal: React.FC<DisableBindingModalProps> = ({
  binding,
  onConfirm,
  onCancel,
  isLoading = false,
}) => {
  // Don't render if no binding
  if (!binding) return null;

  const protocolLabel = protocolLabels[binding.protocol] || binding.protocol.toUpperCase();

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 z-40 transition-opacity"
        onClick={onCancel}
        aria-hidden="true"
      />

      {/* Modal */}
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="disable-modal-title"
        className="fixed inset-0 z-50 flex items-center justify-center p-4"
      >
        <div className="bg-white rounded-lg shadow-xl max-w-md w-full">
          {/* Header */}
          <div className="flex items-start justify-between p-4 border-b border-gray-100">
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 p-2 bg-amber-100 rounded-full">
                <AlertTriangle className="h-5 w-5 text-amber-600" />
              </div>
              <div>
                <h3
                  id="disable-modal-title"
                  className="text-lg font-medium text-gray-900"
                >
                  Disable {protocolLabel} binding?
                </h3>
              </div>
            </div>
            <button
              onClick={onCancel}
              className="text-gray-400 hover:text-gray-500 transition-colors"
              aria-label="Close"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Body */}
          <div className="p-4">
            <p className="text-sm text-gray-600">
              This binding has received{' '}
              <span className="font-semibold text-gray-900">
                {(binding.traffic_24h ?? 0).toLocaleString()} requests
              </span>{' '}
              in the last 24 hours.
            </p>
            <p className="mt-2 text-sm text-gray-600">
              Disabling it may affect active integrations that depend on this endpoint.
              The binding can be re-enabled at any time.
            </p>

            {/* Endpoint info */}
            {binding.endpoint && (
              <div className="mt-3 p-2 bg-gray-50 rounded text-xs text-gray-500 font-mono truncate">
                {binding.endpoint}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="flex justify-end gap-3 p-4 border-t border-gray-100 bg-gray-50 rounded-b-lg">
            <button
              onClick={onCancel}
              disabled={isLoading}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              onClick={onConfirm}
              disabled={isLoading}
              className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700 transition-colors disabled:opacity-50 flex items-center gap-2"
            >
              {isLoading ? (
                <>
                  <span className="animate-spin">⏳</span>
                  Disabling...
                </>
              ) : (
                'Disable'
              )}
            </button>
          </div>
        </div>
      </div>
    </>
  );
};

export default DisableBindingModal;
