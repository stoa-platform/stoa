/**
 * Advanced API Comparison (CAB-1470)
 */

import { useState } from 'react';
import { GitCompareArrows, Plus, X, Search } from 'lucide-react';
import { useAPIComparison } from '../../hooks/useAPIComparison';
import { useAuth } from '../../contexts/AuthContext';

export function APIComparePage() {
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [inputValue, setInputValue] = useState('');
  const { data, isLoading, isFetching } = useAPIComparison(selectedIds);

  if (authLoading || !isAuthenticated) {
    return null;
  }

  const addApiId = () => {
    const trimmed = inputValue.trim();
    if (trimmed && !selectedIds.includes(trimmed) && selectedIds.length < 5) {
      setSelectedIds([...selectedIds, trimmed]);
      setInputValue('');
    }
  };

  const removeApiId = (id: string) => {
    setSelectedIds(selectedIds.filter((x) => x !== id));
  };

  const fields = data?.fields ?? [];
  const apiNames = data?.api_names ?? {};

  return (
    <div className="min-h-screen bg-neutral-50 dark:bg-neutral-900">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <GitCompareArrows className="w-6 h-6 text-neutral-700 dark:text-neutral-200" />
          <div>
            <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Compare APIs</h1>
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              Side-by-side comparison of API capabilities
            </p>
          </div>
        </div>

        {/* API selector */}
        <div className="bg-white dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700 p-4 mb-6">
          <div className="flex flex-wrap gap-2 mb-3">
            {selectedIds.map((id) => (
              <span
                key={id}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-300 rounded-lg border border-primary-200 dark:border-primary-700"
              >
                {apiNames[id] || id}
                <button onClick={() => removeApiId(id)} className="hover:text-red-500">
                  <X className="w-3.5 h-3.5" />
                </button>
              </span>
            ))}
          </div>
          <div className="flex gap-2">
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400" />
              <input
                type="text"
                placeholder="Enter API ID to compare..."
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && addApiId()}
                disabled={selectedIds.length >= 5}
                className="w-full pl-10 pr-4 py-2 text-sm bg-white dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 rounded-lg focus:ring-2 focus:ring-primary-500 text-neutral-900 dark:text-white placeholder-neutral-400 disabled:opacity-50"
              />
            </div>
            <button
              onClick={addApiId}
              disabled={!inputValue.trim() || selectedIds.length >= 5}
              className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50"
            >
              <Plus className="w-4 h-4" />
              Add
            </button>
          </div>
          <p className="text-xs text-neutral-400 mt-2">
            Select 2-5 APIs to compare. {selectedIds.length}/5 selected.
          </p>
        </div>

        {/* Comparison table */}
        {selectedIds.length >= 2 && (
          <div className="bg-white dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700 overflow-hidden">
            {isLoading || isFetching ? (
              <div className="p-8 text-center text-neutral-400">Comparing APIs...</div>
            ) : fields.length === 0 ? (
              <div className="p-8 text-center text-neutral-400">No comparison data available</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800">
                      <th className="text-left px-4 py-3 font-medium text-neutral-500 dark:text-neutral-400 sticky left-0 bg-neutral-50 dark:bg-neutral-800">
                        Feature
                      </th>
                      {selectedIds.map((id) => (
                        <th
                          key={id}
                          className="text-left px-4 py-3 font-medium text-neutral-700 dark:text-neutral-200 min-w-[150px]"
                        >
                          {apiNames[id] || id}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {fields.map((field, i) => (
                      <tr key={i} className="border-b border-neutral-100 dark:border-neutral-700">
                        <td className="px-4 py-3 font-medium text-neutral-900 dark:text-white sticky left-0 bg-white dark:bg-neutral-800">
                          {field.label}
                        </td>
                        {selectedIds.map((id) => {
                          const val = field.values[id];
                          if (typeof val === 'boolean') {
                            return (
                              <td key={id} className="px-4 py-3 text-center">
                                {val ? (
                                  <span className="text-emerald-500">Yes</span>
                                ) : (
                                  <span className="text-neutral-400">No</span>
                                )}
                              </td>
                            );
                          }
                          return (
                            <td
                              key={id}
                              className="px-4 py-3 text-neutral-600 dark:text-neutral-300"
                            >
                              {val ?? '—'}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {selectedIds.length < 2 && (
          <div className="text-center py-16">
            <GitCompareArrows className="w-12 h-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-4" />
            <h2 className="text-lg font-medium text-neutral-600 dark:text-neutral-300">
              Select at least 2 APIs to compare
            </h2>
            <p className="text-sm text-neutral-400 mt-1">
              Add API IDs above to see a side-by-side feature comparison
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

export default APIComparePage;
