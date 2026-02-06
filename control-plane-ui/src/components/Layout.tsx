import { ReactNode, useState, useEffect, useMemo } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useBreadcrumbs } from '../hooks/useBreadcrumbs';
import { Breadcrumb } from '@stoa/shared/components/Breadcrumb';
import { useCommandPalette, type CommandItem } from '@stoa/shared/components/CommandPalette';
import { useSequenceShortcuts } from '@stoa/shared/hooks';
import { ThemeToggle } from '@stoa/shared/components/ThemeToggle';
import { useTheme } from '@stoa/shared/contexts';
import {
  LayoutDashboard,
  Building2,
  Layers,
  AppWindow,
  Rocket,
  LogOut,
  User,
  ChevronDown,
  Wrench,
  AlertTriangle,
  Activity,
  Server,
  Network,
  ArrowUpDown,
  BarChart3,
  PieChart,
  TrendingUp,
  Menu,
  X,
  Search,
  Plus,
  Sun,
  Moon,
  Shield,
  Gauge,
  ScrollText,
} from 'lucide-react';
import { clsx } from 'clsx';

interface LayoutProps {
  children: ReactNode;
}

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard, shortcut: ['g', 'd'] },
  { name: 'Operations', href: '/operations', icon: Activity, permission: 'tenants:read', shortcut: ['g', 'o'] },
  { name: 'My Usage', href: '/my-usage', icon: PieChart, shortcut: ['g', 'u'] },
  { name: 'Business', href: '/business', icon: TrendingUp, permission: 'tenants:read', shortcut: ['g', 'b'] },
  // CAB-1108: Embedded platform services
  { name: 'Observability', href: '/observability', icon: Gauge, shortcut: ['g', 'g'] },
  { name: 'Identity', href: '/identity', icon: Shield, shortcut: ['g', 'i'] },
  // CAB-1114: OpenSearch Dashboards for API trace logs
  { name: 'Logs', href: '/logs', icon: ScrollText, shortcut: ['g', 'l'] },
  { name: 'Tenants', href: '/tenants', icon: Building2, permission: 'tenants:read', shortcut: ['g', 't'] },
  { name: 'APIs', href: '/apis', icon: Layers, permission: 'apis:read', shortcut: ['g', 'a'] },
  { name: 'AI Tools', href: '/ai-tools', icon: Wrench, permission: 'apis:read', shortcut: ['g', 'w'] },
  { name: 'External MCP Servers', href: '/external-mcp-servers', icon: Server, permission: 'admin:servers' },
  { name: 'Gateway', href: '/gateway', icon: Server, permission: 'apis:read' },
  { name: 'Gateway Registry', href: '/gateways', icon: Network, permission: 'tenants:read' },
  { name: 'Gateway Deployments', href: '/gateway-deployments', icon: ArrowUpDown, permission: 'tenants:read' },
  { name: 'Gateway Metrics', href: '/gateway-observability', icon: BarChart3, permission: 'tenants:read' },
  { name: 'Applications', href: '/applications', icon: AppWindow, permission: 'apps:read' },
  { name: 'Deployments', href: '/deployments', icon: Rocket, permission: 'apis:deploy' },
  { name: 'API Monitoring', href: '/monitoring', icon: Activity, permission: 'apis:read' },
  { name: 'Error Snapshots', href: '/mcp/errors', icon: AlertTriangle, permission: 'apis:read' },
];

