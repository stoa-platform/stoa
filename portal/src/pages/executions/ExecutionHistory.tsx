/**
 * Execution History Page — Portal read-only consumer view (CAB-1318)
 *
 * Shows execution logs, error breakdown, and status filtering.
 */

import { useState } from 'react';
import { useExecutions, useExecutionTaxonomy } from '../../hooks/useExecutions';

const STATUS_COLORS: Record<string, string> = {
  success: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  error: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  timeout: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
};

const CATEGORY_LABELS: Record<string, string> = {
  auth: 'Auth',
  rate_limit: 'Rate Limit',
  backend: 'Backend',
  timeout: 'Timeout',
  validation: 'Validation',
};

export function ExecutionHistoryPage() {
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string>('');

  const { data: executions, isLoading } = useExecutions({
    page,
    page_size: 20,
    status: statusFilter || undefined,
  });
  const { data: taxonomy } = useExecutionTaxonomy();

  const totalPages = executions ? Math.ceil(executions.total / executions.page_size) : 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">My Execution History</h1>
        <p className="text-neutral-500 dark:text-neutral-400 mt-1">
          View your API call history and error patterns
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none p-4">
          <p className="text-sm text-neutral-500 dark:text-neutral-400">Total Calls</p>
          <p className="text-2xl font-bold text-neutral-900 dark:text-white">
            {taxonomy?.total_executions ?? 0}
          </p>
        </div>
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none p-4">
          <p className="text-sm text-neutral-500 dark:text-neutral-400">Errors</p>
          <p className="text-2xl font-bold text-red-600">{taxonomy?.total_errors ?? 0}</p>
        </div>
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none p-4">
          <p className="text-sm text-neutral-500 dark:text-neutral-400">Error Breakdown</p>
          <div className="flex flex-wrap gap-2 mt-1">
            {taxonomy?.items.map((item) => (
              <span
                key={item.category}
                className="text-xs bg-neutral-100 dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300 px-2 py-0.5 rounded"
              >
                {CATEGORY_LABELS[item.category] || item.category}: {item.count}
              </span>
            )) ?? <span className="text-xs text-neutral-400 dark:text-neutral-500">No errors</span>}
          </div>
        </div>
      </div>

      {/* Filter */}
      <div className="flex gap-4">
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
          className="rounded-md border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 text-sm px-3 py-2 text-neutral-900 dark:text-white"
          aria-label="Filter by status"
        >
          <option value="">All Statuses</option>
          <option value="success">Success</option>
          <option value="error">Error</option>
          <option value="timeout">Timeout</option>
        </select>
      </div>

      {/* Executions Table */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none overflow-hidden">
        {isLoading ? (
          <div className="p-8 text-center text-neutral-500 dark:text-neutral-400">Loading...</div>
        ) : !executions || executions.items.length === 0 ? (
          <div className="p-8 text-center text-neutral-500 dark:text-neutral-400">
            No executions found
          </div>
        ) : (
          <table className="min-w-full divide-y divide-neutral-200 dark:divide-neutral-700">
            <thead className="bg-neutral-50 dark:bg-neutral-900">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                  Time
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                  API / Tool
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                  Duration
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                  Error
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-200 dark:divide-neutral-700">
              {executions.items.map((exec) => (
                <tr key={exec.id}>
                  <td className="px-4 py-3 text-sm text-neutral-900 dark:text-white whitespace-nowrap">
                    {new Date(exec.started_at).toLocaleTimeString()}
                  </td>
                  <td className="px-4 py-3 text-sm text-neutral-900 dark:text-white">
                    {exec.api_name || exec.tool_name || exec.path || '—'}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex px-2 py-0.5 text-xs font-medium rounded-full ${STATUS_COLORS[exec.status] || ''}`}
                    >
                      {exec.status_code ?? exec.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-neutral-500 dark:text-neutral-400">
                    {exec.duration_ms != null ? `${exec.duration_ms}ms` : '—'}
                  </td>
                  <td className="px-4 py-3 text-sm text-neutral-500 dark:text-neutral-400">
                    {exec.error_category
                      ? CATEGORY_LABELS[exec.error_category] || exec.error_category
                      : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="px-4 py-3 border-t border-neutral-200 dark:border-neutral-700 flex items-center justify-between">
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              Page {page} of {totalPages} ({executions?.total ?? 0} total)
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="px-3 py-1 text-sm rounded border border-neutral-300 dark:border-neutral-600 disabled:opacity-50"
              >
                Previous
              </button>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="px-3 py-1 text-sm rounded border border-neutral-300 dark:border-neutral-600 disabled:opacity-50"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
