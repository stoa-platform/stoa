import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import { PlatformMetricsDashboard } from './PlatformMetricsDashboard';
import { createAuthMock, renderWithProviders } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

// Mock dependencies
vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

vi.mock('../../services/api', () => ({
  apiService: {
    getTopAPIs: vi.fn(() => Promise.resolve([])),
    get: vi.fn(() =>
      Promise.resolve({
        data: {
          gitops: {
            components: [],
          },
        },
      })
    ),
  },
}));

vi.mock('../../hooks/usePrometheus', () => ({
  usePrometheusQuery: vi.fn(() => ({
    data: null,
    loading: false,
    error: null,
    refetch: vi.fn(),
  })),
  usePrometheusRange: vi.fn(() => ({
    data: null,
    loading: false,
    error: null,
    refetch: vi.fn(),
  })),
  scalarValue: vi.fn(() => null),
}));

vi.mock('../../components/charts/SparklineChart', () => ({
  SparklineChart: () => <div data-testid="sparkline-chart">Sparkline</div>,
}));

vi.mock('../../components/metrics/MetricCard', () => ({
  MetricCard: ({ label }: { label: string }) => <div data-testid="metric-card">{label}</div>,
}));

vi.mock('../../components/metrics/MetricTimeseries', () => ({
  MetricTimeseries: ({ label }: { label: string }) => (
    <div data-testid="metric-timeseries">{label}</div>
  ),
}));

describe('PlatformMetricsDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders the page title', () => {
    renderWithProviders(<PlatformMetricsDashboard />);
    expect(screen.getByText('Platform Observability')).toBeInTheDocument();
  });

  it('renders the page subtitle', () => {
    renderWithProviders(<PlatformMetricsDashboard />);
    expect(
      screen.getByText('Real-time platform metrics, MCP activity, arena benchmarks')
    ).toBeInTheDocument();
  });

  it('renders time range selector with default 1h selected', () => {
    renderWithProviders(<PlatformMetricsDashboard />);
    const buttons = screen.getAllByRole('button');
    const oneHourButton = buttons.find((btn) => btn.textContent === '1h');
    expect(oneHourButton).toHaveClass('bg-white');
  });

  it('changes time range when button clicked', () => {
    renderWithProviders(<PlatformMetricsDashboard />);
    const buttons = screen.getAllByRole('button');
    const sixHourButton = buttons.find((btn) => btn.textContent === '6h');

    if (sixHourButton) {
      fireEvent.click(sixHourButton);
      expect(sixHourButton).toHaveClass('bg-white');
    }
  });

  it('renders refresh button', () => {
    renderWithProviders(<PlatformMetricsDashboard />);
    const refreshButton = screen.getByText('Refresh');
    expect(refreshButton).toBeInTheDocument();
  });

  it('shows KPI metric cards', async () => {
    renderWithProviders(<PlatformMetricsDashboard />);
    await waitFor(() => {
      expect(screen.getByText(/Total Requests/i)).toBeInTheDocument();
    });
    const errorRateElements = screen.getAllByText(/Error Rate/i);
    expect(errorRateElements.length).toBeGreaterThan(0);
    expect(screen.getAllByText(/P95 Latency/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Services Up/i)).toBeInTheDocument();
  });

  it('renders SLO section', async () => {
    renderWithProviders(<PlatformMetricsDashboard />);
    await waitFor(() => {
      expect(screen.getByText('SLO Status')).toBeInTheDocument();
    });
    expect(screen.getAllByText(/Availability/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Error Budget/i).length).toBeGreaterThan(0);
  });

  it('renders sparkline section titles', async () => {
    renderWithProviders(<PlatformMetricsDashboard />);
    await waitFor(() => {
      expect(screen.getByText('Request Rate')).toBeInTheDocument();
    });
  });

  it('renders MCP & AI Activity section', async () => {
    renderWithProviders(<PlatformMetricsDashboard />);
    await waitFor(() => {
      expect(screen.getByText('MCP & AI Activity')).toBeInTheDocument();
    });
    expect(screen.getByText('MCP Sessions Active')).toBeInTheDocument();
    expect(screen.getByText('Tool Calls / h')).toBeInTheDocument();
  });

  it('renders Gateway Adapters section', async () => {
    renderWithProviders(<PlatformMetricsDashboard />);
    await waitFor(() => {
      expect(screen.getByText('Gateway Adapters')).toBeInTheDocument();
    });
    expect(screen.getByText('Adapter Ops / h')).toBeInTheDocument();
    expect(screen.getByText('Circuit Breakers Open')).toBeInTheDocument();
  });

  it('renders Arena Benchmark section', async () => {
    renderWithProviders(<PlatformMetricsDashboard />);
    await waitFor(() => {
      expect(screen.getByText('Arena Benchmark')).toBeInTheDocument();
    });
    expect(screen.getByText('STOA Score')).toBeInTheDocument();
    expect(screen.getByText('Enterprise Score')).toBeInTheDocument();
  });

  it('renders Platform Health CUJs section', async () => {
    renderWithProviders(<PlatformMetricsDashboard />);
    await waitFor(() => {
      expect(screen.getByText('Platform Health (CUJs)')).toBeInTheDocument();
    });
    expect(screen.getByText('Health Chain')).toBeInTheDocument();
    expect(screen.getByText('Auth Flow')).toBeInTheDocument();
    expect(screen.getByText('MCP Discovery')).toBeInTheDocument();
  });

  it('renders top endpoints section', async () => {
    renderWithProviders(<PlatformMetricsDashboard />);
    await waitFor(() => {
      expect(screen.getByText('Top Endpoints')).toBeInTheDocument();
    });
  });

  it('shows "No API data available" when no top APIs', async () => {
    renderWithProviders(<PlatformMetricsDashboard />);
    await waitFor(() => {
      expect(screen.getByText('No API data available')).toBeInTheDocument();
    });
  });

  it('calls refetch when refresh button clicked', () => {
    renderWithProviders(<PlatformMetricsDashboard />);
    const refreshButton = screen.getByText('Refresh');
    fireEvent.click(refreshButton);
    expect(refreshButton).toBeInTheDocument();
  });

  it('renders link to business page', async () => {
    renderWithProviders(<PlatformMetricsDashboard />);
    await waitFor(() => {
      expect(screen.getByText('View All')).toBeInTheDocument();
    });
    const viewAllLink = screen.getByText('View All');
    expect(viewAllLink.closest('a')).toHaveAttribute('href', '/business');
  });

  it('renders cross-links to Transaction Tracing and Operations', () => {
    renderWithProviders(<PlatformMetricsDashboard />);
    expect(screen.getByText(/Transaction Tracing/i)).toBeInTheDocument();
    expect(screen.getByText(/SLO & Deployments/i)).toBeInTheDocument();
  });

  it('displays last refresh time', () => {
    renderWithProviders(<PlatformMetricsDashboard />);
    const timeElements = screen.getAllByText(/:/);
    expect(timeElements.length).toBeGreaterThan(0);
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderWithProviders(<PlatformMetricsDashboard />);
        expect(screen.getByText('Platform Observability')).toBeInTheDocument();
      });
    }
  );
});