export function Layout({ children }: LayoutProps) {
  const { user, logout, hasPermission } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const breadcrumbItems = useBreadcrumbs();
  const { setOpen: setCommandPaletteOpen, setItems: setCommandItems } = useCommandPalette();
  const { resolvedTheme, toggleTheme } = useTheme();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const filteredNavigation = navigation.filter(
    item => !item.permission || hasPermission(item.permission)
  );

  // Close sidebar when route changes (mobile)
  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  // Register sequence shortcuts for navigation (g+key)
  const sequenceShortcuts = useMemo(() =>
    filteredNavigation
      .filter(item => item.shortcut)
      .map(item => ({
        keys: item.shortcut!,
        handler: () => navigate(item.href),
        description: `Go to ${item.name}`,
      })),
    [filteredNavigation, navigate]
  );

  useSequenceShortcuts(sequenceShortcuts);

  // Register command palette items
  useEffect(() => {
    const commands: CommandItem[] = [
      // Navigation commands
      ...filteredNavigation.map(item => ({
        id: `nav-${item.href}`,
        label: item.name,
        description: `Navigate to ${item.name}`,
        icon: <item.icon className="h-4 w-4" />,
        section: 'Navigation',
        shortcut: item.shortcut ? ['G', item.shortcut[1].toUpperCase()] : undefined,
        keywords: [item.name.toLowerCase(), 'go', 'navigate'],
        onSelect: () => navigate(item.href),
      })),
      // Quick actions
      {
        id: 'action-new-api',
        label: 'Create New API',
        description: 'Add a new API definition',
        icon: <Plus className="h-4 w-4" />,
        section: 'Actions',
        shortcut: ['N'],
        keywords: ['new', 'create', 'add', 'api'],
        onSelect: () => {
          navigate('/apis');
          // The page will need to handle opening the create modal
        },
      },
      {
        id: 'action-new-tenant',
        label: 'Create New Tenant',
        description: 'Add a new tenant',
        icon: <Plus className="h-4 w-4" />,
        section: 'Actions',
        keywords: ['new', 'create', 'add', 'tenant'],
        onSelect: () => {
          navigate('/tenants');
        },
      },
      // User actions
      {
        id: 'user-logout',
        label: 'Logout',
        description: 'Sign out of your account',
        icon: <LogOut className="h-4 w-4" />,
        section: 'Account',
        keywords: ['logout', 'sign out', 'exit'],
        onSelect: logout,
      },
      // Theme toggle
      {
        id: 'toggle-theme',
        label: resolvedTheme === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode',
        description: `Currently in ${resolvedTheme} mode`,
        icon: resolvedTheme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />,
        section: 'Settings',
        keywords: ['theme', 'dark', 'light', 'mode', 'toggle'],
        onSelect: toggleTheme,
      },
    ];

    setCommandItems(commands);
  }, [filteredNavigation, navigate, logout, setCommandItems, resolvedTheme, toggleTheme]);

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-neutral-900 transition-colors">
      {/* Mobile sidebar backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 lg:hidden animate-fade-in"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <div
        className={clsx(
          'fixed inset-y-0 left-0 z-50 w-64 bg-gray-900 dark:bg-neutral-950 transition-transform duration-300 ease-in-out lg:translate-x-0',
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        {/* Sidebar header */}
        <div className="flex h-16 items-center justify-between border-b border-gray-800 dark:border-neutral-800 px-4">
          <h1 className="text-lg font-bold text-white">STOA Control Plane</h1>
          <button
            onClick={() => setSidebarOpen(false)}
            className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-800 dark:hover:bg-neutral-800 hover:text-white lg:hidden"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav className="mt-6 px-3 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 180px)' }}>
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
                        : 'text-gray-300 hover:bg-gray-800 dark:hover:bg-neutral-800 hover:text-white'
                    )}
                  >
                    <item.icon className="h-5 w-5 flex-shrink-0" />
                    <span className="truncate">{item.name}</span>
                    {item.shortcut && (
                      <span className="ml-auto text-xs text-gray-500 hidden xl:block">
                        g{item.shortcut[1]}
                      </span>
                    )}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        {/* User section */}
        <div className="absolute bottom-0 left-0 right-0 border-t border-gray-800 dark:border-neutral-800 p-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary-600 flex-shrink-0">
              <User className="h-5 w-5 text-white" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="truncate text-sm font-medium text-white">{user?.name}</p>
              <p className="truncate text-xs text-gray-400">{user?.roles.join(', ')}</p>
            </div>
            <button
              onClick={logout}
              className="rounded-lg p-2 text-gray-400 hover:bg-gray-800 dark:hover:bg-neutral-800 hover:text-white flex-shrink-0"
              title="Logout"
            >
              <LogOut className="h-5 w-5" />
            </button>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="lg:pl-64">
        {/* Header */}
        <header className="sticky top-0 z-40 flex h-16 items-center gap-4 border-b bg-white dark:bg-neutral-900 dark:border-neutral-800 px-4 sm:px-6 shadow-sm dark:shadow-none">
          {/* Mobile menu button */}
          <button
            onClick={() => setSidebarOpen(true)}
            className="rounded-lg p-2 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-neutral-800 lg:hidden"
          >
            <Menu className="h-5 w-5" />
          </button>

          {/* Breadcrumbs */}
          <Breadcrumb
            items={breadcrumbItems}
            showHome={false}
            onNavigate={navigate}
            className="flex-1 hidden sm:flex"
          />

          {/* Mobile: Just show current page name */}
          <span className="flex-1 font-medium text-gray-900 dark:text-white truncate sm:hidden">
            {breadcrumbItems[breadcrumbItems.length - 1]?.label || 'Dashboard'}
          </span>

          {/* Command Palette trigger */}
          <button
            onClick={() => setCommandPaletteOpen(true)}
            className="hidden sm:flex items-center gap-2 rounded-lg border border-gray-200 dark:border-neutral-700 bg-gray-50 dark:bg-neutral-800 px-3 py-1.5 text-sm text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-neutral-700 hover:border-gray-300 dark:hover:border-neutral-600 transition-colors"
          >
            <Search className="h-4 w-4" />
            <span className="hidden md:inline">Search...</span>
            <kbd className="hidden md:flex items-center gap-0.5 rounded bg-white dark:bg-neutral-700 px-1.5 py-0.5 text-xs font-medium border border-gray-200 dark:border-neutral-600">
              <span className="text-xs">⌘</span>K
            </kbd>
          </button>

          {/* Mobile search button */}
          <button
            onClick={() => setCommandPaletteOpen(true)}
            className="rounded-lg p-2 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-neutral-800 sm:hidden"
          >
            <Search className="h-5 w-5" />
          </button>

          {/* Theme toggle */}
          <ThemeToggle size="md" />

          {/* Tenant selector */}
          {user?.tenant_id && (
            <div className="hidden sm:flex items-center gap-2 rounded-lg bg-neutral-100 dark:bg-neutral-800 px-3 py-1.5">
              <Building2 className="h-4 w-4 text-neutral-500 dark:text-neutral-400" />
              <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300 max-w-[120px] truncate">{user.tenant_id}</span>
              <ChevronDown className="h-4 w-4 text-neutral-400" />
            </div>
          )}
        </header>

        {/* Page content */}
        <main className="p-4 sm:p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
