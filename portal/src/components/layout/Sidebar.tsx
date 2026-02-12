import { NavLink } from 'react-router-dom';
import {
  BookOpen,
  User,
  UserPlus,
  X,
  Webhook,
  BarChart3,
  Wrench,
  ExternalLink,
  Briefcase,
  Server,
  LucideIcon,
} from 'lucide-react';
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
  permission?: string;
  scope?: string;
  role?: string;
  external?: boolean;
}

interface NavSection {
  title: string;
  items: NavItem[];
}

const sections: NavSection[] = [
  {
    title: 'Discover',
    items: [
      {
        name: 'API Catalog',
        href: '/apis',
        icon: BookOpen,
        enabled: config.features.enableAPICatalog,
        scope: 'stoa:catalog:read',
      },
      {
        name: 'AI Tools',
        href: '/servers',
        icon: Wrench,
        enabled: config.features.enableMCPTools,
        scope: 'stoa:catalog:read',
      },
    ],
  },
  {
    title: 'My Workspace',
    items: [
      {
        name: 'My Apps & Credentials',
        href: '/workspace',
        icon: Briefcase,
        permission: 'apps:read',
      },
      {
        name: 'Register Consumer',
        href: '/consumers/register',
        icon: UserPlus,
        scope: 'stoa:subscriptions:write',
      },
      {
        name: 'Usage',
        href: '/usage',
        icon: BarChart3,
        enabled: config.features.enableSubscriptions,
        scope: 'stoa:metrics:read',
      },
      {
        name: 'Webhooks',
        href: '/webhooks',
        icon: Webhook,
        enabled: config.features.enableSubscriptions,
        scope: 'stoa:subscriptions:write',
      },
    ],
  },
  {
    title: 'Operations',
    items: [
      {
        name: 'Gateways',
        href: '/gateways',
        icon: Server,
        enabled: config.features.enableGateways,
        scope: 'stoa:admin',
      },
    ],
  },
  {
    title: 'Account',
    items: [
      { name: 'Profile', href: '/profile', icon: User },
      {
        name: 'Console',
        href: config.services.console.url,
        icon: ExternalLink,
        external: true,
      },
    ],
  },
];

function isItemVisible(
  item: NavItem,
  hasPermission: (p: string) => boolean,
  hasScope: (s: string) => boolean,
  hasRole: (r: string) => boolean
): boolean {
  if (item.enabled === false) return false;
  if (item.permission && !hasPermission(item.permission)) return false;
  if (item.scope && !hasScope(item.scope)) return false;
  if (item.role && !hasRole(item.role)) return false;
  return true;
}

export function Sidebar({ isOpen, onClose }: SidebarProps) {
  const { hasPermission, hasScope, hasRole, user } = useAuth();

  const filteredSections = sections
    .map((section) => ({
      ...section,
      items: section.items.filter((item) => isItemVisible(item, hasPermission, hasScope, hasRole)),
    }))
    .filter((section) => section.items.length > 0);

  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-gray-600/50 dark:bg-black/60 z-40 lg:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside
        className={`
          fixed top-0 left-0 z-50 h-full w-64 bg-white dark:bg-neutral-900 border-r border-gray-200 dark:border-neutral-800
          transform transition-transform duration-200 ease-in-out
          lg:translate-x-0 lg:static lg:z-auto lg:h-auto lg:min-h-full
          flex flex-col
          ${isOpen ? 'translate-x-0' : '-translate-x-full'}
        `}
      >
        {/* Mobile close button */}
        <div className="flex items-center justify-between h-16 px-4 border-b border-gray-200 dark:border-neutral-800 lg:hidden">
          <span className="text-lg font-semibold text-gray-900 dark:text-white">Menu</span>
          <button
            onClick={onClose}
            className="p-2 text-gray-500 dark:text-neutral-400 hover:text-gray-700 dark:hover:text-neutral-200 hover:bg-gray-100 dark:hover:bg-neutral-800 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 transition-colors"
            aria-label="Close menu"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        {/* Navigation - sectioned */}
        <nav className="flex-1 p-4 pb-20 space-y-6 overflow-y-auto">
          {filteredSections.map((section) => (
            <div key={section.title}>
              <h3 className="px-3 mb-2 text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-neutral-500">
                {section.title}
              </h3>
              <div className="space-y-1">
                {section.items.map((item) =>
                  item.external ? (
                    <a
                      key={item.name}
                      href={item.href}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={onClose}
                      className="flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium text-gray-700 dark:text-neutral-300 hover:bg-gray-100 dark:hover:bg-neutral-800 transition-colors"
                    >
                      <item.icon className="h-5 w-5" aria-hidden="true" />
                      {item.name}
                      <ExternalLink className="h-3 w-3 ml-auto text-gray-400" aria-hidden="true" />
                    </a>
                  ) : (
                    <NavLink
                      key={item.name}
                      to={item.href}
                      onClick={onClose}
                      className={({ isActive }) =>
                        `flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors cursor-pointer ${
                          isActive
                            ? 'bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-400'
                            : 'text-gray-700 dark:text-neutral-300 hover:bg-gray-100 dark:hover:bg-neutral-800'
                        }`
                      }
                    >
                      <item.icon className="h-5 w-5" aria-hidden="true" />
                      {item.name}
                    </NavLink>
                  )
                )}
              </div>
            </div>
          ))}
        </nav>

        {/* Footer info */}
        <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-gray-200 dark:border-neutral-800 bg-white dark:bg-neutral-900">
          <a
            href={`https://api.${config.baseDomain}/docs`}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 text-xs text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300 mb-2 transition-colors"
          >
            <BookOpen className="h-3.5 w-3.5" aria-hidden="true" />
            API Documentation
            <ExternalLink className="h-3 w-3" aria-hidden="true" />
            <span className="sr-only">(opens in new tab)</span>
          </a>
          <div className="text-xs text-gray-500 dark:text-neutral-400">
            <p>STOA Developer Portal</p>
            <p>v{config.app.version}</p>
          </div>

          {/* Debug: show user roles in development */}
          {import.meta.env.DEV && user && (
            <div className="mt-2 pt-2 border-t border-gray-100 dark:border-neutral-800">
              <p className="text-xs text-gray-400 dark:text-neutral-500">
                Roles: {user.roles.join(', ') || 'none'}
              </p>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
