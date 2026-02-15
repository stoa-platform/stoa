import { ReactNode, useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../contexts/AuthContext';
import { useEnvironment } from '../contexts/EnvironmentContext';
import { useBreadcrumbs } from '../hooks/useBreadcrumbs';
import { Breadcrumb } from '@stoa/shared/components/Breadcrumb';
import { useCommandPalette, type CommandItem } from '@stoa/shared/components/CommandPalette';
import { StoaLogo } from '@stoa/shared/components/StoaLogo';
import { useSequenceShortcuts } from '@stoa/shared/hooks';
import { ThemeToggle } from '@stoa/shared/components/ThemeToggle';
import { useTheme } from '@stoa/shared/contexts';
import { apiService } from '../services/api';
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
  Eye,
  Coins,
  FileCheck,
  ClipboardList,
  Check,
  Lock,
  Users,
} from 'lucide-react';
import { clsx } from 'clsx';
import { useApiConnectivity } from '../hooks/useApiConnectivity';

interface LayoutProps {
  children: ReactNode;
}

interface NavItem {
  name: string;
  href: string;
  icon: typeof LayoutDashboard;
  permission?: string;
  shortcut?: string[];
  badge?: string;
}

interface NavSection {
  title: string;
  items: NavItem[];
  accent?: boolean;
}

const navigationSections: NavSection[] = [
  {
    title: 'Overview',
    items: [
      { name: 'Dashboard', href: '/', icon: LayoutDashboard, shortcut: ['g', 'd'] },
      {
        name: 'Operations',
        href: '/operations',
        icon: Activity,
        permission: 'tenants:read',
        shortcut: ['g', 'o'],
      },
      { name: 'My Usage', href: '/my-usage', icon: PieChart, shortcut: ['g', 'u'] },
      {
        name: 'Business',
        href: '/business',
        icon: TrendingUp,
        permission: 'tenants:read',
        shortcut: ['g', 'b'],
      },
    ],
  },
  {
    title: 'Catalog',
    items: [
      {
        name: 'Tenants',
        href: '/tenants',
        icon: Building2,
        permission: 'tenants:read',
        shortcut: ['g', 't'],
      },
      {
        name: 'APIs',
        href: '/apis',
        icon: Layers,
        permission: 'apis:read',
        shortcut: ['g', 'a'],
      },
      {
        name: 'AI Tools',
        href: '/ai-tools',
        icon: Wrench,
        permission: 'apis:read',
        shortcut: ['g', 'w'],
        badge: 'STOA',
      },
      {
        name: 'External MCP Servers',
        href: '/external-mcp-servers',
        icon: Server,
        permission: 'admin:servers',
      },
      { name: 'Applications', href: '/applications', icon: AppWindow, permission: 'apps:read' },
      {
        name: 'Consumers',
        href: '/consumers',
        icon: Users,
        permission: 'consumers:read',
        shortcut: ['g', 'c'],
      },
    ],
  },
  {
    title: '\u26A1 Gateway',
    accent: true,
    items: [
      { name: 'Status', href: '/gateway', icon: Server, permission: 'apis:read' },
      {
        name: 'Registry',
        href: '/gateways',
        icon: Network,
        permission: 'tenants:read',
      },
      {
        name: 'Modes',
        href: '/gateways/modes',
        icon: Gauge,
        permission: 'tenants:read',
        shortcut: ['g', 'm'],
        badge: 'STOA',
      },
      {
        name: 'Deployments',
        href: '/gateway-deployments',
        icon: ArrowUpDown,
        permission: 'tenants:read',
      },
      {
        name: 'Drift',
        href: '/drift',
        icon: AlertTriangle,
        permission: 'tenants:read',
      },
      {
        name: 'Metrics',
        href: '/gateway-observability',
        icon: BarChart3,
        permission: 'tenants:read',
      },
    ],
  },
  {
    title: 'Insights',
    items: [
      { name: 'Observability', href: '/observability', icon: Gauge, shortcut: ['g', 'g'] },
      { name: 'Identity', href: '/identity', icon: Shield, shortcut: ['g', 'i'] },
      { name: 'Logs', href: '/logs', icon: ScrollText, shortcut: ['g', 'l'] },
      {
        name: 'API Monitoring',
        href: '/monitoring',
        icon: Activity,
        permission: 'apis:read',
      },
      {
        name: 'Error Snapshots',
        href: '/errors',
        icon: AlertTriangle,
        permission: 'apis:read',
        badge: 'STOA',
      },
      {
        name: 'Shadow Discovery',
        href: '/shadow-discovery',
        icon: Eye,
        permission: 'apis:read',
      },
      {
        name: 'Token Optimizer',
        href: '/token-optimizer',
        icon: Coins,
        permission: 'apis:read',
      },
    ],
  },
  {
    title: 'Governance',
    items: [
      { name: 'Deployments', href: '/deployments', icon: Rocket, permission: 'apis:deploy' },
      { name: 'Policies', href: '/policies', icon: FileCheck, permission: 'apis:read' },
      {
        name: 'Audit Log',
        href: '/audit-log',
        icon: ClipboardList,
        permission: 'audit:read',
      },
    ],
  },
];

