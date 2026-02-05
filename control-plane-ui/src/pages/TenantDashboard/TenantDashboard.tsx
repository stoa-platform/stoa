import { useEffect, useState } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { apiService } from '../../services/api';
import { BarChart3, ExternalLink, RefreshCw } from 'lucide-react';

interface DashboardInfo {
  url: string;
  tier: string;
  tenant_id: string;
}

export function TenantDashboard() {
  const { user } = useAuth();
  const [dashboard, setDashboard] = useState<DashboardInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const tenantId = user?.tenant_id;

  useEffect(() => {
    if (!tenantId) {
      setLoading(false);
      setError('No tenant associated with your account.');
      return;
    }

    async function fetchDashboardUrl() {
      try {
        setLoading(true);
        const data = await apiService.getTenantDashboardUrl(tenantId!);
        setDashboard(data);
        setError(null);
      } catch (err: any) {
        console.error('Failed to load tenant dashboard:', err);
        setError(
          err?.response?.status === 404
            ? 'Dashboard not provisioned for your tenant yet. Contact your administrator.'
            : 'Failed to load observability dashboard.'
        );
      } finally {
        setLoading(false);
      }
    }

    fetchDashboardUrl();
  }, [tenantId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (error || !dashboard) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Tenant Observability</h1>
            <p className="text-gray-500 mt-1">Metrics, SLOs, and traces for your tenant</p>
          </div>
        </div>
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6 text-center">
          <BarChart3 className="h-12 w-12 text-yellow-500 mx-auto mb-3" />
          <p className="text-yellow-800 font-medium">{error || 'Dashboard unavailable'}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Tenant Observability</h1>
          <p className="text-gray-500 mt-1">
            Metrics and SLO dashboard for <span className="font-medium">{dashboard.tenant_id}</span>
            {dashboard.tier && (
              <span className="ml-2 inline-flex items-center rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-medium text-blue-800">
                {dashboard.tier}
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => window.location.reload()}
            className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
          <a
            href={dashboard.url.replace('&kiosk', '')}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            <ExternalLink className="h-4 w-4" />
            Open in Grafana
          </a>
        </div>
      </div>

      {/* Embedded Grafana iframe */}
      <div className="bg-white rounded-lg shadow overflow-hidden" style={{ height: 'calc(100vh - 200px)' }}>
        <iframe
          src={dashboard.url}
          title="Tenant Observability Dashboard"
          className="w-full h-full border-0"
          sandbox="allow-scripts allow-same-origin allow-popups"
        />
      </div>
    </div>
  );
}
