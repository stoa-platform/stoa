/**
 * Admin Roles Page (CAB-1454)
 *
 * Read-only view of RBAC role definitions and their permissions.
 * cpi-admin only.
 */
import { useAuth } from '../contexts/AuthContext';
import { useAdminRoles } from '../hooks/useAdminRoles';
import { AlertTriangle, Shield, Users, Check } from 'lucide-react';

const roleColors: Record<string, { bg: string; text: string; border: string }> = {
  'cpi-admin': {
    bg: 'bg-red-50 dark:bg-red-900/20',
    text: 'text-red-800 dark:text-red-400',
    border: 'border-red-200 dark:border-red-800',
  },
  'tenant-admin': {
    bg: 'bg-blue-50 dark:bg-blue-900/20',
    text: 'text-blue-800 dark:text-blue-400',
    border: 'border-blue-200 dark:border-blue-800',
  },
  devops: {
    bg: 'bg-purple-50 dark:bg-purple-900/20',
    text: 'text-purple-800 dark:text-purple-400',
    border: 'border-purple-200 dark:border-purple-800',
  },
  viewer: {
    bg: 'bg-neutral-50 dark:bg-neutral-800',
    text: 'text-neutral-800 dark:text-neutral-400',
    border: 'border-neutral-200 dark:border-neutral-700',
  },
};

const defaultRoleColor = {
  bg: 'bg-neutral-50 dark:bg-neutral-800',
  text: 'text-neutral-800 dark:text-neutral-400',
  border: 'border-neutral-200 dark:border-neutral-700',
};

export function AdminRoles() {
  const { hasRole } = useAuth();

  const { data: rolesData, isLoading, error } = useAdminRoles({ enabled: hasRole('cpi-admin') });

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

  return (
    <div className="min-h-screen bg-neutral-50 dark:bg-neutral-900 p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">
            Roles &amp; Permissions
          </h1>
          <p className="text-neutral-500 dark:text-neutral-400 mt-1">
            Platform RBAC role definitions and their associated permissions
          </p>
        </div>

        {/* Error state */}
        {error && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
            <p className="text-sm text-red-700 dark:text-red-400">
              Failed to load roles. Please try again.
            </p>
          </div>
        )}

        {/* Loading */}
        {isLoading ? (
          <div className="flex items-center justify-center p-12">
            <div className="animate-spin rounded-full h-8 w-8 border-2 border-blue-600 border-t-transparent" />
          </div>
        ) : !rolesData?.roles.length ? (
          <div className="flex flex-col items-center justify-center p-12 text-neutral-500 dark:text-neutral-400">
            <Shield className="h-10 w-10 mb-3 opacity-50" />
            <p className="text-sm">No roles configured</p>
          </div>
        ) : (
          <div className="grid gap-6 md:grid-cols-2">
            {rolesData.roles.map((role) => {
              const colors = roleColors[role.name] || defaultRoleColor;
              return (
                <div
                  key={role.name}
                  className={`rounded-lg border ${colors.border} ${colors.bg} p-5`}
                >
                  <div className="flex items-center justify-between mb-3">
                    <div>
                      <h3 className={`text-lg font-semibold ${colors.text}`}>
                        {role.display_name}
                      </h3>
                      <p className="text-sm text-neutral-600 dark:text-neutral-400 mt-0.5">
                        {role.description}
                      </p>
                    </div>
                    <div className="flex items-center gap-1.5 text-sm text-neutral-500 dark:text-neutral-400">
                      <Users className="h-4 w-4" />
                      <span>
                        {role.user_count} user{role.user_count !== 1 ? 's' : ''}
                      </span>
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <p className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                      Permissions
                    </p>
                    <div className="grid gap-1">
                      {role.permissions.map((perm) => (
                        <div key={perm.name} className="flex items-start gap-2">
                          <Check className="h-3.5 w-3.5 text-green-500 mt-0.5 flex-shrink-0" />
                          <div>
                            <span className="text-sm font-mono text-neutral-900 dark:text-white">
                              {perm.name}
                            </span>
                            {perm.description && (
                              <span className="text-xs text-neutral-500 dark:text-neutral-400 ml-2">
                                {perm.description}
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
