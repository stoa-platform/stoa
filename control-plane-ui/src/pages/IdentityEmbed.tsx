import { config } from '../config';
import { ExternalLink, Shield, User, Key, Smartphone, Monitor, LogOut } from 'lucide-react';

/**
 * IdentityEmbed - STOA Identity Management landing page
 * Part of CAB-1108 Phase 2: Console Integration
 *
 * Note: Keycloak 23.0 sets X-Frame-Options: SAMEORIGIN which prevents iframe embedding.
 * This component provides a branded landing page with quick links to Keycloak features.
 * Phase 3 will implement reverse proxy solution for seamless embedding.
 */
export function IdentityEmbed() {
  const keycloakBaseUrl = `${config.keycloak.url}/realms/${config.keycloak.realm}/account`;

  const quickLinks = [
    {
      title: 'Personal Info',
      description: 'Update your name, email, and profile details',
      icon: User,
      href: keycloakBaseUrl,
      color: 'bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400',
    },
    {
      title: 'Security',
      description: 'Change password and manage 2FA settings',
      icon: Key,
      href: `${keycloakBaseUrl}/#/security/signingin`,
      color: 'bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400',
    },
    {
      title: 'Authenticator',
      description: 'Set up authenticator app or security key',
      icon: Smartphone,
      href: `${keycloakBaseUrl}/#/security/signingin`,
      color: 'bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400',
    },
    {
      title: 'Active Sessions',
      description: 'View and manage your active login sessions',
      icon: Monitor,
      href: `${keycloakBaseUrl}/#/security/device-activity`,
      color: 'bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400',
    },
  ];

  const handleOpenKeycloak = () => {
    window.open(keycloakBaseUrl, '_blank', 'noopener,noreferrer');
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 bg-gradient-to-br from-purple-500 to-indigo-600 rounded-xl flex items-center justify-center shadow-lg">
            <Shield className="h-6 w-6 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
              Identity Management
            </h1>
            <p className="text-gray-500 dark:text-neutral-400">
              Manage your account security and preferences
            </p>
          </div>
        </div>
        <button
          onClick={handleOpenKeycloak}
          className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-purple-600 rounded-lg hover:bg-purple-700 transition-colors shadow-sm"
        >
          <ExternalLink className="h-4 w-4" />
          Open Full Console
        </button>
      </div>

      {/* Quick Links Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {quickLinks.map((link) => (
          <a
            key={link.title}
            href={link.href}
            target="_blank"
            rel="noopener noreferrer"
            className="group block p-6 bg-white dark:bg-neutral-800 rounded-xl border border-gray-200 dark:border-neutral-700 hover:border-purple-300 dark:hover:border-purple-700 hover:shadow-md transition-all"
          >
            <div className="flex items-start gap-4">
              <div className={`p-3 rounded-lg ${link.color}`}>
                <link.icon className="h-6 w-6" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white group-hover:text-purple-600 dark:group-hover:text-purple-400 transition-colors">
                    {link.title}
                  </h3>
                  <ExternalLink className="h-4 w-4 text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity" />
                </div>
                <p className="text-sm text-gray-500 dark:text-neutral-400 mt-1">
                  {link.description}
                </p>
              </div>
            </div>
          </a>
        ))}
      </div>

      {/* Logout Card */}
      <div className="bg-white dark:bg-neutral-800 rounded-xl border border-gray-200 dark:border-neutral-700 p-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="p-3 rounded-lg bg-red-100 dark:bg-red-900/30">
              <LogOut className="h-6 w-6 text-red-600 dark:text-red-400" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                Sign Out Everywhere
              </h3>
              <p className="text-sm text-gray-500 dark:text-neutral-400">
                Sign out of all devices and sessions
              </p>
            </div>
          </div>
          <a
            href={`${config.keycloak.url}/realms/${config.keycloak.realm}/protocol/openid-connect/logout`}
            className="px-4 py-2 text-sm font-medium text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/40 transition-colors"
          >
            Sign Out All
          </a>
        </div>
      </div>

      {/* Info Banner */}
      <div className="bg-gradient-to-r from-purple-50 to-indigo-50 dark:from-purple-900/20 dark:to-indigo-900/20 rounded-xl p-6 border border-purple-100 dark:border-purple-800/50">
        <div className="flex items-start gap-4">
          <div className="p-2 bg-white dark:bg-neutral-800 rounded-lg shadow-sm">
            <Shield className="h-5 w-5 text-purple-600 dark:text-purple-400" />
          </div>
          <div>
            <h4 className="font-semibold text-gray-900 dark:text-white">
              Powered by STOA Identity
            </h4>
            <p className="text-sm text-gray-600 dark:text-neutral-400 mt-1">
              Your identity is secured by STOA's enterprise-grade authentication platform.
              All sessions are encrypted and monitored for suspicious activity.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default IdentityEmbed;
