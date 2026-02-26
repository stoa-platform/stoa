/**
 * Audit Log Viewer (CAB-1470)
 */

import { useState } from 'react';
import { FileText, Search, Filter } from 'lucide-react';
import { useAuditLog } from '../../hooks/useAuditLog';
import { useAuth } from '../../contexts/AuthContext';
import type { AuditLogFilters, AuditAction } from '../../types';

const ACTIONS: { value: AuditAction | ''; label: string }[] = [
  { value: '', label: 'All actions' },
  { value: 'api.subscribed', label: 'API Subscribed' },
  { value: 'api.unsubscribed', label: 'API Unsubscribed' },
  { value: 'key.created', label: 'Key Created' },
  { value: 'key.rotated', label: 'Key Rotated' },
  { value: 'key.revoked', label: 'Key Revoked' },
  { value: 'app.created', label: 'App Created' },
  { value: 'app.updated', label: 'App Updated' },
  { value: 'app.deleted', label: 'App Deleted' },
  { value: 'login', label: 'Login' },
  { value: 'logout', label: 'Logout' },
];

export function AuditLogPage() {
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const [filters, setFilters] = useState<AuditLogFilters>({ page: 1, limit: 25 });
  const [searchInput, setSearchInput] = useState('');
  const { data, isLoading } = useAuditLog(filters);

  if (authLoading || !isAuthenticated) {
    return null;
  }

  const entries = data?.entries ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / (filters.limit ?? 25));

  const handleSearch = () => {
    setFilters((prev) => ({ ...prev, search: searchInput || undefined, page: 1 }));
  };

  return (
    <div className="min-h-screen bg-neutral-50 dark:bg-neutral-900">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <FileText className="w-6 h-6 text-neutral-700 dark:text-neutral-200" />
          <div>
            <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Audit Log</h1>
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              Activity history for your account
            </p>
          </div>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap gap-3 mb-6">
          <div className="relative flex-1 min-w-[200px] max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400" />
            <input
              type="text"
              placeholder="Search by resource or actor..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              className="w-full pl-10 pr-4 py-2 text-sm bg-white dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-neutral-900 dark:text-white placeholder-neutral-400"
            />
          </div>
          <div className="relative">
            <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400" />
            <select
              value={filters.action ?? ''}
              onChange={(e) =>
                setFilters((prev) => ({
                  ...prev,
                  action: (e.target.value || undefined) as AuditAction | undefined,
                  page: 1,
                }))
              }
              className="pl-10 pr-8 py-2 text-sm bg-white dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 rounded-lg focus:ring-2 focus:ring-primary-500 text-neutral-900 dark:text-white appearance-none"
            >
              {ACTIONS.map((a) => (
                <option key={a.value} value={a.value}>
                  {a.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Table */}
        <div className="bg-white dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800">
                  <th className="text-left px-4 py-3 font-medium text-neutral-500 dark:text-neutral-400">
                    Timestamp
                  </th>
                  <th className="text-left px-4 py-3 font-medium text-neutral-500 dark:text-neutral-400">
                    Action
                  </th>
                  <th className="text-left px-4 py-3 font-medium text-neutral-500 dark:text-neutral-400">
                    Resource
                  </th>
                  <th className="text-left px-4 py-3 font-medium text-neutral-500 dark:text-neutral-400">
                    Actor
                  </th>
                  <th className="text-left px-4 py-3 font-medium text-neutral-500 dark:text-neutral-400">
                    Details
                  </th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-neutral-400">
                      Loading audit log...
                    </td>
                  </tr>
                ) : entries.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-neutral-400">
                      No audit log entries found
                    </td>
                  </tr>
                ) : (
                  entries.map((entry) => (
                    <tr
                      key={entry.id}
                      className="border-b border-neutral-100 dark:border-neutral-700 hover:bg-neutral-50 dark:hover:bg-neutral-750"
                    >
                      <td className="px-4 py-3 text-neutral-600 dark:text-neutral-300 whitespace-nowrap">
                        {new Date(entry.timestamp).toLocaleString()}
                      </td>
                      <td className="px-4 py-3">
                        <span className="inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full bg-neutral-100 dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300">
                          {entry.action}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-neutral-900 dark:text-white">
                        {entry.resource_name}
                        <span className="text-neutral-400 ml-1 text-xs">
                          ({entry.resource_type})
                        </span>
                      </td>
                      <td className="px-4 py-3 text-neutral-600 dark:text-neutral-300">
                        {entry.actor_name}
                      </td>
                      <td className="px-4 py-3 text-neutral-500 dark:text-neutral-400 max-w-xs truncate">
                        {entry.details}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between px-4 py-3 border-t border-neutral-200 dark:border-neutral-700">
              <span className="text-sm text-neutral-500 dark:text-neutral-400">
                Page {filters.page ?? 1} of {totalPages} ({total} entries)
              </span>
              <div className="flex gap-2">
                <button
                  onClick={() => setFilters((p) => ({ ...p, page: (p.page ?? 1) - 1 }))}
                  disabled={(filters.page ?? 1) <= 1}
                  className="px-3 py-1 text-sm rounded border border-neutral-300 dark:border-neutral-600 disabled:opacity-50 hover:bg-neutral-100 dark:hover:bg-neutral-700 text-neutral-700 dark:text-neutral-200"
                >
                  Previous
                </button>
                <button
                  onClick={() => setFilters((p) => ({ ...p, page: (p.page ?? 1) + 1 }))}
                  disabled={(filters.page ?? 1) >= totalPages}
                  className="px-3 py-1 text-sm rounded border border-neutral-300 dark:border-neutral-600 disabled:opacity-50 hover:bg-neutral-100 dark:hover:bg-neutral-700 text-neutral-700 dark:text-neutral-200"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default AuditLogPage;
