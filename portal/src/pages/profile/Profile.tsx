import { User, Mail, Building, Key, Shield } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';

export function ProfilePage() {
  const { user } = useAuth();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">My Profile</h1>
        <p className="text-neutral-500 dark:text-neutral-400 mt-1">
          View and manage your account settings
        </p>
      </div>

      {/* Profile Card */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 overflow-hidden">
        {/* Header with avatar */}
        <div className="bg-gradient-to-r from-primary-600 to-accent-600 px-6 py-8">
          <div className="flex items-center gap-4">
            <div className="w-20 h-20 bg-white rounded-full flex items-center justify-center">
              <User className="h-10 w-10 text-primary-600" />
            </div>
            <div className="text-white">
              <h2 className="text-2xl font-bold">{user?.name || 'Unknown User'}</h2>
              <p className="text-primary-100">{user?.email}</p>
            </div>
          </div>
        </div>

        {/* Details */}
        <div className="p-6 space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-4">
              <h3 className="text-sm font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                Account Information
              </h3>

              <div className="flex items-center gap-3">
                <div className="p-2 bg-neutral-100 dark:bg-neutral-700 rounded-lg">
                  <User className="h-5 w-5 text-neutral-600 dark:text-neutral-300" />
                </div>
                <div>
                  <p className="text-sm text-neutral-500 dark:text-neutral-400">Full Name</p>
                  <p className="font-medium text-neutral-900 dark:text-white">
                    {user?.name || 'Not set'}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <div className="p-2 bg-neutral-100 dark:bg-neutral-700 rounded-lg">
                  <Mail className="h-5 w-5 text-neutral-600 dark:text-neutral-300" />
                </div>
                <div>
                  <p className="text-sm text-neutral-500 dark:text-neutral-400">Email</p>
                  <p className="font-medium text-neutral-900 dark:text-white">
                    {user?.email || 'Not set'}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <div className="p-2 bg-neutral-100 dark:bg-neutral-700 rounded-lg">
                  <Building className="h-5 w-5 text-neutral-600 dark:text-neutral-300" />
                </div>
                <div>
                  <p className="text-sm text-neutral-500 dark:text-neutral-400">Organization</p>
                  <p className="font-medium text-neutral-900 dark:text-white">
                    {user?.organization || 'Not set'}
                  </p>
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <h3 className="text-sm font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                Security
              </h3>

              <div className="flex items-center gap-3">
                <div className="p-2 bg-neutral-100 dark:bg-neutral-700 rounded-lg">
                  <Key className="h-5 w-5 text-neutral-600 dark:text-neutral-300" />
                </div>
                <div>
                  <p className="text-sm text-neutral-500 dark:text-neutral-400">User ID</p>
                  <p className="font-mono text-sm text-neutral-900 dark:text-white">
                    {user?.id || 'Unknown'}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <div className="p-2 bg-neutral-100 dark:bg-neutral-700 rounded-lg">
                  <Shield className="h-5 w-5 text-neutral-600 dark:text-neutral-300" />
                </div>
                <div>
                  <p className="text-sm text-neutral-500 dark:text-neutral-400">Authentication</p>
                  <p className="font-medium text-neutral-900 dark:text-white">OIDC (Keycloak)</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* API Keys Section (placeholder) */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6">
        <h3 className="text-lg font-semibold text-neutral-900 dark:text-white mb-4">API Keys</h3>
        <p className="text-neutral-500 dark:text-neutral-400">
          API key management will be available soon. For now, use your OIDC access token for API
          authentication.
        </p>
      </div>
    </div>
  );
}
