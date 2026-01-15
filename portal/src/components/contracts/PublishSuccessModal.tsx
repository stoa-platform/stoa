/**
 * PublishSuccessModal Component
 *
 * Modal shown after successfully publishing a contract.
 * Displays the "wow" effect by showing all auto-generated bindings
 * (REST, MCP, GraphQL, etc.) that STOA created automatically.
 *
 * Key UX goal: User sees that a single contract definition
 * instantly becomes available via multiple protocols, with
 * MCP (AI agent access) highlighted as "Auto-generated".
 *
 * Reference: CAB-560 - Universal API Contracts
 */

import React from 'react';
import { PublishContractResponse, ProtocolType } from '../../types';
import { GeneratedBindingRow } from './GeneratedBindingRow';
import { CheckCircle, X, ExternalLink, Play } from 'lucide-react';

interface PublishSuccessModalProps {
  isOpen: boolean;
  onClose: () => void;
  data: PublishContractResponse | null;
  onViewContract?: (id: string) => void;
  onTestPlayground?: (url: string) => void;
}

// Display order for bindings (most important first)
const BINDING_ORDER: ProtocolType[] = ['rest', 'mcp', 'graphql', 'grpc', 'kafka'];

export const PublishSuccessModal: React.FC<PublishSuccessModalProps> = ({
  isOpen,
  onClose,
  data,
  onViewContract,
  onTestPlayground,
}) => {
  if (!isOpen || !data) return null;

  // Separate and count bindings by status
  const createdBindings = data.bindings_generated.filter(b => b.status === 'created');
  const availableBindings = data.bindings_generated.filter(b => b.status === 'available');

  // Find the first playground URL for the main action button
  const firstPlayground = createdBindings.find(b => b.playground_url)?.playground_url;

  // Sort bindings by predefined order
  const sortedBindings = [...data.bindings_generated].sort(
    (a, b) => BINDING_ORDER.indexOf(a.protocol) - BINDING_ORDER.indexOf(b.protocol)
  );

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-labelledby="publish-success-title"
    >
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 transition-opacity"
        onClick={handleBackdropClick}
      />

      {/* Modal */}
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="relative bg-white rounded-xl shadow-2xl max-w-lg w-full transform transition-all animate-in fade-in zoom-in-95 duration-200">
          {/* Close button */}
          <button
            onClick={onClose}
            className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 transition-colors"
            aria-label="Close modal"
          >
            <X className="h-5 w-5" />
          </button>

          {/* Header */}
          <div className="p-6 pb-4">
            <div className="flex items-center gap-3">
              <div className="flex-shrink-0">
                <div className="h-12 w-12 rounded-full bg-green-100 flex items-center justify-center">
                  <CheckCircle className="h-7 w-7 text-green-600" />
                </div>
              </div>
              <div>
                <h2
                  id="publish-success-title"
                  className="text-xl font-semibold text-gray-900"
                >
                  Contract published!
                </h2>
                <p className="text-sm text-gray-500 mt-0.5">
                  <span className="font-mono font-medium">{data.name}</span>
                  {' '}v{data.version}
                </p>
              </div>
            </div>
          </div>

          {/* Divider */}
          <div className="border-t border-gray-100" />

          {/* Bindings list */}
          <div className="p-6 pt-4">
            <h3 className="text-sm font-medium text-gray-700 mb-3">
              Auto-generated bindings
            </h3>

            <div className="space-y-2">
              {sortedBindings.map((binding) => (
                <GeneratedBindingRow
                  key={binding.protocol}
                  binding={binding}
                />
              ))}
            </div>

            {/* Stats summary */}
            <div className="mt-4 pt-4 border-t border-gray-100">
              <p className="text-sm text-gray-500">
                <span className="font-medium text-gray-700">{createdBindings.length}</span> binding{createdBindings.length !== 1 ? 's' : ''} active
                {availableBindings.length > 0 && (
                  <span>
                    {' '}&bull;{' '}
                    <span className="font-medium text-gray-700">{availableBindings.length}</span> more available
                  </span>
                )}
              </p>
            </div>
          </div>

          {/* Footer actions */}
          <div className="p-6 pt-0 flex gap-3">
            <button
              onClick={() => onViewContract?.(data.id)}
              className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              <ExternalLink className="h-4 w-4" />
              View Contract
            </button>

            {firstPlayground ? (
              <button
                onClick={() => onTestPlayground?.(firstPlayground)}
                className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors"
              >
                <Play className="h-4 w-4" />
                Test in Playground
              </button>
            ) : (
              <button
                onClick={onClose}
                className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors"
              >
                Done
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default PublishSuccessModal;
