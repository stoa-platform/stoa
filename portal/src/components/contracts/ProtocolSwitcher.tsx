/**
 * ProtocolSwitcher Component
 *
 * Main component for managing protocol bindings on a UAC contract.
 * Allows users to enable/disable REST, MCP, GraphQL, gRPC, and Kafka bindings.
 *
 * Usage:
 * ```tsx
 * <ProtocolSwitcher contractId="550e8400-e29b-41d4-a716-446655440000" />
 * ```
 */

import React, { useState, useCallback } from 'react';
import { Loader2, AlertCircle, RefreshCw } from 'lucide-react';
import { useBindings, useEnableBinding, useDisableBinding } from '../../hooks/useContracts';
import { ProtocolRow } from './ProtocolRow';
import { DisableBindingModal } from './DisableBindingModal';
import type { ProtocolBinding, ProtocolType } from '../../types';

interface ProtocolSwitcherProps {
  /** The contract ID to manage bindings for */
  contractId: string;
  /** Optional CSS class name */
  className?: string;
  /** Called when a binding is successfully enabled */
  onBindingEnabled?: (protocol: ProtocolType) => void;
  /** Called when a binding is successfully disabled */
  onBindingDisabled?: (protocol: ProtocolType) => void;
}

/** Protocol display order */
const PROTOCOL_ORDER: ProtocolType[] = ['rest', 'mcp', 'graphql', 'grpc', 'kafka'];

/**
 * Toast notification component (simple inline implementation)
 */
const Toast: React.FC<{
  message: string;
  type: 'success' | 'error';
  onClose: () => void;
}> = ({ message, type, onClose }) => {
  React.useEffect(() => {
    const timer = setTimeout(onClose, 4000);
    return () => clearTimeout(timer);
  }, [onClose]);

  return (
    <div
      className={`
        fixed bottom-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg
        flex items-center gap-2 animate-slide-up
        ${type === 'success' ? 'bg-green-600 text-white' : 'bg-red-600 text-white'}
      `}
    >
      <span>{type === 'success' ? '✓' : '✕'}</span>
      <span className="text-sm font-medium">{message}</span>
      <button
        onClick={onClose}
        className="ml-2 text-white/80 hover:text-white"
      >
        ×
      </button>
    </div>
  );
};

export const ProtocolSwitcher: React.FC<ProtocolSwitcherProps> = ({
  contractId,
  className = '',
  onBindingEnabled,
  onBindingDisabled,
}) => {
  // Fetch bindings
  const {
    data,
    isLoading,
    error,
    refetch,
  } = useBindings(contractId);

  // Mutations
  const enableBinding = useEnableBinding(contractId);
  const disableBinding = useDisableBinding(contractId);

  // Local state for confirmation modal
  const [pendingDisable, setPendingDisable] = useState<ProtocolBinding | null>(null);

  // Toast state
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);

  /**
   * Handle toggle action on a binding
   */
  const handleToggle = useCallback(
    async (binding: ProtocolBinding, enabled: boolean) => {
      if (enabled) {
        // Enable binding
        try {
          await enableBinding.mutateAsync(binding.protocol);
          setToast({
            message: `${binding.protocol.toUpperCase()} endpoint ready`,
            type: 'success',
          });
          onBindingEnabled?.(binding.protocol);
        } catch (err) {
          setToast({
            message: `Failed to enable ${binding.protocol.toUpperCase()}: ${(err as Error).message}`,
            type: 'error',
          });
        }
      } else {
        // Check if we need confirmation (traffic > 0)
        if (binding.traffic_24h && binding.traffic_24h > 0) {
          setPendingDisable(binding);
        } else {
          // Disable directly
          await confirmDisable(binding.protocol);
        }
      }
    },
    [enableBinding, onBindingEnabled]
  );

  /**
   * Confirm and execute disable action
   */
  const confirmDisable = useCallback(
    async (protocol?: ProtocolType) => {
      const protocolToDisable = protocol || pendingDisable?.protocol;
      if (!protocolToDisable) return;

      try {
        await disableBinding.mutateAsync(protocolToDisable);
        setToast({
          message: `${protocolToDisable.toUpperCase()} binding disabled`,
          type: 'success',
        });
        onBindingDisabled?.(protocolToDisable);
      } catch (err) {
        setToast({
          message: `Failed to disable: ${(err as Error).message}`,
          type: 'error',
        });
      } finally {
        setPendingDisable(null);
      }
    },
    [disableBinding, pendingDisable, onBindingDisabled]
  );

  // Loading state
  if (isLoading) {
    return (
      <div className={`border rounded-lg ${className}`}>
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
          <span className="ml-2 text-sm text-gray-500">Loading bindings...</span>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className={`border border-red-200 rounded-lg bg-red-50 ${className}`}>
        <div className="flex items-center justify-center py-8 px-4">
          <AlertCircle className="h-5 w-5 text-red-500 mr-2" />
          <span className="text-sm text-red-700">
            Failed to load bindings: {(error as Error).message}
          </span>
          <button
            onClick={() => refetch()}
            className="ml-4 text-sm text-red-600 hover:text-red-800 underline"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  // Sort bindings by protocol order
  const sortedBindings = [...(data?.bindings || [])].sort((a, b) => {
    const indexA = PROTOCOL_ORDER.indexOf(a.protocol);
    const indexB = PROTOCOL_ORDER.indexOf(b.protocol);
    return indexA - indexB;
  });

  // Count enabled bindings
  const enabledCount = sortedBindings.filter((b) => b.enabled).length;

  return (
    <div className={`border border-gray-200 rounded-lg overflow-hidden ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between bg-gray-50 px-4 py-3 border-b border-gray-200">
        <div>
          <h3 className="text-sm font-medium text-gray-900">Protocols</h3>
          <p className="text-xs text-gray-500 mt-0.5">
            {enabledCount} of {sortedBindings.length} enabled
          </p>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isLoading}
          className="p-1.5 text-gray-400 hover:text-gray-600 transition-colors rounded"
          title="Refresh"
        >
          <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Bindings list */}
      <div className="divide-y divide-gray-100">
        {sortedBindings.map((binding) => (
          <ProtocolRow
            key={binding.protocol}
            binding={binding}
            onToggle={(enabled) => handleToggle(binding, enabled)}
            isLoading={
              (enableBinding.isPending && enableBinding.variables === binding.protocol) ||
              (disableBinding.isPending && disableBinding.variables === binding.protocol)
            }
          />
        ))}

        {sortedBindings.length === 0 && (
          <div className="py-8 text-center text-sm text-gray-500">
            No protocol bindings available
          </div>
        )}
      </div>

      {/* Disable confirmation modal */}
      <DisableBindingModal
        binding={pendingDisable}
        onConfirm={() => confirmDisable()}
        onCancel={() => setPendingDisable(null)}
        isLoading={disableBinding.isPending}
      />

      {/* Toast notification */}
      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={() => setToast(null)}
        />
      )}
    </div>
  );
};

export default ProtocolSwitcher;
