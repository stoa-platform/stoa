import { useState, useEffect, useCallback } from 'react';
import {
  RefreshCw,
  Shield,
  CheckCircle,
  XCircle,
  Clock,
  AlertTriangle,
  UserCheck,
  UserX,
  Flag,
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { apiService } from '../../services/api';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import { StatCard } from '@stoa/shared/components/StatCard';

const ACTIVE_TENANT_KEY = 'stoa-active-tenant';

interface OAuthClient {
  id: string;
  tenant_id: string;
  keycloak_client_id: string;
  client_name: string;
  description: string | null;
  product_roles: string[] | null;
  status: 'active' | 'revoked' | 'expired' | 'pending_review';
  created_at: string;
  updated_at: string;
}

interface ClientListResponse {
  items: OAuthClient[];
  total: number;
  page: number;
  page_size: number;
}

export function AccessReviewDashboard() {
  const { user, hasPermission } = useAuth();
  const [clients, setClients] = useState<OAuthClient[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const tenantId = sessionStorage.getItem(ACTIVE_TENANT_KEY) || user?.tenant_id || '';
  const canManageClients = hasPermission('admin:servers');

  const fetchClients = useCallback(async () => {
    try {
      const response = await apiService.get<ClientListResponse>(
        `/v1/tenants/${tenantId}/oauth-clients`
      );
      setClients(response.data.items);
    } catch {
      setClients([]);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [tenantId]);

  useEffect(() => {
    fetchClients();
  }, [fetchClients]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchClients();
  };

  const activeCount = clients.filter((c) => c.status === 'active').length;
  const revokedCount = clients.filter((c) => c.status === 'revoked').length;
  const pendingCount = clients.filter((c) => c.status === 'pending_review').length;

  if (loading) {
    return (
      <div className="space-y-6 p-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
          {[...Array(4)].map((_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Access Review</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Review and manage OAuth client access for tenant{' '}
            <span className="font-medium">{tenantId}</span>
          </p>
        </div>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
          data-testid="refresh-btn"
        >
          <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-4" data-testid="summary-cards">
        <StatCard label="Total Clients" value={clients.length} icon={Shield} />
        <StatCard
          label="Active"
          value={activeCount}
          icon={CheckCircle}
          colorClass="text-green-500"
        />
        <StatCard label="Revoked" value={revokedCount} icon={XCircle} colorClass="text-red-500" />
        <StatCard
          label="Pending Review"
          value={pendingCount}
          icon={AlertTriangle}
          colorClass="text-yellow-500"
        />
      </div>

      {/* Clients Table */}
      <div className="overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700">
        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                Client Name
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                Roles
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                Last Updated
              </th>
              {canManageClients && (
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                  Actions
                </th>
              )}
            </tr>
          </thead>
          <tbody
            className="divide-y divide-gray-200 bg-white dark:divide-gray-700 dark:bg-gray-900"
            data-testid="clients-table-body"
          >
            {clients.length === 0 ? (
              <tr>
                <td
                  colSpan={canManageClients ? 5 : 4}
                  className="px-6 py-8 text-center text-sm text-gray-500 dark:text-gray-400"
                >
                  No OAuth clients found for this tenant.
                </td>
              </tr>
            ) : (
              clients.map((client) => (
                <tr key={client.id} data-testid={`client-row-${client.id}`}>
                  <td className="whitespace-nowrap px-6 py-4">
                    <div className="text-sm font-medium text-gray-900 dark:text-white">
                      {client.client_name}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      {client.keycloak_client_id}
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-6 py-4">
                    <StatusBadge status={client.status} />
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex flex-wrap gap-1">
                      {(client.product_roles || []).map((role) => (
                        <span
                          key={role}
                          className="inline-flex rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-800 dark:bg-blue-900 dark:text-blue-200"
                        >
                          {role}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500 dark:text-gray-400">
                    {new Date(client.updated_at).toLocaleDateString()}
                  </td>
                  {canManageClients && (
                    <td className="whitespace-nowrap px-6 py-4">
                      <div className="flex gap-2">
                        {client.status === 'pending_review' && (
                          <button
                            className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-green-700 hover:bg-green-50 dark:text-green-400 dark:hover:bg-green-900/20"
                            data-testid={`approve-${client.id}`}
                          >
                            <UserCheck className="h-3 w-3" />
                            Approve
                          </button>
                        )}
                        {client.status === 'active' && (
                          <button
                            className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20"
                            data-testid={`revoke-${client.id}`}
                          >
                            <UserX className="h-3 w-3" />
                            Revoke
                          </button>
                        )}
                        <button
                          className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-yellow-700 hover:bg-yellow-50 dark:text-yellow-400 dark:hover:bg-yellow-900/20"
                          data-testid={`flag-${client.id}`}
                        >
                          <Flag className="h-3 w-3" />
                          Flag
                        </button>
                      </div>
                    </td>
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { color: string; icon: React.ReactNode }> = {
    active: {
      color: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
      icon: <CheckCircle className="h-3 w-3" />,
    },
    revoked: {
      color: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
      icon: <XCircle className="h-3 w-3" />,
    },
    expired: {
      color: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
      icon: <Clock className="h-3 w-3" />,
    },
    pending_review: {
      color: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
      icon: <AlertTriangle className="h-3 w-3" />,
    },
  };
  const { color, icon } = config[status] || config.active;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${color}`}
      data-testid={`status-badge-${status}`}
    >
      {icon}
      {status.replace('_', ' ')}
    </span>
  );
}
