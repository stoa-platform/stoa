import { useState } from 'react';
import { X } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { backendApisService } from '../../services/backendApisApi';
import type { SaasApiKeyCreatedResponse } from '../../types';

interface CreateKeyModalProps {
  tenantId: string;
  onClose: () => void;
  onCreated: (result: SaasApiKeyCreatedResponse) => void;
}

export function CreateKeyModal({ tenantId, onClose, onCreated }: CreateKeyModalProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [selectedApiIds, setSelectedApiIds] = useState<string[]>([]);
  const [rateLimitRpm, setRateLimitRpm] = useState('');
  const [expiresAt, setExpiresAt] = useState('');

  const { data: backendApis } = useQuery({
    queryKey: ['backend-apis', tenantId],
    queryFn: () => backendApisService.listBackendApis(tenantId),
    enabled: !!tenantId,
  });

  const activeApis = (backendApis?.items || []).filter((api) => api.status === 'active');

  const toggleApi = (apiId: string) => {
    setSelectedApiIds((prev) =>
      prev.includes(apiId) ? prev.filter((id) => id !== apiId) : [...prev, apiId]
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const result = await backendApisService.createSaasKey(tenantId, {
        name,
        description: description || undefined,
        allowed_backend_api_ids: selectedApiIds,
        rate_limit_rpm: rateLimitRpm ? parseInt(rateLimitRpm, 10) : undefined,
        expires_at: expiresAt || undefined,
      });
      onCreated(result);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to create API key';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-xl w-full max-w-lg max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex justify-between items-center px-6 py-4 border-b dark:border-neutral-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Create API Key</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-neutral-300"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-5">
          {error && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg text-sm">
              {error}
            </div>
          )}

          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1">
              Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full border border-gray-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500"
              placeholder="my-api-key"
              required
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1">
              Description
            </label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full border border-gray-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500"
              placeholder="Key for production use"
            />
          </div>

          {/* Allowed Backend APIs */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1">
              Allowed Backend APIs
            </label>
            {activeApis.length === 0 ? (
              <p className="text-sm text-gray-500 dark:text-neutral-400">
                No active backend APIs available. Register and activate an API first.
              </p>
            ) : (
              <div className="space-y-2 max-h-40 overflow-y-auto border border-gray-200 dark:border-neutral-600 rounded-lg p-3">
                {activeApis.map((api) => (
                  <label key={api.id} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedApiIds.includes(api.id)}
                      onChange={() => toggleApi(api.id)}
                      className="rounded border-gray-300 dark:border-neutral-600"
                    />
                    <span className="text-sm text-gray-700 dark:text-neutral-300">
                      {api.display_name || api.name}
                    </span>
                  </label>
                ))}
              </div>
            )}
            <p className="text-xs text-gray-500 dark:text-neutral-400 mt-1">
              Leave empty to allow access to all APIs.
            </p>
          </div>

          {/* Rate Limit */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1">
              Rate Limit (requests/min)
            </label>
            <input
              type="number"
              value={rateLimitRpm}
              onChange={(e) => setRateLimitRpm(e.target.value)}
              className="w-full border border-gray-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500"
              placeholder="No limit"
              min="1"
            />
          </div>

          {/* Expires At */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1">
              Expiration Date
            </label>
            <input
              type="date"
              value={expiresAt}
              onChange={(e) => setExpiresAt(e.target.value)}
              className="w-full border border-gray-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500"
              min={new Date().toISOString().split('T')[0]}
            />
            <p className="text-xs text-gray-500 dark:text-neutral-400 mt-1">
              Leave empty for no expiration.
            </p>
          </div>
        </form>

        {/* Footer */}
        <div className="flex justify-end gap-3 px-6 py-4 border-t dark:border-neutral-700 bg-gray-50 dark:bg-neutral-800">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 border border-gray-300 dark:border-neutral-600 rounded-lg hover:bg-white dark:hover:bg-neutral-700 dark:text-neutral-300"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={loading}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? 'Creating...' : 'Create Key'}
          </button>
        </div>
      </div>
    </div>
  );
}
