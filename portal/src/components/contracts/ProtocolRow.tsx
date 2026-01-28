// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * ProtocolRow Component
 *
 * Displays a single protocol binding with toggle switch and status information.
 * Part of the Protocol Switcher for UAC contracts.
 */

import React from 'react';
import { ExternalLink, Loader2 } from 'lucide-react';
import type { ProtocolBinding, ProtocolType } from '../../types';

interface ProtocolRowProps {
  binding: ProtocolBinding;
  onToggle: (enabled: boolean) => void;
  isLoading?: boolean;
}

/**
 * Protocol display configuration
 */
const protocolConfig: Record<
  ProtocolType,
  { label: string; icon: string; color: string; bgColor: string }
> = {
  rest: {
    label: 'REST',
    icon: '🌐',
    color: 'text-green-800',
    bgColor: 'bg-green-100',
  },
  graphql: {
    label: 'GraphQL',
    icon: '◈',
    color: 'text-pink-800',
    bgColor: 'bg-pink-100',
  },
  grpc: {
    label: 'gRPC',
    icon: '⚡',
    color: 'text-blue-800',
    bgColor: 'bg-blue-100',
  },
  mcp: {
    label: 'MCP',
    icon: '🤖',
    color: 'text-purple-800',
    bgColor: 'bg-purple-100',
  },
  kafka: {
    label: 'Kafka',
    icon: '📨',
    color: 'text-orange-800',
    bgColor: 'bg-orange-100',
  },
};

/**
 * Custom toggle switch component
 */
const ToggleSwitch: React.FC<{
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}> = ({ checked, onChange, disabled }) => {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`
        relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full
        border-2 border-transparent transition-colors duration-200 ease-in-out
        focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2
        ${checked ? 'bg-primary-600' : 'bg-gray-200'}
        ${disabled ? 'opacity-50 cursor-not-allowed' : ''}
      `}
    >
      <span
        className={`
          pointer-events-none inline-block h-5 w-5 transform rounded-full
          bg-white shadow ring-0 transition duration-200 ease-in-out
          ${checked ? 'translate-x-5' : 'translate-x-0'}
        `}
      />
    </button>
  );
};

export const ProtocolRow: React.FC<ProtocolRowProps> = ({
  binding,
  onToggle,
  isLoading = false,
}) => {
  const config = protocolConfig[binding.protocol];

  /**
   * Get the endpoint/tool display text based on protocol
   */
  const getEndpointDisplay = (): string => {
    if (!binding.enabled) {
      return '─ Enable to generate';
    }

    switch (binding.protocol) {
      case 'mcp':
        return binding.tool_name ? `tool: ${binding.tool_name}` : binding.endpoint || '';
      case 'graphql':
        if (binding.operations && binding.operations.length > 0) {
          return binding.operations.join(', ');
        }
        return binding.endpoint || '';
      case 'kafka':
        return binding.topic_name || binding.endpoint || '';
      case 'grpc':
        return binding.proto_file_url
          ? `proto: ${binding.proto_file_url.split('/').pop()}`
          : binding.endpoint || '';
      default:
        return binding.endpoint || '';
    }
  };

  /**
   * Get the action link label and URL based on protocol
   */
  const getActionLink = (): { label: string; url: string } | null => {
    if (!binding.enabled) return null;

    const labels: Record<ProtocolType, string> = {
      rest: 'Endpoint',
      graphql: 'Playground',
      grpc: 'Proto',
      mcp: 'Test',
      kafka: 'Topics',
    };

    const url = binding.playground_url || binding.endpoint;
    if (!url) return null;

    return {
      label: labels[binding.protocol],
      url,
    };
  };

  const actionLink = getActionLink();

  return (
    <div className="flex items-center justify-between py-3 px-4 border-b border-gray-100 last:border-b-0 hover:bg-gray-50 transition-colors">
      {/* Left side: Toggle + Protocol badge + Endpoint */}
      <div className="flex items-center gap-3 min-w-0 flex-1">
        {/* Toggle or Loading spinner */}
        {isLoading ? (
          <div className="w-11 flex justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
          </div>
        ) : (
          <ToggleSwitch
            checked={binding.enabled}
            onChange={onToggle}
            disabled={isLoading}
          />
        )}

        {/* Protocol badge */}
        <span
          className={`
            inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded
            ${config.bgColor} ${config.color}
          `}
        >
          <span>{config.icon}</span>
          <span>{config.label}</span>
        </span>

        {/* Endpoint display */}
        <span
          className={`
            text-sm truncate
            ${binding.enabled ? 'text-gray-700' : 'text-gray-400 italic'}
          `}
          title={binding.enabled ? binding.endpoint : undefined}
        >
          {getEndpointDisplay()}
        </span>
      </div>

      {/* Right side: Traffic stats + Action link */}
      <div className="flex items-center gap-4 flex-shrink-0 ml-4">
        {/* Traffic stats (only when enabled) */}
        {binding.enabled && binding.traffic_24h !== undefined && (
          <span className="text-xs text-gray-500 whitespace-nowrap">
            {binding.traffic_24h.toLocaleString()} req/24h
          </span>
        )}

        {/* Action link */}
        {actionLink ? (
          <a
            href={actionLink.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-sm text-primary-600 hover:text-primary-800 transition-colors"
          >
            {actionLink.label}
            <ExternalLink className="h-3 w-3" />
          </a>
        ) : !binding.enabled ? (
          <button
            onClick={() => onToggle(true)}
            disabled={isLoading}
            className="text-sm text-primary-600 hover:text-primary-800 font-medium disabled:opacity-50"
          >
            + Enable
          </button>
        ) : null}
      </div>
    </div>
  );
};

export default ProtocolRow;
