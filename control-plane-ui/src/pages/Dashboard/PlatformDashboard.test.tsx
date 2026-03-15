import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createAuthMock } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('../../services/api', () => ({
  apiService: {
    getGatewayHealthSummary: vi.fn().mockResolvedValue({
      online: 3,
      offline: 1,
      degraded: 0,
      maintenance: 0,
      total: 4,
    }),
    getGatewayModeStats: vi.fn().mockResolvedValue({ modes: [], total_gateways: 4 }),
    getGatewayInstances: vi.fn().mockResolvedValue({
      items: [
        {
          id: 'gw-1',
          name: 'prod-edge',
          display_name: 'Production Edge',
          gateway_type: 'stoa',
          mode: 'edge-mcp',
          status: 'online',
          last_health_check: new Date().toISOString(),
        },
        {
          id: 'gw-2',
          name: 'staging',
          display_name: 'Staging Gateway',
          gateway_type: 'stoa',
          mode: 'edge-mcp',
          status: 'offline',
          last_health_check: null,
        },
      ],
      total: 2,
    }),
  },
}));

// Mock Prometheus hooks
const mockRefetch = vi.fn();

vi.mock('../../hooks/usePrometheus', () => ({
  usePrometheusQuery: vi.fn(() => ({
    data: null,
    loading: false,
    error: 'not connected',
    refetch: mockRefetch,
  })),
  usePrometheusRange: vi.fn(() => ({
    data: null,
    loading: false,
    error: 'not connected',
    refetch: mockRefetch,
  })),
  scalarValue: vi.fn(() => null),
  groupByLabel: vi.fn(() => ({})),
}));

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
  TimeRangeSelector: ({ onChange }: { onChange: (v: string) => void }) => (
    <select data-testid="time-range-selector" onChange={(e) => onChange(e.target.value)}>
      <option value="24h">24h</option>
      <option value="1h">1h</option>
    </select>
  ),
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

vi.mock('../../components/charts/SparklineChart', () => ({
  SparklineChart: () => <svg data-testid="sparkline-chart" />,
}));

import { PlatformDashboard } from './PlatformDashboard';

function renderDashboard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PlatformDashboard />
    </QueryClientProvider>
  );
}

describe('PlatformDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders the Dashboard heading', () => {
    renderDashboard();
    expect(screen.getByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
  });

  it('greets the user by name', () => {
    renderDashboard();
    expect(screen.getByText('Hello, James Halliday!')).toBeInTheDocument();
  });

  it('renders 4 KPI stat cards', async () => {
    renderDashboard();
    expect(await screen.findByText('Gateways')).toBeInTheDocument();
    expect(screen.getByText('Total tool calls')).toBeInTheDocument();
    expect(screen.getByText('5xx + tool errors')).toBeInTheDocument();
    expect(screen.getByText('Response time')).toBeInTheDocument();
  });

  it('renders time range selector', () => {
    renderDashboard();
    expect(screen.getByTestId('time-range-selector')).toBeInTheDocument();
  });

  it('renders Refresh button', () => {
    renderDashboard();
    expect(screen.getByText('Refresh')).toBeInTheDocument();
  });

  it('shows demo mode banner when Prometheus is unreachable', async () => {
    renderDashboard();
    expect(
      await screen.findByText('Sample Data — Connect Prometheus to see live metrics')
    ).toBeInTheDocument();
  });

  it('renders Traffic and Errors chart sections', async () => {
    renderDashboard();
    expect(await screen.findByText('Traffic')).toBeInTheDocument();
    expect(screen.getByText('Errors')).toBeInTheDocument();
  });

  it('renders Gateway Instances section with instance cards', async () => {
    renderDashboard();
    expect(await screen.findByText('Gateway Instances')).toBeInTheDocument();
    expect(await screen.findByText('Production Edge')).toBeInTheDocument();
    expect(screen.getByText('Staging Gateway')).toBeInTheDocument();
  });

  it('renders Top APIs section', async () => {
    renderDashboard();
    expect(await screen.findByText(/Top APIs/)).toBeInTheDocument();
  });

  it('shows empty state for Top APIs when no traffic', async () => {
    renderDashboard();
    expect(await screen.findByText('Connect Prometheus for live data')).toBeInTheDocument();
  });

  // CAB-1775: 4-persona coverage
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      beforeEach(() => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
      });

      it('renders the dashboard', async () => {
        renderDashboard();
        expect(screen.getByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
        expect(await screen.findByText('Gateways')).toBeInTheDocument();
      });

      it('renders Gateway Instances section', async () => {
        renderDashboard();
        expect(await screen.findByText('Gateway Instances')).toBeInTheDocument();
      });
    }
  );
});
