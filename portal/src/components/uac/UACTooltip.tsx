/**
 * UACTooltip Component
 *
 * Educational tooltip content explaining Universal API Contract (UAC).
 * Shows all enabled bindings (REST, MCP, GraphQL, etc.) for a contract.
 *
 * Reference: CAB-564 - UAC Badge & Tooltips
 */

import React from 'react';
import { ProtocolType, ProtocolBinding } from '../../types';
import { ExternalLink } from 'lucide-react';

interface UACTooltipProps {
  contractName: string;
  bindings: ProtocolBinding[];
  docsUrl?: string;
}

const protocolIcons: Record<ProtocolType, string> = {
  rest: '🌐',
  mcp: '🤖',
  graphql: '◈',
  grpc: '⚡',
  kafka: '📨',
};

const protocolLabels: Record<ProtocolType, string> = {
  rest: 'REST',
  mcp: 'MCP',
  graphql: 'GraphQL',
  grpc: 'gRPC',
  kafka: 'Kafka',
};

export const UACTooltip: React.FC<UACTooltipProps> = ({ bindings, docsUrl = '/docs/uac' }) => {
  const enabledBindings = bindings.filter((b) => b.enabled);

  const getBindingDisplay = (binding: ProtocolBinding): string => {
    if (binding.tool_name) return `tool: ${binding.tool_name}`;
    if (binding.operations?.length) return binding.operations.join(', ');
    if (binding.endpoint) return binding.endpoint;
    return 'Enabled';
  };

  return (
    <div className="w-72">
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <span className="text-lg">🔗</span>
        <span className="font-semibold text-neutral-900 dark:text-white">Universal API Contract</span>
      </div>

      {/* Description */}
      <p className="text-sm text-neutral-600 dark:text-neutral-400 mb-3">
        This API is defined once and automatically available via multiple protocols:
      </p>

      {/* Bindings list */}
      <div className="space-y-2 mb-3">
        {enabledBindings.map((binding) => (
          <div key={binding.protocol} className="flex items-start gap-2 text-sm">
            <span className="flex-shrink-0 w-5 text-center">{protocolIcons[binding.protocol]}</span>
            <div className="min-w-0">
              <span className="font-medium text-neutral-800 dark:text-neutral-200">
                {protocolLabels[binding.protocol]}
              </span>
              <span className="ml-2 text-neutral-500 dark:text-neutral-400 font-mono text-xs truncate block">
                {getBindingDisplay(binding)}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Tagline */}
      <p className="text-xs text-neutral-500 dark:text-neutral-400 italic mb-3">
        One contract, zero duplication.
      </p>

      {/* Divider and link */}
      <div className="pt-3 border-t border-neutral-100 dark:border-neutral-700">
        <a
          href={docsUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-sm text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 font-medium"
        >
          Learn more
          <ExternalLink className="h-3 w-3" />
        </a>
      </div>
    </div>
  );
};

export default UACTooltip;
