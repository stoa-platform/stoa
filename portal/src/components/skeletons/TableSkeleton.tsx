// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
import { Skeleton } from '../common/Skeleton';

interface TableRowSkeletonProps {
  columns?: number;
}

/**
 * Single table row skeleton.
 */
export function TableRowSkeleton({ columns = 5 }: TableRowSkeletonProps) {
  return (
    <tr>
      {Array.from({ length: columns }).map((_, i) => (
        <td key={i} className="px-4 py-3">
          <Skeleton className="h-4 w-full" />
        </td>
      ))}
    </tr>
  );
}

/**
 * Table body with multiple skeleton rows.
 */
export function TableSkeleton({
  rows = 5,
  columns = 5,
}: {
  rows?: number;
  columns?: number;
}) {
  return (
    <tbody className="divide-y divide-gray-200">
      {Array.from({ length: rows }).map((_, i) => (
        <TableRowSkeleton key={i} columns={columns} />
      ))}
    </tbody>
  );
}

/**
 * Full table with header skeleton.
 */
export function FullTableSkeleton({
  rows = 5,
  columns = 5,
  headers,
}: {
  rows?: number;
  columns?: number;
  headers?: string[];
}) {
  const headerCount = headers?.length || columns;

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            {Array.from({ length: headerCount }).map((_, i) => (
              <th key={i} className="px-4 py-3 text-left">
                {headers ? (
                  <span className="text-xs font-medium text-gray-500 uppercase">
                    {headers[i]}
                  </span>
                ) : (
                  <Skeleton className="h-4 w-20" />
                )}
              </th>
            ))}
          </tr>
        </thead>
        <TableSkeleton rows={rows} columns={headerCount} />
      </table>
    </div>
  );
}

/**
 * Subscription table skeleton.
 */
export function SubscriptionTableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Server</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">API Key</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200">
          {Array.from({ length: rows }).map((_, i) => (
            <tr key={i}>
              <td className="px-4 py-3">
                <div className="flex items-center gap-3">
                  <Skeleton className="h-8 w-8 rounded" />
                  <div>
                    <Skeleton className="h-4 w-32 mb-1" />
                    <Skeleton className="h-3 w-24" />
                  </div>
                </div>
              </td>
              <td className="px-4 py-3">
                <Skeleton className="h-6 w-16 rounded-full" />
              </td>
              <td className="px-4 py-3">
                <Skeleton className="h-4 w-28 font-mono" />
              </td>
              <td className="px-4 py-3">
                <Skeleton className="h-4 w-24" />
              </td>
              <td className="px-4 py-3">
                <div className="flex gap-2">
                  <Skeleton className="h-8 w-8 rounded" />
                  <Skeleton className="h-8 w-8 rounded" />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
