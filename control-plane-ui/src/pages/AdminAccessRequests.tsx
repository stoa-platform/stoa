/**
 * Admin Access Requests Page (CAB-1468)
 *
 * Read-only table view of portal enterprise access requests.
 * cpi-admin only. Status filter + pagination.
 */
import { useState, useCallback, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useAccessRequests } from '../hooks/useAccessRequests';
import type { AccessRequestStatus } from '../types';
import { AlertTriangle, ChevronLeft, ChevronRight, Mail } from 'lucide-react';

const PAGE_SIZE = 25;

const statusColors: Record<AccessRequestStatus, { bg: string; text: string; dot: string }> = {
  pending: {
    bg: 'bg-amber-100 dark:bg-amber-900/30',
    text: 'text-amber-800 dark:text-amber-400',
    dot: 'bg-amber-500',
  },
  contacted: {
    bg: 'bg-blue-100 dark:bg-blue-900/30',
    text: 'text-blue-800 dark:text-blue-400',
    dot: 'bg-blue-500',
  },
  converted: {
    bg: 'bg-green-100 dark:bg-green-900/30',
    text: 'text-green-800 dark:text-green-400',
    dot: 'bg-green-500',
  },
};

function formatDate(date: string | undefined | null): string {
  if (!date) return '\u2014';
  return new Date(date).toLocaleDateString('fr-FR', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function AdminAccessRequests() {
  const { hasRole } = useAuth();
  const [statusFilter, setStatusFilter] = useState<AccessRequestStatus | ''>('');
  const [page, setPage] = useState(1);

  const {
    data: requestsData,
    isLoading,
    error,
  } = useAccessRequests(
    { status: statusFilter || undefined, page, limit: PAGE_SIZE },
    { enabled: hasRole('cpi-admin') }
  );

  useEffect(() => {
    setPage(1);
  }, [statusFilter]);

  const handleStatusChange = useCallback((value: AccessRequestStatus | '') => {
    setStatusFilter(value);
  }, []);

  if (!hasRole('cpi-admin')) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <AlertTriangle className="h-12 w-12 text-red-500 mx-auto mb-4" />
          <h1 className="text-xl font-semibold text-neutral-900 dark:text-white mb-2">
            Access Denied
          </h1>
          <p className="text-neutral-600 dark:text-neutral-400">
            Platform admin role required to view this page.
          </p>
        </div>
      </div>
    );
  }

  const totalPages = requestsData ? Math.ceil(requestsData.total / PAGE_SIZE) : 0;

  return (
    <div className="min-h-screen bg-neutral-50 dark:bg-neutral-900 p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Access Requests</h1>
            <p className="text-neutral-500 dark:text-neutral-400 mt-1">
              Enterprise access requests from the Developer Portal
            </p>
          </div>
          {requestsData && (
            <span className="text-sm text-neutral-500 dark:text-neutral-400">
              {requestsData.total} total request{requestsData.total !== 1 ? 's' : ''}
            </span>
          )}
        </div>

        {/* Filters */}
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4">
          <div className="flex items-center gap-4">
            <label className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
              Status
            </label>
            <select
              value={statusFilter}
              onChange={(e) => handleStatusChange(e.target.value as AccessRequestStatus | '')}
              className="rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="">All statuses</option>
              <option value="pending">Pending</option>
              <option value="contacted">Contacted</option>
              <option value="converted">Converted</option>
            </select>
          </div>
        </div>

        {/* Error state */}
        {error && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
            <p className="text-sm text-red-700 dark:text-red-400">
              Failed to load access requests. Please try again.
            </p>
          </div>
        )}

        {/* Table */}
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 overflow-hidden">
          {isLoading ? (
            <div className="flex items-center justify-center p-12">
              <div className="animate-spin rounded-full h-8 w-8 border-2 border-blue-600 border-t-transparent" />
            </div>
          ) : !requestsData?.data.length ? (
            <div className="flex flex-col items-center justify-center p-12 text-neutral-500 dark:text-neutral-400">
              <Mail className="h-10 w-10 mb-3 opacity-50" />
              <p className="text-sm">No access requests found</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-neutral-200 dark:divide-neutral-700">
                <thead className="bg-neutral-50 dark:bg-neutral-800/50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                      Email
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                      Name
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                      Company
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                      Role
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                      Source
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                      Date
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-200 dark:divide-neutral-700">
                  {requestsData.data.map((req) => {
                    const colors = statusColors[req.status] || statusColors.pending;
                    return (
                      <tr
                        key={req.id}
                        className="hover:bg-neutral-50 dark:hover:bg-neutral-700/50 transition-colors"
                      >
                        <td className="px-4 py-3 text-sm font-medium text-neutral-900 dark:text-white">
                          {req.email}
                        </td>
                        <td className="px-4 py-3 text-sm text-neutral-600 dark:text-neutral-300">
                          {[req.first_name, req.last_name].filter(Boolean).join(' ') || '\u2014'}
                        </td>
                        <td className="px-4 py-3 text-sm text-neutral-600 dark:text-neutral-300">
                          {req.company || '\u2014'}
                        </td>
                        <td className="px-4 py-3 text-sm text-neutral-600 dark:text-neutral-300">
                          {req.role || '\u2014'}
                        </td>
                        <td className="px-4 py-3 text-sm text-neutral-600 dark:text-neutral-300">
                          {req.source || '\u2014'}
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium ${colors.bg} ${colors.text}`}
                          >
                            <span className={`h-1.5 w-1.5 rounded-full ${colors.dot}`} />
                            {req.status}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-sm text-neutral-500 dark:text-neutral-400">
                          {formatDate(req.created_at)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between px-4 py-3 border-t border-neutral-200 dark:border-neutral-700">
              <p className="text-sm text-neutral-600 dark:text-neutral-400">
                Page {page} of {totalPages}
              </p>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="p-1.5 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  <ChevronLeft className="h-4 w-4 text-neutral-600 dark:text-neutral-400" />
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="p-1.5 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  <ChevronRight className="h-4 w-4 text-neutral-600 dark:text-neutral-400" />
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
