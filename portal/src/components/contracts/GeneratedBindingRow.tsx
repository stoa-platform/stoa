/**
 * GeneratedBindingRow Component
 *
 * Displays a single auto-generated binding after contract publication.
 * Part of the "wow" effect showing users that STOA automatically
 * generates multiple protocol bindings from a single contract.
 *
 * Reference: CAB-560 - Universal API Contracts
 */

import React from 'react';
import { GeneratedBinding, ProtocolType } from '../../types';
import { Check, Clock, ExternalLink, Sparkles } from 'lucide-react';

interface GeneratedBindingRowProps {
  binding: GeneratedBinding;
}

const protocolConfig: Record<ProtocolType, {
  label: string;
  icon: string;
  color: string;
  bgColor: string;
}> = {
  rest: {
    label: 'REST',
    icon: '🌐',
    color: 'text-green-700',
    bgColor: 'bg-green-50',
  },
  graphql: {
    label: 'GraphQL',
    icon: '◈',
    color: 'text-pink-700',
    bgColor: 'bg-pink-50',
  },
  grpc: {
    label: 'gRPC',
    icon: '⚡',
    color: 'text-blue-700',
    bgColor: 'bg-blue-50',
  },
  mcp: {
    label: 'MCP',
    icon: '🤖',
    color: 'text-purple-700',
    bgColor: 'bg-purple-50',
  },
  kafka: {
    label: 'Kafka',
    icon: '📨',
    color: 'text-orange-700',
    bgColor: 'bg-orange-50',
  },
};

export const GeneratedBindingRow: React.FC<GeneratedBindingRowProps> = ({ binding }) => {
  const config = protocolConfig[binding.protocol];
  const isCreated = binding.status === 'created';

  const getStatusIcon = () => {
    if (isCreated) {
      return <Check className="h-5 w-5 text-green-500" />;
    }
    return <Clock className="h-5 w-5 text-gray-400" />;
  };

  const getEndpointDisplay = () => {
    if (!isCreated) {
      return (
        <span className="text-gray-400 text-sm">
          Enable in Protocol Settings
        </span>
      );
    }

    if (binding.protocol === 'mcp' && binding.tool_name) {
      return (
        <span className="text-gray-600 text-sm font-mono">
          tool: {binding.tool_name}
        </span>
      );
    }

    if (binding.protocol === 'graphql' && binding.operations?.length) {
      return (
        <span className="text-gray-600 text-sm font-mono">
          {binding.operations.join(', ')}
        </span>
      );
    }

    if (binding.endpoint) {
      return (
        <span className="text-gray-600 text-sm font-mono truncate">
          {binding.endpoint}
        </span>
      );
    }

    return null;
  };

  return (
    <div className={`flex items-start gap-3 p-3 rounded-lg ${isCreated ? config.bgColor : 'bg-gray-50'}`}>
      {/* Status icon */}
      <div className="flex-shrink-0 mt-0.5">
        {getStatusIcon()}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`font-medium ${isCreated ? config.color : 'text-gray-500'}`}>
            {config.icon} {config.label}
            {isCreated ? ' endpoint created' : ' available'}
          </span>

          {/* Auto-generated badge for MCP */}
          {binding.auto_generated && isCreated && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium bg-purple-100 text-purple-700 rounded-full">
              <Sparkles className="h-3 w-3" />
              Auto-generated
            </span>
          )}
        </div>

        <div className="mt-1">
          {getEndpointDisplay()}
        </div>
      </div>

      {/* Action link */}
      {isCreated && binding.playground_url && (
        <a
          href={binding.playground_url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex-shrink-0 text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1"
        >
          Test
          <ExternalLink className="h-3 w-3" />
        </a>
      )}
    </div>
  );
};

export default GeneratedBindingRow;
