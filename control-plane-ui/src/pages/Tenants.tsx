import { useQuery } from '@tanstack/react-query';
import { apiService } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { EmptyState } from '@stoa/shared/components/EmptyState';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import { Users } from 'lucide-react';

export function Tenants() {
  const { isReady } = useAuth();

  const {
    data: tenants = [],
    isLoading: loading,
    error,
  } = useQuery({
    queryKey: ['tenants'],
    queryFn: () => apiService.getTenants(),
    enabled: isReady,
  });

  const statusColors: Record<string, string> = {
    active: 'bg-green-100 text-green-800',
    suspended: 'bg-red-100 text-red-800',
    pending: 'bg-yellow-100 text-yellow-800',
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3].map((i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Tenants</h1>
          <p className="text-gray-500 mt-1">View tenant organizations</p>
        </div>
        <div className="text-sm text-gray-500 bg-gray-100 px-3 py-2 rounded-lg">
          Tenant management via GitOps (Phase 2)
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error.message || 'Failed to load tenants'}
        </div>
      )}

      {/* Tenants Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {tenants.length === 0 ? (
          <div className="col-span-full bg-white rounded-lg shadow">
            <EmptyState
              variant="users"
              title="No tenants found"
              description="Tenants are managed via GitOps configuration in the iam/tenants.yaml file."
              illustration={
                <div className="w-24 h-24 rounded-2xl bg-gradient-to-br from-purple-50 to-purple-100 flex items-center justify-center">
                  <Users className="w-10 h-10 text-purple-500" />
                </div>
              }
            />
          </div>
        ) : (
          tenants.map((tenant) => (
            <div
              key={tenant.id}
              className="bg-white rounded-lg shadow p-6 hover:shadow-md transition-shadow"
            >
              <div className="flex justify-between items-start mb-4">
                <div>
                  <h3 className="text-lg font-semibold text-gray-900">
                    {tenant.display_name || tenant.name}
                  </h3>
                  <p className="text-sm text-gray-500 font-mono">{tenant.name}</p>
                </div>
                <span
                  className={`px-2 py-1 text-xs font-medium rounded-full ${statusColors[tenant.status]}`}
                >
                  {tenant.status}
                </span>
              </div>

              <div className="space-y-2 text-sm text-gray-600">
                <div className="flex justify-between">
                  <span className="text-gray-500">Tenant ID:</span>
                  <span className="font-mono text-xs">{tenant.id}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Created:</span>
                  <span>{new Date(tenant.created_at).toLocaleDateString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Last Updated:</span>
                  <span>{new Date(tenant.updated_at).toLocaleDateString()}</span>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Info Banner */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="flex gap-3">
          <svg
            className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <div>
            <h4 className="text-sm font-medium text-blue-800">Tenant Management</h4>
            <p className="text-sm text-blue-700 mt-1">
              Tenant creation and IAM configuration is managed via the GitOps repository. See the{' '}
              <code className="bg-blue-100 px-1 rounded">iam/tenants.yaml</code> file for tenant
              definitions.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