const SIDEBAR_SECTIONS_KEY = 'stoa-sidebar-sections';
const ACTIVE_TENANT_KEY = 'stoa-active-tenant';

// Prefetch route chunks on hover — loads JS before click for instant navigation
const routePrefetchMap: Record<string, () => Promise<unknown>> = {
  '/apis': () => import('../pages/APIs'),
  '/tenants': () => import('../pages/Tenants'),
  '/ai-tools': () => import('../pages/AITools'),
  '/applications': () => import('../pages/Applications'),
  '/deployments': () => import('../pages/Deployments'),
  '/monitoring': () => import('../pages/APIMonitoring'),
};

export function Layout({ children }: LayoutProps) {
  const { user, logout, hasPermission } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const breadcrumbItems = useBreadcrumbs();
  const { setOpen: setCommandPaletteOpen, setItems: setCommandItems } = useCommandPalette();
  const { resolvedTheme, toggleTheme } = useTheme();
  const { isConnected, isChecking } = useApiConnectivity();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Collapsible section state — persisted to localStorage
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>(() => {
    try {
      const stored = localStorage.getItem(SIDEBAR_SECTIONS_KEY);
      if (stored) return JSON.parse(stored);
    } catch {
      /* ignore corrupt data */
    }
    // Default: Gateway open, others closed
    return {
      Overview: true,
      Catalog: true,
      '\u26A1 Gateway': false,
      Insights: true,
      Governance: true,
    };
  });

  const toggleSection = useCallback((title: string) => {
    setCollapsedSections((prev) => {
      const next = { ...prev, [title]: !prev[title] };
      localStorage.setItem(SIDEBAR_SECTIONS_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  // Tenant selector state
  const [tenantDropdownOpen, setTenantDropdownOpen] = useState(false);
  const tenantDropdownRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();

  const { data: tenants } = useQuery({
    queryKey: ['tenants'],
    queryFn: () => apiService.getTenants(),
    enabled: hasPermission('tenants:read'),
    staleTime: 5 * 60 * 1000,
  });

  const [activeTenantId, setActiveTenantId] = useState<string>(
    () => localStorage.getItem(ACTIVE_TENANT_KEY) || ''
  );

  const activeTenant = useMemo(() => {
    const id = activeTenantId || user?.tenant_id;
    return tenants?.find((t) => t.id === id || t.name === id);
  }, [activeTenantId, user?.tenant_id, tenants]);

  const handleTenantSwitch = useCallback(
    (tenantId: string) => {
      setActiveTenantId(tenantId);
      localStorage.setItem(ACTIVE_TENANT_KEY, tenantId);
      setTenantDropdownOpen(false);
      queryClient.invalidateQueries();
    },
    [queryClient]
  );

  // Close tenant dropdown on outside click
  useEffect(() => {
    if (!tenantDropdownOpen) return;
    function handleClickOutside(event: MouseEvent) {
      if (tenantDropdownRef.current && !tenantDropdownRef.current.contains(event.target as Node)) {
        setTenantDropdownOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [tenantDropdownOpen]);

  // Environment selector state (ADR-040)
  const { activeEnvironment, activeConfig, environments, switchEnvironment } = useEnvironment();
  const [envDropdownOpen, setEnvDropdownOpen] = useState(false);
  const envDropdownRef = useRef<HTMLDivElement>(null);

  const handleEnvSwitch = useCallback(
    (env: 'dev' | 'staging' | 'prod') => {
      switchEnvironment(env);
      setEnvDropdownOpen(false);
    },
    [switchEnvironment]
  );

  useEffect(() => {
    if (!envDropdownOpen) return;
    function handleClickOutside(event: MouseEvent) {
      if (envDropdownRef.current && !envDropdownRef.current.contains(event.target as Node)) {
        setEnvDropdownOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [envDropdownOpen]);

  const filteredSections = useMemo(
    () =>
      navigationSections
        .map((section) => ({
          ...section,
          items: section.items.filter((item) => !item.permission || hasPermission(item.permission)),
        }))
        .filter((section) => section.items.length > 0),
    [hasPermission]
  );

  const filteredNavigation = useMemo(
    () => filteredSections.flatMap((s) => s.items),
    [filteredSections]
  );

  // Close sidebar when route changes (mobile)
  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  // Register sequence shortcuts for navigation (g+key)
  const sequenceShortcuts = useMemo(
    () =>
      filteredNavigation
        .filter((item) => item.shortcut)
        .map((item) => ({
          keys: item.shortcut!,
          handler: () => navigate(item.href),
          description: `Go to ${item.name}`,
        })),
    [filteredNavigation, navigate]
  );

  useSequenceShortcuts(sequenceShortcuts);

  // Memoize navigation commands separately (only changes when nav items change)
  const navigationCommands = useMemo(
    () =>
      filteredNavigation.map((item) => ({
        id: `nav-${item.href}`,
        label: item.name,
        description: `Navigate to ${item.name}`,
        icon: <item.icon className="h-4 w-4" />,
        section: 'Navigation' as const,
        shortcut: item.shortcut ? ['G', item.shortcut[1].toUpperCase()] : undefined,
        keywords: [item.name.toLowerCase(), 'go', 'navigate'],
        onSelect: () => navigate(item.href),
      })),
    [filteredNavigation, navigate]
  );

  // Register command palette items — only theme-dependent items rebuild on theme change
  useEffect(() => {
    const commands: CommandItem[] = [
      ...navigationCommands,
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
  }, [navigationCommands, navigate, logout, setCommandItems, resolvedTheme, toggleTheme]);

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
          'fixed inset-y-0 left-0 z-50 w-64 bg-gray-100 dark:bg-neutral-950 border-r border-gray-200 dark:border-neutral-800 transition-transform duration-300 ease-in-out lg:translate-x-0',
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        {/* Sidebar header */}
        <div className="flex h-16 items-center justify-between border-b border-gray-200 dark:border-neutral-800 px-4">
          <div className="flex items-center gap-2">
            <StoaLogo size="sm" />
            <div>
              <h1 className="text-lg font-bold text-gray-900 dark:text-white leading-tight">
                STOA
              </h1>
              <p className="text-[10px] font-medium text-gray-500 dark:text-gray-400 tracking-wider uppercase">
                Control Plane
              </p>
            </div>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-200 dark:hover:bg-neutral-800 hover:text-gray-900 dark:hover:text-white lg:hidden"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav className="mt-2 px-3 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 180px)' }}>
          <div className="space-y-1">
            {filteredSections.map((section) => {
              const isCollapsed = !!collapsedSections[section.title];
              return (
                <div
                  key={section.title}
                  className={clsx(
                    'rounded-lg',
                    section.accent &&
                      'border-l-2 border-primary-500 bg-primary-50/30 dark:bg-primary-950/20'
                  )}
                >
                  <button
                    onClick={() => toggleSection(section.title)}
                    className={clsx(
                      'flex items-center w-full px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wider transition-colors rounded hover:bg-gray-200/50 dark:hover:bg-neutral-800/50',
                      section.accent
                        ? 'text-primary-600 dark:text-primary-400'
                        : 'text-gray-500 dark:text-gray-500'
                    )}
                  >
                    <ChevronDown
                      className={clsx(
                        'h-3 w-3 mr-1.5 transition-transform duration-200',
                        isCollapsed && '-rotate-90'
                      )}
                    />
                    {section.title}
                  </button>
                  <div
                    className={clsx(
                      'grid transition-[grid-template-rows] duration-200 ease-in-out',
                      isCollapsed ? 'grid-rows-[0fr]' : 'grid-rows-[1fr]'
                    )}
                  >
                    <div className="overflow-hidden">
                      <ul className="space-y-0.5 pb-1">
                        {section.items.map((item) => {
                          const isActive =
                            location.pathname === item.href ||
                            (item.href !== '/' && location.pathname.startsWith(item.href));

                          return (
                            <li key={item.href}>
                              <Link
                                to={item.href}
                                onMouseEnter={() => routePrefetchMap[item.href]?.()}
                                className={clsx(
                                  'flex items-center gap-3 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors',
                                  isActive
                                    ? 'bg-primary-600 text-white'
                                    : 'text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-neutral-800 hover:text-gray-900 dark:hover:text-white'
                                )}
                              >
                                <item.icon className="h-4 w-4 flex-shrink-0" />
                                <span className="truncate">{item.name}</span>
                                {item.badge && (
                                  <span className="ml-auto rounded-full bg-accent-500/20 px-1.5 py-0.5 text-[10px] font-bold text-accent-600 dark:text-accent-400">
                                    {item.badge}
                                  </span>
                                )}
                                {!item.badge && item.shortcut && (
                                  <span className="ml-auto text-xs text-gray-500 hidden xl:block">
                                    g{item.shortcut[1]}
                                  </span>
                                )}
                              </Link>
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </nav>

        {/* Mobile-only: Env & Tenant selectors */}
        <div className="lg:hidden border-t border-gray-200 dark:border-neutral-800 px-3 py-3 space-y-2">
          {/* Environment selector */}
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-500 mb-1 px-1">
              Environment
            </p>
            {environments.map((env) => (
              <button
                key={env.name}
                onClick={() => {
                  handleEnvSwitch(env.name);
                  setSidebarOpen(false);
                }}
                className={clsx(
                  'w-full flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                  activeEnvironment === env.name
                    ? 'bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-300'
                    : 'text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-neutral-800'
                )}
              >
                <span
                  className={clsx(
                    'h-2 w-2 rounded-full flex-shrink-0',
                    env.color === 'green' && 'bg-green-500',
                    env.color === 'amber' && 'bg-amber-500',
                    env.color === 'red' && 'bg-red-500'
                  )}
                />
                <span className="flex-1 text-left">{env.label}</span>
                {env.mode === 'read-only' && (
                  <Lock className="h-3 w-3 text-neutral-400 flex-shrink-0" />
                )}
                {activeEnvironment === env.name && (
                  <Check className="h-4 w-4 text-primary-600 flex-shrink-0" />
                )}
              </button>
            ))}
          </div>

          {/* Tenant selector */}
          {tenants && tenants.length > 0 && (
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-500 mb-1 px-1">
                Tenant
              </p>
              {tenants.map((tenant) => {
                const selectedId = activeTenantId || user?.tenant_id;
                const isSelected = selectedId === tenant.id || selectedId === tenant.name;
                return (
                  <button
                    key={tenant.id}
                    onClick={() => {
                      handleTenantSwitch(tenant.id);
                      setSidebarOpen(false);
                    }}
                    className={clsx(
                      'w-full flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                      isSelected
                        ? 'bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-300'
                        : 'text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-neutral-800'
                    )}
                  >
                    <Building2 className="h-4 w-4 flex-shrink-0 text-gray-400" />
                    <span className="flex-1 text-left truncate">
                      {tenant.display_name || tenant.name}
                    </span>
                    {isSelected && <Check className="h-4 w-4 text-primary-600 flex-shrink-0" />}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* User section */}
        <div className="absolute bottom-0 left-0 right-0 border-t border-gray-200 dark:border-neutral-800 p-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary-600 flex-shrink-0">
              <User className="h-5 w-5 text-white" />
            </div>
            <div className="flex-1 min-w-0">
              {user ? (
                <>
                  <p className="truncate text-sm font-medium text-gray-900 dark:text-white">
                    {user.name}
                  </p>
                  <p className="truncate text-xs text-gray-500 dark:text-gray-400">
                    {user.roles.join(', ')}
                  </p>
                </>
              ) : (
                <>
                  <div className="h-4 w-24 bg-gray-300 dark:bg-gray-700 rounded animate-pulse" />
                  <div className="h-3 w-16 bg-gray-300 dark:bg-gray-700 rounded animate-pulse mt-1" />
                </>
              )}
            </div>
            {user && (
              <button
                onClick={logout}
                className="rounded-lg p-2 text-gray-400 hover:bg-gray-200 dark:hover:bg-neutral-800 hover:text-gray-900 dark:hover:text-white flex-shrink-0"
                title="Logout"
              >
                <LogOut className="h-5 w-5" />
              </button>
            )}
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
            className="rounded-lg p-2.5 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-neutral-800 lg:hidden"
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

          {/* Environment selector (ADR-040) */}
          <div className="hidden sm:block relative" ref={envDropdownRef}>
            <button
              onClick={() => setEnvDropdownOpen(!envDropdownOpen)}
              className="flex items-center gap-2 rounded-lg bg-neutral-100 dark:bg-neutral-800 px-3 py-1.5 hover:bg-neutral-200 dark:hover:bg-neutral-700 transition-colors"
            >
              <span
                className={clsx(
                  'h-2 w-2 rounded-full',
                  activeConfig.color === 'green' && 'bg-green-500',
                  activeConfig.color === 'amber' && 'bg-amber-500',
                  activeConfig.color === 'red' && 'bg-red-500'
                )}
              />
              <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
                {activeConfig.label}
              </span>
              {activeConfig.mode === 'read-only' && <Lock className="h-3 w-3 text-neutral-400" />}
              <ChevronDown
                className={clsx(
                  'h-4 w-4 text-neutral-400 transition-transform duration-200',
                  envDropdownOpen && 'rotate-180'
                )}
              />
            </button>
            {envDropdownOpen && (
              <div className="absolute right-0 mt-1 w-56 bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 shadow-lg z-50 py-1">
                {environments.map((env) => (
                  <button
                    key={env.name}
                    onClick={() => handleEnvSwitch(env.name)}
                    className={clsx(
                      'w-full flex items-center gap-3 px-3 py-2 text-left text-sm transition-colors',
                      activeEnvironment === env.name
                        ? 'bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-300'
                        : 'text-gray-700 dark:text-neutral-300 hover:bg-gray-50 dark:hover:bg-neutral-700'
                    )}
                  >
                    <span
                      className={clsx(
                        'h-2 w-2 rounded-full flex-shrink-0',
                        env.color === 'green' && 'bg-green-500',
                        env.color === 'amber' && 'bg-amber-500',
                        env.color === 'red' && 'bg-red-500'
                      )}
                    />
                    <div className="flex-1 min-w-0">
                      <p className="truncate font-medium">{env.label}</p>
                      <p className="truncate text-xs text-gray-500 dark:text-neutral-400">
                        {env.mode === 'read-only' ? 'Read-only' : 'Full access'}
                      </p>
                    </div>
                    {env.mode === 'read-only' && (
                      <Lock className="h-3 w-3 text-neutral-400 flex-shrink-0" />
                    )}
                    {activeEnvironment === env.name && (
                      <Check className="h-4 w-4 text-primary-600 flex-shrink-0" />
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Tenant selector */}
          {(user?.tenant_id || (tenants && tenants.length > 0)) && (
            <div className="hidden sm:block relative" ref={tenantDropdownRef}>
              <button
                onClick={() => setTenantDropdownOpen(!tenantDropdownOpen)}
                className="flex items-center gap-2 rounded-lg bg-neutral-100 dark:bg-neutral-800 px-3 py-1.5 hover:bg-neutral-200 dark:hover:bg-neutral-700 transition-colors"
              >
                <Building2 className="h-4 w-4 text-neutral-500 dark:text-neutral-400" />
                <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300 max-w-[120px] truncate">
                  {activeTenant?.display_name ||
                    activeTenant?.name ||
                    user?.tenant_id ||
                    'Select tenant'}
                </span>
                <ChevronDown
                  className={clsx(
                    'h-4 w-4 text-neutral-400 transition-transform duration-200',
                    tenantDropdownOpen && 'rotate-180'
                  )}
                />
              </button>
              {tenantDropdownOpen && tenants && tenants.length > 0 && (
                <div className="absolute right-0 mt-1 w-64 bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 shadow-lg z-50 py-1 max-h-64 overflow-y-auto">
                  {tenants.map((tenant) => {
                    const selectedId = activeTenantId || user?.tenant_id;
                    const isSelected = selectedId === tenant.id || selectedId === tenant.name;
                    return (
                      <button
                        key={tenant.id}
                        onClick={() => handleTenantSwitch(tenant.id)}
                        className={clsx(
                          'w-full flex items-center gap-3 px-3 py-2 text-left text-sm transition-colors',
                          isSelected
                            ? 'bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-300'
                            : 'text-gray-700 dark:text-neutral-300 hover:bg-gray-50 dark:hover:bg-neutral-700'
                        )}
                      >
                        <Building2 className="h-4 w-4 flex-shrink-0 text-gray-400" />
                        <div className="flex-1 min-w-0">
                          <p className="truncate font-medium">
                            {tenant.display_name || tenant.name}
                          </p>
                          <p className="truncate text-xs text-gray-500 dark:text-neutral-400">
                            {tenant.name}
                          </p>
                        </div>
                        {isSelected && <Check className="h-4 w-4 text-primary-600 flex-shrink-0" />}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </header>

        {/* API connectivity banner */}
        {!isConnected && !isChecking && (
          <div className="bg-red-600 text-white px-4 py-2 text-sm text-center">
            <AlertTriangle className="inline h-4 w-4 mr-2 -mt-0.5" />
            Cannot connect to the STOA API. Some features may be unavailable.
          </div>
        )}

        {/* Page content */}
        <main className="p-4 sm:p-6">{children}</main>
      </div>
    </div>
  );
}
