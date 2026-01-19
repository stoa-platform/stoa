import { NavLink } from 'react-router-dom';
import { Home, CreditCard, BookOpen, User, X, AppWindow, Webhook, BarChart3, Shield, Wrench, ExternalLink, FileCode2, LucideIcon } from 'lucide-react';
import { config } from '../../config';
import { useAuth } from '../../contexts/AuthContext';

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

interface NavItem {
  name: string;
  href: string;
  icon: LucideIcon;
  enabled?: boolean;
  /** Permission required to see this item (granular permission like 'apis:read') */
  permission?: string;
  /** OAuth2 scope required to see this item (like 'stoa:catalog:read') */
  scope?: string;
  /** Keycloak role required to see this item */
  role?: string;
}

const navigation: NavItem[] = [
  // Public routes (no permission required)
  { name: 'Home', href: '/', icon: Home },
  { name: 'Profile', href: '/profile', icon: User },

  // Consumer Catalogs - Main features (requires catalog:read)
  { name: 'API Catalog', href: '/apis', icon: BookOpen, enabled: config.features.enableAPICatalog, scope: 'stoa:catalog:read' },
  { name: 'AI Tools', href: '/servers', icon: Wrench, enabled: config.features.enableMCPTools, scope: 'stoa:catalog:read' },

  // Universal API Contracts (UAC) (requires catalog:read)
  { name: 'Contracts', href: '/contracts', icon: FileCode2, scope: 'stoa:catalog:read' },

  // Consumer Resources (requires apps:read or subscriptions:read)
  { name: 'My Apps', href: '/apps', icon: AppWindow, enabled: config.features.enableAPICatalog, permission: 'apps:read' },
  { name: 'My Subscriptions', href: '/subscriptions', icon: CreditCard, enabled: config.features.enableSubscriptions, scope: 'stoa:subscriptions:read' },

  // Service Accounts - tenant-admin+ (requires subscriptions:write)
  { name: 'Service Accounts', href: '/service-accounts', icon: Shield, enabled: config.features.enableMCPTools, scope: 'stoa:subscriptions:write' },

  // Analytics - requires metrics:read
  { name: 'Usage', href: '/usage', icon: BarChart3, enabled: config.features.enableSubscriptions, scope: 'stoa:metrics:read' },

  // Tenant Admin - requires subscriptions:write
  { name: 'Webhooks', href: '/webhooks', icon: Webhook, enabled: config.features.enableSubscriptions, scope: 'stoa:subscriptions:write' },
];

export function Sidebar({ isOpen, onClose }: SidebarProps) {
  const { hasPermission, hasScope, hasRole, user } = useAuth();

  // Filter navigation items based on:
  // 1. Feature flags (enabled)
  // 2. Permissions/scopes/roles
  const filteredNavigation = navigation.filter(item => {
    // Check feature flag
    if (item.enabled === false) return false;

    // Check permission if specified
    if (item.permission && !hasPermission(item.permission)) return false;

    // Check scope if specified
    if (item.scope && !hasScope(item.scope)) return false;

    // Check role if specified
    if (item.role && !hasRole(item.role)) return false;

    return true;
  });

  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-gray-600 bg-opacity-50 z-40 lg:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside
        className={`
          fixed top-0 left-0 z-50 h-full w-64 bg-white border-r border-gray-200
          transform transition-transform duration-200 ease-in-out
          lg:translate-x-0 lg:static lg:z-auto lg:h-auto lg:min-h-full
          flex flex-col
          ${isOpen ? 'translate-x-0' : '-translate-x-full'}
        `}
      >
        {/* Mobile close button */}
        <div className="flex items-center justify-between h-16 px-4 border-b border-gray-200 lg:hidden">
          <span className="text-lg font-semibold text-gray-900">Menu</span>
          <button
            onClick={onClose}
            className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
            aria-label="Close menu"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        {/* Navigation - flex-1 to push footer down, pb for footer spacing */}
        <nav className="flex-1 p-4 pb-20 space-y-1 overflow-y-auto">
          {filteredNavigation.map((item) => (
            <NavLink
              key={item.name}
              to={item.href}
              onClick={onClose}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors cursor-pointer ${
                  isActive
                    ? 'bg-primary-50 text-primary-700'
                    : 'text-gray-700 hover:bg-gray-100'
                }`
              }
            >
              <item.icon className="h-5 w-5" aria-hidden="true" />
              {item.name}
            </NavLink>
          ))}
        </nav>

        {/* Footer info */}
        <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-gray-200 bg-white">
          <a
            href={`https://api.${config.baseDomain}/docs`}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 text-xs text-primary-600 hover:text-primary-700 mb-2 transition-colors"
          >
            <BookOpen className="h-3.5 w-3.5" aria-hidden="true" />
            API Documentation
            <ExternalLink className="h-3 w-3" aria-hidden="true" />
            <span className="sr-only">(opens in new tab)</span>
          </a>
          <div className="text-xs text-gray-500">
            <p>STOA Developer Portal</p>
            <p>v{config.app.version}</p>
          </div>

          {/* Debug: show user roles in development */}
          {import.meta.env.DEV && user && (
            <div className="mt-2 pt-2 border-t border-gray-100">
              <p className="text-xs text-gray-400">
                Roles: {user.roles.join(', ') || 'none'}
              </p>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
