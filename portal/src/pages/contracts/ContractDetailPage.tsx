// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * ContractDetailPage
 *
 * Detailed view of a Universal API Contract with Protocol Switcher.
 * Users can manage protocol bindings (enable/disable) from this page.
 *
 * Reference: CAB-564 - UAC Badge & Tooltips
 */

import React from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  ArrowLeft,
  Settings,
  Trash2,
  ExternalLink,
  Loader2,
  AlertCircle,
  FileCode2,
} from 'lucide-react';
import { useContract } from '../../hooks/useContracts';
import { ProtocolSwitcher } from '../../components/contracts';
import { UACBadge } from '../../components/uac';
import { formatRelativeTime } from '../../utils/format';
import type { ProtocolType, ProtocolBinding } from '../../types';

// Quick access card configuration
const quickAccessConfig: Record<
  ProtocolType,
  {
    label: string;
    icon: string;
    actionLabel: string;
    bgColor: string;
    borderColor: string;
  }
> = {
  rest: {
    label: 'REST API',
    icon: '🌐',
    actionLabel: 'View Docs',
    bgColor: 'bg-green-50',
    borderColor: 'border-green-200',
  },
  mcp: {
    label: 'MCP Tool',
    icon: '🤖',
    actionLabel: 'Test Tool',
    bgColor: 'bg-purple-50',
    borderColor: 'border-purple-200',
  },
  graphql: {
    label: 'GraphQL',
    icon: '◈',
    actionLabel: 'Open Playground',
    bgColor: 'bg-pink-50',
    borderColor: 'border-pink-200',
  },
  grpc: {
    label: 'gRPC',
    icon: '⚡',
    actionLabel: 'View Proto',
    bgColor: 'bg-blue-50',
    borderColor: 'border-blue-200',
  },
  kafka: {
    label: 'Kafka Events',
    icon: '📨',
    actionLabel: 'View Topics',
    bgColor: 'bg-orange-50',
    borderColor: 'border-orange-200',
  },
};

// Quick access card component
interface QuickAccessCardProps {
  binding: ProtocolBinding;
}

const QuickAccessCard: React.FC<QuickAccessCardProps> = ({ binding }) => {
  const config = quickAccessConfig[binding.protocol];

  const getDisplayValue = () => {
    if (binding.tool_name) return binding.tool_name;
    if (binding.endpoint) return binding.endpoint;
    if (binding.operations?.length) return binding.operations.join(', ');
    return 'Enabled';
  };

  return (
    <div
      className={`
        p-4 rounded-lg border
        ${config.bgColor} ${config.borderColor}
      `}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span>{config.icon}</span>
            <span className="font-medium text-gray-900">{config.label}</span>
          </div>
          <p className="text-sm text-gray-600 font-mono truncate">{getDisplayValue()}</p>
        </div>

        {binding.playground_url && (
          <a
            href={binding.playground_url}
            target="_blank"
            rel="noopener noreferrer"
            className="
              flex items-center gap-1
              text-sm text-blue-600 hover:text-blue-800
              flex-shrink-0
            "
          >
            {config.actionLabel}
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
        )}
      </div>
    </div>
  );
};

// Loading state
const LoadingState: React.FC = () => (
  <div className="flex items-center justify-center py-24">
    <Loader2 className="h-8 w-8 text-blue-600 animate-spin" />
  </div>
);

// Error state
const ErrorState: React.FC<{ message: string }> = ({ message }) => (
  <div className="text-center py-24">
    <AlertCircle className="h-12 w-12 text-red-400 mx-auto mb-4" />
    <h2 className="text-lg font-medium text-gray-900 mb-2">Failed to load contract</h2>
    <p className="text-gray-500 mb-6">{message}</p>
    <Link
      to="/contracts"
      className="text-blue-600 hover:text-blue-800 font-medium"
    >
      Back to Contracts
    </Link>
  </div>
);

// Not found state
const NotFoundState: React.FC = () => (
  <div className="text-center py-24">
    <FileCode2 className="h-12 w-12 text-gray-300 mx-auto mb-4" />
    <h2 className="text-lg font-medium text-gray-900 mb-2">Contract not found</h2>
    <p className="text-gray-500 mb-6">
      The contract you're looking for doesn't exist or you don't have access to it.
    </p>
    <Link
      to="/contracts"
      className="text-blue-600 hover:text-blue-800 font-medium"
    >
      Back to Contracts
    </Link>
  </div>
);

export const ContractDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: contract, isLoading, error } = useContract(id);

  if (isLoading) {
    return <LoadingState />;
  }

  if (error) {
    return <ErrorState message={error.message} />;
  }

  if (!contract) {
    return <NotFoundState />;
  }

  // Prepare bindings for UACBadge
  const badgeBindings: ProtocolBinding[] =
    contract.bindings?.map((b) => ({
      protocol: b.protocol,
      enabled: b.enabled,
      endpoint: b.endpoint,
      tool_name: b.tool_name,
      operations: b.operations,
      playground_url: b.playground_url,
    })) || [];

  const enabledBindings = badgeBindings.filter((b) => b.enabled);

  return (
    <div className="space-y-6">
      {/* Back link */}
      <button
        onClick={() => navigate('/contracts')}
        className="flex items-center gap-2 text-gray-500 hover:text-gray-700 transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Contracts
      </button>

      {/* Header */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="flex items-start justify-between gap-4 mb-4">
          <div className="flex items-center gap-3 min-w-0">
            <h1 className="text-2xl font-bold text-gray-900 truncate">
              {contract.display_name || contract.name}
            </h1>

            {/* UAC Badge */}
            <UACBadge
              contractName={contract.name}
              bindings={badgeBindings}
              variant="with-count"
            />
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
              title="Settings"
            >
              <Settings className="h-5 w-5" />
            </button>
            <button
              className="p-2 text-red-500 hover:text-red-700 hover:bg-red-50 rounded-lg transition-colors"
              title="Delete"
            >
              <Trash2 className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* Meta info */}
        <div className="flex items-center gap-3 text-sm text-gray-500 mb-4">
          <span className="bg-gray-100 px-2 py-0.5 rounded">v{contract.version}</span>
          <span>•</span>
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
          <span>•</span>
          <span>Updated {formatRelativeTime(contract.updated_at)}</span>
        </div>

        {/* Description */}
        {contract.description && (
          <p className="text-gray-600">{contract.description}</p>
        )}
      </div>

      {/* Main content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Protocol Switcher - Main feature */}
        <div className="lg:col-span-2 bg-white rounded-lg border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            Protocol Bindings
          </h2>
          <ProtocolSwitcher
            contractId={contract.id}
            onBindingEnabled={(protocol) => {
              console.log(`${protocol} enabled`);
            }}
            onBindingDisabled={(protocol) => {
              console.log(`${protocol} disabled`);
            }}
          />
        </div>

        {/* Quick access to endpoints */}
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Quick Access</h2>
          {enabledBindings.length > 0 ? (
            <div className="space-y-3">
              {enabledBindings.map((binding) => (
                <QuickAccessCard key={binding.protocol} binding={binding} />
              ))}
            </div>
          ) : (
            <p className="text-gray-500 text-sm">
              Enable protocol bindings to access your API endpoints.
            </p>
          )}
        </div>
      </div>

      {/* Contract source (optional) */}
      {contract.openapi_spec_url && (
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">OpenAPI Spec</h2>
          <a
            href={contract.openapi_spec_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 text-blue-600 hover:text-blue-800"
          >
            {contract.openapi_spec_url}
            <ExternalLink className="h-4 w-4" />
          </a>
        </div>
      )}
    </div>
  );
};

export default ContractDetailPage;
