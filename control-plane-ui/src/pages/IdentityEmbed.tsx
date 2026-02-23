import { ExternalLink, Shield, User, Key, Clock, Building2 } from 'lucide-react';
import { config } from '../config';
import { useAuth } from '../contexts/AuthContext';

/**
 * IdentityEmbed - Native identity management page
 *
 * Displays user profile, roles, and security info from the auth context.
 * Links to Keycloak Account Console for advanced management (password change, sessions, etc.)
 *
 * Note: Previously used iframe embedding (CAB-1108), replaced with native view
 * because cross-origin cookie restrictions prevent Keycloak Account Console
 * from authenticating in an iframe in production.
 */
export function IdentityEmbed() {
  const { user, hasRole } = useAuth();
  const keycloakAccountUrl = `${config.keycloak.url}/realms/${config.keycloak.realm}/account`;

  const handleOpenKeycloak = () => {
    window.open(keycloakAccountUrl, '_blank', 'noopener,noreferrer');
  };

  const roleLabels: Record<string, string> = {
    'cpi-admin': 'Platform Administrator',
    'tenant-admin': 'Tenant Administrator',
    devops: 'DevOps Engineer',
    viewer: 'Viewer',
  };

  const roleColors: Record<string, string> = {
    'cpi-admin': 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
    'tenant-admin': 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
    devops: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
    viewer: 'bg-neutral-100 text-neutral-800 dark:bg-neutral-700 dark:text-neutral-300',
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-purple-100 dark:bg-purple-900/30 rounded-lg flex items-center justify-center">
            <Shield className="h-5 w-5 text-purple-600 dark:text-purple-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">
              Identity Management
            </h1>
            <p className="text-neutral-500 dark:text-neutral-400 mt-0.5">
              Your profile, roles, and security settings
            </p>
          </div>
        </div>
        <button
          onClick={handleOpenKeycloak}
          className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-purple-600 rounded-lg hover:bg-purple-700 transition-colors"
        >
          <ExternalLink className="h-4 w-4" />
          Manage in Keycloak
        </button>
      </div>

      {/* Profile Card */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none border border-neutral-200 dark:border-neutral-700 p-6">
        <div className="flex items-start gap-6">
          <div className="w-16 h-16 bg-purple-100 dark:bg-purple-900/30 rounded-full flex items-center justify-center flex-shrink-0">
            <User className="h-8 w-8 text-purple-600 dark:text-purple-400" />
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">
              {user?.name || 'Unknown User'}
            </h2>
            <p className="text-neutral-500 dark:text-neutral-400 mt-1">
              {user?.email || 'No email'}
            </p>
            <div className="flex flex-wrap gap-2 mt-3">
              {user?.roles?.map((role) => (
                <span
                  key={role}
                  className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${roleColors[role] || roleColors.viewer}`}
                >
                  {roleLabels[role] || role}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Account Details */}
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none border border-neutral-200 dark:border-neutral-700 p-6">
          <h3 className="text-lg font-semibold text-neutral-900 dark:text-white mb-4 flex items-center gap-2">
            <Key className="h-5 w-5 text-neutral-400" />
            Account Details
          </h3>
          <dl className="space-y-4">
            <div>
              <dt className="text-sm font-medium text-neutral-500 dark:text-neutral-400">
                User ID
              </dt>
              <dd className="mt-1 text-sm text-neutral-900 dark:text-white font-mono">
                {user?.id || '—'}
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-neutral-500 dark:text-neutral-400">Email</dt>
              <dd className="mt-1 text-sm text-neutral-900 dark:text-white">
                {user?.email || '—'}
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-neutral-500 dark:text-neutral-400">
                Authentication Provider
              </dt>
              <dd className="mt-1 text-sm text-neutral-900 dark:text-white">
                Keycloak OIDC ({config.keycloak.realm} realm)
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-neutral-500 dark:text-neutral-400">
                Client ID
              </dt>
              <dd className="mt-1 text-sm text-neutral-900 dark:text-white font-mono">
                {config.keycloak.clientId}
              </dd>
            </div>
          </dl>
        </div>

        {/* Organization */}
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none border border-neutral-200 dark:border-neutral-700 p-6">
          <h3 className="text-lg font-semibold text-neutral-900 dark:text-white mb-4 flex items-center gap-2">
            <Building2 className="h-5 w-5 text-neutral-400" />
            Organization
          </h3>
          <dl className="space-y-4">
            <div>
              <dt className="text-sm font-medium text-neutral-500 dark:text-neutral-400">Tenant</dt>
              <dd className="mt-1 text-sm text-neutral-900 dark:text-white">
                {user?.tenant_id || '—'}
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-neutral-500 dark:text-neutral-400">
                Access Level
              </dt>
              <dd className="mt-1 text-sm text-neutral-900 dark:text-white">
                {hasRole('cpi-admin')
                  ? 'Full Platform Access'
                  : hasRole('tenant-admin')
                    ? 'Tenant Management'
                    : hasRole('devops')
                      ? 'Deploy & Monitor'
                      : 'Read Only'}
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-neutral-500 dark:text-neutral-400">
                Permissions
              </dt>
              <dd className="mt-1 text-sm text-neutral-900 dark:text-white">
                {user?.permissions?.length || 0} active permissions
              </dd>
            </div>
          </dl>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none border border-neutral-200 dark:border-neutral-700 p-6">
        <h3 className="text-lg font-semibold text-neutral-900 dark:text-white mb-4 flex items-center gap-2">
          <Clock className="h-5 w-5 text-neutral-400" />
          Security Actions
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <button
            onClick={() =>
              window.open(
                `${keycloakAccountUrl}/#/security/signingin`,
                '_blank',
                'noopener,noreferrer'
              )
            }
            className="flex items-center gap-3 p-4 rounded-lg border border-neutral-200 dark:border-neutral-600 hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors text-left"
          >
            <Key className="h-5 w-5 text-purple-500 flex-shrink-0" />
            <div>
              <p className="text-sm font-medium text-neutral-900 dark:text-white">
                Change Password
              </p>
              <p className="text-xs text-neutral-500 dark:text-neutral-400">
                Update your credentials
              </p>
            </div>
          </button>
          <button
            onClick={() =>
              window.open(
                `${keycloakAccountUrl}/#/security/device-activity`,
                '_blank',
                'noopener,noreferrer'
              )
            }
            className="flex items-center gap-3 p-4 rounded-lg border border-neutral-200 dark:border-neutral-600 hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors text-left"
          >
            <Shield className="h-5 w-5 text-blue-500 flex-shrink-0" />
            <div>
              <p className="text-sm font-medium text-neutral-900 dark:text-white">
                Active Sessions
              </p>
              <p className="text-xs text-neutral-500 dark:text-neutral-400">
                View and manage sessions
              </p>
            </div>
          </button>
          <button
            onClick={handleOpenKeycloak}
            className="flex items-center gap-3 p-4 rounded-lg border border-neutral-200 dark:border-neutral-600 hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors text-left"
          >
            <ExternalLink className="h-5 w-5 text-green-500 flex-shrink-0" />
            <div>
              <p className="text-sm font-medium text-neutral-900 dark:text-white">
                Full Account Console
              </p>
              <p className="text-xs text-neutral-500 dark:text-neutral-400">
                Open Keycloak management
              </p>
            </div>
          </button>
        </div>
      </div>
    </div>
  );
}

export default IdentityEmbed;
