import { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import {
  LayoutDashboard,
  Building2,
  Layers,
  AppWindow,
  Rocket,
  GitBranch,
  LogOut,
  User,
  ChevronDown,
  Activity,
} from 'lucide-react';
import { clsx } from 'clsx';

interface LayoutProps {
  children: ReactNode;
}

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Tenants', href: '/tenants', icon: Building2, permission: 'tenants:read' },
  { name: 'APIs', href: '/apis', icon: Layers, permission: 'apis:read' },
  { name: 'Applications', href: '/applications', icon: AppWindow, permission: 'apps:read' },
  { name: 'Deployments', href: '/deployments', icon: Rocket, permission: 'apis:deploy' },
  { name: 'Git', href: '/git', icon: GitBranch, permission: 'apis:read' },
  { name: 'Monitoring', href: '/monitoring', icon: Activity, permission: 'apis:read' },
];

export function Layout({ children }: LayoutProps) {
  const { user, logout, hasPermission } = useAuth();
  const location = useLocation();

  const filteredNavigation = navigation.filter(
    item => !item.permission || hasPermission(item.permission)
  );

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Sidebar */}
      <div className="fixed inset-y-0 left-0 z-50 w-64 bg-gray-900">
        <div className="flex h-16 items-center justify-center border-b border-gray-800">
          <h1 className="text-xl font-bold text-white">APIM Control Plane</h1>
        </div>

        <nav className="mt-6 px-3">
          <ul className="space-y-1">
            {filteredNavigation.map((item) => {
              const isActive = location.pathname === item.href ||
                (item.href !== '/' && location.pathname.startsWith(item.href));

              return (
                <li key={item.name}>
                  <Link
                    to={item.href}
                    className={clsx(
                      'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                      isActive
                        ? 'bg-primary-600 text-white'
                        : 'text-gray-300 hover:bg-gray-800 hover:text-white'
                    )}
                  >
                    <item.icon className="h-5 w-5" />
                    {item.name}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        {/* User section */}
        <div className="absolute bottom-0 left-0 right-0 border-t border-gray-800 p-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary-600">
              <User className="h-5 w-5 text-white" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="truncate text-sm font-medium text-white">{user?.name}</p>
              <p className="truncate text-xs text-gray-400">{user?.roles.join(', ')}</p>
            </div>
            <button
              onClick={logout}
              className="rounded-lg p-2 text-gray-400 hover:bg-gray-800 hover:text-white"
              title="Logout"
            >
              <LogOut className="h-5 w-5" />
            </button>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="pl-64">
        {/* Header */}
        <header className="sticky top-0 z-40 flex h-16 items-center gap-4 border-b bg-white px-6 shadow-sm">
          <div className="flex flex-1 items-center gap-4">
            {user?.tenant_id && (
              <div className="flex items-center gap-2 rounded-lg bg-gray-100 px-3 py-1.5">
                <Building2 className="h-4 w-4 text-gray-500" />
                <span className="text-sm font-medium text-gray-700">{user.tenant_id}</span>
                <ChevronDown className="h-4 w-4 text-gray-400" />
              </div>
            )}
          </div>
        </header>

        {/* Page content */}
        <main className="p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
