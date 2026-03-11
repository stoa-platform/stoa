import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createAuthMock } from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';
import type { PersonaRole } from '../test/helpers';

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
  AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('../services/api', () => ({
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

vi.mock('@stoa/shared/components/Toast', () => ({
  ToastProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useToast: () => ({ addToast: vi.fn() }),
  useToastActions: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

vi.mock('@stoa/shared/components/CommandPalette', () => ({
  CommandPaletteProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useCommandPalette: () => ({ setOpen: vi.fn(), setItems: vi.fn() }),
}));

vi.mock('@stoa/shared/contexts', () => ({
  ThemeProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useTheme: () => ({ resolvedTheme: 'light', toggleTheme: vi.fn() }),
}));

vi.mock('@stoa/shared/hooks', () => ({
  useSequenceShortcuts: vi.fn(),
}));

vi.mock('../hooks/useBreadcrumbs', () => ({
  useBreadcrumbs: () => [{ label: 'Home' }],
}));

vi.mock('@stoa/shared/components/Breadcrumb', () => ({
  Breadcrumb: () => <nav data-testid="breadcrumb" />,
}));

vi.mock('@stoa/shared/components/ThemeToggle', () => ({
  ThemeToggle: () => <button data-testid="theme-toggle">Toggle</button>,
}));

vi.mock('react-oidc-context', () => ({
  useAuth: () => ({ isAuthenticated: true, isLoading: false, user: null }),
  hasAuthParams: () => false,
  AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('../services/mcpGatewayApi', () => ({
  mcpGatewayService: { setAuthToken: vi.fn(), clearAuthToken: vi.fn() },
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

vi.mock('../components/charts/SparklineChart', () => ({
  SparklineChart: () => <svg data-testid="sparkline-chart" />,
}));

// Mock Prometheus hooks — return no data (demo mode)
vi.mock('../hooks/usePrometheus', () => ({
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

import App from '../App';

function renderApp(route = '/') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('Dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders the Dashboard heading', async () => {
    renderApp('/');
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
  });

  it('greets the authenticated user by name', async () => {
    renderApp('/');
    expect(await screen.findByText('Hello, James Halliday!')).toBeInTheDocument();
  });

  it('shows gateway KPI card', async () => {
    renderApp('/');
    expect(await screen.findByText('Gateways')).toBeInTheDocument();
  });

  it('shows Refresh button', async () => {
    renderApp('/');
    expect(await screen.findByText('Refresh')).toBeInTheDocument();
  });

  it('shows demo mode banner when Prometheus is unreachable', async () => {
    renderApp('/');
    expect(
      await screen.findByText('Sample Data — Connect Prometheus to see live metrics')
    ).toBeInTheDocument();
  });

  // CAB-1775: 4-persona widget permission coverage
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      beforeEach(() => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
      });

      it('renders the dashboard heading', async () => {
        renderApp('/');
        expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
      });

      it('renders KPI stat cards', async () => {
        renderApp('/');
        expect(await screen.findByText('Gateways')).toBeInTheDocument();
      });

      it('renders Gateway Instances section', async () => {
        renderApp('/');
        expect(await screen.findByText('Gateway Instances')).toBeInTheDocument();
      });
    }
  );
});
