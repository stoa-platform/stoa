/**
 * Execution View Dashboard — Consumer execution view + error taxonomy (CAB-1318)
 *
 * Admin dashboard showing execution logs with filtering, error taxonomy chart,
 * and drill-down detail modal.
 */

import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { apiService } from '../../services/api';
import { ErrorTaxonomyChart } from './ErrorTaxonomyChart';
import { ExecutionDetailModal } from './ExecutionDetailModal';

interface ExecutionSummary {
  id: string;
  api_name: string | null;
  tool_name: string | null;
  request_id: string;
  method: string | null;
  path: string | null;
  status_code: number | null;
  status: 'success' | 'error' | 'timeout';
  error_category: string | null;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
}

interface ExecutionDetail extends ExecutionSummary {
  tenant_id: string;
  consumer_id: string | null;
  api_id: string | null;
  request_headers: Record<string, unknown> | null;
  response_summary: Record<string, unknown> | null;
}

interface ExecutionListResponse {
  items: ExecutionSummary[];
  total: number;
  page: number;
  page_size: number;
}

interface TaxonomyItem {
  category: string;
  count: number;
  avg_duration_ms: number | null;
  percentage: number;
}

interface TaxonomyResponse {
  items: TaxonomyItem[];
  total_errors: number;
  total_executions: number;
  error_rate: number;
}

const STATUS_COLORS: Record<string, string> = {
  success: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  error: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  timeout: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
};

export function ExecutionViewDashboard() {
  const { user } = useAuth();
  const tenantId = user?.tenant_id;
  const [executions, setExecutions] = useState<ExecutionSummary[]>([]);
  const [taxonomy, setTaxonomy] = useState<TaxonomyResponse | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [categoryFilter, setCategoryFilter] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [selectedExecution, setSelectedExecution] = useState<ExecutionDetail | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const pageSize = 20;

  const fetchExecutions = useCallback(async () => {
    if (!tenantId) return;
    setLoading(true);
    try {
      const params: Record<string, string | number> = {
        page,
        page_size: pageSize,
      };
      if (statusFilter) params.status = statusFilter;
      if (categoryFilter) params.error_category = categoryFilter;

      const { data } = await apiService.get<ExecutionListResponse>(
        `/v1/tenants/${tenantId}/executions`,
        { params }
      );
      setExecutions(data.items);
      setTotal(data.total);
    } catch {
      setExecutions([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [tenantId, page, statusFilter, categoryFilter]);

  const fetchTaxonomy = useCallback(async () => {
    if (!tenantId) return;
    try {
      const { data } = await apiService.get<TaxonomyResponse>(
        `/v1/tenants/${tenantId}/executions/taxonomy`
      );
      setTaxonomy(data);
    } catch {
      setTaxonomy(null);
    }
  }, [tenantId]);

  useEffect(() => {
    fetchExecutions();
  }, [fetchExecutions]);

  useEffect(() => {
    fetchTaxonomy();
  }, [fetchTaxonomy]);

  const handleRowClick = async (execution: ExecutionSummary) => {
    if (!tenantId) return;
    try {
      const { data: detail } = await apiService.get<ExecutionDetail>(
        `/v1/tenants/${tenantId}/executions/${execution.id}`
      );
      setSelectedExecution(detail);
      setModalOpen(true);
    } catch {
      // Silently fail — user can retry
    }
  };

  const totalPages = Math.ceil(total / pageSize);
  const successCount = taxonomy ? taxonomy.total_executions - taxonomy.total_errors : 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Execution View</h1>
        <p className="text-neutral-500 dark:text-neutral-400 mt-1">
          Monitor API executions and error patterns
        </p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none p-4">
          <p className="text-sm text-neutral-500 dark:text-neutral-400">Total Calls</p>
          <p className="text-2xl font-bold text-neutral-900 dark:text-white">
            {taxonomy?.total_executions ?? 0}
          </p>
        </div>
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none p-4">
          <p className="text-sm text-neutral-500 dark:text-neutral-400">Success</p>
          <p className="text-2xl font-bold text-green-600">{successCount}</p>
        </div>
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none p-4">
          <p className="text-sm text-neutral-500 dark:text-neutral-400">Errors</p>
          <p className="text-2xl font-bold text-red-600">{taxonomy?.total_errors ?? 0}</p>
        </div>
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none p-4">
          <p className="text-sm text-neutral-500 dark:text-neutral-400">Error Rate</p>
          <p className="text-2xl font-bold text-neutral-900 dark:text-white">
            {taxonomy?.error_rate ?? 0}%
          </p>
        </div>
      </div>

      {/* Error Taxonomy Chart */}
      {taxonomy && taxonomy.items.length > 0 && (
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none p-6">
          <h2 className="text-lg font-semibold text-neutral-900 dark:text-white mb-4">
            Error Taxonomy
          </h2>
          <ErrorTaxonomyChart items={taxonomy.items} totalErrors={taxonomy.total_errors} />
        </div>
      )}

      {/* Filters */}
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
        <select
          value={categoryFilter}
          onChange={(e) => {
            setCategoryFilter(e.target.value);
            setPage(1);
          }}
          className="rounded-md border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 text-sm px-3 py-2 text-neutral-900 dark:text-white"
          aria-label="Filter by error category"
        >
          <option value="">All Categories</option>
          <option value="auth">Auth</option>
          <option value="rate_limit">Rate Limit</option>
          <option value="backend">Backend</option>
          <option value="timeout">Timeout</option>
          <option value="validation">Validation</option>
        </select>
      </div>

      {/* Executions Table */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-neutral-500 dark:text-neutral-400">Loading...</div>
        ) : executions.length === 0 ? (
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
                  Method
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
              {executions.map((exec) => (
                <tr
                  key={exec.id}
                  onClick={() => handleRowClick(exec)}
                  className="hover:bg-neutral-50 dark:hover:bg-neutral-700 cursor-pointer"
                >
                  <td className="px-4 py-3 text-sm text-neutral-900 dark:text-white whitespace-nowrap">
                    {new Date(exec.started_at).toLocaleTimeString()}
                  </td>
                  <td className="px-4 py-3 text-sm text-neutral-900 dark:text-white">
                    {exec.api_name || exec.tool_name || exec.path || '—'}
                  </td>
                  <td className="px-4 py-3 text-sm text-neutral-500 dark:text-neutral-400">
                    {exec.method || '—'}
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
                    {exec.error_category || '—'}
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
              Page {page} of {totalPages} ({total} total)
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

      {/* Detail Modal */}
      {modalOpen && selectedExecution && (
        <ExecutionDetailModal
          execution={selectedExecution}
          onClose={() => {
            setModalOpen(false);
            setSelectedExecution(null);
          }}
        />
      )}
    </div>
  );
}
