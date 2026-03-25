import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Module-level mock so we can override per-test
const mockUseAuth = vi.fn(() => ({
  user: {
    id: 'u1',
    email: 'parzival@oasis.gg',
    name: 'Parzival',
    roles: ['cpi-admin'],
    tenant_id: 'oasis-gunters',
    permissions: [
      'tenants:read',
      'apis:read',
      'apps:read',
      'apis:deploy',
      'audit:read',
      'admin:servers',
    ],
  },
  isAuthenticated: true,
  isLoading: false,
  isReady: true,
  login: vi.fn(),
  logout: vi.fn(),
  hasPermission: vi.fn(() => true),
  hasRole: vi.fn(() => true),
}));

vi.mock('./contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
  AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('./services/api', () => ({
  apiService: {
    setAuthToken: vi.fn(),
    clearAuthToken: vi.fn(),
    getTenants: vi.fn().mockResolvedValue([]),
    getPlatformStatus: vi.fn().mockResolvedValue({
      gitops: { status: 'healthy', components: [], checked_at: '' },
      events: [],
      external_links: {},
      timestamp: '',
    }),
    getPlatformComponents: vi.fn().mockResolvedValue([]),
    getPlatformEvents: vi.fn().mockResolvedValue([]),
    getGatewayHealthSummary: vi.fn().mockResolvedValue({
      online: 2,
      offline: 0,
      degraded: 0,
      maintenance: 0,
      total: 2,
    }),
    getGatewayModeStats: vi.fn().mockResolvedValue({ modes: [], total_gateways: 2 }),
    getGatewayInstances: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  },
}));

// Mock Prometheus hooks — return no data (demo mode)
vi.mock('./hooks/usePrometheus', () => ({
  usePrometheusQuery: () => ({
    data: null,
    loading: false,
    error: 'not connected',
    refetch: vi.fn(),
  }),
  usePrometheusRange: () => ({
    data: null,
    loading: false,
    error: 'not connected',
    refetch: vi.fn(),
  }),
  scalarValue: () => null,
  groupByLabel: () => ({}),
}));

vi.mock('./services/mcpGatewayApi', () => ({
  mcpGatewayService: { setAuthToken: vi.fn(), clearAuthToken: vi.fn() },
}));

vi.mock('@stoa/shared/components/Toast', () => ({
  ToastProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useToast: () => ({ addToast: vi.fn() }),
}));

vi.mock('@stoa/shared/components/CommandPalette', () => ({
  CommandPaletteProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useCommandPalette: () => ({ setOpen: vi.fn(), setItems: vi.fn() }),
}));

vi.mock('@stoa/shared/components/Breadcrumb', () => ({
  Breadcrumb: () => <nav data-testid="breadcrumb" />,
}));

vi.mock('@stoa/shared/components/ThemeToggle', () => ({
  ThemeToggle: () => <button data-testid="theme-toggle">Toggle</button>,
}));

vi.mock('@stoa/shared/contexts', () => ({
  ThemeProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useTheme: () => ({ resolvedTheme: 'light', toggleTheme: vi.fn() }),
}));

vi.mock('@stoa/shared/hooks', () => ({
  useSequenceShortcuts: vi.fn(),
}));

vi.mock('./hooks/useBreadcrumbs', () => ({
  useBreadcrumbs: () => [{ label: 'Home' }],
}));

vi.mock('react-oidc-context', () => ({
  useAuth: () => ({ isAuthenticated: true, isLoading: false, user: null }),
  hasAuthParams: () => false,
  AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

// Shared component mocks for PlatformDashboard
vi.mock('@stoa/shared/components/StatCard', () => ({
  StatCard: ({ label, value, subtitle }: { label: string; value: string; subtitle?: string }) => (
    <div data-testid={`stat-card-${label}`}>
      <span>{label}</span>
      <span>{value}</span>
      {subtitle && <span>{subtitle}</span>}
    </div>
  ),
}));

vi.mock('@stoa/shared/components/TimeRangeSelector', () => ({
  TimeRangeSelector: () => <div data-testid="time-range-selector" />,
  RANGE_CONFIG: {
    '1h': { seconds: 3600, step: '1m', label: '1 hour' },
    '6h': { seconds: 21600, step: '5m', label: '6 hours' },
    '24h': { seconds: 86400, step: '15m', label: '24 hours' },
    '7d': { seconds: 604800, step: '1h', label: '7 days' },
    '30d': { seconds: 2592000, step: '6h', label: '30 days' },
  },
}));

vi.mock('@stoa/shared/components/TrendIndicator', () => ({
  TrendIndicator: () => <span data-testid="trend-indicator" />,
}));

vi.mock('@stoa/shared/components/Skeleton', () => ({
  CardSkeleton: ({ className }: { className?: string }) => (
    <div data-testid="card-skeleton" className={className} />
  ),
}));

vi.mock('./components/charts/SparklineChart', () => ({
  SparklineChart: () => <svg data-testid="sparkline-chart" />,
}));

// Lazy pages mock
vi.mock('./pages/Tenants', () => ({ Tenants: () => <div>Tenants Page</div> }));
vi.mock('./pages/APIs', () => ({ APIs: () => <div>APIs Page</div> }));
vi.mock('./pages/Applications', () => ({ Applications: () => <div>Applications Page</div> }));

import App from './App';

function renderApp(route = '/') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('App', () => {
  it('renders Dashboard heading at root route', async () => {
    renderApp('/');
    expect(
      await screen.findByRole('heading', { name: 'Dashboard' }, { timeout: 10_000 })
    ).toBeInTheDocument();
  });

  it('renders welcome message with user name', async () => {
    renderApp('/');
    expect(
      await screen.findByText('Hello, Parzival!', {}, { timeout: 10_000 })
    ).toBeInTheDocument();
  });

  it('renders gateway KPI card on dashboard', async () => {
    renderApp('/');
    expect(await screen.findByText('Gateways', {}, { timeout: 10_000 })).toBeInTheDocument();
  });

  it('blocks protected route when not authenticated', () => {
    mockUseAuth.mockReturnValueOnce({
      user: null as never,
      isAuthenticated: false,
      isLoading: false,
      isReady: false,
      login: vi.fn(),
      logout: vi.fn(),
      hasPermission: vi.fn(() => false),
      hasRole: vi.fn(() => false),
    });

    renderApp('/apis');
    expect(screen.queryByText('APIs Page')).not.toBeInTheDocument();
  });

  it('shows loading state when auth is loading', () => {
    mockUseAuth.mockReturnValueOnce({
      user: null as never,
      isAuthenticated: true,
      isLoading: true,
      isReady: false,
      login: vi.fn(),
      logout: vi.fn(),
      hasPermission: vi.fn(() => false),
      hasRole: vi.fn(() => false),
    });

    renderApp('/');
    expect(screen.getByRole('img', { name: 'Loading' })).toBeInTheDocument();
  });
});
