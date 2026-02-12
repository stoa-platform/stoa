import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock AuthContext
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: vi.fn(() => ({
    user: {
      id: 'user-admin',
      email: 'parzival@oasis.gg',
      name: 'Parzival',
      roles: ['cpi-admin'],
      tenant_id: 'oasis-gunters',
      permissions: ['tenants:read'],
    },
    isAuthenticated: true,
    isLoading: false,
    isReady: true,
    login: vi.fn(),
    logout: vi.fn(),
    hasPermission: vi.fn(() => true),
    hasRole: vi.fn(() => true),
  })),
}));

// Mock shared components
vi.mock('@stoa/shared/components/Skeleton', () => ({
  CardSkeleton: ({ className }: { className?: string }) => (
    <div data-testid="card-skeleton" className={className} />
  ),
}));

// Mock SparklineChart
vi.mock('../../components/charts/SparklineChart', () => ({
  SparklineChart: () => <div data-testid="sparkline-chart" />,
}));

const mockRefetch = vi.fn();

// Default Prometheus hook return values
const defaultInstantResult = {
  data: [{ metric: {}, value: [1707700000, '42'] }],
  loading: false,
  error: null,
  refetch: mockRefetch,
};

const defaultRangeResult = {
  data: [
    { timestamp: 1707700000, value: 1.5 },
    { timestamp: 1707700060, value: 2.0 },
    { timestamp: 1707700120, value: 1.8 },
  ],
  loading: false,
  error: null,
  refetch: mockRefetch,
};

const topToolsResult = {
  data: [
    { metric: { tool: 'weather-api' }, value: [1707700000, '120'] },
    { metric: { tool: 'translate-api' }, value: [1707700000, '80'] },
    { metric: { tool: 'sentiment' }, value: [1707700000, '50'] },
  ],
  loading: false,
  error: null,
  refetch: mockRefetch,
};

const toolLatencyResult = {
  data: [
    { metric: { tool: 'weather-api' }, value: [1707700000, '0.12'] },
    { metric: { tool: 'translate-api' }, value: [1707700000, '0.18'] },
    { metric: { tool: 'sentiment' }, value: [1707700000, '0.095'] },
  ],
  loading: false,
  error: null,
  refetch: mockRefetch,
};

const mockUsePrometheusQuery = vi.fn();
const mockUsePrometheusRange = vi.fn();

vi.mock('../../hooks/usePrometheus', () => ({
  usePrometheusQuery: (...args: unknown[]) => mockUsePrometheusQuery(...args),
  usePrometheusRange: (...args: unknown[]) => mockUsePrometheusRange(...args),
  scalarValue: (results: { value?: [number, string] }[] | null) => {
    if (!results || results.length === 0) return null;
    const val = results[0].value?.[1];
    if (val === undefined) return null;
    const n = parseFloat(val);
    return isNaN(n) ? null : n;
  },
  groupByLabel: (
    results: { metric: Record<string, string>; value?: [number, string] }[] | null,
    label: string
  ) => {
    if (!results) return {};
    const groups: Record<string, number> = {};
    for (const r of results) {
      const key = r.metric[label] || 'unknown';
      groups[key] = (groups[key] || 0) + parseFloat(r.value?.[1] || '0');
    }
    return groups;
  },
}));

import { TenantDashboard } from './TenantDashboard';

function renderComponent() {
  return render(<TenantDashboard />);
}

