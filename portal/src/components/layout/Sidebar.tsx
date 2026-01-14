import { NavLink } from 'react-router-dom';
import { Home, Wrench, CreditCard, BookOpen, User, X, AppWindow, Webhook, BarChart3, Shield, Server } from 'lucide-react';
import { config } from '../../config';

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

const navigation = [
  { name: 'Home', href: '/', icon: Home },
  { name: 'MCP Servers', href: '/servers', icon: Server, enabled: config.features.enableMCPTools },
  { name: 'MCP Tools', href: '/tools', icon: Wrench, enabled: config.features.enableMCPTools },
  { name: 'API Catalog', href: '/apis', icon: BookOpen, enabled: config.features.enableAPICatalog },
  { name: 'My Apps', href: '/apps', icon: AppWindow, enabled: config.features.enableAPICatalog },
  { name: 'My Subscriptions', href: '/subscriptions', icon: CreditCard, enabled: config.features.enableSubscriptions },
  { name: 'Service Accounts', href: '/service-accounts', icon: Shield, enabled: config.features.enableMCPTools },
  { name: 'Usage', href: '/usage', icon: BarChart3, enabled: config.features.enableSubscriptions },
  { name: 'Webhooks', href: '/webhooks', icon: Webhook, enabled: config.features.enableSubscriptions },
  { name: 'Profile', href: '/profile', icon: User },
].filter(item => item.enabled !== false);

export function Sidebar({ isOpen, onClose }: SidebarProps) {
  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-gray-600 bg-opacity-50 z-40 lg:hidden"
          onClick={onClose}
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
            className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-md"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Navigation - flex-1 to push footer down, pb for footer spacing */}
        <nav className="flex-1 p-4 pb-20 space-y-1 overflow-y-auto">
          {navigation.map((item) => (
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
              <item.icon className="h-5 w-5" />
              {item.name}
            </NavLink>
          ))}
        </nav>

        {/* Footer info */}
        <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-gray-200 bg-white">
          <div className="text-xs text-gray-500">
            <p>STOA Developer Portal</p>
            <p>v{config.app.version}</p>
          </div>
        </div>
      </aside>
    </>
  );
}
