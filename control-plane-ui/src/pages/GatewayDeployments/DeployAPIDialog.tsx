import { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import { apiService } from '../../services/api';

interface CatalogEntry {
  id: string;
  api_name: string;
  tenant_id: string;
  version: string;
}

interface GatewayOption {
  id: string;
  name: string;
  display_name: string;
  gateway_type: string;
  environment: string;
}

interface DeployAPIDialogProps {
  onClose: () => void;
  onDeployed: () => void;
}

export function DeployAPIDialog({ onClose, onDeployed }: DeployAPIDialogProps) {
  const [catalogEntries, setCatalogEntries] = useState<CatalogEntry[]>([]);
  const [gateways, setGateways] = useState<GatewayOption[]>([]);
  const [selectedApi, setSelectedApi] = useState('');
  const [selectedGateways, setSelectedGateways] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        const [entries, gwResult] = await Promise.all([
          apiService.getCatalogEntries(),
          apiService.getGatewayInstances({ page_size: 100 }),
        ]);
        setCatalogEntries(entries);
        setGateways(gwResult.items);
      } catch (err: any) {
        setError(err.response?.data?.detail || 'Failed to load data');
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  const toggleGateway = (id: string) => {
    setSelectedGateways((prev) =>
      prev.includes(id) ? prev.filter((g) => g !== id) : [...prev, id]
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedApi || selectedGateways.length === 0) return;

    setSubmitting(true);
    setError(null);

    try {
      await apiService.deployApiToGateways({
        api_catalog_id: selectedApi,
        gateway_instance_ids: selectedGateways,
      });
      onDeployed();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to deploy API');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl mx-4">
        {/* Header */}
        <div className="flex items-center justify-between border-b px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">Deploy API to Gateways</h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
              {error}
            </div>
          )}

          {loading ? (
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <div className="h-4 w-32 bg-gray-200 rounded animate-pulse" />
                <div className="h-10 w-full bg-gray-200 rounded animate-pulse" />
              </div>
              <div className="space-y-2">
                <div className="h-4 w-28 bg-gray-200 rounded animate-pulse" />
                <div className="h-32 w-full bg-gray-200 rounded animate-pulse" />
              </div>
            </div>
          ) : (
            <>
              {/* API Selection */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  API Catalog Entry
                </label>
                <select
                  value={selectedApi}
                  onChange={(e) => setSelectedApi(e.target.value)}
                  required
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="">Select an API...</option>
                  {catalogEntries.map((entry) => (
                    <option key={entry.id} value={entry.id}>
                      {entry.api_name} v{entry.version} ({entry.tenant_id})
                    </option>
                  ))}
                </select>
              </div>

              {/* Gateway Multi-Select */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Target Gateways
                </label>
                {gateways.length === 0 ? (
                  <p className="text-sm text-gray-500">
                    No gateways registered. Register a gateway first.
                  </p>
                ) : (
                  <div className="space-y-2 max-h-48 overflow-y-auto border border-gray-200 rounded-lg p-3">
                    {gateways.map((gw) => (
                      <label
                        key={gw.id}
                        className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 cursor-pointer"
                      >
                        <input
                          type="checkbox"
                          checked={selectedGateways.includes(gw.id)}
                          onChange={() => toggleGateway(gw.id)}
                          className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                        />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-gray-900">
                            {gw.display_name}
                          </p>
                          <p className="text-xs text-gray-500">
                            {gw.gateway_type} &middot; {gw.environment}
                          </p>
                        </div>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-2 border-t">
            <button
              type="button"
              onClick={onClose}
              className="border border-gray-300 text-gray-700 px-4 py-2 rounded-lg text-sm hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || !selectedApi || selectedGateways.length === 0}
              className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50"
            >
              {submitting ? 'Deploying...' : 'Deploy'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