describe('TenantDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();

    // Default: return instant result for most queries, top tools for topk query
    mockUsePrometheusQuery.mockImplementation((query: string) => {
      if (query.includes('topk')) return topToolsResult;
      if (query.includes('duration_seconds_sum') && query.includes('by (tool)'))
        return toolLatencyResult;
      return defaultInstantResult;
    });

    mockUsePrometheusRange.mockReturnValue(defaultRangeResult);
  });

  it('renders the heading', async () => {
    renderComponent();
    expect(await screen.findByRole('heading', { name: 'My Usage' })).toBeInTheDocument();
  });

  it('shows tenant ID from localStorage when set', async () => {
    localStorage.setItem('stoa-active-tenant', 'custom-tenant');
    renderComponent();
    expect(await screen.findByText('custom-tenant')).toBeInTheDocument();
  });

  it('falls back to user tenant_id when localStorage is empty', async () => {
    renderComponent();
    expect(await screen.findByText('oasis-gunters')).toBeInTheDocument();
  });

  it('shows time range selector buttons', async () => {
    renderComponent();
    expect(await screen.findByText('1h')).toBeInTheDocument();
    expect(screen.getByText('6h')).toBeInTheDocument();
    expect(screen.getByText('24h')).toBeInTheDocument();
  });

  it('shows KPI metric cards', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText(/Tool Calls/)).toBeInTheDocument();
    });
    expect(screen.getByText(/Avg Latency/)).toBeInTheDocument();
    expect(screen.getByText(/Error Rate/)).toBeInTheDocument();
    expect(screen.getByText(/Rate Limit Hits/)).toBeInTheDocument();
  });

  it('shows Top 5 Tools section with tool names from Prometheus', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText(/Top 5 Tools/)).toBeInTheDocument();
    });
    expect(screen.getByText('weather-api')).toBeInTheDocument();
    expect(screen.getByText('translate-api')).toBeInTheDocument();
    expect(screen.getByText('sentiment')).toBeInTheDocument();
  });

  it('shows Usage Trend and Error Trend sections', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText(/Usage Trend/)).toBeInTheDocument();
    });
    expect(screen.getByText(/Error Trend/)).toBeInTheDocument();
  });

  it('shows sparkline charts when data is available', async () => {
    renderComponent();
    await waitFor(() => {
      const sparklines = screen.getAllByTestId('sparkline-chart');
      expect(sparklines).toHaveLength(2);
    });
  });

  it('shows Refresh button', async () => {
    renderComponent();
    expect(await screen.findByText('Refresh')).toBeInTheDocument();
  });

  it('calls refetch on all queries when Refresh is clicked', async () => {
    renderComponent();
    const refreshBtn = await screen.findByText('Refresh');
    await userEvent.click(refreshBtn);
    // 6 instant + 2 range = 8 refetch calls
    expect(mockRefetch).toHaveBeenCalledTimes(8);
  });

  it('shows Prometheus unavailable banner on error', async () => {
    mockUsePrometheusQuery.mockReturnValue({
      data: null,
      loading: false,
      error: 'Prometheus returned 503',
      refetch: mockRefetch,
    });
    renderComponent();
    expect(await screen.findByText(/Prometheus is not reachable/)).toBeInTheDocument();
    expect(screen.getByText('Retry')).toBeInTheDocument();
  });

  it('shows loading skeletons while data is loading', async () => {
    mockUsePrometheusQuery.mockReturnValue({
      data: null,
      loading: true,
      error: null,
      refetch: mockRefetch,
    });
    mockUsePrometheusRange.mockReturnValue({
      data: null,
      loading: true,
      error: null,
      refetch: mockRefetch,
    });
    renderComponent();
    const skeletons = await screen.findAllByTestId('card-skeleton');
    expect(skeletons.length).toBeGreaterThanOrEqual(4);
  });

  it('falls back to default tenant when user has no tenant_id', async () => {
    const { useAuth } = await import('../../contexts/AuthContext');
    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: 'user-no-tenant',
        email: 'no@tenant.com',
        name: 'NoTenant',
        roles: ['viewer'],
        tenant_id: undefined,
        permissions: [],
      },
      isAuthenticated: true,
      isLoading: false,
      isReady: true,
      login: vi.fn(),
      logout: vi.fn(),
      hasPermission: vi.fn(() => false),
      hasRole: vi.fn(() => false),
    } as any);
    renderComponent();
    // Should still render with fallback tenant 'default' instead of showing error
    expect(await screen.findByText('default')).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'My Usage' })).toBeInTheDocument();
  });
});
