// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * CallsTable Component - CAB-280
 * Table des derniers appels MCP avec filtres
 */

import { useState } from 'react';
import { Check, X, Clock } from 'lucide-react';
import type { UsageCall, UsageCallStatus } from '../../types';
import { formatLatency } from '../../services/usage';

interface CallsTableProps {
  calls: UsageCall[];
  isLoading?: boolean;
  onFilterChange?: (status: UsageCallStatus | null, toolId: string | null) => void;
}

function StatusBadge({ status }: { status: UsageCallStatus }) {
  const configs = {
    success: {
      icon: <Check className="w-3 h-3" />,
      bg: 'bg-emerald-100',
      text: 'text-emerald-700',
      label: 'Success',
    },
    error: {
      icon: <X className="w-3 h-3" />,
      bg: 'bg-red-100',
      text: 'text-red-700',
      label: 'Error',
    },
    timeout: {
      icon: <Clock className="w-3 h-3" />,
      bg: 'bg-amber-100',
      text: 'text-amber-700',
      label: 'Timeout',
    },
  };

  const config = configs[status];

  return (
    <span className={`
      inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium
      ${config.bg} ${config.text}
    `}>
      {config.icon}
      {config.label}
    </span>
  );
}

function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;

  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;

  return date.toLocaleDateString('en-US', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function TableSkeleton() {
  return (
    <div className="animate-pulse">
      {[...Array(5)].map((_, i) => (
        <div key={i} className="flex items-center gap-4 p-4 border-b border-gray-100">
          <div className="h-4 w-20 bg-gray-200 rounded" />
          <div className="h-4 w-32 bg-gray-200 rounded flex-1" />
          <div className="h-6 w-16 bg-gray-200 rounded-full" />
          <div className="h-4 w-16 bg-gray-200 rounded" />
        </div>
      ))}
    </div>
  );
}

export function CallsTable({ calls, isLoading = false, onFilterChange }: CallsTableProps) {
  const [selectedStatus, setSelectedStatus] = useState<UsageCallStatus | null>(null);

  const handleStatusFilter = (status: UsageCallStatus | null) => {
    setSelectedStatus(status);
    onFilterChange?.(status, null);
  };

  const filteredCalls = selectedStatus
    ? calls.filter(c => c.status === selectedStatus)
    : calls;

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      {/* Header avec filtres */}
      <div className="flex items-center justify-between p-4 border-b border-gray-100">
        <h3 className="text-lg font-semibold text-gray-900">Recent Calls</h3>

        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-500 mr-2">Filter:</span>

          {(['all', 'success', 'error', 'timeout'] as const).map((status) => (
            <button
              key={status}
              onClick={() => handleStatusFilter(status === 'all' ? null : status as UsageCallStatus)}
              className={`
                px-3 py-1.5 rounded-lg text-xs font-medium transition-colors
                ${(status === 'all' && !selectedStatus) || selectedStatus === status
                  ? 'bg-primary-100 text-primary-700 border border-primary-200'
                  : 'bg-gray-50 text-gray-600 border border-transparent hover:bg-gray-100'
                }
              `}
            >
              {status === 'all' ? 'All' : status.charAt(0).toUpperCase() + status.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      {isLoading ? (
        <TableSkeleton />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider border-b border-gray-100 bg-gray-50">
                <th className="px-4 py-3">Time</th>
                <th className="px-4 py-3">Tool</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Latency</th>
              </tr>
            </thead>
            <tbody>
              {filteredCalls.map((call) => (
                <tr
                  key={call.id}
                  className="border-b border-gray-50 hover:bg-gray-50 transition-colors"
                >
                  <td className="px-4 py-3">
                    <span className="text-sm text-gray-500">
                      {formatTimestamp(call.timestamp)}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div>
                      <div className="text-sm font-medium text-gray-900">{call.tool_name}</div>
                      <div className="text-xs text-gray-400">{call.tool_id}</div>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={call.status} />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span className={`
                      text-sm font-mono
                      ${call.latency_ms > 500 ? 'text-amber-600' : 'text-gray-600'}
                    `}>
                      {formatLatency(call.latency_ms)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Empty state */}
          {filteredCalls.length === 0 && (
            <div className="p-8 text-center">
              <p className="text-gray-500">No calls found</p>
            </div>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100 bg-gray-50">
        <span className="text-sm text-gray-500">
          Showing {filteredCalls.length} of {calls.length} calls
        </span>
        <button className="text-sm text-primary-600 hover:text-primary-700 font-medium transition-colors">
          View all →
        </button>
      </div>
    </div>
  );
}
