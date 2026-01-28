// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * ContractListPage
 *
 * Lists all Universal API Contracts for the current tenant.
 * Each contract card shows the UACBadge with enabled bindings.
 *
 * Reference: CAB-564 - UAC Badge & Tooltips
 */

import React from 'react';
import { Link } from 'react-router-dom';
import { Plus, FileCode2, AlertCircle, Loader2 } from 'lucide-react';
import { useContracts } from '../../hooks/useContracts';
import { UACBadge } from '../../components/uac';
import { formatRelativeTime } from '../../utils/format';
import type { Contract, ProtocolType, ProtocolBinding } from '../../types';

// Protocol badge colors
const protocolConfig: Record<ProtocolType, { label: string; className: string }> = {
  rest: { label: 'REST', className: 'bg-green-50 text-green-700 border-green-200' },
  mcp: { label: 'MCP', className: 'bg-purple-50 text-purple-700 border-purple-200' },
  graphql: { label: 'GraphQL', className: 'bg-pink-50 text-pink-700 border-pink-200' },
  grpc: { label: 'gRPC', className: 'bg-blue-50 text-blue-700 border-blue-200' },
  kafka: { label: 'Kafka', className: 'bg-orange-50 text-orange-700 border-orange-200' },
};

// Small protocol badge for the card
const ProtocolBadge: React.FC<{ protocol: ProtocolType }> = ({ protocol }) => {
  const { label, className } = protocolConfig[protocol];

  return (
    <span className={`px-2 py-0.5 text-xs font-medium rounded border ${className}`}>
      {label}
    </span>
  );
};

// Contract card component
interface ContractCardProps {
  contract: Contract;
}

const ContractCard: React.FC<ContractCardProps> = ({ contract }) => {
  // Prepare bindings for UACBadge
  const badgeBindings: ProtocolBinding[] = contract.bindings?.map((b) => ({
    protocol: b.protocol,
    enabled: b.enabled,
    endpoint: b.endpoint,
    tool_name: b.tool_name,
    operations: b.operations,
  })) || [];

  const enabledBindings = badgeBindings.filter((b) => b.enabled);

  return (
    <Link
      to={`/contracts/${contract.id}`}
      className="
        block bg-white rounded-lg border border-gray-200
        hover:border-blue-300 hover:shadow-md
        transition-all duration-200
        overflow-hidden
      "
    >
      <div className="p-5">
        {/* Header */}
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex items-center gap-2 min-w-0">
            <h3 className="font-semibold text-gray-900 truncate">
              {contract.display_name || contract.name}
            </h3>
            <span className="flex-shrink-0 text-xs text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">
              v{contract.version}
            </span>
          </div>

          {/* UAC Badge */}
          <div className="flex-shrink-0" onClick={(e) => e.preventDefault()}>
            <UACBadge
              contractName={contract.name}
              bindings={badgeBindings}
              variant="default"
            />
          </div>
        </div>

        {/* Description */}
        {contract.description && (
          <p className="text-sm text-gray-600 mb-3 line-clamp-2">
            {contract.description}
          </p>
        )}

        {/* Protocol badges */}
        <div className="flex flex-wrap items-center gap-1.5 mb-3">
          {enabledBindings.map((binding) => (
            <ProtocolBadge key={binding.protocol} protocol={binding.protocol} />
          ))}

          {/* Show count of disabled bindings */}
          {badgeBindings.length > enabledBindings.length && (
            <span className="text-xs text-gray-400">
              +{badgeBindings.length - enabledBindings.length} available
            </span>
          )}
        </div>

        {/* Stats footer */}
        <div className="flex items-center justify-between text-xs text-gray-500 pt-3 border-t border-gray-100">
          <span>Updated {formatRelativeTime(contract.updated_at)}</span>
          <span
            className={`
              px-2 py-0.5 rounded-full font-medium
              ${contract.status === 'published'
                ? 'bg-green-100 text-green-700'
                : contract.status === 'draft'
                  ? 'bg-yellow-100 text-yellow-700'
                  : 'bg-gray-100 text-gray-600'}
            `}
          >
            {contract.status}
          </span>
        </div>
      </div>
    </Link>
  );
};

// Empty state component
const EmptyState: React.FC = () => (
  <div className="text-center py-12 bg-white rounded-lg border border-gray-200">
    <FileCode2 className="h-12 w-12 text-gray-300 mx-auto mb-4" />
    <h3 className="text-lg font-medium text-gray-900 mb-2">No contracts yet</h3>
    <p className="text-gray-500 mb-6 max-w-md mx-auto">
      Create your first Universal API Contract to expose your API via multiple protocols
      automatically.
    </p>
    <Link
      to="/contracts/new"
      className="
        inline-flex items-center gap-2
        px-4 py-2
        bg-blue-600 text-white
        rounded-lg font-medium
        hover:bg-blue-700
        transition-colors
      "
    >
      <Plus className="h-4 w-4" />
      Create your first contract
    </Link>
  </div>
);

// Loading state component
const LoadingState: React.FC = () => (
  <div className="flex items-center justify-center py-12">
    <Loader2 className="h-8 w-8 text-blue-600 animate-spin" />
  </div>
);

// Error state component
const ErrorState: React.FC<{ message: string }> = ({ message }) => (
  <div className="text-center py-12 bg-white rounded-lg border border-red-200">
    <AlertCircle className="h-12 w-12 text-red-400 mx-auto mb-4" />
    <h3 className="text-lg font-medium text-gray-900 mb-2">Failed to load contracts</h3>
    <p className="text-gray-500">{message}</p>
  </div>
);

export const ContractListPage: React.FC = () => {
  const { data, isLoading, error } = useContracts();

  const contracts = data?.items || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Contracts</h1>
          <p className="text-gray-500 mt-1">
            Manage your Universal API Contracts and protocol bindings
          </p>
        </div>
        <Link
          to="/contracts/new"
          className="
            inline-flex items-center gap-2
            px-4 py-2
            bg-blue-600 text-white
            rounded-lg font-medium
            hover:bg-blue-700
            transition-colors
            flex-shrink-0
          "
        >
          <Plus className="h-4 w-4" />
          New Contract
        </Link>
      </div>

      {/* Content */}
      {isLoading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error.message} />
      ) : contracts.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {contracts.map((contract) => (
            <ContractCard key={contract.id} contract={contract} />
          ))}
        </div>
      )}
    </div>
  );
};

export default ContractListPage;
